import streamlit as st
import pandas as pd
import sqlite3
import os
import sys
import re
from datetime import datetime
from pathlib import Path

# Add src directory to path for Streamlit Cloud compatibility
try:
    src_path = Path(__file__).parent.resolve()
except NameError:
    src_path = Path.cwd()

if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Ensure data directory exists (for Streamlit Cloud)
data_dir = src_path.parent / 'data'
data_dir.mkdir(exist_ok=True)

from fb_ads_module import render_fb_ads_module
from fb_comment_bot_module import render_fb_comment_bot_module
from user_journey_module import render_user_journey_module
from logistics_module import render_logistics_module

# Page config must be first Streamlit command
st.set_page_config(
    page_title="GuitarBro Analytics",
    page_icon="🎸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# RAZORPAY-STYLE CSS STYLING
# =============================================================================
def inject_custom_css():
    st.markdown("""
    <style>
    /* Main background - WHITE */
    .stApp {
        background-color: #FFFFFF;
    }

    /* FORCE ALL TEXT TO BE BLACK */
    .stApp, .stApp * {
        color: #1A1A1A !important;
    }

    /* Exception: White text on dark buttons */
    .stButton > button {
        color: #FFFFFF !important;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E5E7EB;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #1A1A1A !important;
    }

    /* All text elements - force black */
    p, span, div, label, h1, h2, h3, h4, h5, h6, caption, small {
        color: #1A1A1A !important;
    }

    /* Streamlit specific elements */
    [data-testid="stMarkdownContainer"] {
        color: #1A1A1A !important;
    }

    [data-testid="stCaption"] {
        color: #374151 !important;
    }

    .stTextInput label, .stSelectbox label, .stDateInput label, .stFileUploader label {
        color: #1A1A1A !important;
    }

    /* Tab text */
    .stTabs [data-baseweb="tab"] {
        color: #1A1A1A !important;
    }

    .stTabs [aria-selected="true"] {
        color: #1A1A1A !important;
        font-weight: 600 !important;
    }

    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Sidebar collapse/expand button styling */
    [data-testid="collapsedControl"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 8px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15) !important;
        top: 16px !important;
        left: 16px !important;
        width: 44px !important;
        height: 44px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    [data-testid="collapsedControl"]:hover {
        background-color: #528FF0 !important;
        border-color: #528FF0 !important;
    }

    [data-testid="collapsedControl"]:hover svg {
        color: #FFFFFF !important;
    }

    [data-testid="collapsedControl"] svg {
        color: #1A1A1A !important;
        width: 24px !important;
        height: 24px !important;
    }

    /* Make sidebar overlay on top */
    [data-testid="stSidebar"] {
        z-index: 999 !important;
    }

    /* Sidebar close button (X) styling */
    [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] {
        background-color: transparent !important;
    }

    /* Custom card styling */
    .metric-card {
        background-color: #FFFFFF;
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        border: 1px solid #E5E7EB;
        margin-bottom: 16px;
    }

    .metric-value {
        font-size: 32px;
        font-weight: 700;
        color: #1A1A1A;
        margin: 0;
        line-height: 1.2;
    }

    .metric-value-blue {
        font-size: 32px;
        font-weight: 700;
        color: #528FF0;
        margin: 0;
        line-height: 1.2;
    }

    .metric-label {
        font-size: 14px;
        color: #6B7280;
        margin-top: 8px;
        font-weight: 500;
    }

    .metric-sublabel {
        font-size: 12px;
        color: #9CA3AF;
        margin-top: 4px;
    }

    /* Navigation button styling */
    .nav-button {
        display: block;
        width: 100%;
        padding: 12px 16px;
        margin: 4px 0;
        border: none;
        border-radius: 8px;
        text-align: left;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        background-color: transparent;
        color: #6B7280;
    }

    .nav-button:hover {
        background-color: #F3F4F6;
        color: #1A1A1A;
    }

    .nav-button-active {
        display: block;
        width: 100%;
        padding: 12px 16px;
        margin: 4px 0;
        border: none;
        border-radius: 8px;
        text-align: left;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        background-color: #EEF4FE;
        color: #528FF0;
        border-left: 3px solid #528FF0;
    }

    /* Section headers */
    .section-header {
        font-size: 18px;
        font-weight: 600;
        color: #1A1A1A;
        margin: 24px 0 16px 0;
    }

    /* Placeholder page styling */
    .placeholder-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 400px;
        background-color: #FFFFFF;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        border: 1px solid #E5E7EB;
        margin: 24px 0;
    }

    .placeholder-icon {
        font-size: 48px;
        margin-bottom: 16px;
    }

    .placeholder-title {
        font-size: 24px;
        font-weight: 600;
        color: #1A1A1A;
        margin-bottom: 8px;
    }

    .placeholder-subtitle {
        font-size: 14px;
        color: #6B7280;
    }

    /* Table styling */
    .stDataFrame {
        background-color: #FFFFFF;
        border-radius: 8px;
        overflow: hidden;
    }

    [data-testid="stDataFrame"] > div {
        background-color: #FFFFFF;
        border-radius: 8px;
        border: 1px solid #E5E7EB;
    }

    /* File uploader styling */
    [data-testid="stFileUploader"] {
        background-color: #FFFFFF;
        border-radius: 8px;
        padding: 16px;
        border: 1px dashed #E5E7EB;
    }

    /* Date input styling */
    [data-testid="stDateInput"] {
        background-color: #FFFFFF;
    }

    /* Logo/Brand section */
    .brand-section {
        padding: 20px 16px;
        border-bottom: 1px solid #E5E7EB;
        margin-bottom: 16px;
    }

    .brand-title {
        font-size: 20px;
        font-weight: 700;
        color: #1A1A1A;
        margin: 0;
    }

    .brand-subtitle {
        font-size: 12px;
        color: #6B7280;
        margin-top: 4px;
    }

    /* Page title */
    .page-title {
        font-size: 28px;
        font-weight: 700;
        color: #1A1A1A;
        margin-bottom: 8px;
    }

    .page-subtitle {
        font-size: 14px;
        color: #6B7280;
        margin-bottom: 24px;
    }

    /* Custom divider */
    .custom-divider {
        height: 1px;
        background-color: #E5E7EB;
        margin: 24px 0;
    }

    /* Info/Success/Warning boxes */
    .stAlert {
        border-radius: 8px;
    }

    /* Streamlit metric override */
    [data-testid="stMetric"] {
        background-color: #F3F4F6;
        padding: 16px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        border: 1px solid #E5E7EB;
    }

    [data-testid="stMetricLabel"] {
        color: #1A1A1A !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }

    [data-testid="stMetricValue"] {
        color: #1A1A1A !important;
        font-size: 28px !important;
        font-weight: 700 !important;
    }

    [data-testid="stMetricDelta"] {
        color: #374151 !important;
    }

    /* Pills/Badges - light gray background */
    .stBadge, [data-testid="stBadge"] {
        background-color: #E5E7EB !important;
        color: #1A1A1A !important;
    }

    /* Info/Success/Warning/Error boxes - ensure dark text */
    .stAlert {
        color: #1A1A1A !important;
    }

    .stAlert > div {
        color: #1A1A1A !important;
    }

    /* Dataframe/Table text */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        color: #1A1A1A !important;
    }

    .stDataFrame th, .stDataFrame td {
        color: #1A1A1A !important;
    }

    /* Chart titles and labels */
    .stPlotlyChart text {
        fill: #1A1A1A !important;
    }

    /* Expander text */
    .streamlit-expanderHeader {
        color: #1A1A1A !important;
    }

    /* Subheader */
    .stSubheader, [data-testid="stSubheader"] {
        color: #1A1A1A !important;
    }

    /* Button styling - white text on dark buttons */
    .stButton > button {
        color: #FFFFFF !important;
        background-color: #1A1A1A !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 8px 16px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }

    .stButton > button:hover {
        background-color: #333333 !important;
        color: #FFFFFF !important;
    }

    .stButton > button:disabled {
        background-color: #E5E7EB !important;
        color: #9CA3AF !important;
    }

    /* Secondary/outline buttons */
    .stButton > button[kind="secondary"] {
        background-color: #FFFFFF !important;
        color: #1A1A1A !important;
        border: 1px solid #E5E7EB !important;
    }

    .stButton > button[kind="secondary"]:hover {
        background-color: #F7F8FA !important;
        color: #1A1A1A !important;
    }

    /* Sidebar button styling */
    [data-testid="stSidebar"] .stButton > button {
        background-color: transparent !important;
        color: #6B7280 !important;
        border: none !important;
        text-align: left !important;
        justify-content: flex-start !important;
    }

    [data-testid="stSidebar"] .stButton > button:hover {
        background-color: #F3F4F6 !important;
        color: #1A1A1A !important;
    }

    </style>
    """, unsafe_allow_html=True)

inject_custom_css()

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================
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


# =============================================================================
# DATA PROCESSING FUNCTIONS
# =============================================================================
def deduplicate_orders(df):
    """
    Deduplicate orders - Shopify CSV has one row per LINE ITEM, not per order.
    Use 'Name' column (like #14079) as unique order identifier.
    """
    if df.empty:
        return df

    if "Name" in df.columns:
        order_id_col = "Name"
    elif "Id" in df.columns:
        order_id_col = "Id"
    else:
        return df

    df_sorted = df.sort_values(
        by=[order_id_col, "Created at"] if "Created at" in df.columns else [order_id_col]
    )
    deduplicated = df_sorted.drop_duplicates(subset=[order_id_col], keep="first")

    return deduplicated.reset_index(drop=True)


def parse_note_attribute(note_attributes, key):
    """Parse a specific key from the Note Attributes column."""
    if pd.isna(note_attributes) or not note_attributes:
        return None

    note_str = str(note_attributes)

    # Pattern 1: key:value or key: value
    pattern1 = rf'{key}\s*:\s*([^,\n\]]+)'
    match = re.search(pattern1, note_str, re.IGNORECASE)
    if match:
        return match.group(1).strip().strip('"\'')

    # Pattern 2: "key"=>"value" (Ruby hash format)
    pattern2 = rf'["\']?{key}["\']?\s*=>\s*["\']?([^"\',$\]]+)["\']?'
    match = re.search(pattern2, note_str, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Pattern 3: "key":"value" (JSON format)
    pattern3 = rf'["\']?{key}["\']?\s*:\s*["\']([^"\']+)["\']'
    match = re.search(pattern3, note_str, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return None


def categorize_utm_source(value):
    """Categorize utm_source into Meta, Google, WhatsApp, or Miscellaneous."""
    if pd.isna(value) or not value:
        return "Miscellaneous"

    value_lower = str(value).lower()

    meta_sources = ['ig', 'fb', 'facebook', 'instagram', 'an']
    if value_lower in meta_sources:
        return "Meta"

    google_sources = ['google', 'youtube', 'bing']
    if value_lower in google_sources:
        return "Google"

    whatsapp_sources = ['bitespeed', 'whatsapp', 'whatmore-live']
    if value_lower in whatsapp_sources:
        return "WhatsApp"

    return "Miscellaneous"


def categorize_utm_medium(value):
    """Categorize utm_medium into Paid, Organic, WhatsApp, or Miscellaneous."""
    if pd.isna(value) or not value:
        return "Miscellaneous"

    value_lower = str(value).lower()

    paid_mediums = [
        'paid', 'instagram_reels', 'instagram_feed', 'instagram_stories',
        'facebook_mobile_reels', 'facebook_mobile_feed', 'facebook_stories',
        'facebook_instream_video', 'cpc', 'instagram_explore_grid_home',
        'threads_feed', 'facebook_desktop_feed'
    ]
    if value_lower in paid_mediums:
        return "Paid"

    organic_mediums = ['organic', 'bio']
    if value_lower in organic_mediums:
        return "Organic"

    whatsapp_mediums = ['bitespeed', 'whatsapp']
    if value_lower in whatsapp_mediums:
        return "WhatsApp"

    return "Miscellaneous"


def categorize_payment_method(value):
    """Categorize payment_method into Prepaid, COD, or Miscellaneous."""
    if pd.isna(value) or not value:
        return "Miscellaneous"

    value_lower = str(value).lower()

    prepaid_methods = ['upi', 'card', 'emi', 'wallet', 'netbanking']
    if value_lower in prepaid_methods:
        return "Prepaid"

    if value_lower == 'cod':
        return "COD"

    return "Miscellaneous"


def create_breakdown_table(df, category_column):
    """Create a breakdown table with category, count, and percentage."""
    counts = df[category_column].value_counts()
    total = len(df)

    breakdown_data = []
    for category, count in counts.items():
        percentage = (count / total * 100) if total > 0 else 0
        breakdown_data.append({
            "Category": category,
            "Orders": count,
            "% of Total": f"{percentage:.1f}%"
        })

    return pd.DataFrame(breakdown_data)


# =============================================================================
# UI COMPONENTS
# =============================================================================
def render_metric_card(value, label, sublabel=None, is_blue=False):
    """Render a custom metric card."""
    value_class = "metric-value-blue" if is_blue else "metric-value"
    sublabel_html = f'<p class="metric-sublabel">{sublabel}</p>' if sublabel else ""

    st.markdown(f"""
    <div class="metric-card">
        <p class="{value_class}">{value}</p>
        <p class="metric-label">{label}</p>
        {sublabel_html}
    </div>
    """, unsafe_allow_html=True)


def render_placeholder_page(title, icon):
    """Render a placeholder page for modules not yet implemented."""
    st.markdown(f"""
    <div class="placeholder-container">
        <div class="placeholder-icon">{icon}</div>
        <div class="placeholder-title">{title}</div>
        <div class="placeholder-subtitle">Coming Soon</div>
    </div>
    """, unsafe_allow_html=True)


def render_section_header(title):
    """Render a section header."""
    st.markdown(f'<p class="section-header">{title}</p>', unsafe_allow_html=True)


# =============================================================================
# PAGE MODULES
# =============================================================================
def render_fb_ads_page():
    """Render the FB Ads module page."""
    render_fb_ads_module()


def render_fb_comment_bot_page():
    """Render the FB Comment Bot module page."""
    st.markdown('<p class="page-title">FB Comment Bot</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Automated comment management and reply system</p>', unsafe_allow_html=True)
    render_fb_comment_bot_module()


def render_user_journey_page():
    """Render the User Journey Tracker module page."""
    st.markdown('<p class="page-title">User Journey Tracker</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Track customer journeys from order to upsell</p>', unsafe_allow_html=True)
    render_user_journey_module()


def render_logistics_recon_page():
    """Render the Logistics Reconciliation module page."""
    render_logistics_module()


def render_live_learning_page():
    """Render the Live Learning module page."""
    st.markdown('<p class="page-title">Live Learning</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Educational content performance tracking</p>', unsafe_allow_html=True)
    render_placeholder_page("Live Learning Module", "🎓")


def render_inventory_page():
    """Render the Inventory module page."""
    st.markdown('<p class="page-title">Inventory</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Stock levels and inventory management</p>', unsafe_allow_html=True)
    render_placeholder_page("Inventory Module", "📦")


def render_creative_pipeline_page():
    """Render the Creative Pipeline module page."""
    st.markdown('<p class="page-title">Creative Pipeline</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Content creation and asset management</p>', unsafe_allow_html=True)
    render_placeholder_page("Creative Pipeline Module", "🎨")


def render_revenue_page():
    """Render the Revenue module page."""
    st.markdown('<p class="page-title">Revenue</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Financial performance and revenue analytics</p>', unsafe_allow_html=True)
    render_placeholder_page("Revenue Module", "💰")


def render_logistics_page():
    """Render the Logistics module page with all existing functionality."""
    st.markdown('<p class="page-title">Logistics</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-subtitle">Order analytics and shipping insights</p>', unsafe_allow_html=True)

    # File uploader section
    render_section_header("Upload Data")
    uploaded_file = st.file_uploader("Upload Shopify Orders CSV", type=["csv"], key="logistics_uploader")

    if uploaded_file is not None:
        uploaded_df = pd.read_csv(uploaded_file)
        new_count, duplicate_count = save_orders_to_db(uploaded_df)

        if new_count > 0:
            st.success(f"Added {new_count} new line items to database.")
        if duplicate_count > 0:
            st.info(f"Skipped {duplicate_count} duplicate line items.")

    # Load orders from database
    df_raw = load_orders_from_db()

    if df_raw.empty:
        st.info("No orders in database. Upload your Shopify orders CSV to get started.")
        return

    # Parse the "Created at" column as datetime
    df_raw["Created at"] = pd.to_datetime(df_raw["Created at"])

    # Date range filter
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    render_section_header("Date Range Filter")

    col1, col2 = st.columns(2)
    min_date = df_raw["Created at"].min().date()
    max_date = df_raw["Created at"].max().date()

    with col1:
        start_date = st.date_input("Start Date", value=min_date, min_value=min_date, max_value=max_date)
    with col2:
        end_date = st.date_input("End Date", value=max_date, min_value=min_date, max_value=max_date)

    # Filter dataframe by date range FIRST (on raw data)
    mask = (df_raw["Created at"].dt.date >= start_date) & (df_raw["Created at"].dt.date <= end_date)
    filtered_raw = df_raw[mask].copy()

    # Deduplicate orders AFTER date filtering
    filtered_df = deduplicate_orders(filtered_raw)

    # Calculate COD vs Prepaid orders based on Financial Status
    if "Financial Status" in filtered_df.columns:
        financial_status_lower = filtered_df["Financial Status"].str.lower()
        cod_orders = filtered_df[financial_status_lower == "pending"]
        prepaid_orders = filtered_df[financial_status_lower == "paid"]
    else:
        cod_orders = pd.DataFrame()
        prepaid_orders = pd.DataFrame()

    # Calculate Total Revenue
    total_revenue = 0
    if "Total" in filtered_df.columns:
        total_revenue = pd.to_numeric(filtered_df["Total"], errors="coerce").fillna(0).sum()

    # Calculate percentages
    total_orders = len(filtered_df)
    cod_count = len(cod_orders)
    prepaid_count = len(prepaid_orders)
    cod_pct = (cod_count / total_orders * 100) if total_orders > 0 else 0
    prepaid_pct = (prepaid_count / total_orders * 100) if total_orders > 0 else 0

    # Overview metric cards
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    render_section_header("Overview")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    with metric_col1:
        render_metric_card(f"{total_orders:,}", "Total Orders", is_blue=True)

    with metric_col2:
        render_metric_card(f"{cod_count:,}", "COD Orders", f"{cod_pct:.1f}% of total")

    with metric_col3:
        render_metric_card(f"{prepaid_count:,}", "Prepaid Orders", f"{prepaid_pct:.1f}% of total")

    with metric_col4:
        render_metric_card(f"₹{total_revenue:,.0f}", "Total Revenue")

    # State-wise breakdown
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    render_section_header("State-wise Order Distribution")

    if "Shipping Province Name" in filtered_df.columns:
        state_counts = filtered_df["Shipping Province Name"].value_counts()
        total_orders_state = len(filtered_df)

        state_data = []
        for state, count in state_counts.items():
            percentage = (count / total_orders_state * 100) if total_orders_state > 0 else 0
            state_name = state if pd.notna(state) and state else "Unknown"
            state_data.append({
                "State": state_name,
                "Orders": count,
                "% of Total": f"{percentage:.1f}%"
            })

        state_df = pd.DataFrame(state_data)
        st.dataframe(state_df, use_container_width=True, hide_index=True)
    else:
        st.warning("'Shipping Province Name' column not found in data.")

    # UTM & Payment Breakdown
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    render_section_header("Attribution & Payment Breakdown")

    if "Note Attributes" in filtered_df.columns:
        filtered_df["utm_source_raw"] = filtered_df["Note Attributes"].apply(
            lambda x: parse_note_attribute(x, "utm_source")
        )
        filtered_df["utm_medium_raw"] = filtered_df["Note Attributes"].apply(
            lambda x: parse_note_attribute(x, "utm_medium")
        )
        filtered_df["payment_method_raw"] = filtered_df["Note Attributes"].apply(
            lambda x: parse_note_attribute(x, "payment_method")
        )

        filtered_df["utm_source_category"] = filtered_df["utm_source_raw"].apply(categorize_utm_source)
        filtered_df["utm_medium_category"] = filtered_df["utm_medium_raw"].apply(categorize_utm_medium)
        filtered_df["payment_method_category"] = filtered_df["payment_method_raw"].apply(categorize_payment_method)

        breakdown_col1, breakdown_col2, breakdown_col3 = st.columns(3)

        with breakdown_col1:
            st.markdown("**UTM Source**")
            utm_source_table = create_breakdown_table(filtered_df, "utm_source_category")
            st.dataframe(utm_source_table, use_container_width=True, hide_index=True)

        with breakdown_col2:
            st.markdown("**UTM Medium**")
            utm_medium_table = create_breakdown_table(filtered_df, "utm_medium_category")
            st.dataframe(utm_medium_table, use_container_width=True, hide_index=True)

        with breakdown_col3:
            st.markdown("**Payment Method**")
            payment_table = create_breakdown_table(filtered_df, "payment_method_category")
            st.dataframe(payment_table, use_container_width=True, hide_index=True)
    else:
        st.warning("'Note Attributes' column not found in data. UTM and Payment breakdowns unavailable.")

    # Line Item Analysis
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    render_section_header("Line Item Analysis")

    if "Lineitem name" in filtered_raw.columns:
        line_item_stats = []
        unique_items = filtered_raw["Lineitem name"].dropna().unique()

        for item in unique_items:
            item_rows = filtered_raw[filtered_raw["Lineitem name"] == item]

            if "Name" in item_rows.columns:
                order_count = item_rows["Name"].nunique()
            elif "Id" in item_rows.columns:
                order_count = item_rows["Id"].nunique()
            else:
                order_count = len(item_rows)

            if "Lineitem price" in item_rows.columns and "Lineitem quantity" in item_rows.columns:
                item_rows_calc = item_rows.copy()
                item_rows_calc["Lineitem price"] = pd.to_numeric(
                    item_rows_calc["Lineitem price"], errors="coerce"
                ).fillna(0)
                item_rows_calc["Lineitem quantity"] = pd.to_numeric(
                    item_rows_calc["Lineitem quantity"], errors="coerce"
                ).fillna(0)
                total_item_revenue = (
                    item_rows_calc["Lineitem price"] * item_rows_calc["Lineitem quantity"]
                ).sum()
            elif "Lineitem price" in item_rows.columns:
                total_item_revenue = pd.to_numeric(
                    item_rows["Lineitem price"], errors="coerce"
                ).fillna(0).sum()
            else:
                total_item_revenue = 0

            aov = total_item_revenue / order_count if order_count > 0 else 0

            line_item_stats.append({
                "Line Item": item,
                "Orders": order_count,
                "Total Revenue": f"₹{total_item_revenue:,.2f}",
                "AOV": f"₹{aov:,.2f}"
            })

        line_item_df = pd.DataFrame(line_item_stats)
        line_item_df = line_item_df.sort_values(by="Orders", ascending=False).reset_index(drop=True)

        st.dataframe(line_item_df, use_container_width=True, hide_index=True)
    else:
        st.warning("'Lineitem name' column not found in data.")


# =============================================================================
# SIDEBAR NAVIGATION
# =============================================================================
def render_sidebar():
    """Render the sidebar navigation."""
    with st.sidebar:
        # Brand section
        st.markdown("""
        <div class="brand-section">
            <p class="brand-title">🎸 GuitarBro</p>
            <p class="brand-subtitle">Analytics Dashboard</p>
        </div>
        """, unsafe_allow_html=True)

        # Navigation
        st.markdown("### Navigation")

        # Define navigation items
        nav_items = [
            ("FB Ads", "fb_ads", "📊"),
            ("FB Comment Bot", "fb_comment_bot", "💬"),
            ("User Journey", "user_journey", "🎯"),
            ("Logistics Recon", "logistics_recon", "📦"),
            ("Logistics (Old)", "logistics", "🚚"),
            ("Live Learning", "live_learning", "🎓"),
            ("Inventory", "inventory", "📦"),
            ("Creative Pipeline", "creative_pipeline", "🎨"),
            ("Revenue", "revenue", "💰"),
        ]

        # Initialize session state for active page
        if "active_page" not in st.session_state:
            st.session_state.active_page = "logistics_recon"  # Default to Logistics Recon

        # Render navigation buttons
        for label, key, icon in nav_items:
            is_active = st.session_state.active_page == key

            if is_active:
                st.markdown(f"""
                <div class="nav-button-active">
                    {icon} {label}
                </div>
                """, unsafe_allow_html=True)

            if st.button(
                f"{icon} {label}" if not is_active else f"",
                key=f"nav_{key}",
                use_container_width=True,
                disabled=is_active,
                type="secondary" if not is_active else "primary"
            ):
                st.session_state.active_page = key
                st.rerun()


# =============================================================================
# MAIN APP
# =============================================================================
def main():
    # Initialize database
    init_db()

    # Initialize session state for active page
    if "active_page" not in st.session_state:
        st.session_state.active_page = "logistics_recon"

    # Always render sidebar
    render_sidebar()

    # Add JavaScript to toggle sidebar with a button
    st.markdown("""
    <script>
    const toggleSidebar = () => {
        const sidebar = window.parent.document.querySelector('[data-testid="stSidebar"]');
        const btn = window.parent.document.querySelector('[data-testid="collapsedControl"]');
        if (btn) btn.click();
    };
    </script>
    """, unsafe_allow_html=True)

    # Render the active page
    page_map = {
        "fb_ads": render_fb_ads_page,
        "fb_comment_bot": render_fb_comment_bot_page,
        "user_journey": render_user_journey_page,
        "logistics_recon": render_logistics_recon_page,
        "logistics": render_logistics_page,
        "live_learning": render_live_learning_page,
        "inventory": render_inventory_page,
        "creative_pipeline": render_creative_pipeline_page,
        "revenue": render_revenue_page,
    }

    active_page = st.session_state.get("active_page", "logistics_recon")
    page_renderer = page_map.get(active_page, render_logistics_recon_page)
    page_renderer()


if __name__ == "__main__":
    main()
