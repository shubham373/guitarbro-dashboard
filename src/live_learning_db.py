"""
Live Learning Module - Database Operations

Handles database schema and CRUD operations for:
- Events (Luma/Zoom uploads)
- Unified Users (deduplicated by email/phone)
- Registrations (per event)
- Attendance (Zoom data)

Uses the same logistics.db database for order matching.
"""

import sqlite3
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database path (same as logistics module)
DB_PATH = "data/logistics.db"


def get_db_connection():
    """Get a connection to the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# SCHEMA INITIALIZATION
# =============================================================================

def init_live_learning_tables():
    """Initialize the Live Learning module tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date DATE NOT NULL,
            event_name TEXT,
            source TEXT NOT NULL,  -- 'luma' or 'zoom'
            zoom_meeting_id TEXT,
            total_registrations INTEGER DEFAULT 0,
            total_attendees INTEGER DEFAULT 0,
            file_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Unified Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_unified_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primary_name TEXT,
            primary_email TEXT,
            primary_phone TEXT,
            all_emails TEXT,  -- JSON array
            all_phones TEXT,  -- JSON array
            all_names TEXT,   -- JSON array
            total_events_registered INTEGER DEFAULT 0,
            total_events_attended INTEGER DEFAULT 0,
            first_registered_at DATE,
            last_registered_at DATE,
            first_attended_at DATE,
            last_attended_at DATE,
            shopify_order_id TEXT,
            shopify_order_date DATE,
            order_matched INTEGER DEFAULT 0,  -- 0=false, 1=true
            match_method TEXT,  -- 'email', 'phone', 'both'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Event Registrations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_event_registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            unified_user_id INTEGER NOT NULL,
            source TEXT NOT NULL,  -- 'luma' or 'zoom'
            raw_name TEXT,
            raw_email TEXT,
            raw_phone TEXT,
            registered_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES live_events(id),
            FOREIGN KEY (unified_user_id) REFERENCES live_unified_users(id)
        )
    """)

    # Event Attendance table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_event_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            unified_user_id INTEGER NOT NULL,
            total_duration_minutes INTEGER DEFAULT 0,
            join_frequency INTEGER DEFAULT 1,
            first_join_time TIMESTAMP,
            last_leave_time TIMESTAMP,
            raw_name TEXT,
            raw_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES live_events(id),
            FOREIGN KEY (unified_user_id) REFERENCES live_unified_users(id)
        )
    """)

    # Create indexes for faster lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON live_unified_users(primary_email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON live_unified_users(primary_phone)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON live_events(event_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_registrations_event ON live_event_registrations(event_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_event ON live_event_attendance(event_id)")

    conn.commit()
    conn.close()
    logger.info("Live Learning tables initialized")


# =============================================================================
# NORMALIZATION UTILITIES
# =============================================================================

def normalize_phone(phone_str: Any) -> Optional[str]:
    """Normalize phone number to 10 digits."""
    if phone_str is None or str(phone_str).strip() == '':
        return None

    phone_str = str(phone_str).strip()

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


def normalize_email(email: Any) -> Optional[str]:
    """Normalize email to lowercase."""
    if email is None or str(email).strip() == '':
        return None

    email = str(email).strip().lower()
    if '@' not in email:
        return None

    return email


def normalize_name(name: Any) -> Optional[str]:
    """Normalize name - title case, strip whitespace."""
    if name is None or str(name).strip() == '':
        return None

    return str(name).strip().title()


# =============================================================================
# EVENT OPERATIONS
# =============================================================================

def create_event(
    event_date: str,
    source: str,
    event_name: Optional[str] = None,
    zoom_meeting_id: Optional[str] = None,
    file_name: Optional[str] = None
) -> int:
    """Create a new event record."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO live_events (event_date, event_name, source, zoom_meeting_id, file_name)
        VALUES (?, ?, ?, ?, ?)
    """, (event_date, event_name, source, zoom_meeting_id, file_name))

    event_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Created event {event_id}: {event_date} ({source})")
    return event_id


def update_event_counts(event_id: int, registrations: int = None, attendees: int = None):
    """Update event registration/attendance counts."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if registrations is not None:
        cursor.execute(
            "UPDATE live_events SET total_registrations = ? WHERE id = ?",
            (registrations, event_id)
        )

    if attendees is not None:
        cursor.execute(
            "UPDATE live_events SET total_attendees = ? WHERE id = ?",
            (attendees, event_id)
        )

    conn.commit()
    conn.close()


def get_events_in_range(start_date: str, end_date: str) -> List[Dict]:
    """Get all events within a date range."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM live_events
        WHERE event_date BETWEEN ? AND ?
        ORDER BY event_date DESC
    """, (start_date, end_date))

    events = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return events


def check_event_exists(event_date: str, source: str) -> Optional[int]:
    """Check if an event already exists for this date and source."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM live_events
        WHERE event_date = ? AND source = ?
    """, (event_date, source))

    row = cursor.fetchone()
    conn.close()

    return row['id'] if row else None


# =============================================================================
# USER OPERATIONS
# =============================================================================

def find_user_by_email_or_phone(email: Optional[str], phone: Optional[str]) -> Optional[Dict]:
    """
    Find a unified user by email OR phone match.
    Checks both primary fields and all_emails/all_phones arrays.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    user = None

    # Try email match first
    if email:
        cursor.execute("""
            SELECT * FROM live_unified_users
            WHERE primary_email = ?
               OR all_emails LIKE ?
        """, (email, f'%"{email}"%'))
        row = cursor.fetchone()
        if row:
            user = dict(row)

    # Try phone match if no email match
    if not user and phone:
        cursor.execute("""
            SELECT * FROM live_unified_users
            WHERE primary_phone = ?
               OR all_phones LIKE ?
        """, (phone, f'%"{phone}"%'))
        row = cursor.fetchone()
        if row:
            user = dict(row)

    conn.close()
    return user


def create_user(
    name: Optional[str],
    email: Optional[str],
    phone: Optional[str]
) -> int:
    """Create a new unified user."""
    conn = get_db_connection()
    cursor = conn.cursor()

    all_emails = json.dumps([email]) if email else json.dumps([])
    all_phones = json.dumps([phone]) if phone else json.dumps([])
    all_names = json.dumps([name]) if name else json.dumps([])

    cursor.execute("""
        INSERT INTO live_unified_users (
            primary_name, primary_email, primary_phone,
            all_emails, all_phones, all_names
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, email, phone, all_emails, all_phones, all_names))

    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.debug(f"Created user {user_id}: {email or phone}")
    return user_id


def merge_user_data(
    user_id: int,
    name: Optional[str],
    email: Optional[str],
    phone: Optional[str]
):
    """Merge new data into existing user (add emails/phones/names if new)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM live_unified_users WHERE id = ?", (user_id,))
    user = dict(cursor.fetchone())

    # Parse existing arrays
    all_emails = json.loads(user['all_emails'] or '[]')
    all_phones = json.loads(user['all_phones'] or '[]')
    all_names = json.loads(user['all_names'] or '[]')

    updated = False

    # Add email if new
    if email and email not in all_emails:
        all_emails.append(email)
        updated = True

    # Add phone if new
    if phone and phone not in all_phones:
        all_phones.append(phone)
        updated = True

    # Add name if new
    if name and name not in all_names:
        all_names.append(name)
        updated = True

    if updated:
        cursor.execute("""
            UPDATE live_unified_users
            SET all_emails = ?, all_phones = ?, all_names = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (json.dumps(all_emails), json.dumps(all_phones), json.dumps(all_names), user_id))
        conn.commit()

    conn.close()


def update_user_registration_stats(user_id: int, event_date: str):
    """Update user's registration statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM live_unified_users WHERE id = ?", (user_id,))
    user = dict(cursor.fetchone())

    # Count unique events registered
    cursor.execute("""
        SELECT COUNT(DISTINCT event_id) as count
        FROM live_event_registrations
        WHERE unified_user_id = ?
    """, (user_id,))
    total_registered = cursor.fetchone()['count']

    # Update first/last registered dates
    first_registered = user['first_registered_at'] or event_date
    if event_date < first_registered:
        first_registered = event_date

    last_registered = user['last_registered_at'] or event_date
    if event_date > last_registered:
        last_registered = event_date

    cursor.execute("""
        UPDATE live_unified_users
        SET total_events_registered = ?,
            first_registered_at = ?,
            last_registered_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (total_registered, first_registered, last_registered, user_id))

    conn.commit()
    conn.close()


def update_user_attendance_stats(user_id: int, event_date: str):
    """Update user's attendance statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM live_unified_users WHERE id = ?", (user_id,))
    user = dict(cursor.fetchone())

    # Count unique events attended
    cursor.execute("""
        SELECT COUNT(DISTINCT event_id) as count
        FROM live_event_attendance
        WHERE unified_user_id = ?
    """, (user_id,))
    total_attended = cursor.fetchone()['count']

    # Update first/last attended dates
    first_attended = user['first_attended_at'] or event_date
    if event_date < first_attended:
        first_attended = event_date

    last_attended = user['last_attended_at'] or event_date
    if event_date > last_attended:
        last_attended = event_date

    cursor.execute("""
        UPDATE live_unified_users
        SET total_events_attended = ?,
            first_attended_at = ?,
            last_attended_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (total_attended, first_attended, last_attended, user_id))

    conn.commit()
    conn.close()


# =============================================================================
# REGISTRATION OPERATIONS
# =============================================================================

def create_registration(
    event_id: int,
    unified_user_id: int,
    source: str,
    raw_name: Optional[str],
    raw_email: Optional[str],
    raw_phone: Optional[str],
    registered_at: Optional[str] = None
) -> int:
    """Create a registration record."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO live_event_registrations (
            event_id, unified_user_id, source,
            raw_name, raw_email, raw_phone, registered_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (event_id, unified_user_id, source, raw_name, raw_email, raw_phone, registered_at))

    reg_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return reg_id


def check_registration_exists(event_id: int, unified_user_id: int, source: str) -> bool:
    """Check if a user is already registered for an event from a source."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM live_event_registrations
        WHERE event_id = ? AND unified_user_id = ? AND source = ?
    """, (event_id, unified_user_id, source))

    exists = cursor.fetchone() is not None
    conn.close()
    return exists


# =============================================================================
# ATTENDANCE OPERATIONS
# =============================================================================

def create_or_update_attendance(
    event_id: int,
    unified_user_id: int,
    total_duration_minutes: int,
    join_frequency: int,
    first_join_time: str,
    last_leave_time: str,
    raw_name: Optional[str],
    raw_email: Optional[str]
) -> int:
    """Create or update attendance record for a user at an event."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if attendance already exists
    cursor.execute("""
        SELECT id FROM live_event_attendance
        WHERE event_id = ? AND unified_user_id = ?
    """, (event_id, unified_user_id))

    existing = cursor.fetchone()

    if existing:
        # Update existing record
        cursor.execute("""
            UPDATE live_event_attendance
            SET total_duration_minutes = total_duration_minutes + ?,
                join_frequency = join_frequency + ?,
                last_leave_time = ?
            WHERE id = ?
        """, (total_duration_minutes, join_frequency, last_leave_time, existing['id']))
        att_id = existing['id']
    else:
        # Create new record
        cursor.execute("""
            INSERT INTO live_event_attendance (
                event_id, unified_user_id, total_duration_minutes,
                join_frequency, first_join_time, last_leave_time,
                raw_name, raw_email
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (event_id, unified_user_id, total_duration_minutes,
              join_frequency, first_join_time, last_leave_time,
              raw_name, raw_email))
        att_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return att_id


# =============================================================================
# ORDER MATCHING
# =============================================================================

def run_order_matching() -> Dict[str, int]:
    """
    Match unmatched users with Shopify orders.
    Searches from latest orders first for efficiency.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all unmatched users
    cursor.execute("""
        SELECT id, all_emails, all_phones
        FROM live_unified_users
        WHERE order_matched = 0
    """)

    unmatched_users = cursor.fetchall()
    matched_count = 0
    processed_count = 0

    for user in unmatched_users:
        processed_count += 1
        user_id = user['id']
        all_emails = json.loads(user['all_emails'] or '[]')
        all_phones = json.loads(user['all_phones'] or '[]')

        if not all_emails and not all_phones:
            continue

        # Build query to find matching order (latest first)
        query_parts = []
        params = []

        if all_emails:
            email_placeholders = ','.join(['?' for _ in all_emails])
            query_parts.append(f"email IN ({email_placeholders})")
            params.extend(all_emails)

        if all_phones:
            phone_placeholders = ','.join(['?' for _ in all_phones])
            query_parts.append(f"phone IN ({phone_placeholders})")
            query_parts.append(f"billing_phone IN ({phone_placeholders})")
            params.extend(all_phones)
            params.extend(all_phones)

        if not query_parts:
            continue

        where_clause = ' OR '.join(query_parts)

        cursor.execute(f"""
            SELECT order_id, order_date, email, phone, billing_phone
            FROM raw_shopify_orders
            WHERE {where_clause}
            ORDER BY order_date DESC
            LIMIT 1
        """, params)

        order = cursor.fetchone()

        if order:
            # Determine match method
            order_email = normalize_email(order['email'])
            order_phone = normalize_phone(order['phone'])
            order_billing_phone = normalize_phone(order['billing_phone'])

            email_match = order_email and order_email in all_emails
            phone_match = (order_phone and order_phone in all_phones) or \
                          (order_billing_phone and order_billing_phone in all_phones)

            if email_match and phone_match:
                match_method = 'both'
            elif email_match:
                match_method = 'email'
            else:
                match_method = 'phone'

            # Update user with order info
            cursor.execute("""
                UPDATE live_unified_users
                SET shopify_order_id = ?,
                    shopify_order_date = ?,
                    order_matched = 1,
                    match_method = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (order['order_id'], order['order_date'], match_method, user_id))

            matched_count += 1

    conn.commit()
    conn.close()

    logger.info(f"Order matching: {matched_count} matched out of {processed_count} processed")
    return {
        'processed': processed_count,
        'matched': matched_count,
        'unmatched': processed_count - matched_count
    }


# =============================================================================
# DASHBOARD QUERIES
# =============================================================================

def get_dashboard_metrics(start_date: str, end_date: str) -> Dict[str, Any]:
    """Get aggregated metrics for events in date range."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get event IDs in range
    cursor.execute("""
        SELECT id FROM live_events
        WHERE event_date BETWEEN ? AND ?
    """, (start_date, end_date))
    event_ids = [row['id'] for row in cursor.fetchall()]

    if not event_ids:
        conn.close()
        return {
            'total_events': 0,
            'total_registered': 0,
            'total_attended': 0,
            'total_matched': 0,
            'total_unmatched': 0,
            'attendance_rate': 0,
            'match_rate': 0,
            'avg_duration': 0,
            'first_time_registrants': 0,
            'repeat_registrants': 0
        }

    event_placeholders = ','.join(['?' for _ in event_ids])

    # Total unique registered users
    cursor.execute(f"""
        SELECT COUNT(DISTINCT unified_user_id) as count
        FROM live_event_registrations
        WHERE event_id IN ({event_placeholders})
    """, event_ids)
    total_registered = cursor.fetchone()['count']

    # Total unique attended users
    cursor.execute(f"""
        SELECT COUNT(DISTINCT unified_user_id) as count
        FROM live_event_attendance
        WHERE event_id IN ({event_placeholders})
    """, event_ids)
    total_attended = cursor.fetchone()['count']

    # Get user IDs who registered in this period
    cursor.execute(f"""
        SELECT DISTINCT unified_user_id
        FROM live_event_registrations
        WHERE event_id IN ({event_placeholders})
    """, event_ids)
    registered_user_ids = [row['unified_user_id'] for row in cursor.fetchall()]

    # Count matched/unmatched among registered users
    if registered_user_ids:
        user_placeholders = ','.join(['?' for _ in registered_user_ids])
        cursor.execute(f"""
            SELECT
                SUM(CASE WHEN order_matched = 1 THEN 1 ELSE 0 END) as matched,
                SUM(CASE WHEN order_matched = 0 THEN 1 ELSE 0 END) as unmatched
            FROM live_unified_users
            WHERE id IN ({user_placeholders})
        """, registered_user_ids)
        row = cursor.fetchone()
        total_matched = row['matched'] or 0
        total_unmatched = row['unmatched'] or 0

        # First-time vs repeat registrants
        cursor.execute(f"""
            SELECT
                SUM(CASE WHEN total_events_registered = 1 THEN 1 ELSE 0 END) as first_time,
                SUM(CASE WHEN total_events_registered > 1 THEN 1 ELSE 0 END) as repeat
            FROM live_unified_users
            WHERE id IN ({user_placeholders})
        """, registered_user_ids)
        row = cursor.fetchone()
        first_time_registrants = row['first_time'] or 0
        repeat_registrants = row['repeat'] or 0
    else:
        total_matched = 0
        total_unmatched = 0
        first_time_registrants = 0
        repeat_registrants = 0

    # Average duration
    cursor.execute(f"""
        SELECT AVG(total_duration_minutes) as avg_duration
        FROM live_event_attendance
        WHERE event_id IN ({event_placeholders})
    """, event_ids)
    avg_duration = cursor.fetchone()['avg_duration'] or 0

    conn.close()

    attendance_rate = (total_attended / total_registered * 100) if total_registered > 0 else 0
    match_rate = (total_matched / total_registered * 100) if total_registered > 0 else 0

    return {
        'total_events': len(event_ids),
        'total_registered': total_registered,
        'total_attended': total_attended,
        'total_matched': total_matched,
        'total_unmatched': total_unmatched,
        'attendance_rate': round(attendance_rate, 1),
        'match_rate': round(match_rate, 1),
        'avg_duration': round(avg_duration, 1),
        'first_time_registrants': first_time_registrants,
        'repeat_registrants': repeat_registrants
    }


def get_user_journey_data(
    start_date: str,
    end_date: str,
    filter_type: str = 'all'
) -> List[Dict]:
    """Get user journey data for events in date range."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get event IDs in range
    cursor.execute("""
        SELECT id FROM live_events
        WHERE event_date BETWEEN ? AND ?
    """, (start_date, end_date))
    event_ids = [row['id'] for row in cursor.fetchall()]

    if not event_ids:
        conn.close()
        return []

    event_placeholders = ','.join(['?' for _ in event_ids])

    # Get all users who registered or attended in this period
    cursor.execute(f"""
        SELECT DISTINCT u.*,
            (SELECT SUM(a.total_duration_minutes)
             FROM live_event_attendance a
             WHERE a.unified_user_id = u.id AND a.event_id IN ({event_placeholders})) as period_duration,
            (SELECT MAX(a.last_leave_time)
             FROM live_event_attendance a
             WHERE a.unified_user_id = u.id AND a.event_id IN ({event_placeholders})) as period_last_leave,
            (SELECT SUM(a.join_frequency)
             FROM live_event_attendance a
             WHERE a.unified_user_id = u.id AND a.event_id IN ({event_placeholders})) as period_join_frequency,
            (SELECT COUNT(DISTINCT r.event_id)
             FROM live_event_registrations r
             WHERE r.unified_user_id = u.id AND r.event_id IN ({event_placeholders})) as period_events_registered,
            (SELECT COUNT(DISTINCT a.event_id)
             FROM live_event_attendance a
             WHERE a.unified_user_id = u.id AND a.event_id IN ({event_placeholders})) as period_events_attended
        FROM live_unified_users u
        WHERE u.id IN (
            SELECT DISTINCT unified_user_id FROM live_event_registrations WHERE event_id IN ({event_placeholders})
            UNION
            SELECT DISTINCT unified_user_id FROM live_event_attendance WHERE event_id IN ({event_placeholders})
        )
    """, event_ids + event_ids + event_ids + event_ids + event_ids + event_ids + event_ids)

    users = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Apply filters
    if filter_type == 'matched':
        users = [u for u in users if u['order_matched'] == 1]
    elif filter_type == 'unmatched':
        users = [u for u in users if u['order_matched'] == 0]
    elif filter_type == 'attended':
        users = [u for u in users if u['period_events_attended'] and u['period_events_attended'] > 0]
    elif filter_type == 'no_show':
        users = [u for u in users if not u['period_events_attended'] or u['period_events_attended'] == 0]

    return users


def get_all_events() -> List[Dict]:
    """Get all events ordered by date."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM live_events
        ORDER BY event_date DESC
    """)

    events = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return events


def get_table_counts() -> Dict[str, int]:
    """Get counts of records in each table."""
    conn = get_db_connection()
    cursor = conn.cursor()

    counts = {}

    for table in ['live_events', 'live_unified_users', 'live_event_registrations', 'live_event_attendance']:
        try:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
            counts[table] = cursor.fetchone()['count']
        except:
            counts[table] = 0

    conn.close()
    return counts


# Initialize tables on import
init_live_learning_tables()
