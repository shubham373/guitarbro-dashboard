"""
User Journey Tracker Module

Tracks customer journeys from order to upsell purchase by matching
Shopify orders with Zoom attendance data.
"""

import streamlit as st
import pandas as pd
import sqlite3
import os
import re
from difflib import SequenceMatcher
from typing import Tuple, Optional, Dict, Any, List

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================
DB_PATH = "data/journey.db"


def get_journey_db():
    """Get SQLite connection for journey database."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_journey_db():
    """Initialize all database tables for user journey tracking."""
    conn = get_journey_db()
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

    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_journey_shopify_email ON raw_shopify_orders(email)",
        "CREATE INDEX IF NOT EXISTS idx_journey_shopify_phone ON raw_shopify_orders(phone)",
        "CREATE INDEX IF NOT EXISTS idx_journey_zoom_email ON raw_zoom_attendance(email)",
        "CREATE INDEX IF NOT EXISTS idx_journey_zoom_deduped_email ON zoom_participants_deduped(email)",
        "CREATE INDEX IF NOT EXISTS idx_journey_unified_email ON unified_users(primary_email)",
    ]

    for idx in indexes:
        cursor.execute(idx)

    conn.commit()
    conn.close()


# =============================================================================
# NORMALIZATION FUNCTIONS
# =============================================================================
def normalize_phone(phone_str: str) -> Optional[str]:
    """Remove all non-digits, strip +91/0 prefix, return 10 digits or None."""
    if not phone_str or str(phone_str).strip() == '' or pd.isna(phone_str):
        return None

    digits = re.sub(r'\D', '', str(phone_str).strip())

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


def normalize_name(name: str) -> Optional[str]:
    """Normalize name for matching."""
    if not name or str(name).strip() == '':
        return None

    name = str(name).lower().strip()
    prefixes = ['mr', 'mrs', 'ms', 'dr', 'shri', 'smt', 'prof']
    for prefix in prefixes:
        name = re.sub(rf'^{prefix}\.?\s+', '', name)
    name = re.sub(r'[^a-z\s]', '', name)
    name = ' '.join(name.split())
    return name if name else None


# =============================================================================
# DATA EXTRACTION FUNCTIONS
# =============================================================================
def extract_from_note_attributes(note_attrs: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract razorpay_order_id and payment_type from Note Attributes."""
    razorpay_order_id = None
    payment_type = None

    if not note_attrs or pd.isna(note_attrs):
        return None, None

    note_str = str(note_attrs)

    razorpay_match = re.search(r'razorpay_order_id:\s*(order_\w+)', note_str, re.IGNORECASE)
    if razorpay_match:
        razorpay_order_id = razorpay_match.group(1)

    payment_match = re.search(r'payment_method:\s*(\w+)', note_str, re.IGNORECASE)
    if payment_match:
        payment_type = payment_match.group(1).lower()

    return razorpay_order_id, payment_type


def extract_rto_risk(tags: str) -> Optional[str]:
    """Extract RTO risk level from tags string."""
    if not tags or pd.isna(tags):
        return None

    tags_str = str(tags).lower()
    rto_match = re.search(r'rto\s*risk\s*[-:]\s*(low|medium|high)', tags_str, re.IGNORECASE)
    if rto_match:
        return rto_match.group(1).lower()
    return None


def classify_payment_method(payment_method: str) -> str:
    """Classify payment method into simplified categories."""
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


# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================
def load_shopify_csv(file_or_path) -> Tuple[int, int, int]:
    """Load Shopify orders CSV into database."""
    df = pd.read_csv(file_or_path, low_memory=False)
    total_rows = len(df)

    df_deduped = df.drop_duplicates(subset=['Name'], keep='first')
    unique_orders = len(df_deduped)
    duplicates_removed = total_rows - unique_orders

    conn = get_journey_db()
    cursor = conn.cursor()

    for _, row in df_deduped.iterrows():
        razorpay_order_id, payment_type = extract_from_note_attributes(
            row.get('Note Attributes', '')
        )
        rto_risk = extract_rto_risk(row.get('Tags', ''))
        payment_method_raw = row.get('Payment Method', '')
        payment_method_classified = classify_payment_method(payment_method_raw)
        phone = normalize_phone(row.get('Phone', ''))
        billing_phone = normalize_phone(row.get('Billing Phone', ''))
        email = normalize_email(row.get('Email', ''))

        def safe_float(val):
            try:
                if pd.isna(val):
                    return None
                return float(val)
            except (ValueError, TypeError):
                return None

        try:
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
                row.get('Name'),
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
        except Exception:
            pass

    conn.commit()
    conn.close()
    return total_rows, unique_orders, duplicates_removed


def load_zoom_csv(file_or_path) -> Tuple[int, int, int, str, str]:
    """Load Zoom attendance CSV into database."""
    df_meta = pd.read_csv(file_or_path, nrows=2, header=None)
    headers = df_meta.iloc[0].tolist()
    values = df_meta.iloc[1].tolist()
    meeting_info = dict(zip(headers, values))
    meeting_id = str(meeting_info.get('Meeting ID', meeting_info.get('ID', '')))
    meeting_topic = meeting_info.get('Topic', 'Unknown')
    start_time = meeting_info.get('Start time', '')
    meeting_date = str(start_time).split(' ')[0] if start_time else ''

    if hasattr(file_or_path, 'seek'):
        file_or_path.seek(0)

    df_participants = pd.read_csv(file_or_path, skiprows=3)

    conn = get_journey_db()
    cursor = conn.cursor()

    total_participants = 0
    internal_count = 0

    for _, row in df_participants.iterrows():
        name = row.get('Name (original name)', row.get('Name', ''))
        email = normalize_email(row.get('Email', ''))
        duration_str = row.get('Duration (minutes)', row.get('Duration', 0))
        try:
            duration_minutes = int(float(str(duration_str).replace(' mins', '').replace(' min', '')))
        except (ValueError, TypeError):
            duration_minutes = 0

        is_guest = row.get('Guest', 'No')
        is_internal = 1 if email and 'topbeat.in' in email else 0
        if is_internal:
            internal_count += 1

        cursor.execute("""
            INSERT INTO raw_zoom_attendance (
                meeting_id, meeting_topic, meeting_date, participant_name,
                email, join_time, leave_time, duration_minutes, is_guest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meeting_id, meeting_topic, meeting_date, name, email,
            row.get('Join time', ''), row.get('Leave time', ''),
            duration_minutes, is_guest
        ))
        total_participants += 1

    conn.commit()

    # Dedupe participants
    cursor.execute("DELETE FROM zoom_participants_deduped WHERE meeting_id = ?", (meeting_id,))
    cursor.execute("""
        INSERT INTO zoom_participants_deduped (
            meeting_id, meeting_topic, meeting_date, participant_name, email,
            total_duration_minutes, first_join, last_leave, session_count, is_internal
        )
        SELECT
            meeting_id, meeting_topic, meeting_date, participant_name, email,
            SUM(duration_minutes), MIN(join_time), MAX(leave_time), COUNT(*),
            CASE WHEN email LIKE '%topbeat.in%' THEN 1 ELSE 0 END
        FROM raw_zoom_attendance
        WHERE meeting_id = ? AND email IS NOT NULL AND email != ''
        GROUP BY meeting_id, email
    """, (meeting_id,))
    conn.commit()

    cursor.execute("""
        SELECT COUNT(*) FROM zoom_participants_deduped
        WHERE meeting_id = ? AND is_internal = 0
    """, (meeting_id,))
    external_count = cursor.fetchone()[0]

    conn.close()
    return total_participants, external_count, internal_count, meeting_topic, meeting_date


# =============================================================================
# MATCHING FUNCTIONS
# =============================================================================
def email_fuzzy_match(email1: str, email2: str, threshold: float = 0.85) -> Tuple[bool, float]:
    """Fuzzy match two emails with SequenceMatcher."""
    if not email1 or not email2:
        return False, 0.0

    e1 = normalize_email(email1)
    e2 = normalize_email(email2)
    if not e1 or not e2:
        return False, 0.0

    local1 = e1.split('@')[0]
    local2 = e2.split('@')[0]
    ratio = SequenceMatcher(None, local1, local2).ratio()
    return ratio >= threshold, ratio


def name_fuzzy_match(name1: str, name2: str, threshold: float = 0.75) -> Tuple[bool, float]:
    """Fuzzy match two names with SequenceMatcher."""
    if not name1 or not name2:
        return False, 0.0

    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if not n1 or not n2:
        return False, 0.0

    ratio = SequenceMatcher(None, n1, n2).ratio()
    if ratio >= threshold:
        return True, ratio

    parts1 = n1.split()
    parts2 = n2.split()
    if len(parts1) >= 2 and len(parts2) >= 2:
        reversed1 = ' '.join(reversed(parts1))
        ratio_reversed = SequenceMatcher(None, reversed1, n2).ratio()
        if ratio_reversed >= threshold:
            return True, ratio_reversed

    return False, ratio


def find_matching_order(zoom_email: str, zoom_name: str) -> Dict[str, Any]:
    """Find matching Shopify order using waterfall matching."""
    conn = get_journey_db()
    cursor = conn.cursor()

    result = {
        'matched': False, 'order_number': None, 'confidence': 0.0,
        'match_method': 'none', 'order_data': None
    }

    zoom_email_normalized = normalize_email(zoom_email)
    zoom_name_normalized = normalize_name(zoom_name)

    # Step 1: Exact email match
    if zoom_email_normalized:
        cursor.execute("""
            SELECT * FROM raw_shopify_orders WHERE email = ?
            ORDER BY created_at DESC LIMIT 1
        """, (zoom_email_normalized,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return {'matched': True, 'order_number': row['order_number'],
                    'confidence': 1.0, 'match_method': 'exact_email', 'order_data': dict(row)}

    # Step 2: Fuzzy email match
    if zoom_email_normalized:
        cursor.execute("SELECT DISTINCT email FROM raw_shopify_orders WHERE email IS NOT NULL")
        shopify_emails = [r['email'] for r in cursor.fetchall()]
        best_match, best_conf = None, 0.0
        for se in shopify_emails:
            is_match, conf = email_fuzzy_match(zoom_email_normalized, se)
            if is_match and conf > best_conf:
                best_match, best_conf = se, conf
        if best_match and best_conf >= 0.85:
            cursor.execute("SELECT * FROM raw_shopify_orders WHERE email = ? ORDER BY created_at DESC LIMIT 1", (best_match,))
            row = cursor.fetchone()
            if row:
                conn.close()
                return {'matched': True, 'order_number': row['order_number'],
                        'confidence': best_conf, 'match_method': 'fuzzy_email', 'order_data': dict(row)}

    # Step 3: Exact name match
    if zoom_name_normalized:
        cursor.execute("""
            SELECT * FROM raw_shopify_orders
            WHERE LOWER(billing_name) = ? OR LOWER(shipping_name) = ?
            ORDER BY created_at DESC LIMIT 1
        """, (zoom_name_normalized, zoom_name_normalized))
        row = cursor.fetchone()
        if row:
            conn.close()
            return {'matched': True, 'order_number': row['order_number'],
                    'confidence': 0.7, 'match_method': 'exact_name', 'order_data': dict(row)}

    # Step 4: Fuzzy name match
    if zoom_name_normalized:
        cursor.execute("""
            SELECT DISTINCT billing_name, shipping_name, order_number
            FROM raw_shopify_orders WHERE billing_name IS NOT NULL OR shipping_name IS NOT NULL
        """)
        rows = cursor.fetchall()
        best_order, best_conf = None, 0.0
        for row in rows:
            for name_field in ['billing_name', 'shipping_name']:
                if row[name_field]:
                    is_match, conf = name_fuzzy_match(zoom_name_normalized, row[name_field])
                    if is_match and conf > best_conf:
                        best_order, best_conf = row['order_number'], conf
        if best_order and best_conf >= 0.6:
            cursor.execute("SELECT * FROM raw_shopify_orders WHERE order_number = ?", (best_order,))
            row = cursor.fetchone()
            if row:
                conn.close()
                return {'matched': True, 'order_number': row['order_number'],
                        'confidence': best_conf * 0.85, 'match_method': 'fuzzy_name', 'order_data': dict(row)}

    conn.close()
    return result


def run_matching_for_meeting(meeting_id: str) -> Dict[str, Any]:
    """Run matching for all participants in a meeting."""
    conn = get_journey_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM zoom_participants_deduped WHERE meeting_id = ? AND is_internal = 0
    """, (meeting_id,))
    participants = cursor.fetchall()

    stats = {
        'total_participants': len(participants), 'matched': 0, 'unmatched': 0,
        'match_methods': {'exact_email': 0, 'fuzzy_email': 0, 'exact_name': 0, 'fuzzy_name': 0},
        'results': []
    }

    for participant in participants:
        email = participant['email']
        name = participant['participant_name']
        match_result = find_matching_order(email, name)

        if match_result['matched']:
            stats['matched'] += 1
            stats['match_methods'][match_result['match_method']] += 1
            create_or_update_unified_user(dict(participant), match_result['order_data'],
                                          match_result['confidence'], match_result['match_method'])
        else:
            stats['unmatched'] += 1

        stats['results'].append({
            'participant_name': name, 'email': email, 'matched': match_result['matched'],
            'match_method': match_result['match_method'], 'confidence': match_result['confidence'],
            'order_number': match_result['order_number']
        })

    conn.close()
    return stats


def create_or_update_unified_user(zoom_participant: Dict, order_data: Dict,
                                   match_confidence: float, match_method: str) -> int:
    """Create or update unified user record."""
    conn = get_journey_db()
    cursor = conn.cursor()

    email = order_data.get('email') or zoom_participant.get('email')
    phone = order_data.get('phone')

    cursor.execute("SELECT id FROM unified_users WHERE primary_email = ? OR primary_phone = ?", (email, phone))
    existing = cursor.fetchone()

    if existing:
        user_id = existing['id']
        cursor.execute("""
            UPDATE unified_users SET
                zoom_attendance_ids = COALESCE(zoom_attendance_ids, '') || ',' || ?,
                has_attended_any = 1, total_events_attended = total_events_attended + 1,
                latest_event_attended = ?, latest_event_duration = ?,
                journey_stage = CASE WHEN journey_stage = 'ordered' THEN 'engaged' ELSE journey_stage END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (str(zoom_participant.get('id', '')), zoom_participant.get('meeting_topic'),
              zoom_participant.get('total_duration_minutes'), user_id))
    else:
        cursor.execute("""
            INSERT INTO unified_users (
                primary_email, primary_phone, primary_name, city, state, pincode,
                shopify_order_numbers, zoom_attendance_ids, order_source,
                first_order_date, latest_order_date, order_count, total_order_value,
                payment_method, financial_status, fulfillment_status, primary_product,
                rto_risk, has_attended_any, total_events_attended, latest_event_attended,
                latest_event_duration, journey_stage, match_confidence, match_method, needs_review, ltv
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            email, phone, order_data.get('billing_name') or order_data.get('shipping_name'),
            order_data.get('billing_city'), order_data.get('billing_province'), order_data.get('billing_zip'),
            order_data.get('order_number'), str(zoom_participant.get('id', '')), order_data.get('source'),
            order_data.get('created_at'), order_data.get('created_at'), 1, order_data.get('total', 0),
            order_data.get('payment_method'), order_data.get('financial_status'), order_data.get('fulfillment_status'),
            order_data.get('lineitem_name'), order_data.get('rto_risk'), 1, 1,
            zoom_participant.get('meeting_topic'), zoom_participant.get('total_duration_minutes'),
            'engaged', match_confidence, match_method, 1 if match_confidence < 0.8 else 0, order_data.get('total', 0)
        ))
        user_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO match_audit_log (unified_user_id, source_table, source_record_identifier,
            match_field, value_from_user, value_from_source, confidence, match_result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, 'zoom_participants_deduped', str(zoom_participant.get('id', '')),
          match_method.replace('_', ' '), zoom_participant.get('email') or zoom_participant.get('participant_name'),
          order_data.get('email') or order_data.get('billing_name'), match_confidence, 'matched'))

    conn.commit()
    conn.close()
    return user_id


def import_orders_as_unified_users() -> int:
    """Import unmatched Shopify orders as unified users."""
    conn = get_journey_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM raw_shopify_orders
        WHERE email NOT IN (SELECT primary_email FROM unified_users WHERE primary_email IS NOT NULL)
        AND order_number NOT IN (SELECT shopify_order_numbers FROM unified_users WHERE shopify_order_numbers IS NOT NULL)
    """)
    orders = cursor.fetchall()
    created = 0

    for order in orders:
        cursor.execute("""
            INSERT INTO unified_users (
                primary_email, primary_phone, primary_name, city, state, pincode,
                shopify_order_numbers, order_source, first_order_date, latest_order_date,
                order_count, total_order_value, payment_method, financial_status,
                fulfillment_status, primary_product, rto_risk, has_attended_any,
                journey_stage, match_confidence, match_method, ltv
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order['email'], order['phone'], order['billing_name'] or order['shipping_name'],
            order['billing_city'], order['billing_province'], order['billing_zip'],
            order['order_number'], order['source'], order['created_at'], order['created_at'],
            1, order['total'] or 0, order['payment_method'], order['financial_status'],
            order['fulfillment_status'], order['lineitem_name'], order['rto_risk'], 0,
            'ordered', 1.0, 'direct_import', order['total'] or 0
        ))
        created += 1

    conn.commit()
    conn.close()
    return created


# =============================================================================
# STATS FUNCTIONS
# =============================================================================
def get_shopify_stats() -> dict:
    """Get Shopify data statistics."""
    conn = get_journey_db()
    cursor = conn.cursor()
    stats = {}
    cursor.execute("SELECT COUNT(*) FROM raw_shopify_orders")
    stats['total_orders'] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM raw_shopify_orders WHERE payment_method = 'cod'")
    stats['cod_orders'] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM raw_shopify_orders WHERE payment_method = 'prepaid'")
    stats['prepaid_orders'] = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total) FROM raw_shopify_orders")
    result = cursor.fetchone()[0]
    stats['total_value'] = result if result else 0
    conn.close()
    return stats


def get_zoom_stats() -> dict:
    """Get Zoom data statistics."""
    conn = get_journey_db()
    cursor = conn.cursor()
    stats = {}
    cursor.execute("SELECT COUNT(*) FROM raw_zoom_attendance")
    stats['total_raw_records'] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM zoom_participants_deduped WHERE is_internal = 0")
    stats['external_participants'] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT meeting_id) FROM zoom_participants_deduped")
    stats['unique_meetings'] = cursor.fetchone()[0]
    conn.close()
    return stats


def get_matching_stats() -> Dict[str, Any]:
    """Get overall matching statistics."""
    conn = get_journey_db()
    cursor = conn.cursor()
    stats = {}

    cursor.execute("SELECT COUNT(*) FROM unified_users")
    stats['total_unified_users'] = cursor.fetchone()[0]

    cursor.execute("SELECT journey_stage, COUNT(*) as count FROM unified_users GROUP BY journey_stage")
    stats['by_journey_stage'] = {r['journey_stage']: r['count'] for r in cursor.fetchall()}

    cursor.execute("SELECT match_method, COUNT(*) as count FROM unified_users GROUP BY match_method")
    stats['by_match_method'] = {r['match_method']: r['count'] for r in cursor.fetchall()}

    cursor.execute("SELECT COUNT(*) FROM unified_users WHERE needs_review = 1")
    stats['needs_review'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM unified_users WHERE has_attended_any = 1")
    stats['attended_events'] = cursor.fetchone()[0]

    cursor.execute("SELECT AVG(match_confidence) FROM unified_users")
    result = cursor.fetchone()[0]
    stats['avg_confidence'] = round(result, 3) if result else 0

    conn.close()
    return stats


def get_table_counts() -> dict:
    """Get row counts for all journey tables."""
    conn = get_journey_db()
    cursor = conn.cursor()
    counts = {}
    tables = ["raw_shopify_orders", "raw_zoom_attendance", "zoom_participants_deduped", "unified_users", "match_audit_log"]
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cursor.fetchone()[0]
    conn.close()
    return counts


def reset_journey_db():
    """Clear all data from journey tables."""
    conn = get_journey_db()
    cursor = conn.cursor()
    tables = ["raw_shopify_orders", "raw_zoom_attendance", "zoom_participants_deduped", "unified_users", "match_audit_log"]
    for table in tables:
        cursor.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()


# =============================================================================
# STREAMLIT UI RENDERING
# =============================================================================
def render_user_journey_module():
    """Main render function for the User Journey Tracker module."""
    init_journey_db()

    # CSS for black text and white pill buttons
    st.markdown("""
    <style>
    /* All text black */
    .stMarkdown, .stText, p, span, label, div, h1, h2, h3, h4, h5, h6 {
        color: #1A1A1A !important;
    }

    /* Metric values and labels */
    [data-testid="stMetricValue"] {
        color: #1A1A1A !important;
    }
    [data-testid="stMetricLabel"] {
        color: #1A1A1A !important;
    }
    [data-testid="stMetricDelta"] {
        color: #1A1A1A !important;
    }

    /* Tab text */
    .stTabs [data-baseweb="tab"] {
        color: #1A1A1A !important;
    }
    .stTabs [data-baseweb="tab-list"] button {
        color: #1A1A1A !important;
    }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        color: #1A1A1A !important;
    }

    /* Multiselect pills - white background with black text */
    [data-baseweb="tag"] {
        background-color: #FFFFFF !important;
        color: #1A1A1A !important;
        border: 1px solid #E5E7EB !important;
    }
    [data-baseweb="tag"] span {
        color: #1A1A1A !important;
    }

    /* Selectbox and multiselect dropdown */
    [data-baseweb="select"] {
        color: #1A1A1A !important;
    }
    [data-baseweb="select"] div {
        color: #1A1A1A !important;
    }

    /* Input labels */
    .stSelectbox label, .stMultiSelect label, .stTextInput label {
        color: #1A1A1A !important;
    }

    /* Checkbox labels */
    .stCheckbox label {
        color: #1A1A1A !important;
    }
    .stCheckbox label span {
        color: #1A1A1A !important;
    }

    /* File uploader text */
    [data-testid="stFileUploader"] label {
        color: #1A1A1A !important;
    }
    [data-testid="stFileUploader"] span {
        color: #1A1A1A !important;
    }
    [data-testid="stFileUploader"] p {
        color: #1A1A1A !important;
    }
    [data-testid="stFileUploader"] div {
        color: #1A1A1A !important;
    }

    /* Dataframe text */
    [data-testid="stDataFrame"] {
        color: #1A1A1A !important;
    }

    /* Info, success, warning boxes */
    .stAlert p, .stAlert span {
        color: #1A1A1A !important;
    }

    /* Caption text */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: #1A1A1A !important;
    }

    /* Expander headers */
    .streamlit-expanderHeader {
        color: #1A1A1A !important;
    }

    /* Bar chart labels */
    .stBarChart text {
        fill: #1A1A1A !important;
    }
    </style>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["Upload & Preview", "Run Matching", "Unified Users", "Audit Log"])

    with tab1:
        render_upload_tab()

    with tab2:
        render_matching_tab()

    with tab3:
        render_unified_users_tab()

    with tab4:
        render_audit_tab()


def render_upload_tab():
    """Render the Upload & Preview tab."""
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Shopify Orders CSV")
        shopify_file = st.file_uploader("Upload Shopify Orders Export", type=['csv'], key="journey_shopify_upload")

        if shopify_file:
            with st.spinner("Processing Shopify orders..."):
                try:
                    total, unique, dupes = load_shopify_csv(shopify_file)
                    st.success(f"Loaded {unique} unique orders ({dupes} duplicates removed)")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

        stats = get_shopify_stats()
        if stats['total_orders'] > 0:
            st.markdown("**Current Data:**")
            cols = st.columns(3)
            cols[0].metric("Total Orders", stats['total_orders'])
            cols[1].metric("COD", stats['cod_orders'])
            cols[2].metric("Prepaid", stats['prepaid_orders'])

    with col2:
        st.subheader("Zoom Attendance CSV")
        zoom_file = st.file_uploader("Upload Zoom Attendance Report", type=['csv'], key="journey_zoom_upload")

        if zoom_file:
            with st.spinner("Processing Zoom attendance..."):
                try:
                    total, external, internal, topic, date = load_zoom_csv(zoom_file)
                    st.success(f"Loaded: {topic} ({date})")
                    st.info(f"{external} external, {internal} internal")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

        stats = get_zoom_stats()
        if stats['total_raw_records'] > 0:
            st.markdown("**Current Data:**")
            cols = st.columns(3)
            cols[0].metric("Raw Records", stats['total_raw_records'])
            cols[1].metric("External", stats['external_participants'])
            cols[2].metric("Meetings", stats['unique_meetings'])

    st.divider()
    st.subheader("Database Management")

    col1, col2 = st.columns(2)
    with col1:
        counts = get_table_counts()
        for table, count in counts.items():
            st.text(f"{table}: {count}")

    with col2:
        if st.button("Reset All Journey Data", type="secondary"):
            if st.session_state.get('confirm_journey_reset'):
                reset_journey_db()
                st.success("Journey database reset")
                st.session_state['confirm_journey_reset'] = False
                st.rerun()
            else:
                st.session_state['confirm_journey_reset'] = True
                st.warning("Click again to confirm")


def render_matching_tab():
    """Render the Run Matching tab."""
    conn = get_journey_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT meeting_id, meeting_topic, meeting_date, COUNT(*) as cnt
        FROM zoom_participants_deduped WHERE is_internal = 0
        GROUP BY meeting_id ORDER BY meeting_date DESC
    """)
    meetings = cursor.fetchall()
    conn.close()

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Match Zoom Participants to Orders")

        if not meetings:
            st.info("No Zoom meetings loaded. Upload in Upload tab first.")
        else:
            meeting_options = {f"{m['meeting_topic']} ({m['meeting_date']}) - {m['cnt']} participants": m['meeting_id'] for m in meetings}
            selected = st.selectbox("Select Meeting", options=list(meeting_options.keys()))

            if selected and st.button("Run Matching", type="primary"):
                meeting_id = meeting_options[selected]
                with st.spinner("Running matching..."):
                    stats = run_matching_for_meeting(meeting_id)

                st.success("Matching complete!")
                cols = st.columns(3)
                cols[0].metric("Total", stats['total_participants'])
                cols[1].metric("Matched", stats['matched'])
                cols[2].metric("Unmatched", stats['unmatched'])

                st.markdown("**Match Methods:**")
                for method, count in stats['match_methods'].items():
                    if count > 0:
                        st.text(f"  {method.replace('_', ' ').title()}: {count}")

                if stats['results']:
                    results_df = pd.DataFrame(stats['results'])
                    st.dataframe(results_df, use_container_width=True)

    with col2:
        st.subheader("Import Orders")
        st.markdown("Import Shopify orders as unified users (for non-attendees)")

        if get_shopify_stats()['total_orders'] == 0:
            st.info("No Shopify orders loaded.")
        elif st.button("Import Unmatched Orders"):
            with st.spinner("Importing..."):
                count = import_orders_as_unified_users()
            st.success(f"Imported {count} orders")


def render_unified_users_tab():
    """Render the Unified Users tab."""
    stats = get_matching_stats()

    cols = st.columns(5)
    cols[0].metric("Total Users", stats['total_unified_users'])
    cols[1].metric("Attended", stats['attended_events'])
    cols[2].metric("Needs Review", stats['needs_review'])
    cols[3].metric("Avg Confidence", f"{stats['avg_confidence']:.1%}")
    cols[4].metric("Stages", len(stats.get('by_journey_stage', {})))

    if stats.get('by_journey_stage'):
        st.subheader("Journey Stage Distribution")
        stage_df = pd.DataFrame([{"Stage": k, "Count": v} for k, v in stats['by_journey_stage'].items()])
        st.bar_chart(stage_df.set_index('Stage'))

    st.subheader("User List")

    conn = get_journey_db()
    df = pd.read_sql_query("SELECT * FROM unified_users ORDER BY updated_at DESC", conn)
    conn.close()

    if df.empty:
        st.info("No unified users yet. Run matching or import orders first.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            stage_filter = st.multiselect("Journey Stage", options=df['journey_stage'].dropna().unique().tolist())
        with col2:
            attended_filter = st.selectbox("Attendance", ["All", "Attended", "Not Attended"])
        with col3:
            review_filter = st.checkbox("Needs Review Only")

        filtered = df.copy()
        if stage_filter:
            filtered = filtered[filtered['journey_stage'].isin(stage_filter)]
        if attended_filter == "Attended":
            filtered = filtered[filtered['has_attended_any'] == 1]
        elif attended_filter == "Not Attended":
            filtered = filtered[filtered['has_attended_any'] == 0]
        if review_filter:
            filtered = filtered[filtered['needs_review'] == 1]

        display_cols = ['primary_name', 'primary_email', 'primary_phone', 'journey_stage',
                        'order_count', 'total_order_value', 'has_attended_any', 'match_confidence', 'needs_review']
        available = [c for c in display_cols if c in filtered.columns]
        st.dataframe(filtered[available], use_container_width=True)
        st.caption(f"Showing {len(filtered)} of {len(df)} users")


def render_audit_tab():
    """Render the Audit Log tab."""
    conn = get_journey_db()
    df = pd.read_sql_query("""
        SELECT mal.*, uu.primary_name, uu.primary_email
        FROM match_audit_log mal
        LEFT JOIN unified_users uu ON mal.unified_user_id = uu.id
        ORDER BY mal.created_at DESC LIMIT 500
    """, conn)
    conn.close()

    if df.empty:
        st.info("No audit records yet.")
    else:
        cols = st.columns(3)
        cols[0].metric("Total Records", len(df))
        cols[1].metric("Avg Confidence", f"{df['confidence'].mean():.1%}")
        cols[2].metric("Unique Users", df['unified_user_id'].nunique())

        st.subheader("Audit Trail")
        st.dataframe(df, use_container_width=True)
