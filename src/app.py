import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

st.set_page_config(
    page_title="GuitarBro Analytics",
    page_icon="🎸",
    layout="wide"
)

DB_PATH = "data/orders.db"


def init_db():
    """Initialize the SQLite database and create orders table if not exists."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            data JSON
        )
    """)
    conn.commit()
    conn.close()


def load_orders_from_db():
    """Load all orders from the database."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT data FROM orders")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return pd.DataFrame()

    orders = [pd.read_json(row[0], typ="series") for row in rows]
    return pd.DataFrame(orders)


def save_orders_to_db(df):
    """Save orders to database, deduplicating by Id. Returns (new_count, duplicate_count)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    new_count = 0
    duplicate_count = 0

    for _, row in df.iterrows():
        order_id = str(row["Id"])
        try:
            cursor.execute(
                "INSERT INTO orders (id, data) VALUES (?, ?)",
                (order_id, row.to_json())
            )
            new_count += 1
        except sqlite3.IntegrityError:
            duplicate_count += 1

    conn.commit()
    conn.close()

    return new_count, duplicate_count


# Initialize database
init_db()

st.title("🎸 GuitarBro Shopify Analytics Dashboard")

# File uploader
uploaded_file = st.file_uploader("Upload Shopify Orders CSV", type=["csv"])

if uploaded_file is not None:
    uploaded_df = pd.read_csv(uploaded_file)
    new_count, duplicate_count = save_orders_to_db(uploaded_df)

    if new_count > 0:
        st.success(f"Added {new_count} new orders to database.")
    if duplicate_count > 0:
        st.info(f"Skipped {duplicate_count} duplicate orders.")

# Load orders from database
df = load_orders_from_db()

if df.empty:
    st.info("No orders in database. Upload your Shopify orders CSV to get started.")
else:
    # Parse the "Created at" column as datetime
    df["Created at"] = pd.to_datetime(df["Created at"])

    # Date range picker
    st.subheader("Filter by Date Range")
    col1, col2 = st.columns(2)

    min_date = df["Created at"].min().date()
    max_date = df["Created at"].max().date()

    with col1:
        start_date = st.date_input("Start Date", value=min_date, min_value=min_date, max_value=max_date)
    with col2:
        end_date = st.date_input("End Date", value=max_date, min_value=min_date, max_value=max_date)

    # Filter dataframe by date range
    mask = (df["Created at"].dt.date >= start_date) & (df["Created at"].dt.date <= end_date)
    filtered_df = df[mask]

    # Calculate COD vs Prepaid orders based on Financial Status
    # pending = COD, paid = Prepaid (case-insensitive)
    financial_status_lower = filtered_df["Financial Status"].str.lower()
    cod_orders = filtered_df[financial_status_lower == "pending"]
    prepaid_orders = filtered_df[financial_status_lower == "paid"]

    # Metric cards
    st.subheader("Order Summary")
    metric_col1, metric_col2, metric_col3 = st.columns(3)

    with metric_col1:
        st.metric(label="Total Orders", value=len(filtered_df))
    with metric_col2:
        st.metric(label="COD Orders", value=len(cod_orders))
    with metric_col3:
        st.metric(label="Prepaid Orders", value=len(prepaid_orders))
