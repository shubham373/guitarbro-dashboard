"""
Logistics Reconciliation - Database Module

Handles database setup, connections, and data operations for
Shopify + Prozo logistics reconciliation.

Database Backend:
- Primary: Supabase (cloud, persistent)
- Fallback: SQLite (local, ephemeral on Streamlit Cloud)
"""

import sqlite3
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = "data/logistics.db"

# =============================================================================
# DATABASE BACKEND SELECTION
# =============================================================================

USE_SUPABASE = False

try:
    from supabase_logistics_db import (
        check_logistics_supabase_connection,
        insert_shopify_orders as supabase_insert_shopify_orders,
        get_shopify_orders as supabase_get_shopify_orders,
        clear_shopify_orders as supabase_clear_shopify_orders,
        insert_line_items as supabase_insert_line_items,
        get_line_items as supabase_get_line_items,
        clear_line_items as supabase_clear_line_items,
        insert_prozo_orders as supabase_insert_prozo_orders,
        get_prozo_orders as supabase_get_prozo_orders,
        clear_prozo_orders as supabase_clear_prozo_orders,
        upsert_unified_orders as supabase_upsert_unified_orders,
        get_unified_orders as supabase_get_unified_orders,
        get_unified_order_by_id as supabase_get_unified_order_by_id,
        clear_unified_orders as supabase_clear_unified_orders,
        get_delivery_status_mapping as supabase_get_delivery_status_mapping,
        get_payment_method_mapping as supabase_get_payment_method_mapping,
        log_import as supabase_log_import,
        get_last_import_info as supabase_get_last_import_info,
        get_table_counts as supabase_get_table_counts,
        get_logistics_stats as supabase_get_logistics_stats,
        clear_all_data as supabase_clear_all_data,
    )

    # Check if Supabase is connected
    conn_status = check_logistics_supabase_connection()
    if conn_status.get('connected'):
        USE_SUPABASE = True
        logger.info("Logistics: Using Supabase database backend")
    else:
        logger.warning(f"Logistics: Supabase not connected: {conn_status.get('error')}. Falling back to SQLite.")
except ImportError as e:
    logger.warning(f"Logistics: Supabase module not available: {e}. Using SQLite.")


def get_db_connection() -> sqlite3.Connection:
    """Get SQLite connection with row factory."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize all database tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # =========================================
    # RAW SHOPIFY ORDERS
    # =========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_shopify_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE,
            shopify_id TEXT,

            -- Customer
            email TEXT,
            phone TEXT,
            billing_phone TEXT,
            billing_name TEXT,
            shipping_name TEXT,

            -- Location
            shipping_city TEXT,
            shipping_state TEXT,
            shipping_pincode TEXT,

            -- Financials
            subtotal REAL,
            total REAL,
            discount_code TEXT,
            discount_amount REAL,
            refunded_amount REAL,

            -- Status
            financial_status TEXT,
            fulfillment_status TEXT,

            -- Payment
            payment_method_raw TEXT,
            payment_method TEXT,

            -- Product (aggregated)
            lineitem_names TEXT,
            total_quantity INTEGER,

            -- Dates
            order_date TEXT,
            cancelled_at TEXT,

            -- Meta
            source TEXT,
            tags TEXT,

            -- Import tracking
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            import_batch_id TEXT
        )
    """)

    # =========================================
    # ORDER LINE ITEMS (detailed breakdown)
    # =========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_line_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            lineitem_name TEXT,
            lineitem_sku TEXT,
            lineitem_quantity INTEGER,
            lineitem_price REAL,
            lineitem_discount REAL,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =========================================
    # RAW PROZO ORDERS
    # =========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_prozo_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            awb TEXT,
            order_id TEXT,

            -- Status
            status_raw TEXT,
            status TEXT,

            -- Customer
            drop_name TEXT,
            drop_phone TEXT,
            drop_email TEXT,
            drop_city TEXT,
            drop_state TEXT,
            drop_pincode TEXT,

            -- Logistics
            courier_partner TEXT,
            payment_mode TEXT,

            -- Dates
            order_created_at TEXT,
            pickup_date TEXT,
            delivery_date TEXT,
            rto_delivery_date TEXT,

            -- TAT
            min_tat INTEGER,
            max_tat INTEGER,

            -- NDR
            ndr_status TEXT,
            total_attempts INTEGER,
            latest_remark TEXT,

            -- Costs
            merchant_price REAL,
            merchant_price_rto REAL,

            -- Import tracking
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            import_batch_id TEXT
        )
    """)

    # =========================================
    # UNIFIED ORDERS (matched view)
    # =========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unified_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE,

            -- Customer
            customer_email TEXT,
            customer_phone TEXT,
            customer_name TEXT,
            customer_city TEXT,
            customer_state TEXT,
            customer_pincode TEXT,

            -- Order
            order_date TEXT,
            total_amount REAL,
            subtotal REAL,
            discount_amount REAL,
            lineitem_names TEXT,
            total_quantity INTEGER,

            -- Payment
            payment_mode TEXT,
            financial_status TEXT,

            -- Delivery (from Prozo)
            prozo_awb TEXT,
            delivery_status TEXT,
            delivery_status_raw TEXT,
            courier_partner TEXT,
            pickup_date TEXT,
            delivery_date TEXT,
            rto_date TEXT,

            -- Dispatch Time
            dispatch_hours REAL,
            dispatch_category TEXT,

            -- Computed flags
            is_delivered INTEGER DEFAULT 0,
            is_in_transit INTEGER DEFAULT 0,
            is_rto INTEGER DEFAULT 0,
            is_cancelled INTEGER DEFAULT 0,
            is_refunded INTEGER DEFAULT 0,
            is_not_shipped INTEGER DEFAULT 0,
            revenue_category TEXT,

            -- Timestamps
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =========================================
    # LOOKUP: Payment Method Mapping
    # =========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_method_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_value TEXT,
            source_system TEXT,
            normalized_value TEXT,
            display_name TEXT
        )
    """)

    # =========================================
    # LOOKUP: Delivery Status Mapping
    # =========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delivery_status_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_value TEXT,
            source_system TEXT,
            normalized_value TEXT,
            is_revenue INTEGER DEFAULT 0,
            is_pending INTEGER DEFAULT 0,
            is_lost INTEGER DEFAULT 0,
            display_name TEXT
        )
    """)

    # =========================================
    # IMPORT LOG
    # =========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS import_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT UNIQUE,
            source TEXT,
            file_name TEXT,
            records_total INTEGER,
            records_new INTEGER,
            records_updated INTEGER,
            records_failed INTEGER,
            date_range_start TEXT,
            date_range_end TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =========================================
    # INDEXES
    # =========================================
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_shopify_order_id ON raw_shopify_orders(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_shopify_email ON raw_shopify_orders(email)",
        "CREATE INDEX IF NOT EXISTS idx_shopify_phone ON raw_shopify_orders(phone)",
        "CREATE INDEX IF NOT EXISTS idx_shopify_order_date ON raw_shopify_orders(order_date)",
        "CREATE INDEX IF NOT EXISTS idx_prozo_order_id ON raw_prozo_orders(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_prozo_awb ON raw_prozo_orders(awb)",
        "CREATE INDEX IF NOT EXISTS idx_prozo_status ON raw_prozo_orders(status)",
        "CREATE INDEX IF NOT EXISTS idx_unified_order_id ON unified_orders(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_unified_delivery_status ON unified_orders(delivery_status)",
        "CREATE INDEX IF NOT EXISTS idx_unified_payment_mode ON unified_orders(payment_mode)",
        "CREATE INDEX IF NOT EXISTS idx_unified_order_date ON unified_orders(order_date)",
        "CREATE INDEX IF NOT EXISTS idx_line_items_order_id ON order_line_items(order_id)",
    ]

    for idx_sql in indexes:
        cursor.execute(idx_sql)

    conn.commit()

    # Populate lookup tables
    _populate_lookup_tables(conn)

    conn.close()


def _populate_lookup_tables(conn: sqlite3.Connection):
    """Populate lookup tables with default mappings."""
    cursor = conn.cursor()

    # Check if already populated
    cursor.execute("SELECT COUNT(*) FROM delivery_status_mapping")
    if cursor.fetchone()[0] > 0:
        return

    # Delivery Status Mapping (Prozo)
    delivery_mappings = [
        # (source_value, source_system, normalized_value, is_revenue, is_pending, is_lost, display_name)
        ("DELIVERED", "prozo", "delivered", 1, 0, 0, "Delivered"),
        ("SHIPMENT_DELAYED", "prozo", "in_transit", 0, 1, 0, "In Transit"),
        ("OUT_FOR_DELIVERY", "prozo", "in_transit", 0, 1, 0, "In Transit"),
        ("FAILED_DELIVERY", "prozo", "in_transit", 0, 1, 0, "In Transit"),
        ("CANCELLED_ORDER", "prozo", "cancelled", 0, 0, 1, "Cancelled"),
        ("RTO_DELIVERED", "prozo", "rto", 0, 0, 1, "RTO"),
        ("RTO_REQUESTED", "prozo", "rto", 0, 0, 1, "RTO"),
        ("RTO_INTRANSIT", "prozo", "rto", 0, 0, 1, "RTO"),
        ("RTO_OUT_FOR_DELIVERY", "prozo", "rto", 0, 0, 1, "RTO"),
    ]

    cursor.executemany("""
        INSERT INTO delivery_status_mapping
        (source_value, source_system, normalized_value, is_revenue, is_pending, is_lost, display_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, delivery_mappings)

    # Payment Method Mapping (Shopify)
    payment_mappings = [
        # (source_value, source_system, normalized_value, display_name)
        ("paid", "shopify_financial", "prepaid", "Full Prepaid"),
        ("partially_paid", "shopify_financial", "partial", "Partial Prepaid"),
        ("pending", "shopify_financial", "cod", "COD"),
        ("voided", "shopify_financial", "cancelled", "Cancelled"),
        ("refunded", "shopify_financial", "refunded", "Refunded"),
        ("partially_refunded", "shopify_financial", "partial_refund", "Partially Refunded"),
        ("Cash on Delivery (COD)", "shopify_payment", "cod", "COD"),
        ("Razorpay", "shopify_payment", "prepaid", "Prepaid"),
        ("manual", "shopify_payment", "manual", "Manual"),
    ]

    cursor.executemany("""
        INSERT INTO payment_method_mapping
        (source_value, source_system, normalized_value, display_name)
        VALUES (?, ?, ?, ?)
    """, payment_mappings)

    conn.commit()


def get_delivery_status_mapping() -> Dict[str, Dict]:
    """Get delivery status mapping as dictionary."""
    if USE_SUPABASE:
        return supabase_get_delivery_status_mapping()

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM delivery_status_mapping WHERE source_system = 'prozo'")
    rows = cursor.fetchall()
    conn.close()

    return {
        row['source_value']: {
            'normalized': row['normalized_value'],
            'is_revenue': row['is_revenue'],
            'is_pending': row['is_pending'],
            'is_lost': row['is_lost'],
            'display_name': row['display_name']
        }
        for row in rows
    }


def clear_all_data():
    """Clear all data from tables (for fresh import)."""
    if USE_SUPABASE:
        return supabase_clear_all_data()

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    tables = [
        "raw_shopify_orders",
        "raw_prozo_orders",
        "unified_orders",
        "order_line_items",
        "import_log"
    ]

    for table in tables:
        cursor.execute(f"DELETE FROM {table}")

    conn.commit()
    conn.close()


def get_table_counts() -> Dict[str, int]:
    """Get row counts for all tables."""
    if USE_SUPABASE:
        return supabase_get_table_counts()

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    tables = [
        "raw_shopify_orders",
        "raw_prozo_orders",
        "unified_orders",
        "order_line_items"
    ]

    counts = {}
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cursor.fetchone()[0]

    conn.close()
    return counts


def get_last_import_info(source: str) -> Optional[Dict]:
    """Get info about last import for a source."""
    if USE_SUPABASE:
        return supabase_get_last_import_info(source)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM import_log
        WHERE source = ?
        ORDER BY imported_at DESC
        LIMIT 1
    """, (source,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None
