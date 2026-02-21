"""
Supabase Database Helper for Logistics Reconciliation

This module provides database operations using Supabase instead of SQLite.
Data persists in the cloud and survives app reboots.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

# Import the shared Supabase client
try:
    from supabase_db import get_supabase_client, SUPABASE_AVAILABLE
except ImportError:
    SUPABASE_AVAILABLE = False
    def get_supabase_client():
        return None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_logistics_supabase_connection() -> Dict[str, Any]:
    """Check if Supabase connection is working for logistics tables."""
    client = get_supabase_client()

    if not client:
        return {"connected": False, "error": "Supabase client not available"}

    try:
        result = client.table('unified_orders').select('id').limit(1).execute()
        return {"connected": True, "error": None}
    except Exception as e:
        return {"connected": False, "error": str(e)}


# =============================================================================
# RAW SHOPIFY ORDERS
# =============================================================================

def insert_shopify_orders(orders: List[Dict[str, Any]], batch_id: str) -> int:
    """Insert multiple Shopify orders. Returns count of inserted records."""
    client = get_supabase_client()
    if not client or not orders:
        return 0

    try:
        # Add batch_id to each order
        for order in orders:
            order['import_batch_id'] = batch_id

        # Upsert to handle duplicates
        client.table('raw_shopify_orders').upsert(
            orders, on_conflict='order_id'
        ).execute()

        logger.info(f"Inserted {len(orders)} Shopify orders")
        return len(orders)
    except Exception as e:
        logger.error(f"Error inserting Shopify orders: {e}")
        return 0


def get_shopify_orders(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Get Shopify orders with optional filters."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        query = client.table('raw_shopify_orders').select('*')

        if filters:
            if filters.get('order_date_from'):
                query = query.gte('order_date', filters['order_date_from'])
            if filters.get('order_date_to'):
                query = query.lte('order_date', filters['order_date_to'])
            if filters.get('payment_method'):
                query = query.eq('payment_method', filters['payment_method'])

        query = query.order('order_date', desc=True)
        result = query.execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching Shopify orders: {e}")
        return []


def clear_shopify_orders() -> bool:
    """Clear all Shopify orders."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table('raw_shopify_orders').delete().neq('id', 0).execute()
        return True
    except Exception as e:
        logger.error(f"Error clearing Shopify orders: {e}")
        return False


# =============================================================================
# ORDER LINE ITEMS
# =============================================================================

def insert_line_items(items: List[Dict[str, Any]]) -> int:
    """Insert order line items."""
    client = get_supabase_client()
    if not client or not items:
        return 0

    try:
        client.table('order_line_items').insert(items).execute()
        return len(items)
    except Exception as e:
        logger.error(f"Error inserting line items: {e}")
        return 0


def get_line_items(order_id: str) -> List[Dict[str, Any]]:
    """Get line items for an order."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        result = client.table('order_line_items').select('*').eq(
            'order_id', order_id
        ).execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching line items: {e}")
        return []


def clear_line_items() -> bool:
    """Clear all line items."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table('order_line_items').delete().neq('id', 0).execute()
        return True
    except Exception as e:
        logger.error(f"Error clearing line items: {e}")
        return False


# =============================================================================
# RAW PROZO ORDERS
# =============================================================================

def insert_prozo_orders(orders: List[Dict[str, Any]], batch_id: str) -> int:
    """Insert multiple Prozo orders."""
    client = get_supabase_client()
    if not client or not orders:
        return 0

    try:
        for order in orders:
            order['import_batch_id'] = batch_id

        client.table('raw_prozo_orders').insert(orders).execute()
        logger.info(f"Inserted {len(orders)} Prozo orders")
        return len(orders)
    except Exception as e:
        logger.error(f"Error inserting Prozo orders: {e}")
        return 0


def get_prozo_orders(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Get Prozo orders with optional filters."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        query = client.table('raw_prozo_orders').select('*')

        if filters:
            if filters.get('status'):
                query = query.eq('status', filters['status'])
            if filters.get('order_id'):
                query = query.eq('order_id', filters['order_id'])

        result = query.execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching Prozo orders: {e}")
        return []


def clear_prozo_orders() -> bool:
    """Clear all Prozo orders."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table('raw_prozo_orders').delete().neq('id', 0).execute()
        return True
    except Exception as e:
        logger.error(f"Error clearing Prozo orders: {e}")
        return False


# =============================================================================
# UNIFIED ORDERS
# =============================================================================

def upsert_unified_orders(orders: List[Dict[str, Any]]) -> int:
    """Upsert unified orders."""
    client = get_supabase_client()
    if not client or not orders:
        return 0

    try:
        # Add updated_at timestamp
        now = datetime.now().isoformat()
        for order in orders:
            order['updated_at'] = now

        client.table('unified_orders').upsert(
            orders, on_conflict='order_id'
        ).execute()
        return len(orders)
    except Exception as e:
        logger.error(f"Error upserting unified orders: {e}")
        return 0


def get_unified_orders(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Get unified orders with filters."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        query = client.table('unified_orders').select('*')

        if filters:
            if filters.get('order_date_from'):
                query = query.gte('order_date', filters['order_date_from'])
            if filters.get('order_date_to'):
                query = query.lte('order_date', filters['order_date_to'])
            if filters.get('delivery_status'):
                query = query.eq('delivery_status', filters['delivery_status'])
            if filters.get('payment_mode'):
                query = query.eq('payment_mode', filters['payment_mode'])

        query = query.order('order_date', desc=True)
        result = query.execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching unified orders: {e}")
        return []


def get_unified_order_by_id(order_id: str) -> Optional[Dict[str, Any]]:
    """Get a single unified order."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        result = client.table('unified_orders').select('*').eq(
            'order_id', order_id
        ).limit(1).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error fetching unified order: {e}")
        return None


def clear_unified_orders() -> bool:
    """Clear all unified orders."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table('unified_orders').delete().neq('id', 0).execute()
        return True
    except Exception as e:
        logger.error(f"Error clearing unified orders: {e}")
        return False


# =============================================================================
# LOOKUP TABLES
# =============================================================================

def get_delivery_status_mapping() -> Dict[str, Dict]:
    """Get delivery status mapping as dictionary."""
    client = get_supabase_client()
    if not client:
        return {}

    try:
        result = client.table('delivery_status_mapping').select('*').eq(
            'source_system', 'prozo'
        ).execute()

        return {
            row['source_value']: {
                'normalized': row['normalized_value'],
                'is_revenue': row['is_revenue'],
                'is_pending': row['is_pending'],
                'is_lost': row['is_lost'],
                'display_name': row['display_name']
            }
            for row in result.data
        }
    except Exception as e:
        logger.error(f"Error fetching delivery status mapping: {e}")
        return {}


def get_payment_method_mapping() -> Dict[str, Dict]:
    """Get payment method mapping as dictionary."""
    client = get_supabase_client()
    if not client:
        return {}

    try:
        result = client.table('payment_method_mapping').select('*').execute()

        return {
            row['source_value']: {
                'normalized': row['normalized_value'],
                'display_name': row['display_name']
            }
            for row in result.data
        }
    except Exception as e:
        logger.error(f"Error fetching payment method mapping: {e}")
        return {}


# =============================================================================
# IMPORT LOG
# =============================================================================

def log_import(
    batch_id: str,
    source: str,
    file_name: str,
    records_total: int,
    records_new: int = 0,
    records_updated: int = 0,
    records_failed: int = 0,
    date_range_start: str = None,
    date_range_end: str = None
) -> bool:
    """Log an import operation."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table('import_log').upsert({
            'batch_id': batch_id,
            'source': source,
            'file_name': file_name,
            'records_total': records_total,
            'records_new': records_new,
            'records_updated': records_updated,
            'records_failed': records_failed,
            'date_range_start': date_range_start,
            'date_range_end': date_range_end
        }, on_conflict='batch_id').execute()
        return True
    except Exception as e:
        logger.error(f"Error logging import: {e}")
        return False


def get_last_import_info(source: str) -> Optional[Dict[str, Any]]:
    """Get info about last import for a source."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        result = client.table('import_log').select('*').eq(
            'source', source
        ).order('imported_at', desc=True).limit(1).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error fetching last import: {e}")
        return None


# =============================================================================
# STATISTICS
# =============================================================================

def get_table_counts() -> Dict[str, int]:
    """Get row counts for all tables."""
    client = get_supabase_client()
    if not client:
        return {}

    counts = {}
    tables = ['raw_shopify_orders', 'raw_prozo_orders', 'unified_orders', 'order_line_items']

    for table in tables:
        try:
            result = client.table(table).select('id', count='exact').execute()
            counts[table] = result.count or 0
        except Exception as e:
            logger.error(f"Error counting {table}: {e}")
            counts[table] = 0

    return counts


def get_logistics_stats(filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get logistics dashboard statistics."""
    client = get_supabase_client()
    if not client:
        return {
            'total_orders': 0,
            'delivered': 0,
            'in_transit': 0,
            'rto': 0,
            'cancelled': 0,
            'not_shipped': 0,
            'total_revenue': 0,
            'cod_orders': 0,
            'prepaid_orders': 0
        }

    try:
        query = client.table('unified_orders').select('*')

        if filters:
            if filters.get('order_date_from'):
                query = query.gte('order_date', filters['order_date_from'])
            if filters.get('order_date_to'):
                query = query.lte('order_date', filters['order_date_to'])

        result = query.execute()
        orders = result.data

        total = len(orders)
        delivered = sum(1 for o in orders if o.get('is_delivered'))
        in_transit = sum(1 for o in orders if o.get('is_in_transit'))
        rto = sum(1 for o in orders if o.get('is_rto'))
        cancelled = sum(1 for o in orders if o.get('is_cancelled'))
        not_shipped = sum(1 for o in orders if o.get('is_not_shipped'))

        total_revenue = sum(o.get('total_amount', 0) or 0 for o in orders if o.get('is_delivered'))
        cod_orders = sum(1 for o in orders if o.get('payment_mode') == 'cod')
        prepaid_orders = sum(1 for o in orders if o.get('payment_mode') == 'prepaid')

        return {
            'total_orders': total,
            'delivered': delivered,
            'in_transit': in_transit,
            'rto': rto,
            'cancelled': cancelled,
            'not_shipped': not_shipped,
            'total_revenue': total_revenue,
            'cod_orders': cod_orders,
            'prepaid_orders': prepaid_orders
        }
    except Exception as e:
        logger.error(f"Error getting logistics stats: {e}")
        return {
            'total_orders': 0,
            'delivered': 0,
            'in_transit': 0,
            'rto': 0,
            'cancelled': 0,
            'not_shipped': 0,
            'total_revenue': 0,
            'cod_orders': 0,
            'prepaid_orders': 0
        }


def clear_all_data() -> bool:
    """Clear all logistics data."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table('raw_shopify_orders').delete().neq('id', 0).execute()
        client.table('raw_prozo_orders').delete().neq('id', 0).execute()
        client.table('unified_orders').delete().neq('id', 0).execute()
        client.table('order_line_items').delete().neq('id', 0).execute()
        client.table('import_log').delete().neq('id', 0).execute()
        return True
    except Exception as e:
        logger.error(f"Error clearing all data: {e}")
        return False
