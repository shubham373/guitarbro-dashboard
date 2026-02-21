"""
Database Schema for User Journey Tracker

This module defines and initializes all SQLite tables for tracking
customer journeys across Shopify orders, Zoom attendance, and future
data sources.
"""

import sqlite3
import os

DB_PATH = "data/journey.db"


def get_db_connection():
    """Get SQLite connection with row factory."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize all database tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Table 1: raw_shopify_orders
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_shopify_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE,
            order_id TEXT,
            email TEXT,
            phone TEXT,
            billing_phone TEXT,
            billing_name TEXT,
            shipping_name TEXT,
            billing_city TEXT,
            shipping_city TEXT,
            billing_zip TEXT,
            shipping_zip TEXT,
            billing_province TEXT,
            shipping_province TEXT,
            total REAL,
            subtotal REAL,
            financial_status TEXT,
            fulfillment_status TEXT,
            payment_method TEXT,
            lineitem_name TEXT,
            discount_code TEXT,
            discount_amount REAL,
            created_at TEXT,
            cancelled_at TEXT,
            refunded_amount REAL,
            tags TEXT,
            note_attributes TEXT,
            razorpay_order_id TEXT,
            payment_type TEXT,
            rto_risk TEXT,
            source TEXT,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table 2: raw_zoom_attendance
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_zoom_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT,
            meeting_topic TEXT,
            meeting_date TEXT,
            participant_name TEXT,
            email TEXT,
            join_time TEXT,
            leave_time TEXT,
            duration_minutes INTEGER,
            is_guest TEXT,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table 3: zoom_participants_deduped
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zoom_participants_deduped (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT,
            meeting_topic TEXT,
            meeting_date TEXT,
            participant_name TEXT,
            email TEXT,
            total_duration_minutes INTEGER,
            first_join TEXT,
            last_leave TEXT,
            session_count INTEGER,
            is_internal INTEGER DEFAULT 0,
            UNIQUE(meeting_id, email)
        )
    """)

    # Table 4: unified_users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unified_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primary_email TEXT,
            secondary_emails TEXT,
            primary_phone TEXT,
            secondary_phones TEXT,
            primary_name TEXT,
            city TEXT,
            state TEXT,
            pincode TEXT,
            shopify_order_numbers TEXT,
            zoom_attendance_ids TEXT,
            order_source TEXT,
            first_order_date TEXT,
            latest_order_date TEXT,
            order_count INTEGER DEFAULT 0,
            total_order_value REAL DEFAULT 0,
            payment_method TEXT,
            financial_status TEXT,
            fulfillment_status TEXT,
            primary_product TEXT,
            rto_risk TEXT,
            has_attended_any INTEGER DEFAULT 0,
            total_events_attended INTEGER DEFAULT 0,
            latest_event_attended TEXT,
            latest_event_duration INTEGER,
            journey_stage TEXT,
            match_confidence REAL DEFAULT 0,
            match_method TEXT,
            needs_review INTEGER DEFAULT 0,
            ltv REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table 5: match_audit_log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_user_id INTEGER,
            source_table TEXT,
            source_record_identifier TEXT,
            match_field TEXT,
            value_from_user TEXT,
            value_from_source TEXT,
            confidence REAL,
            match_result TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes for faster lookups
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_shopify_email ON raw_shopify_orders(email)",
        "CREATE INDEX IF NOT EXISTS idx_shopify_phone ON raw_shopify_orders(phone)",
        "CREATE INDEX IF NOT EXISTS idx_shopify_billing_name ON raw_shopify_orders(billing_name)",
        "CREATE INDEX IF NOT EXISTS idx_shopify_order_number ON raw_shopify_orders(order_number)",
        "CREATE INDEX IF NOT EXISTS idx_zoom_email ON raw_zoom_attendance(email)",
        "CREATE INDEX IF NOT EXISTS idx_zoom_deduped_email ON zoom_participants_deduped(email)",
        "CREATE INDEX IF NOT EXISTS idx_unified_email ON unified_users(primary_email)",
        "CREATE INDEX IF NOT EXISTS idx_unified_phone ON unified_users(primary_phone)",
    ]

    for idx in indexes:
        cursor.execute(idx)

    conn.commit()
    conn.close()
    print("Database initialized successfully")


def reset_database():
    """Clear all data from all tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    tables = [
        "raw_shopify_orders",
        "raw_zoom_attendance",
        "zoom_participants_deduped",
        "unified_users",
        "match_audit_log"
    ]

    for table in tables:
        cursor.execute(f"DELETE FROM {table}")

    conn.commit()
    conn.close()
    print("Database reset successfully")


def get_table_counts():
    """Get row counts for all tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    counts = {}
    tables = [
        "raw_shopify_orders",
        "raw_zoom_attendance",
        "zoom_participants_deduped",
        "unified_users",
        "match_audit_log"
    ]

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cursor.fetchone()[0]

    conn.close()
    return counts


if __name__ == "__main__":
    init_database()
    print("Tables created:")
    print(get_table_counts())
