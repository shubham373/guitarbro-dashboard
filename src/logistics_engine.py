"""
Logistics Reconciliation - Matching Engine & Metrics

Handles matching Shopify ↔ Prozo orders and calculating metrics.

Database Backend:
- Primary: Supabase (cloud, persistent) - used in production
- Fallback: SQLite (local) - used for local development only
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE BACKEND SELECTION
# =============================================================================

USE_SUPABASE = False

# Try to import and connect to Supabase
try:
    from supabase_logistics_db import (
        check_logistics_supabase_connection,
        get_shopify_orders as supabase_get_shopify_orders,
        get_prozo_orders as supabase_get_prozo_orders,
        upsert_unified_orders as supabase_upsert_unified_orders,
        get_unified_orders as supabase_get_unified_orders,
        clear_unified_orders as supabase_clear_unified_orders,
        get_table_counts as supabase_get_table_counts,
    )
    from supabase_db import get_supabase_client, SUPABASE_AVAILABLE

    # Check if Supabase is actually connected
    if SUPABASE_AVAILABLE:
        conn_status = check_logistics_supabase_connection()
        if conn_status.get('connected'):
            USE_SUPABASE = True
            logger.info("Logistics Engine: Using Supabase database backend")
        else:
            logger.warning(f"Logistics Engine: Supabase connection failed: {conn_status.get('error')}. Using SQLite.")
    else:
        logger.warning("Logistics Engine: Supabase not available. Using SQLite.")
except ImportError as e:
    logger.warning(f"Logistics Engine: Supabase module not available: {e}. Using SQLite.")

# SQLite fallback
if not USE_SUPABASE:
    from logistics_db import get_db_connection
    logger.info("Logistics Engine: Using SQLite database backend (local development)")


def get_current_backend() -> str:
    """Return the current database backend being used."""
    return "supabase" if USE_SUPABASE else "sqlite"


# =============================================================================
# DISPATCH TIME CALCULATION
# =============================================================================

def calculate_dispatch_hours(order_date: str, pickup_date: str) -> Optional[float]:
    """
    Calculate hours between order creation and pickup.
    Returns None if either date is missing.
    """
    if not order_date or not pickup_date:
        return None

    try:
        # Parse dates
        order_dt = datetime.strptime(order_date[:19], "%Y-%m-%d %H:%M:%S")
        pickup_dt = datetime.strptime(pickup_date[:19], "%Y-%m-%d %H:%M:%S")

        # Calculate difference in hours
        delta = pickup_dt - order_dt
        hours = delta.total_seconds() / 3600

        return round(hours, 2) if hours >= 0 else None
    except (ValueError, TypeError):
        return None


def categorize_dispatch_time(hours: Optional[float]) -> str:
    """
    Categorize dispatch time.
    Returns: fast, normal, delayed, not_dispatched
    """
    if hours is None:
        return 'not_dispatched'
    elif hours <= 24:
        return 'fast'
    elif hours <= 48:
        return 'normal'
    else:
        return 'delayed'


# =============================================================================
# INTERNAL DATA ACCESS FUNCTIONS
# =============================================================================

def _get_all_shopify_orders() -> Dict[str, Dict]:
    """Get all Shopify orders as a dictionary keyed by order_id."""
    if USE_SUPABASE:
        orders = supabase_get_shopify_orders()
        return {o['order_id']: o for o in orders if o.get('order_id')}
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM raw_shopify_orders")
        result = {row['order_id']: dict(row) for row in cursor.fetchall() if row['order_id']}
        conn.close()
        return result


def _get_all_prozo_orders() -> Dict[str, Dict]:
    """Get all Prozo orders as a dictionary keyed by order_id."""
    if USE_SUPABASE:
        orders = supabase_get_prozo_orders()
        return {o['order_id']: o for o in orders if o.get('order_id')}
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM raw_prozo_orders")
        result = {row['order_id']: dict(row) for row in cursor.fetchall() if row['order_id']}
        conn.close()
        return result


def _clear_unified_orders():
    """Clear all unified orders."""
    if USE_SUPABASE:
        supabase_clear_unified_orders()
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM unified_orders")
        conn.commit()
        conn.close()


def _save_unified_orders(orders: List[Dict]):
    """Save unified orders to database."""
    if USE_SUPABASE:
        supabase_upsert_unified_orders(orders)
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        for order in orders:
            cursor.execute("""
                INSERT INTO unified_orders (
                    order_id, customer_email, customer_phone, customer_name,
                    customer_city, customer_state, customer_pincode,
                    order_date, total_amount, subtotal, discount_amount,
                    lineitem_names, total_quantity, payment_mode, financial_status,
                    prozo_awb, delivery_status, delivery_status_raw, courier_partner,
                    pickup_date, delivery_date, rto_date,
                    dispatch_hours, dispatch_category,
                    is_delivered, is_in_transit, is_rto, is_cancelled, is_refunded, is_not_shipped,
                    revenue_category
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.get('order_id'),
                order.get('customer_email'),
                order.get('customer_phone'),
                order.get('customer_name'),
                order.get('customer_city'),
                order.get('customer_state'),
                order.get('customer_pincode'),
                order.get('order_date'),
                order.get('total_amount'),
                order.get('subtotal'),
                order.get('discount_amount'),
                order.get('lineitem_names'),
                order.get('total_quantity'),
                order.get('payment_mode'),
                order.get('financial_status'),
                order.get('prozo_awb'),
                order.get('delivery_status'),
                order.get('delivery_status_raw'),
                order.get('courier_partner'),
                order.get('pickup_date'),
                order.get('delivery_date'),
                order.get('rto_date'),
                order.get('dispatch_hours'),
                order.get('dispatch_category'),
                order.get('is_delivered'),
                order.get('is_in_transit'),
                order.get('is_rto'),
                order.get('is_cancelled'),
                order.get('is_refunded'),
                order.get('is_not_shipped'),
                order.get('revenue_category')
            ))
        conn.commit()
        conn.close()


def _get_unified_orders_filtered(
    start_date: str = None,
    end_date: str = None,
    delivery_status: str = None,
    payment_mode: str = None,
    search_query: str = None,
    limit: int = None,
    offset: int = 0
) -> Tuple[List[Dict], int]:
    """Get unified orders with filters. Returns (orders, total_count)."""

    if USE_SUPABASE:
        # Build Supabase filters
        # Note: order_date uses space separator (YYYY-MM-DD HH:MM:SS), not T
        filters = {}
        if start_date:
            filters['order_date_from'] = f"{start_date} 00:00:00"
        if end_date:
            filters['order_date_to'] = f"{end_date} 23:59:59"
        if delivery_status:
            filters['delivery_status'] = delivery_status
        if payment_mode:
            filters['payment_mode'] = payment_mode

        orders = supabase_get_unified_orders(filters)

        # Apply search filter (client-side for Supabase)
        if search_query:
            search_query = search_query.strip().lower()
            orders = [
                o for o in orders
                if (search_query in (o.get('order_id') or '').lower() or
                    search_query in (o.get('customer_phone') or '').lower() or
                    search_query in (o.get('customer_email') or '').lower())
            ]

        total_count = len(orders)

        # Apply limit/offset
        if limit:
            orders = orders[offset:offset + limit]

        return orders, total_count
    else:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build WHERE clause
        conditions = ["1=1"]
        params = []

        if search_query:
            search_query = search_query.strip()
            conditions.append("""
                (order_id LIKE ? OR customer_phone LIKE ? OR customer_email LIKE ?)
            """)
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern, search_pattern])

        if payment_mode:
            conditions.append("payment_mode = ?")
            params.append(payment_mode)

        if delivery_status:
            conditions.append("delivery_status = ?")
            params.append(delivery_status)

        if start_date:
            conditions.append("DATE(order_date) >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("DATE(order_date) <= ?")
            params.append(end_date)

        where_clause = " AND ".join(conditions)

        # Get total count
        cursor.execute(f"SELECT COUNT(*) FROM unified_orders WHERE {where_clause}", params)
        total_count = cursor.fetchone()[0]

        # Get data
        query = f"""
            SELECT * FROM unified_orders
            WHERE {where_clause}
            ORDER BY order_date DESC
        """
        if limit:
            query += f" LIMIT {limit} OFFSET {offset}"

        cursor.execute(query, params)
        orders = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return orders, total_count


def _get_line_items_filtered(
    search_query: str = None,
    limit: int = None,
    offset: int = 0
) -> Tuple[List[Dict], int]:
    """Get line items with filters. Returns (items, total_count)."""

    if USE_SUPABASE:
        # For Supabase, we need to query the line items table
        client = get_supabase_client()
        if not client:
            return [], 0

        try:
            query = client.table('order_line_items').select('*')
            result = query.execute()
            items = result.data

            # Apply search filter
            if search_query:
                search_query = search_query.strip().lower()
                items = [
                    i for i in items
                    if (search_query in (i.get('order_id') or '').lower() or
                        search_query in (i.get('lineitem_sku') or '').lower() or
                        search_query in (i.get('lineitem_name') or '').lower())
                ]

            total_count = len(items)

            # Apply limit/offset
            if limit:
                items = items[offset:offset + limit]

            return items, total_count
        except Exception as e:
            logger.error(f"Error fetching line items from Supabase: {e}")
            return [], 0
    else:
        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = ["1=1"]
        params = []

        if search_query:
            search_query = search_query.strip()
            conditions.append("""
                (order_id LIKE ? OR lineitem_sku LIKE ? OR lineitem_name LIKE ?)
            """)
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern, search_pattern])

        where_clause = " AND ".join(conditions)

        # Get total count
        cursor.execute(f"SELECT COUNT(*) FROM order_line_items WHERE {where_clause}", params)
        total_count = cursor.fetchone()[0]

        # Get data
        query = f"""
            SELECT order_id, lineitem_name, lineitem_sku, lineitem_quantity, lineitem_price, lineitem_discount
            FROM order_line_items
            WHERE {where_clause}
            ORDER BY order_id DESC
        """
        if limit:
            query += f" LIMIT {limit} OFFSET {offset}"

        cursor.execute(query, params)
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return items, total_count


# =============================================================================
# MATCHING ENGINE
# =============================================================================

def run_matching():
    """
    Match Shopify orders with Prozo orders and populate unified_orders.

    Matching is done by order_id (Shopify.order_id = Prozo.order_id).
    """
    logger.info(f"Running matching engine with backend: {get_current_backend()}")

    # Get all Shopify orders
    shopify_orders = _get_all_shopify_orders()

    # If no Shopify orders, return early
    if not shopify_orders:
        return {
            'total_orders': 0,
            'matched': 0,
            'not_shipped': 0,
            'message': 'No Shopify orders found. Please upload Shopify data first.'
        }

    # Get all Prozo orders
    prozo_orders = _get_all_prozo_orders()

    # Clear existing unified orders
    _clear_unified_orders()

    matched_count = 0
    not_shipped_count = 0
    unified_orders_batch = []

    for order_id, shopify in shopify_orders.items():
        prozo = prozo_orders.get(order_id)

        # Determine delivery status
        if prozo:
            delivery_status = prozo.get('status')
            delivery_status_raw = prozo.get('status_raw')
            prozo_awb = prozo.get('awb')
            courier_partner = prozo.get('courier_partner')
            pickup_date = prozo.get('pickup_date')
            delivery_date = prozo.get('delivery_date')
            rto_date = prozo.get('rto_delivery_date')
            matched_count += 1
        else:
            # Not in Prozo = not shipped
            delivery_status = 'not_shipped'
            delivery_status_raw = None
            prozo_awb = None
            courier_partner = None
            pickup_date = None
            delivery_date = None
            rto_date = None
            not_shipped_count += 1

        # Handle refunded orders (from Shopify financial_status)
        financial_status = shopify.get('financial_status', '')
        if financial_status in ['refunded', 'partially_refunded']:
            is_refunded = 1
        else:
            is_refunded = 0

        # Handle cancelled (voided) orders
        if financial_status == 'voided' or delivery_status == 'cancelled':
            is_cancelled = 1
            delivery_status = 'cancelled'
        else:
            is_cancelled = 0

        # Calculate dispatch time
        dispatch_hours = calculate_dispatch_hours(shopify.get('order_date'), pickup_date)
        dispatch_category = categorize_dispatch_time(dispatch_hours)

        # Set flags
        is_delivered = 1 if delivery_status == 'delivered' else 0
        is_in_transit = 1 if delivery_status == 'in_transit' else 0
        is_rto = 1 if delivery_status == 'rto' else 0
        is_not_shipped = 1 if delivery_status == 'not_shipped' else 0

        # Determine revenue category
        if is_delivered and not is_refunded:
            revenue_category = 'actual'
        elif is_in_transit or is_not_shipped:
            revenue_category = 'pending'
        else:
            revenue_category = 'lost'

        # Customer info (prefer Shopify, fallback to Prozo)
        customer_phone = shopify.get('phone') or shopify.get('billing_phone')
        if not customer_phone and prozo:
            customer_phone = prozo.get('drop_phone')

        customer_name = shopify.get('shipping_name') or shopify.get('billing_name')
        if not customer_name and prozo:
            customer_name = prozo.get('drop_name')

        customer_city = shopify.get('shipping_city')
        if not customer_city and prozo:
            customer_city = prozo.get('drop_city')

        customer_state = shopify.get('shipping_state')
        if not customer_state and prozo:
            customer_state = prozo.get('drop_state')

        customer_pincode = shopify.get('shipping_pincode')
        if not customer_pincode and prozo:
            customer_pincode = prozo.get('drop_pincode')

        # Build unified order record
        unified_order = {
            'order_id': order_id,
            'customer_email': shopify.get('email'),
            'customer_phone': customer_phone,
            'customer_name': customer_name,
            'customer_city': customer_city,
            'customer_state': customer_state,
            'customer_pincode': customer_pincode,
            'order_date': shopify.get('order_date'),
            'total_amount': shopify.get('total'),
            'subtotal': shopify.get('subtotal'),
            'discount_amount': shopify.get('discount_amount'),
            'lineitem_names': shopify.get('lineitem_names'),
            'total_quantity': shopify.get('total_quantity'),
            'payment_mode': shopify.get('payment_method'),
            'financial_status': shopify.get('financial_status'),
            'prozo_awb': prozo_awb,
            'delivery_status': delivery_status,
            'delivery_status_raw': delivery_status_raw,
            'courier_partner': courier_partner,
            'pickup_date': pickup_date,
            'delivery_date': delivery_date,
            'rto_date': rto_date,
            'dispatch_hours': dispatch_hours,
            'dispatch_category': dispatch_category,
            'is_delivered': is_delivered,
            'is_in_transit': is_in_transit,
            'is_rto': is_rto,
            'is_cancelled': is_cancelled,
            'is_refunded': is_refunded,
            'is_not_shipped': is_not_shipped,
            'revenue_category': revenue_category
        }
        unified_orders_batch.append(unified_order)

    # Save all unified orders
    _save_unified_orders(unified_orders_batch)

    logger.info(f"Matching complete: {len(shopify_orders)} total, {matched_count} matched, {not_shipped_count} not shipped")

    return {
        'total_orders': len(shopify_orders),
        'matched': matched_count,
        'not_shipped': not_shipped_count
    }


# =============================================================================
# METRICS CALCULATION
# =============================================================================

def get_dashboard_metrics(start_date: str = None, end_date: str = None) -> Dict[str, Any]:
    """
    Calculate all dashboard metrics.

    Args:
        start_date: Filter start date (YYYY-MM-DD)
        end_date: Filter end date (YYYY-MM-DD)

    Returns dict with all metrics.
    """
    logger.info(f"Getting dashboard metrics with backend: {get_current_backend()}")

    # Get all orders for the date range
    orders, total_orders = _get_unified_orders_filtered(
        start_date=start_date,
        end_date=end_date
    )

    if not orders:
        return _empty_metrics()

    # Calculate metrics from orders
    projected_revenue = sum(o.get('total_amount') or 0 for o in orders)

    delivered_orders = [o for o in orders if o.get('is_delivered') and not o.get('is_refunded')]
    actual_revenue = sum(o.get('total_amount') or 0 for o in delivered_orders)

    lost_orders = [o for o in orders if o.get('revenue_category') == 'lost']
    lost_revenue = sum(o.get('total_amount') or 0 for o in lost_orders)

    pending_orders = [o for o in orders if o.get('revenue_category') == 'pending']
    pending_revenue = sum(o.get('total_amount') or 0 for o in pending_orders)

    # Calculate AOVs
    projected_aov = projected_revenue / total_orders if total_orders > 0 else 0
    actual_aov = actual_revenue / len(delivered_orders) if delivered_orders else 0

    # Payment breakdown
    payment_breakdown = {}
    for order in orders:
        mode = order.get('payment_mode')
        if mode:
            if mode not in payment_breakdown:
                payment_breakdown[mode] = {'count': 0, 'total': 0}
            payment_breakdown[mode]['count'] += 1
            payment_breakdown[mode]['total'] += order.get('total_amount') or 0

    for mode in payment_breakdown:
        payment_breakdown[mode]['percentage'] = (
            payment_breakdown[mode]['count'] / total_orders * 100
        ) if total_orders > 0 else 0

    # Delivery status breakdown
    delivery_breakdown = {}
    for order in orders:
        status = order.get('delivery_status') or 'unknown'
        if status not in delivery_breakdown:
            delivery_breakdown[status] = {'count': 0, 'total': 0}
        delivery_breakdown[status]['count'] += 1
        delivery_breakdown[status]['total'] += order.get('total_amount') or 0

    for status in delivery_breakdown:
        delivery_breakdown[status]['percentage'] = (
            delivery_breakdown[status]['count'] / total_orders * 100
        ) if total_orders > 0 else 0

    # Dispatch breakdown
    dispatch_breakdown = {}
    dispatch_hours_list = []
    for order in orders:
        cat = order.get('dispatch_category') or 'not_dispatched'
        if cat not in dispatch_breakdown:
            dispatch_breakdown[cat] = {'count': 0, 'hours': []}
        dispatch_breakdown[cat]['count'] += 1
        if order.get('dispatch_hours') is not None:
            dispatch_breakdown[cat]['hours'].append(order.get('dispatch_hours'))
            dispatch_hours_list.append(order.get('dispatch_hours'))

    for cat in dispatch_breakdown:
        hours = dispatch_breakdown[cat]['hours']
        dispatch_breakdown[cat]['avg_hours'] = round(sum(hours) / len(hours), 1) if hours else None
        dispatch_breakdown[cat]['percentage'] = (
            dispatch_breakdown[cat]['count'] / total_orders * 100
        ) if total_orders > 0 else 0
        del dispatch_breakdown[cat]['hours']  # Remove raw data

    avg_dispatch_hours = round(sum(dispatch_hours_list) / len(dispatch_hours_list), 1) if dispatch_hours_list else None

    # Count specific statuses
    rto_orders = sum(1 for o in orders if o.get('is_rto'))
    rto_amount = sum(o.get('total_amount') or 0 for o in orders if o.get('is_rto'))

    cancelled_orders_list = [o for o in orders if o.get('is_cancelled') and not o.get('is_rto')]
    cancelled_orders = len(cancelled_orders_list)
    cancelled_amount = sum(o.get('total_amount') or 0 for o in cancelled_orders_list)

    in_transit_orders = sum(1 for o in orders if o.get('is_in_transit'))
    in_transit_amount = sum(o.get('total_amount') or 0 for o in orders if o.get('is_in_transit'))

    not_shipped_orders = sum(1 for o in orders if o.get('is_not_shipped'))
    not_shipped_amount = sum(o.get('total_amount') or 0 for o in orders if o.get('is_not_shipped'))

    refunded_orders = sum(1 for o in orders if o.get('is_refunded'))
    refunded_amount = sum(o.get('total_amount') or 0 for o in orders if o.get('is_refunded'))

    # Calculate rates
    delivery_rate = (len(delivered_orders) / total_orders * 100) if total_orders > 0 else 0
    rto_rate = (rto_orders / total_orders * 100) if total_orders > 0 else 0

    return {
        # Summary
        'total_orders': total_orders,
        'projected_revenue': projected_revenue,
        'projected_aov': projected_aov,
        'actual_revenue': actual_revenue,
        'actual_aov': actual_aov,
        'lost_revenue': lost_revenue,
        'pending_revenue': pending_revenue,
        'lost_percentage': (lost_revenue / projected_revenue * 100) if projected_revenue > 0 else 0,

        # Rates
        'delivery_rate': delivery_rate,
        'rto_rate': rto_rate,

        # Payment Breakdown
        'payment_breakdown': payment_breakdown,

        # Delivery Breakdown
        'delivery_breakdown': delivery_breakdown,
        'delivered_orders': len(delivered_orders),
        'in_transit_orders': in_transit_orders,
        'in_transit_amount': in_transit_amount,
        'rto_orders': rto_orders,
        'rto_amount': rto_amount,
        'cancelled_orders': cancelled_orders,
        'cancelled_amount': cancelled_amount,
        'not_shipped_orders': not_shipped_orders,
        'not_shipped_amount': not_shipped_amount,
        'refunded_orders': refunded_orders,
        'refunded_amount': refunded_amount,

        # Dispatch Breakdown
        'dispatch_breakdown': dispatch_breakdown,
        'avg_dispatch_hours': avg_dispatch_hours,
    }


def _empty_metrics() -> Dict[str, Any]:
    """Return empty metrics structure."""
    return {
        'total_orders': 0,
        'projected_revenue': 0,
        'projected_aov': 0,
        'actual_revenue': 0,
        'actual_aov': 0,
        'lost_revenue': 0,
        'pending_revenue': 0,
        'lost_percentage': 0,
        'delivery_rate': 0,
        'rto_rate': 0,
        'payment_breakdown': {},
        'delivery_breakdown': {},
        'delivered_orders': 0,
        'in_transit_orders': 0,
        'in_transit_amount': 0,
        'rto_orders': 0,
        'rto_amount': 0,
        'cancelled_orders': 0,
        'cancelled_amount': 0,
        'not_shipped_orders': 0,
        'not_shipped_amount': 0,
        'refunded_orders': 0,
        'refunded_amount': 0,
        'dispatch_breakdown': {},
        'avg_dispatch_hours': None,
    }


# =============================================================================
# USER JOURNEY DATA
# =============================================================================

def get_user_journey_data(
    search_query: str = None,
    payment_mode: str = None,
    delivery_status: str = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = 500,
    offset: int = 0
) -> Tuple[List[Dict], int]:
    """
    Get user journey data with filters and search.

    Returns tuple of (list of orders, total count).
    """
    orders, total_count = _get_unified_orders_filtered(
        start_date=start_date,
        end_date=end_date,
        delivery_status=delivery_status if delivery_status != 'all' else None,
        payment_mode=payment_mode if payment_mode != 'all' else None,
        search_query=search_query,
        limit=limit,
        offset=offset
    )

    # Select only needed fields
    result = []
    for order in orders:
        result.append({
            'order_id': order.get('order_id'),
            'order_date': order.get('order_date'),
            'customer_phone': order.get('customer_phone'),
            'customer_email': order.get('customer_email'),
            'customer_city': order.get('customer_city'),
            'customer_state': order.get('customer_state'),
            'total_amount': order.get('total_amount'),
            'payment_mode': order.get('payment_mode'),
            'delivery_status': order.get('delivery_status'),
            'delivery_status_raw': order.get('delivery_status_raw'),
            'prozo_awb': order.get('prozo_awb'),
            'dispatch_hours': order.get('dispatch_hours'),
            'dispatch_category': order.get('dispatch_category'),
            'courier_partner': order.get('courier_partner'),
            'lineitem_names': order.get('lineitem_names'),
            'is_refunded': order.get('is_refunded'),
        })

    return result, total_count


# =============================================================================
# LINE ITEMS DATA
# =============================================================================

def get_line_items_data(
    search_query: str = None,
    limit: int = 500,
    offset: int = 0
) -> Tuple[List[Dict], int]:
    """
    Get line items data with search.

    Returns tuple of (list of line items, total count).
    """
    return _get_line_items_filtered(
        search_query=search_query,
        limit=limit,
        offset=offset
    )


# =============================================================================
# DATE RANGE HELPERS
# =============================================================================

def get_date_range() -> Tuple[Optional[str], Optional[str]]:
    """Get min and max order dates from unified orders."""
    orders, _ = _get_unified_orders_filtered()

    if not orders:
        return None, None

    dates = [o.get('order_date') for o in orders if o.get('order_date')]
    if not dates:
        return None, None

    # Extract just the date part
    min_date = min(dates)[:10]
    max_date = max(dates)[:10]

    return min_date, max_date


# =============================================================================
# SKU-LEVEL SALES DATA
# =============================================================================

def get_sku_level_sales(start_date: str = None, end_date: str = None) -> Tuple[List[Dict], int]:
    """
    Get SKU-level sales breakdown.

    Returns:
        - List of SKU data with quantities, orders, revenue
        - Total line items count (for percentage calculation)
    """
    if USE_SUPABASE:
        # For Supabase, we need to join line items with unified orders
        client = get_supabase_client()
        if not client:
            return [], 0

        try:
            # Get unified orders for date range
            orders, _ = _get_unified_orders_filtered(start_date=start_date, end_date=end_date)
            order_ids = {o.get('order_id') for o in orders}

            # Get all line items
            result = client.table('order_line_items').select('*').execute()
            all_items = result.data

            # Filter to matching order IDs
            items = [i for i in all_items if i.get('order_id') in order_ids]

            # Aggregate by SKU
            sku_data = {}
            total_qty = 0

            for item in items:
                sku = item.get('lineitem_sku') or 'No SKU'
                name = item.get('lineitem_name') or 'Unknown'
                qty = item.get('lineitem_quantity') or 0
                price = item.get('lineitem_price') or 0

                key = (sku, name)
                if key not in sku_data:
                    sku_data[key] = {
                        'sku': sku,
                        'item_name': name,
                        'total_qty': 0,
                        'order_count': 0,
                        'revenue': 0,
                        'order_ids': set()
                    }

                sku_data[key]['total_qty'] += qty
                sku_data[key]['revenue'] += price * qty
                sku_data[key]['order_ids'].add(item.get('order_id'))
                total_qty += qty

            # Convert to list and calculate percentages
            result_list = []
            for data in sku_data.values():
                result_list.append({
                    'sku': data['sku'],
                    'item_name': data['item_name'],
                    'total_qty': data['total_qty'],
                    'order_count': len(data['order_ids']),
                    'revenue': data['revenue'],
                    'percentage': (data['total_qty'] / total_qty * 100) if total_qty > 0 else 0
                })

            # Sort by quantity
            result_list.sort(key=lambda x: x['total_qty'], reverse=True)

            return result_list, total_qty

        except Exception as e:
            logger.error(f"Error getting SKU sales from Supabase: {e}")
            return [], 0
    else:
        # SQLite implementation
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build date filter
        date_filter = ""
        params = []
        if start_date:
            date_filter += " AND DATE(u.order_date) >= ?"
            params.append(start_date)
        if end_date:
            date_filter += " AND DATE(u.order_date) <= ?"
            params.append(end_date)

        # Get total line items count
        cursor.execute(f"""
            SELECT SUM(li.lineitem_quantity) as total_qty
            FROM order_line_items li
            INNER JOIN unified_orders u ON li.order_id = u.order_id
            WHERE 1=1 {date_filter}
        """, params)
        row = cursor.fetchone()
        total_line_items = row['total_qty'] or 0

        # Get SKU-level breakdown
        cursor.execute(f"""
            SELECT
                COALESCE(li.lineitem_sku, 'No SKU') as sku,
                COALESCE(li.lineitem_name, 'Unknown') as item_name,
                SUM(li.lineitem_quantity) as total_qty,
                COUNT(DISTINCT li.order_id) as order_count,
                SUM(li.lineitem_price * li.lineitem_quantity) as revenue
            FROM order_line_items li
            INNER JOIN unified_orders u ON li.order_id = u.order_id
            WHERE 1=1 {date_filter}
            GROUP BY li.lineitem_sku, li.lineitem_name
            ORDER BY total_qty DESC
        """, params)

        sku_data = []
        for row in cursor.fetchall():
            sku_data.append({
                'sku': row['sku'],
                'item_name': row['item_name'],
                'total_qty': row['total_qty'] or 0,
                'order_count': row['order_count'] or 0,
                'revenue': row['revenue'] or 0,
                'percentage': (row['total_qty'] / total_line_items * 100) if total_line_items > 0 else 0
            })

        conn.close()
        return sku_data, total_line_items
