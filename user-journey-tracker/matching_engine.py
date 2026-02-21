"""
Matching Engine for User Journey Tracker

Implements a waterfall matching algorithm to link Zoom participants
to Shopify orders based on email, phone, and name matching.

Matching Waterfall:
1. Exact email match (confidence: 1.0)
2. Fuzzy email match (confidence: 0.85+)
3. Exact name match (confidence: 0.7)
4. Fuzzy name match (confidence: 0.6+)
5. No match found
"""

import sqlite3
import re
from difflib import SequenceMatcher
from typing import Optional, Dict, List, Tuple, Any
from schema import get_db_connection
from data_loader import normalize_email, normalize_phone


def normalize_name(name: str) -> Optional[str]:
    """
    Normalize name for matching:
    - Lowercase
    - Remove special characters
    - Remove common prefixes/suffixes (Mr, Mrs, Dr, etc.)
    - Collapse whitespace
    """
    if not name or str(name).strip() == '':
        return None

    name = str(name).lower().strip()

    # Remove common titles/prefixes
    prefixes = ['mr', 'mrs', 'ms', 'dr', 'shri', 'smt', 'prof']
    for prefix in prefixes:
        name = re.sub(rf'^{prefix}\.?\s+', '', name)

    # Remove special characters but keep spaces
    name = re.sub(r'[^a-z\s]', '', name)

    # Collapse multiple spaces
    name = ' '.join(name.split())

    return name if name else None


def email_fuzzy_match(email1: str, email2: str, threshold: float = 0.85) -> Tuple[bool, float]:
    """
    Fuzzy match two emails with SequenceMatcher.

    Returns:
        Tuple of (is_match, confidence_score)
    """
    if not email1 or not email2:
        return False, 0.0

    # Normalize emails
    e1 = normalize_email(email1)
    e2 = normalize_email(email2)

    if not e1 or not e2:
        return False, 0.0

    # Extract local part (before @) for comparison
    local1 = e1.split('@')[0]
    local2 = e2.split('@')[0]

    # Calculate similarity on local part
    ratio = SequenceMatcher(None, local1, local2).ratio()

    return ratio >= threshold, ratio


def name_fuzzy_match(name1: str, name2: str, threshold: float = 0.75) -> Tuple[bool, float]:
    """
    Fuzzy match two names with SequenceMatcher.

    Returns:
        Tuple of (is_match, confidence_score)
    """
    if not name1 or not name2:
        return False, 0.0

    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return False, 0.0

    # Direct comparison
    ratio = SequenceMatcher(None, n1, n2).ratio()

    if ratio >= threshold:
        return True, ratio

    # Try matching with reordered names (first last vs last first)
    parts1 = n1.split()
    parts2 = n2.split()

    if len(parts1) >= 2 and len(parts2) >= 2:
        # Try reversed comparison
        reversed1 = ' '.join(reversed(parts1))
        ratio_reversed = SequenceMatcher(None, reversed1, n2).ratio()
        if ratio_reversed >= threshold:
            return True, ratio_reversed

    return False, ratio


def find_matching_order(zoom_email: str, zoom_name: str) -> Dict[str, Any]:
    """
    Find matching Shopify order for a Zoom participant using waterfall matching.

    Args:
        zoom_email: Email from Zoom attendance
        zoom_name: Name from Zoom attendance

    Returns:
        Dict with match details:
        {
            'matched': bool,
            'order_number': str or None,
            'confidence': float,
            'match_method': str,
            'order_data': dict or None
        }
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    result = {
        'matched': False,
        'order_number': None,
        'confidence': 0.0,
        'match_method': 'none',
        'order_data': None
    }

    zoom_email_normalized = normalize_email(zoom_email)
    zoom_name_normalized = normalize_name(zoom_name)

    # STEP 1: Exact Email Match
    if zoom_email_normalized:
        cursor.execute("""
            SELECT * FROM raw_shopify_orders
            WHERE email = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (zoom_email_normalized,))
        row = cursor.fetchone()

        if row:
            result = {
                'matched': True,
                'order_number': row['order_number'],
                'confidence': 1.0,
                'match_method': 'exact_email',
                'order_data': dict(row)
            }
            conn.close()
            return result

    # STEP 2: Fuzzy Email Match
    if zoom_email_normalized:
        cursor.execute("SELECT DISTINCT email FROM raw_shopify_orders WHERE email IS NOT NULL")
        shopify_emails = [r['email'] for r in cursor.fetchall()]

        best_match = None
        best_confidence = 0.0

        for shopify_email in shopify_emails:
            is_match, confidence = email_fuzzy_match(zoom_email_normalized, shopify_email)
            if is_match and confidence > best_confidence:
                best_match = shopify_email
                best_confidence = confidence

        if best_match and best_confidence >= 0.85:
            cursor.execute("""
                SELECT * FROM raw_shopify_orders
                WHERE email = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (best_match,))
            row = cursor.fetchone()

            if row:
                result = {
                    'matched': True,
                    'order_number': row['order_number'],
                    'confidence': best_confidence,
                    'match_method': 'fuzzy_email',
                    'order_data': dict(row)
                }
                conn.close()
                return result

    # STEP 3: Exact Name Match
    if zoom_name_normalized:
        # Check against billing_name and shipping_name
        cursor.execute("""
            SELECT * FROM raw_shopify_orders
            WHERE LOWER(billing_name) = ? OR LOWER(shipping_name) = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (zoom_name_normalized, zoom_name_normalized))
        row = cursor.fetchone()

        if row:
            result = {
                'matched': True,
                'order_number': row['order_number'],
                'confidence': 0.7,
                'match_method': 'exact_name',
                'order_data': dict(row)
            }
            conn.close()
            return result

    # STEP 4: Fuzzy Name Match
    if zoom_name_normalized:
        cursor.execute("""
            SELECT DISTINCT billing_name, shipping_name, order_number
            FROM raw_shopify_orders
            WHERE billing_name IS NOT NULL OR shipping_name IS NOT NULL
        """)
        rows = cursor.fetchall()

        best_match_order = None
        best_confidence = 0.0

        for row in rows:
            # Check billing name
            if row['billing_name']:
                is_match, confidence = name_fuzzy_match(zoom_name_normalized, row['billing_name'])
                if is_match and confidence > best_confidence:
                    best_match_order = row['order_number']
                    best_confidence = confidence

            # Check shipping name
            if row['shipping_name']:
                is_match, confidence = name_fuzzy_match(zoom_name_normalized, row['shipping_name'])
                if is_match and confidence > best_confidence:
                    best_match_order = row['order_number']
                    best_confidence = confidence

        if best_match_order and best_confidence >= 0.6:
            cursor.execute("""
                SELECT * FROM raw_shopify_orders
                WHERE order_number = ?
            """, (best_match_order,))
            row = cursor.fetchone()

            if row:
                result = {
                    'matched': True,
                    'order_number': row['order_number'],
                    'confidence': best_confidence * 0.85,  # Discount for name-only match
                    'match_method': 'fuzzy_name',
                    'order_data': dict(row)
                }
                conn.close()
                return result

    # STEP 5: No Match
    conn.close()
    return result


def run_matching_for_meeting(meeting_id: str) -> Dict[str, Any]:
    """
    Run matching algorithm for all participants in a meeting.

    Returns:
        Dict with matching statistics
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all external participants for this meeting
    cursor.execute("""
        SELECT * FROM zoom_participants_deduped
        WHERE meeting_id = ? AND is_internal = 0
    """, (meeting_id,))
    participants = cursor.fetchall()

    stats = {
        'total_participants': len(participants),
        'matched': 0,
        'unmatched': 0,
        'match_methods': {
            'exact_email': 0,
            'fuzzy_email': 0,
            'exact_name': 0,
            'fuzzy_name': 0
        },
        'results': []
    }

    for participant in participants:
        email = participant['email']
        name = participant['participant_name']

        match_result = find_matching_order(email, name)

        if match_result['matched']:
            stats['matched'] += 1
            stats['match_methods'][match_result['match_method']] += 1

            # Create or update unified user
            create_or_update_unified_user(
                zoom_participant=dict(participant),
                order_data=match_result['order_data'],
                match_confidence=match_result['confidence'],
                match_method=match_result['match_method']
            )
        else:
            stats['unmatched'] += 1

        stats['results'].append({
            'participant_name': name,
            'email': email,
            'matched': match_result['matched'],
            'match_method': match_result['match_method'],
            'confidence': match_result['confidence'],
            'order_number': match_result['order_number']
        })

    conn.close()
    return stats


def create_or_update_unified_user(
    zoom_participant: Dict,
    order_data: Dict,
    match_confidence: float,
    match_method: str
) -> int:
    """
    Create or update a unified user record based on matched data.

    Returns:
        unified_user_id
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    email = order_data.get('email') or zoom_participant.get('email')
    phone = order_data.get('phone')

    # Check if user already exists
    cursor.execute("""
        SELECT id FROM unified_users
        WHERE primary_email = ? OR primary_phone = ?
    """, (email, phone))
    existing = cursor.fetchone()

    if existing:
        user_id = existing['id']
        # Update existing user
        cursor.execute("""
            UPDATE unified_users SET
                zoom_attendance_ids = COALESCE(zoom_attendance_ids, '') || ',' || ?,
                has_attended_any = 1,
                total_events_attended = total_events_attended + 1,
                latest_event_attended = ?,
                latest_event_duration = ?,
                journey_stage = CASE
                    WHEN journey_stage = 'ordered' THEN 'engaged'
                    ELSE journey_stage
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            str(zoom_participant.get('id', '')),
            zoom_participant.get('meeting_topic'),
            zoom_participant.get('total_duration_minutes'),
            user_id
        ))
    else:
        # Create new unified user
        cursor.execute("""
            INSERT INTO unified_users (
                primary_email, primary_phone, primary_name,
                city, state, pincode,
                shopify_order_numbers, zoom_attendance_ids,
                order_source, first_order_date, latest_order_date,
                order_count, total_order_value, payment_method,
                financial_status, fulfillment_status, primary_product,
                rto_risk, has_attended_any, total_events_attended,
                latest_event_attended, latest_event_duration,
                journey_stage, match_confidence, match_method,
                needs_review, ltv
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            email,
            phone,
            order_data.get('billing_name') or order_data.get('shipping_name'),
            order_data.get('billing_city') or order_data.get('shipping_city'),
            order_data.get('billing_province') or order_data.get('shipping_province'),
            order_data.get('billing_zip') or order_data.get('shipping_zip'),
            order_data.get('order_number'),
            str(zoom_participant.get('id', '')),
            order_data.get('source'),
            order_data.get('created_at'),
            order_data.get('created_at'),
            1,
            order_data.get('total', 0),
            order_data.get('payment_method'),
            order_data.get('financial_status'),
            order_data.get('fulfillment_status'),
            order_data.get('lineitem_name'),
            order_data.get('rto_risk'),
            1,  # has_attended_any
            1,  # total_events_attended
            zoom_participant.get('meeting_topic'),
            zoom_participant.get('total_duration_minutes'),
            'engaged',  # journey_stage
            match_confidence,
            match_method,
            1 if match_confidence < 0.8 else 0,  # needs_review
            order_data.get('total', 0)  # ltv
        ))
        user_id = cursor.lastrowid

    # Log the match
    cursor.execute("""
        INSERT INTO match_audit_log (
            unified_user_id, source_table, source_record_identifier,
            match_field, value_from_user, value_from_source,
            confidence, match_result
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        'zoom_participants_deduped',
        str(zoom_participant.get('id', '')),
        match_method.replace('_', ' '),
        zoom_participant.get('email') or zoom_participant.get('participant_name'),
        order_data.get('email') or order_data.get('billing_name'),
        match_confidence,
        'matched'
    ))

    conn.commit()
    conn.close()

    return user_id


def import_orders_as_unified_users() -> int:
    """
    Import all Shopify orders as unified users (for orders without Zoom matches).

    Returns:
        Number of users created
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all orders that don't have a unified user yet
    cursor.execute("""
        SELECT * FROM raw_shopify_orders
        WHERE email NOT IN (SELECT primary_email FROM unified_users WHERE primary_email IS NOT NULL)
        AND order_number NOT IN (SELECT shopify_order_numbers FROM unified_users WHERE shopify_order_numbers IS NOT NULL)
    """)
    orders = cursor.fetchall()

    created_count = 0

    for order in orders:
        cursor.execute("""
            INSERT INTO unified_users (
                primary_email, primary_phone, primary_name,
                city, state, pincode,
                shopify_order_numbers, order_source,
                first_order_date, latest_order_date,
                order_count, total_order_value, payment_method,
                financial_status, fulfillment_status, primary_product,
                rto_risk, has_attended_any, journey_stage,
                match_confidence, match_method, ltv
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order['email'],
            order['phone'],
            order['billing_name'] or order['shipping_name'],
            order['billing_city'] or order['shipping_city'],
            order['billing_province'] or order['shipping_province'],
            order['billing_zip'] or order['shipping_zip'],
            order['order_number'],
            order['source'],
            order['created_at'],
            order['created_at'],
            1,
            order['total'] or 0,
            order['payment_method'],
            order['financial_status'],
            order['fulfillment_status'],
            order['lineitem_name'],
            order['rto_risk'],
            0,  # has_attended_any
            'ordered',  # journey_stage
            1.0,  # match_confidence (direct import)
            'direct_import',
            order['total'] or 0
        ))
        created_count += 1

    conn.commit()
    conn.close()

    return created_count


def get_unified_users_df():
    """Get all unified users as a DataFrame."""
    import pandas as pd
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM unified_users ORDER BY updated_at DESC", conn)
    conn.close()
    return df


def get_matching_stats() -> Dict[str, Any]:
    """Get overall matching statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    stats = {}

    # Total unified users
    cursor.execute("SELECT COUNT(*) FROM unified_users")
    stats['total_unified_users'] = cursor.fetchone()[0]

    # By journey stage
    cursor.execute("""
        SELECT journey_stage, COUNT(*) as count
        FROM unified_users
        GROUP BY journey_stage
    """)
    stats['by_journey_stage'] = {row['journey_stage']: row['count'] for row in cursor.fetchall()}

    # By match method
    cursor.execute("""
        SELECT match_method, COUNT(*) as count
        FROM unified_users
        GROUP BY match_method
    """)
    stats['by_match_method'] = {row['match_method']: row['count'] for row in cursor.fetchall()}

    # Needs review
    cursor.execute("SELECT COUNT(*) FROM unified_users WHERE needs_review = 1")
    stats['needs_review'] = cursor.fetchone()[0]

    # Attended events
    cursor.execute("SELECT COUNT(*) FROM unified_users WHERE has_attended_any = 1")
    stats['attended_events'] = cursor.fetchone()[0]

    # Average confidence
    cursor.execute("SELECT AVG(match_confidence) FROM unified_users")
    result = cursor.fetchone()[0]
    stats['avg_confidence'] = round(result, 3) if result else 0

    conn.close()
    return stats
