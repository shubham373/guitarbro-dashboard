"""
Logistics Reconciliation - CSV Parsers

Handles parsing and importing Shopify and Prozo CSV files.
"""

import pandas as pd
import re
import uuid
from datetime import datetime
from typing import Tuple, Optional, Dict, Any, List

from logistics_db import (
    get_db_connection,
    get_delivery_status_mapping
)


# =============================================================================
# NORMALIZATION UTILITIES
# =============================================================================

def normalize_phone(phone_str: Any) -> Optional[str]:
    """
    Normalize phone number to 10 digits.
    Removes +91, 91, 0 prefix.
    """
    if pd.isna(phone_str) or phone_str is None:
        return None

    phone_str = str(phone_str).strip()
    if not phone_str:
        return None

    # Remove all non-digits
    digits = re.sub(r'\D', '', phone_str)

    # Remove country code prefixes
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    elif len(digits) == 13 and digits.startswith('091'):
        digits = digits[3:]

    # Return only if valid 10 digits
    if len(digits) == 10:
        return digits

    return None


def normalize_order_id(order_id: Any) -> Optional[str]:
    """
    Normalize order ID - strip # prefix and whitespace.
    """
    if pd.isna(order_id) or order_id is None:
        return None

    order_id = str(order_id).strip()

    # Remove # prefix if present
    if order_id.startswith('#'):
        order_id = order_id[1:]

    return order_id if order_id else None


def normalize_email(email: Any) -> Optional[str]:
    """Normalize email to lowercase."""
    if pd.isna(email) or email is None:
        return None

    email = str(email).strip().lower()
    if '@' not in email:
        return None

    return email


def safe_float(val: Any) -> Optional[float]:
    """Safely convert to float."""
    if pd.isna(val) or val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val: Any) -> Optional[int]:
    """Safely convert to int."""
    if pd.isna(val) or val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_str(val: Any) -> Optional[str]:
    """Safely convert to string."""
    if pd.isna(val) or val is None:
        return None
    return str(val).strip() or None


def parse_date(date_str: Any) -> Optional[str]:
    """Parse date string to ISO format."""
    if pd.isna(date_str) or date_str is None:
        return None

    date_str = str(date_str).strip()
    if not date_str:
        return None

    # Try common formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str[:19], fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    # Return original if parsing fails
    return date_str


# =============================================================================
# SHOPIFY CSV PARSER
# =============================================================================

def classify_payment_method(financial_status: str, payment_method: str) -> str:
    """
    Classify payment method into: prepaid, partial, cod
    Based on financial_status primarily.

    Note: cancelled/refunded are NOT payment modes.
    We determine the original payment method regardless of refund status.
    """
    financial_status = safe_str(financial_status) or ''
    financial_status = financial_status.lower()
    payment_method = safe_str(payment_method) or ''
    payment_method = payment_method.lower()

    # First check payment_method field for COD indicator
    if 'cod' in payment_method or 'cash' in payment_method:
        return 'cod'

    # Then use financial_status
    if financial_status == 'paid':
        return 'prepaid'
    elif financial_status == 'partially_paid':
        return 'partial'
    elif financial_status == 'pending':
        return 'cod'
    elif financial_status in ['voided', 'refunded', 'partially_refunded']:
        # For cancelled/refunded, determine original payment from payment_method field
        if 'razorpay' in payment_method or 'upi' in payment_method or 'card' in payment_method:
            return 'prepaid'
        else:
            # Default to cod if unclear
            return 'cod'
    else:
        # Fallback to payment method field
        if 'razorpay' in payment_method:
            return 'prepaid'
        else:
            return 'unknown'


def parse_shopify_csv(file_or_path) -> Dict[str, Any]:
    """
    Parse Shopify orders CSV.

    Handles multiple line items by:
    - Aggregating quantities
    - Taking first occurrence for customer details
    - Storing individual line items separately

    Returns dict with stats and any errors.
    """
    # Reset file pointer if it's a file-like object (Streamlit UploadedFile)
    if hasattr(file_or_path, 'seek'):
        file_or_path.seek(0)

    # Read CSV with encoding handling
    try:
        df = pd.read_csv(file_or_path, low_memory=False, encoding='utf-8-sig')
    except UnicodeDecodeError:
        # Reset file pointer again for retry
        if hasattr(file_or_path, 'seek'):
            file_or_path.seek(0)
        df = pd.read_csv(file_or_path, low_memory=False, encoding='latin-1')

    # Clean column names: strip whitespace and handle variations
    df.columns = df.columns.str.strip()
    batch_id = str(uuid.uuid4())[:8]

    # Column mapping (handle variations)
    col_map = {
        'order_id': 'Name',
        'shopify_id': 'Id',
        'email': 'Email',
        'phone': 'Phone',
        'billing_phone': 'Billing Phone',
        'billing_name': 'Billing Name',
        'shipping_name': 'Shipping Name',
        'shipping_city': 'Shipping City',
        'shipping_state': 'Shipping Province',
        'shipping_pincode': 'Shipping Zip',
        'subtotal': 'Subtotal',
        'total': 'Total',
        'discount_code': 'Discount Code',
        'discount_amount': 'Discount Amount',
        'refunded_amount': 'Refunded Amount',
        'financial_status': 'Financial Status',
        'fulfillment_status': 'Fulfillment Status',
        'payment_method_raw': 'Payment Method',
        'order_date': 'Created at',
        'cancelled_at': 'Cancelled at',
        'source': 'Source',
        'tags': 'Tags',
        'lineitem_name': 'Lineitem name',
        'lineitem_sku': 'Lineitem sku',
        'lineitem_quantity': 'Lineitem quantity',
        'lineitem_price': 'Lineitem price',
        'lineitem_discount': 'Lineitem discount',
    }

    # Verify required columns exist
    required_cols = ['Name', 'Total', 'Financial Status']
    missing_cols = []

    for col in required_cols:
        if col not in df.columns:
            missing_cols.append(col)

    if missing_cols:
        # Show first 10 columns to help debug
        available_cols = list(df.columns[:15])
        return {
            'success': False,
            'error': f"Missing required columns: {missing_cols}. Available columns: {available_cols}",
            'records_total': 0,
            'records_new': 0,
            'records_updated': 0,
            'records_failed': 0
        }

    conn = get_db_connection()
    cursor = conn.cursor()

    # Group by order_id to handle multiple line items
    df['_order_id_normalized'] = df[col_map['order_id']].apply(normalize_order_id)

    # Aggregate line items per order
    orders_data = {}
    line_items_data = []

    for _, row in df.iterrows():
        order_id = row['_order_id_normalized']
        if not order_id:
            continue

        # Line item data
        lineitem = {
            'order_id': order_id,
            'lineitem_name': safe_str(row.get(col_map['lineitem_name'])),
            'lineitem_sku': safe_str(row.get(col_map['lineitem_sku'])),
            'lineitem_quantity': safe_int(row.get(col_map['lineitem_quantity'])) or 1,
            'lineitem_price': safe_float(row.get(col_map['lineitem_price'])),
            'lineitem_discount': safe_float(row.get(col_map['lineitem_discount'])),
        }
        line_items_data.append(lineitem)

        # Order data (first occurrence wins for customer details)
        if order_id not in orders_data:
            orders_data[order_id] = {
                'order_id': order_id,
                'shopify_id': safe_str(row.get(col_map['shopify_id'])),
                'email': normalize_email(row.get(col_map['email'])),
                'phone': normalize_phone(row.get(col_map['phone'])),
                'billing_phone': normalize_phone(row.get(col_map['billing_phone'])),
                'billing_name': safe_str(row.get(col_map['billing_name'])),
                'shipping_name': safe_str(row.get(col_map['shipping_name'])),
                'shipping_city': safe_str(row.get(col_map['shipping_city'])),
                'shipping_state': safe_str(row.get(col_map['shipping_state'])),
                'shipping_pincode': safe_str(row.get(col_map['shipping_pincode'])),
                'subtotal': safe_float(row.get(col_map['subtotal'])),
                'total': safe_float(row.get(col_map['total'])),
                'discount_code': safe_str(row.get(col_map['discount_code'])),
                'discount_amount': safe_float(row.get(col_map['discount_amount'])),
                'refunded_amount': safe_float(row.get(col_map['refunded_amount'])),
                'financial_status': safe_str(row.get(col_map['financial_status'])),
                'fulfillment_status': safe_str(row.get(col_map['fulfillment_status'])),
                'payment_method_raw': safe_str(row.get(col_map['payment_method_raw'])),
                'order_date': parse_date(row.get(col_map['order_date'])),
                'cancelled_at': parse_date(row.get(col_map['cancelled_at'])),
                'source': safe_str(row.get(col_map['source'])),
                'tags': safe_str(row.get(col_map['tags'])),
                'lineitem_names': [],
                'total_quantity': 0,
            }

        # Aggregate line items
        orders_data[order_id]['lineitem_names'].append(lineitem['lineitem_name'] or '')
        orders_data[order_id]['total_quantity'] += lineitem['lineitem_quantity'] or 0

    # Process aggregated orders
    records_new = 0
    records_updated = 0
    records_failed = 0

    for order_id, order in orders_data.items():
        # Finalize aggregated fields
        order['lineitem_names'] = ', '.join(filter(None, order['lineitem_names']))
        order['payment_method'] = classify_payment_method(
            order['financial_status'],
            order['payment_method_raw']
        )

        try:
            # Check if order exists
            cursor.execute("SELECT id FROM raw_shopify_orders WHERE order_id = ?", (order_id,))
            existing = cursor.fetchone()

            if existing:
                # Update existing
                cursor.execute("""
                    UPDATE raw_shopify_orders SET
                        shopify_id = ?, email = ?, phone = ?, billing_phone = ?,
                        billing_name = ?, shipping_name = ?, shipping_city = ?,
                        shipping_state = ?, shipping_pincode = ?, subtotal = ?,
                        total = ?, discount_code = ?, discount_amount = ?,
                        refunded_amount = ?, financial_status = ?, fulfillment_status = ?,
                        payment_method_raw = ?, payment_method = ?, lineitem_names = ?,
                        total_quantity = ?, order_date = ?, cancelled_at = ?,
                        source = ?, tags = ?, uploaded_at = CURRENT_TIMESTAMP,
                        import_batch_id = ?
                    WHERE order_id = ?
                """, (
                    order['shopify_id'], order['email'], order['phone'], order['billing_phone'],
                    order['billing_name'], order['shipping_name'], order['shipping_city'],
                    order['shipping_state'], order['shipping_pincode'], order['subtotal'],
                    order['total'], order['discount_code'], order['discount_amount'],
                    order['refunded_amount'], order['financial_status'], order['fulfillment_status'],
                    order['payment_method_raw'], order['payment_method'], order['lineitem_names'],
                    order['total_quantity'], order['order_date'], order['cancelled_at'],
                    order['source'], order['tags'], batch_id, order_id
                ))
                records_updated += 1
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO raw_shopify_orders (
                        order_id, shopify_id, email, phone, billing_phone,
                        billing_name, shipping_name, shipping_city, shipping_state,
                        shipping_pincode, subtotal, total, discount_code, discount_amount,
                        refunded_amount, financial_status, fulfillment_status,
                        payment_method_raw, payment_method, lineitem_names, total_quantity,
                        order_date, cancelled_at, source, tags, import_batch_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order['order_id'], order['shopify_id'], order['email'], order['phone'],
                    order['billing_phone'], order['billing_name'], order['shipping_name'],
                    order['shipping_city'], order['shipping_state'], order['shipping_pincode'],
                    order['subtotal'], order['total'], order['discount_code'], order['discount_amount'],
                    order['refunded_amount'], order['financial_status'], order['fulfillment_status'],
                    order['payment_method_raw'], order['payment_method'], order['lineitem_names'],
                    order['total_quantity'], order['order_date'], order['cancelled_at'],
                    order['source'], order['tags'], batch_id
                ))
                records_new += 1

        except Exception as e:
            records_failed += 1
            print(f"Error processing order {order_id}: {e}")

    # Insert line items (clear existing first for this batch)
    order_ids = list(orders_data.keys())
    if order_ids:
        placeholders = ','.join(['?' for _ in order_ids])
        cursor.execute(f"DELETE FROM order_line_items WHERE order_id IN ({placeholders})", order_ids)

        for item in line_items_data:
            if item['order_id'] in orders_data:
                cursor.execute("""
                    INSERT INTO order_line_items (
                        order_id, lineitem_name, lineitem_sku,
                        lineitem_quantity, lineitem_price, lineitem_discount
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    item['order_id'], item['lineitem_name'], item['lineitem_sku'],
                    item['lineitem_quantity'], item['lineitem_price'], item['lineitem_discount']
                ))

    # Log import
    cursor.execute("""
        INSERT INTO import_log (batch_id, source, file_name, records_total, records_new, records_updated, records_failed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (batch_id, 'shopify', 'uploaded_file', len(orders_data), records_new, records_updated, records_failed))

    conn.commit()
    conn.close()

    return {
        'success': True,
        'batch_id': batch_id,
        'records_total': len(orders_data),
        'records_new': records_new,
        'records_updated': records_updated,
        'records_failed': records_failed,
        'line_items_count': len(line_items_data)
    }


# =============================================================================
# PROZO CSV PARSER
# =============================================================================

def map_prozo_status(status_raw: str) -> str:
    """
    Map Prozo status to normalized category.
    Returns: delivered, in_transit, rto, cancelled, or original if unknown
    """
    status_mapping = get_delivery_status_mapping()

    status_raw = safe_str(status_raw) or ''
    status_upper = status_raw.upper().strip()

    if status_upper in status_mapping:
        return status_mapping[status_upper]['normalized']

    # Handle variations
    if 'DELIVER' in status_upper and 'RTO' not in status_upper:
        return 'delivered'
    elif 'RTO' in status_upper:
        return 'rto'
    elif 'CANCEL' in status_upper:
        return 'cancelled'
    elif 'TRANSIT' in status_upper or 'DELAY' in status_upper or 'PICKUP' in status_upper:
        return 'in_transit'

    return 'unknown'


def parse_prozo_csv(file_or_path) -> Dict[str, Any]:
    """
    Parse Prozo MIS report CSV.

    Returns dict with stats and any errors.
    """
    # Reset file pointer if it's a file-like object (Streamlit UploadedFile)
    if hasattr(file_or_path, 'seek'):
        file_or_path.seek(0)

    # Read CSV with encoding handling
    try:
        df = pd.read_csv(file_or_path, low_memory=False, encoding='utf-8-sig')
    except UnicodeDecodeError:
        # Reset file pointer again for retry
        if hasattr(file_or_path, 'seek'):
            file_or_path.seek(0)
        df = pd.read_csv(file_or_path, low_memory=False, encoding='latin-1')

    # Clean column names
    df.columns = df.columns.str.strip()
    batch_id = str(uuid.uuid4())[:8]

    # Column mapping
    col_map = {
        'awb': 'AWB',
        'order_id': 'channelOrderName',  # This is the match key
        'status_raw': 'Status',
        'drop_name': 'Drop Name',
        'drop_phone': 'Drop Phone',
        'drop_email': 'Drop Email',
        'drop_city': 'Drop City',
        'drop_state': 'Drop State',
        'drop_pincode': 'Drop Pincode',
        'courier_partner': 'Courier Partner',
        'payment_mode': 'Payment Mode',
        'order_created_at': 'Created at',
        'pickup_date': 'Pickup Date',
        'delivery_date': 'Delivery Date',
        'rto_delivery_date': 'RTO Delivery Date',
        'min_tat': 'Min Tat',
        'max_tat': 'Max Tat',
        'ndr_status': 'NDR Status',
        'total_attempts': 'Total Attempts',
        'latest_remark': 'Latest Remark',
        'merchant_price': 'Merchant Price',
        'merchant_price_rto': 'Merchant Price RTO',
    }

    # Check required columns
    required = ['AWB', 'Status']
    missing = [c for c in required if c not in df.columns]

    # Try alternate column names for order_id
    order_id_col = None
    for col_name in ['channelOrderName', 'Channel Order Name', 'Reference Number', 'Order ID']:
        if col_name in df.columns:
            order_id_col = col_name
            col_map['order_id'] = col_name
            break

    if not order_id_col:
        missing.append('channelOrderName (or Reference Number)')

    if missing:
        return {
            'success': False,
            'error': f"Missing required columns: {missing}",
            'records_total': 0,
            'records_new': 0,
            'records_updated': 0,
            'records_failed': 0
        }

    conn = get_db_connection()
    cursor = conn.cursor()

    records_new = 0
    records_updated = 0
    records_failed = 0

    for _, row in df.iterrows():
        awb = safe_str(row.get(col_map['awb']))
        if not awb:
            records_failed += 1
            continue

        order_id = normalize_order_id(row.get(col_map['order_id']))
        status_raw = safe_str(row.get(col_map['status_raw']))
        status = map_prozo_status(status_raw)

        order_data = {
            'awb': awb,
            'order_id': order_id,
            'status_raw': status_raw,
            'status': status,
            'drop_name': safe_str(row.get(col_map['drop_name'])),
            'drop_phone': normalize_phone(row.get(col_map['drop_phone'])),
            'drop_email': normalize_email(row.get(col_map['drop_email'])),
            'drop_city': safe_str(row.get(col_map['drop_city'])),
            'drop_state': safe_str(row.get(col_map['drop_state'])),
            'drop_pincode': safe_str(row.get(col_map['drop_pincode'])),
            'courier_partner': safe_str(row.get(col_map['courier_partner'])),
            'payment_mode': safe_str(row.get(col_map['payment_mode'])),
            'order_created_at': parse_date(row.get(col_map['order_created_at'])),
            'pickup_date': parse_date(row.get(col_map['pickup_date'])),
            'delivery_date': parse_date(row.get(col_map['delivery_date'])),
            'rto_delivery_date': parse_date(row.get(col_map['rto_delivery_date'])),
            'min_tat': safe_int(row.get(col_map['min_tat'])),
            'max_tat': safe_int(row.get(col_map['max_tat'])),
            'ndr_status': safe_str(row.get(col_map['ndr_status'])),
            'total_attempts': safe_int(row.get(col_map['total_attempts'])),
            'latest_remark': safe_str(row.get(col_map['latest_remark'])),
            'merchant_price': safe_float(row.get(col_map['merchant_price'])),
            'merchant_price_rto': safe_float(row.get(col_map['merchant_price_rto'])),
        }

        try:
            # Check if AWB exists
            cursor.execute("SELECT id FROM raw_prozo_orders WHERE awb = ?", (awb,))
            existing = cursor.fetchone()

            if existing:
                # Update existing (status may have changed)
                cursor.execute("""
                    UPDATE raw_prozo_orders SET
                        order_id = ?, status_raw = ?, status = ?,
                        drop_name = ?, drop_phone = ?, drop_email = ?,
                        drop_city = ?, drop_state = ?, drop_pincode = ?,
                        courier_partner = ?, payment_mode = ?, order_created_at = ?,
                        pickup_date = ?, delivery_date = ?, rto_delivery_date = ?,
                        min_tat = ?, max_tat = ?, ndr_status = ?,
                        total_attempts = ?, latest_remark = ?,
                        merchant_price = ?, merchant_price_rto = ?,
                        uploaded_at = CURRENT_TIMESTAMP, import_batch_id = ?
                    WHERE awb = ?
                """, (
                    order_data['order_id'], order_data['status_raw'], order_data['status'],
                    order_data['drop_name'], order_data['drop_phone'], order_data['drop_email'],
                    order_data['drop_city'], order_data['drop_state'], order_data['drop_pincode'],
                    order_data['courier_partner'], order_data['payment_mode'], order_data['order_created_at'],
                    order_data['pickup_date'], order_data['delivery_date'], order_data['rto_delivery_date'],
                    order_data['min_tat'], order_data['max_tat'], order_data['ndr_status'],
                    order_data['total_attempts'], order_data['latest_remark'],
                    order_data['merchant_price'], order_data['merchant_price_rto'],
                    batch_id, awb
                ))
                records_updated += 1
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO raw_prozo_orders (
                        awb, order_id, status_raw, status,
                        drop_name, drop_phone, drop_email,
                        drop_city, drop_state, drop_pincode,
                        courier_partner, payment_mode, order_created_at,
                        pickup_date, delivery_date, rto_delivery_date,
                        min_tat, max_tat, ndr_status,
                        total_attempts, latest_remark,
                        merchant_price, merchant_price_rto, import_batch_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order_data['awb'], order_data['order_id'], order_data['status_raw'], order_data['status'],
                    order_data['drop_name'], order_data['drop_phone'], order_data['drop_email'],
                    order_data['drop_city'], order_data['drop_state'], order_data['drop_pincode'],
                    order_data['courier_partner'], order_data['payment_mode'], order_data['order_created_at'],
                    order_data['pickup_date'], order_data['delivery_date'], order_data['rto_delivery_date'],
                    order_data['min_tat'], order_data['max_tat'], order_data['ndr_status'],
                    order_data['total_attempts'], order_data['latest_remark'],
                    order_data['merchant_price'], order_data['merchant_price_rto'], batch_id
                ))
                records_new += 1

        except Exception as e:
            records_failed += 1
            print(f"Error processing AWB {awb}: {e}")

    # Log import
    cursor.execute("""
        INSERT INTO import_log (batch_id, source, file_name, records_total, records_new, records_updated, records_failed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (batch_id, 'prozo', 'uploaded_file', len(df), records_new, records_updated, records_failed))

    conn.commit()
    conn.close()

    return {
        'success': True,
        'batch_id': batch_id,
        'records_total': len(df),
        'records_new': records_new,
        'records_updated': records_updated,
        'records_failed': records_failed
    }
