"""
Logistics Reconciliation - Matching Engine & Metrics

Handles matching Shopify ↔ Prozo orders and calculating metrics.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd

from logistics_db import get_db_connection


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
# MATCHING ENGINE
# =============================================================================

def run_matching():
    """
    Match Shopify orders with Prozo orders and populate unified_orders.

    Matching is done by order_id (Shopify.order_id = Prozo.order_id).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all Shopify orders
    cursor.execute("""
        SELECT * FROM raw_shopify_orders
    """)
    shopify_orders = {row['order_id']: dict(row) for row in cursor.fetchall() if row['order_id']}

    # If no Shopify orders, return early
    if not shopify_orders:
        conn.close()
        return {
            'total_orders': 0,
            'matched': 0,
            'not_shipped': 0,
            'message': 'No Shopify orders found. Please upload Shopify data first.'
        }

    # Get all Prozo orders
    cursor.execute("""
        SELECT * FROM raw_prozo_orders
    """)
    prozo_orders = {row['order_id']: dict(row) for row in cursor.fetchall() if row['order_id']}

    # Clear existing unified orders
    cursor.execute("DELETE FROM unified_orders")

    matched_count = 0
    not_shipped_count = 0

    for order_id, shopify in shopify_orders.items():
        prozo = prozo_orders.get(order_id)

        # Determine delivery status
        if prozo:
            delivery_status = prozo['status']
            delivery_status_raw = prozo['status_raw']
            prozo_awb = prozo['awb']
            courier_partner = prozo['courier_partner']
            pickup_date = prozo['pickup_date']
            delivery_date = prozo['delivery_date']
            rto_date = prozo['rto_delivery_date']
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
            # Keep delivery status but mark as refunded
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

        # Insert unified order (with safe dictionary access)
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
            order_id,
            shopify.get('email'),
            customer_phone,
            customer_name,
            customer_city,
            customer_state,
            customer_pincode,
            shopify.get('order_date'),
            shopify.get('total'),
            shopify.get('subtotal'),
            shopify.get('discount_amount'),
            shopify.get('lineitem_names'),
            shopify.get('total_quantity'),
            shopify.get('payment_method'),  # Note: raw_shopify_orders uses 'payment_method', unified uses 'payment_mode'
            shopify.get('financial_status'),
            prozo_awb,
            delivery_status,
            delivery_status_raw,
            courier_partner,
            pickup_date,
            delivery_date,
            rto_date,
            dispatch_hours,
            dispatch_category,
            is_delivered,
            is_in_transit,
            is_rto,
            is_cancelled,
            is_refunded,
            is_not_shipped,
            revenue_category
        ))

    conn.commit()
    conn.close()

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
    conn = get_db_connection()
    cursor = conn.cursor()

    # Build date filter
    date_filter = ""
    params = []
    if start_date:
        date_filter += " AND DATE(order_date) >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND DATE(order_date) <= ?"
        params.append(end_date)

    # Total orders
    cursor.execute(f"""
        SELECT COUNT(*) as count, SUM(total_amount) as total
        FROM unified_orders
        WHERE 1=1 {date_filter}
    """, params)
    row = cursor.fetchone()
    total_orders = row['count'] or 0
    projected_revenue = row['total'] or 0

    # Actual revenue (delivered only, not refunded)
    cursor.execute(f"""
        SELECT COUNT(*) as count, SUM(total_amount) as total
        FROM unified_orders
        WHERE is_delivered = 1 AND is_refunded = 0 {date_filter}
    """, params)
    row = cursor.fetchone()
    delivered_orders = row['count'] or 0
    actual_revenue = row['total'] or 0

    # Lost revenue (RTO + Cancelled + Refunded)
    cursor.execute(f"""
        SELECT COUNT(*) as count, SUM(total_amount) as total
        FROM unified_orders
        WHERE revenue_category = 'lost' {date_filter}
    """, params)
    row = cursor.fetchone()
    lost_orders = row['count'] or 0
    lost_revenue = row['total'] or 0

    # Pending revenue (In Transit + Not Shipped)
    cursor.execute(f"""
        SELECT COUNT(*) as count, SUM(total_amount) as total
        FROM unified_orders
        WHERE revenue_category = 'pending' {date_filter}
    """, params)
    row = cursor.fetchone()
    pending_orders = row['count'] or 0
    pending_revenue = row['total'] or 0

    # Calculate AOVs
    projected_aov = projected_revenue / total_orders if total_orders > 0 else 0
    actual_aov = actual_revenue / delivered_orders if delivered_orders > 0 else 0

    # =========================================
    # PAYMENT METHOD BREAKDOWN
    # =========================================
    cursor.execute(f"""
        SELECT payment_mode,
               COUNT(*) as count,
               SUM(total_amount) as total
        FROM unified_orders
        WHERE payment_mode IS NOT NULL {date_filter}
        GROUP BY payment_mode
    """, params)

    payment_breakdown = {}
    for row in cursor.fetchall():
        payment_breakdown[row['payment_mode']] = {
            'count': row['count'],
            'total': row['total'] or 0,
            'percentage': (row['count'] / total_orders * 100) if total_orders > 0 else 0
        }

    # =========================================
    # DELIVERY STATUS BREAKDOWN
    # =========================================
    cursor.execute(f"""
        SELECT delivery_status,
               COUNT(*) as count,
               SUM(total_amount) as total
        FROM unified_orders
        WHERE 1=1 {date_filter}
        GROUP BY delivery_status
    """, params)

    delivery_breakdown = {}
    for row in cursor.fetchall():
        status = row['delivery_status'] or 'unknown'
        delivery_breakdown[status] = {
            'count': row['count'],
            'total': row['total'] or 0,
            'percentage': (row['count'] / total_orders * 100) if total_orders > 0 else 0
        }

    # =========================================
    # DISPATCH TIME BREAKDOWN
    # =========================================
    cursor.execute(f"""
        SELECT dispatch_category,
               COUNT(*) as count,
               AVG(dispatch_hours) as avg_hours
        FROM unified_orders
        WHERE 1=1 {date_filter}
        GROUP BY dispatch_category
    """, params)

    dispatch_breakdown = {}
    for row in cursor.fetchall():
        category = row['dispatch_category'] or 'not_dispatched'
        dispatch_breakdown[category] = {
            'count': row['count'],
            'avg_hours': round(row['avg_hours'], 1) if row['avg_hours'] else None,
            'percentage': (row['count'] / total_orders * 100) if total_orders > 0 else 0
        }

    # Average dispatch time (excluding not dispatched)
    cursor.execute(f"""
        SELECT AVG(dispatch_hours) as avg_hours
        FROM unified_orders
        WHERE dispatch_hours IS NOT NULL {date_filter}
    """, params)
    row = cursor.fetchone()
    avg_dispatch_hours = round(row['avg_hours'], 1) if row['avg_hours'] else None

    # =========================================
    # REFUNDED BREAKDOWN (within lost)
    # =========================================
    cursor.execute(f"""
        SELECT COUNT(*) as count, SUM(total_amount) as total
        FROM unified_orders
        WHERE is_refunded = 1 {date_filter}
    """, params)
    row = cursor.fetchone()
    refunded_orders = row['count'] or 0
    refunded_amount = row['total'] or 0

    # RTO orders
    cursor.execute(f"""
        SELECT COUNT(*) as count, SUM(total_amount) as total
        FROM unified_orders
        WHERE is_rto = 1 {date_filter}
    """, params)
    row = cursor.fetchone()
    rto_orders = row['count'] or 0
    rto_amount = row['total'] or 0

    # Cancelled orders
    cursor.execute(f"""
        SELECT COUNT(*) as count, SUM(total_amount) as total
        FROM unified_orders
        WHERE is_cancelled = 1 AND is_rto = 0 {date_filter}
    """, params)
    row = cursor.fetchone()
    cancelled_orders = row['count'] or 0
    cancelled_amount = row['total'] or 0

    # In Transit orders
    cursor.execute(f"""
        SELECT COUNT(*) as count, SUM(total_amount) as total
        FROM unified_orders
        WHERE is_in_transit = 1 {date_filter}
    """, params)
    row = cursor.fetchone()
    in_transit_orders = row['count'] or 0
    in_transit_amount = row['total'] or 0

    # Not Shipped orders
    cursor.execute(f"""
        SELECT COUNT(*) as count, SUM(total_amount) as total
        FROM unified_orders
        WHERE is_not_shipped = 1 {date_filter}
    """, params)
    row = cursor.fetchone()
    not_shipped_orders = row['count'] or 0
    not_shipped_amount = row['total'] or 0

    conn.close()

    # Calculate rates (baseline = total_orders for all percentages)
    delivery_rate = (delivered_orders / total_orders * 100) if total_orders > 0 else 0
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
        'delivered_orders': delivered_orders,
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

    if payment_mode and payment_mode != 'all':
        conditions.append("payment_mode = ?")
        params.append(payment_mode)

    if delivery_status and delivery_status != 'all':
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
    cursor.execute(f"""
        SELECT COUNT(*) FROM unified_orders WHERE {where_clause}
    """, params)
    total_count = cursor.fetchone()[0]

    # Get data
    cursor.execute(f"""
        SELECT
            order_id, order_date, customer_phone, customer_email,
            customer_city, customer_state, total_amount, payment_mode,
            delivery_status, delivery_status_raw, prozo_awb,
            dispatch_hours, dispatch_category, courier_partner,
            lineitem_names, is_refunded
        FROM unified_orders
        WHERE {where_clause}
        ORDER BY order_date DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    orders = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return orders, total_count


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
    conn = get_db_connection()
    cursor = conn.cursor()

    # Build WHERE clause
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
    cursor.execute(f"""
        SELECT COUNT(*) FROM order_line_items WHERE {where_clause}
    """, params)
    total_count = cursor.fetchone()[0]

    # Get data
    cursor.execute(f"""
        SELECT
            order_id, lineitem_name, lineitem_sku,
            lineitem_quantity, lineitem_price, lineitem_discount
        FROM order_line_items
        WHERE {where_clause}
        ORDER BY order_id DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    items = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return items, total_count


# =============================================================================
# DATE RANGE HELPERS
# =============================================================================

def get_date_range() -> Tuple[Optional[str], Optional[str]]:
    """Get min and max order dates from unified orders."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT MIN(DATE(order_date)) as min_date, MAX(DATE(order_date)) as max_date
        FROM unified_orders
    """)
    row = cursor.fetchone()
    conn.close()

    if row:
        return row['min_date'], row['max_date']
    return None, None


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
    conn = get_db_connection()
    cursor = conn.cursor()

    # Build date filter (join with unified_orders for date filtering)
    date_filter = ""
    params = []
    if start_date:
        date_filter += " AND DATE(u.order_date) >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND DATE(u.order_date) <= ?"
        params.append(end_date)

    # Get total line items count for percentage
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
