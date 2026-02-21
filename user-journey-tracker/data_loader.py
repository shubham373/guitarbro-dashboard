"""
Data Loader for User Journey Tracker

Handles CSV parsing for:
- Shopify Orders (with deduplication and field extraction)
- Zoom Attendance (with special format handling and deduplication)
"""

import pandas as pd
import re
import sqlite3
from typing import Tuple, Optional
from schema import get_db_connection


def normalize_phone(phone_str: str) -> Optional[str]:
    """
    Remove all non-digits, strip +91/0 prefix, return 10 digits or None.
    Handles: +91, 0, spaces, dashes, parentheses.
    """
    if not phone_str or str(phone_str).strip() == '' or pd.isna(phone_str):
        return None

    digits = re.sub(r'\D', '', str(phone_str).strip())

    # Handle various prefixes
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    elif len(digits) == 13 and digits.startswith('091'):
        digits = digits[3:]

    if len(digits) == 10:
        return digits
    return None


def normalize_email(email_str: str) -> Optional[str]:
    """Normalize email to lowercase, return None if invalid."""
    if not email_str or str(email_str).strip() == '' or pd.isna(email_str):
        return None

    email = str(email_str).strip().lower()
    if '@' not in email:
        return None
    return email


def extract_from_note_attributes(note_attrs: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract razorpay_order_id and payment_type from Note Attributes string.

    Returns:
        Tuple of (razorpay_order_id, payment_type)
    """
    razorpay_order_id = None
    payment_type = None

    if not note_attrs or pd.isna(note_attrs):
        return None, None

    note_str = str(note_attrs)

    # Extract razorpay_order_id
    razorpay_match = re.search(r'razorpay_order_id:\s*(order_\w+)', note_str, re.IGNORECASE)
    if razorpay_match:
        razorpay_order_id = razorpay_match.group(1)

    # Extract payment_method/payment_type
    payment_match = re.search(r'payment_method:\s*(\w+)', note_str, re.IGNORECASE)
    if payment_match:
        payment_type = payment_match.group(1).lower()

    return razorpay_order_id, payment_type


def extract_rto_risk(tags: str) -> Optional[str]:
    """Extract RTO risk level from tags string."""
    if not tags or pd.isna(tags):
        return None

    tags_str = str(tags).lower()

    # Look for "RTO Risk - low" or "RTO Risk - medium"
    rto_match = re.search(r'rto\s*risk\s*[-:]\s*(low|medium|high)', tags_str, re.IGNORECASE)
    if rto_match:
        return rto_match.group(1).lower()

    return None


def classify_payment_method(payment_method: str) -> str:
    """
    Classify payment method into simplified categories:
    - prepaid, cod, snapmint, manual
    """
    if not payment_method or pd.isna(payment_method):
        return 'unknown'

    pm = str(payment_method).lower()

    if 'razorpay' in pm:
        return 'prepaid'
    elif 'cash on delivery' in pm or 'cod' in pm:
        return 'cod'
    elif 'snapmint' in pm:
        return 'snapmint'
    elif 'manual' in pm:
        return 'manual'
    else:
        return 'other'


def load_shopify_csv(file_or_path) -> Tuple[int, int, int]:
    """
    Load Shopify orders CSV into database.

    Args:
        file_or_path: File object or path to CSV

    Returns:
        Tuple of (total_rows, unique_orders, duplicates_removed)
    """
    # Read CSV
    df = pd.read_csv(file_or_path, low_memory=False)
    total_rows = len(df)

    # CRITICAL DEDUP: Group by "Name" column (order number), keep first row
    # First row has the primary line item; multi-row orders are due to gift wraps, etc.
    df_deduped = df.drop_duplicates(subset=['Name'], keep='first')
    unique_orders = len(df_deduped)
    duplicates_removed = total_rows - unique_orders

    conn = get_db_connection()
    cursor = conn.cursor()

    for _, row in df_deduped.iterrows():
        # Extract from Note Attributes
        razorpay_order_id, payment_type = extract_from_note_attributes(
            row.get('Note Attributes', '')
        )

        # Extract RTO risk from Tags
        rto_risk = extract_rto_risk(row.get('Tags', ''))

        # Classify payment method
        payment_method_raw = row.get('Payment Method', '')
        payment_method_classified = classify_payment_method(payment_method_raw)

        # Normalize phones
        phone = normalize_phone(row.get('Phone', ''))
        billing_phone = normalize_phone(row.get('Billing Phone', ''))

        # Normalize email
        email = normalize_email(row.get('Email', ''))

        # Get numeric values safely
        def safe_float(val):
            try:
                if pd.isna(val):
                    return None
                return float(val)
            except (ValueError, TypeError):
                return None

        # Insert or replace
        cursor.execute("""
            INSERT OR REPLACE INTO raw_shopify_orders (
                order_number, order_id, email, phone, billing_phone,
                billing_name, shipping_name, billing_city, shipping_city,
                billing_zip, shipping_zip, billing_province, shipping_province,
                total, subtotal, financial_status, fulfillment_status,
                payment_method, lineitem_name, discount_code, discount_amount,
                created_at, cancelled_at, refunded_amount, tags, note_attributes,
                razorpay_order_id, payment_type, rto_risk, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row.get('Name'),  # order_number like "#14882"
            row.get('Id'),
            email,
            phone,
            billing_phone,
            row.get('Billing Name'),
            row.get('Shipping Name'),
            row.get('Billing City'),
            row.get('Shipping City'),
            row.get('Billing Zip'),
            row.get('Shipping Zip'),
            row.get('Billing Province'),
            row.get('Shipping Province'),
            safe_float(row.get('Total')),
            safe_float(row.get('Subtotal')),
            row.get('Financial Status'),
            row.get('Fulfillment Status'),
            payment_method_classified,
            row.get('Lineitem name'),
            row.get('Discount Code'),
            safe_float(row.get('Discount Amount')),
            row.get('Created at'),
            row.get('Cancelled at'),
            safe_float(row.get('Refunded Amount')),
            row.get('Tags'),
            row.get('Note Attributes'),
            razorpay_order_id,
            payment_type,
            rto_risk,
            row.get('Source')
        ))

    conn.commit()
    conn.close()

    return total_rows, unique_orders, duplicates_removed


def load_zoom_csv(file_or_path) -> Tuple[int, int, int, str, str]:
    """
    Load Zoom attendance CSV into database.

    Zoom CSV has a special format:
    - Row 0: Meeting metadata headers
    - Row 1: Meeting metadata values
    - Row 2: Empty
    - Row 3: Participant headers
    - Row 4+: Participant data

    Args:
        file_or_path: File object or path to CSV

    Returns:
        Tuple of (total_participants, external_participants, internal_excluded, meeting_topic, meeting_date)
    """
    # First read the meeting metadata (rows 0-1)
    df_meta = pd.read_csv(file_or_path, nrows=2, header=None)

    # Extract meeting info from row 1
    headers = df_meta.iloc[0].tolist()
    values = df_meta.iloc[1].tolist()

    meeting_info = dict(zip(headers, values))
    meeting_id = str(meeting_info.get('Meeting ID', meeting_info.get('ID', '')))
    meeting_topic = meeting_info.get('Topic', 'Unknown')

    # Extract meeting date from "Start time" column
    start_time = meeting_info.get('Start time', '')
    meeting_date = str(start_time).split(' ')[0] if start_time else ''

    # Reset file position and read participant data (skip first 3 rows)
    if hasattr(file_or_path, 'seek'):
        file_or_path.seek(0)

    df_participants = pd.read_csv(file_or_path, skiprows=3)

    conn = get_db_connection()
    cursor = conn.cursor()

    total_participants = 0
    internal_count = 0

    # Store all raw attendance records
    for _, row in df_participants.iterrows():
        # Handle column name variations
        name = row.get('Name (original name)', row.get('Name', ''))
        email = normalize_email(row.get('Email', ''))

        # Parse duration
        duration_str = row.get('Duration (minutes)', row.get('Duration', 0))
        try:
            duration_minutes = int(float(str(duration_str).replace(' mins', '').replace(' min', '')))
        except (ValueError, TypeError):
            duration_minutes = 0

        is_guest = row.get('Guest', 'No')

        # Check if internal (topbeat.in domain)
        is_internal = 1 if email and 'topbeat.in' in email else 0
        if is_internal:
            internal_count += 1

        cursor.execute("""
            INSERT INTO raw_zoom_attendance (
                meeting_id, meeting_topic, meeting_date, participant_name,
                email, join_time, leave_time, duration_minutes, is_guest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meeting_id,
            meeting_topic,
            meeting_date,
            name,
            email,
            row.get('Join time', ''),
            row.get('Leave time', ''),
            duration_minutes,
            is_guest
        ))
        total_participants += 1

    conn.commit()

    # Now create deduped view
    external_count = dedupe_zoom_participants(meeting_id, meeting_topic, meeting_date)

    conn.close()

    return total_participants, external_count, internal_count, meeting_topic, meeting_date


def dedupe_zoom_participants(meeting_id: str, meeting_topic: str, meeting_date: str) -> int:
    """
    Create deduped participant records by grouping on (meeting_id, email).

    Returns:
        Number of external (non-internal) participants after dedup
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Clear existing deduped records for this meeting
    cursor.execute("DELETE FROM zoom_participants_deduped WHERE meeting_id = ?", (meeting_id,))

    # Aggregate by email
    cursor.execute("""
        INSERT INTO zoom_participants_deduped (
            meeting_id, meeting_topic, meeting_date, participant_name, email,
            total_duration_minutes, first_join, last_leave, session_count, is_internal
        )
        SELECT
            meeting_id,
            meeting_topic,
            meeting_date,
            participant_name,
            email,
            SUM(duration_minutes) as total_duration_minutes,
            MIN(join_time) as first_join,
            MAX(leave_time) as last_leave,
            COUNT(*) as session_count,
            CASE WHEN email LIKE '%topbeat.in%' THEN 1 ELSE 0 END as is_internal
        FROM raw_zoom_attendance
        WHERE meeting_id = ? AND email IS NOT NULL AND email != ''
        GROUP BY meeting_id, email
    """, (meeting_id,))

    conn.commit()

    # Count external participants
    cursor.execute("""
        SELECT COUNT(*) FROM zoom_participants_deduped
        WHERE meeting_id = ? AND is_internal = 0
    """, (meeting_id,))
    external_count = cursor.fetchone()[0]

    conn.close()

    return external_count


def get_shopify_stats() -> dict:
    """Get statistics about loaded Shopify data."""
    conn = get_db_connection()
    cursor = conn.cursor()

    stats = {}

    # Total orders
    cursor.execute("SELECT COUNT(*) FROM raw_shopify_orders")
    stats['total_orders'] = cursor.fetchone()[0]

    # COD vs Prepaid
    cursor.execute("SELECT COUNT(*) FROM raw_shopify_orders WHERE payment_method = 'cod'")
    stats['cod_orders'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM raw_shopify_orders WHERE payment_method = 'prepaid'")
    stats['prepaid_orders'] = cursor.fetchone()[0]

    # Fulfilled
    cursor.execute("SELECT COUNT(*) FROM raw_shopify_orders WHERE fulfillment_status = 'fulfilled'")
    stats['fulfilled_orders'] = cursor.fetchone()[0]

    # Total value
    cursor.execute("SELECT SUM(total) FROM raw_shopify_orders")
    result = cursor.fetchone()[0]
    stats['total_value'] = result if result else 0

    conn.close()
    return stats


def get_zoom_stats() -> dict:
    """Get statistics about loaded Zoom data."""
    conn = get_db_connection()
    cursor = conn.cursor()

    stats = {}

    # Total raw records
    cursor.execute("SELECT COUNT(*) FROM raw_zoom_attendance")
    stats['total_raw_records'] = cursor.fetchone()[0]

    # External participants (deduped)
    cursor.execute("SELECT COUNT(*) FROM zoom_participants_deduped WHERE is_internal = 0")
    stats['external_participants'] = cursor.fetchone()[0]

    # Internal participants
    cursor.execute("SELECT COUNT(*) FROM zoom_participants_deduped WHERE is_internal = 1")
    stats['internal_participants'] = cursor.fetchone()[0]

    # Unique meetings
    cursor.execute("SELECT COUNT(DISTINCT meeting_id) FROM zoom_participants_deduped")
    stats['unique_meetings'] = cursor.fetchone()[0]

    conn.close()
    return stats


def get_shopify_orders_df() -> pd.DataFrame:
    """Get all Shopify orders as a DataFrame."""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM raw_shopify_orders", conn)
    conn.close()
    return df


def get_zoom_participants_df(external_only: bool = True) -> pd.DataFrame:
    """Get Zoom participants (deduped) as a DataFrame."""
    conn = get_db_connection()

    query = "SELECT * FROM zoom_participants_deduped"
    if external_only:
        query += " WHERE is_internal = 0"

    df = pd.read_sql_query(query, conn)
    conn.close()
    return df
