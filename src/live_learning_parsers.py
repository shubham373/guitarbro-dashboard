"""
Live Learning Module - CSV Parsers

Parses Luma registration CSVs and Zoom attendance CSVs.
Handles user deduplication and aggregation.
"""

import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from collections import defaultdict

from live_learning_db import (
    normalize_email, normalize_phone, normalize_name,
    create_event, update_event_counts, check_event_exists,
    find_user_by_email_or_phone, create_user, merge_user_data,
    create_registration, check_registration_exists,
    create_or_update_attendance,
    update_user_registration_stats, update_user_attendance_stats
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# LUMA PARSER
# =============================================================================

def parse_luma_csv(
    file_obj,
    event_date: str,
    file_name: str = "luma_upload.csv",
    progress_callback=None
) -> Dict[str, Any]:
    """
    Parse a Luma registration CSV file.

    Expected columns:
    - name (or first_name + last_name)
    - email
    - phone_number
    - created_at
    - approval_status

    Returns:
        Dict with stats: total_rows, processed, skipped, new_users, existing_users
    """
    try:
        df = pd.read_csv(file_obj, encoding='utf-8-sig')
    except Exception as e:
        logger.error(f"Error reading Luma CSV: {e}")
        return {'error': str(e)}

    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()

    # Check for required columns
    if 'email' not in df.columns:
        return {'error': "Missing required column: email"}

    stats = {
        'total_rows': len(df),
        'processed': 0,
        'skipped_declined': 0,
        'skipped_no_contact': 0,
        'new_users': 0,
        'existing_users': 0,
        'registrations_created': 0
    }

    # Check if event exists for this date
    existing_event_id = check_event_exists(event_date, 'luma')
    if existing_event_id:
        event_id = existing_event_id
        logger.info(f"Using existing event ID: {event_id}")
    else:
        event_id = create_event(
            event_date=event_date,
            source='luma',
            event_name=file_name.replace('.csv', ''),
            file_name=file_name
        )
        logger.info(f"Created new event ID: {event_id}")

    total = len(df)

    for idx, row in df.iterrows():
        # Progress callback
        if progress_callback and idx % 10 == 0:
            progress_callback(idx / total)

        # Skip declined registrations
        approval_status = str(row.get('approval_status', '')).lower()
        if approval_status == 'declined':
            stats['skipped_declined'] += 1
            continue

        # Extract and normalize contact info
        email = normalize_email(row.get('email'))
        phone = normalize_phone(row.get('phone_number'))

        # Skip if no email AND no phone
        if not email and not phone:
            stats['skipped_no_contact'] += 1
            continue

        # Get name
        name = row.get('name')
        if not name or pd.isna(name):
            first_name = row.get('first_name', '')
            last_name = row.get('last_name', '')
            name = f"{first_name} {last_name}".strip()
        name = normalize_name(name)

        # Get registration time
        created_at = row.get('created_at')
        if pd.notna(created_at):
            try:
                # Luma format: 2026-02-22T05:34:40.378Z
                registered_at = str(created_at)
            except:
                registered_at = None
        else:
            registered_at = None

        # Find or create unified user
        existing_user = find_user_by_email_or_phone(email, phone)

        if existing_user:
            user_id = existing_user['id']
            # Merge any new contact info
            merge_user_data(user_id, name, email, phone)
            stats['existing_users'] += 1
        else:
            user_id = create_user(name, email, phone)
            stats['new_users'] += 1

        # Check if already registered for this event
        if not check_registration_exists(event_id, user_id, 'luma'):
            create_registration(
                event_id=event_id,
                unified_user_id=user_id,
                source='luma',
                raw_name=name,
                raw_email=email,
                raw_phone=phone,
                registered_at=registered_at
            )
            stats['registrations_created'] += 1

            # Update user's registration stats
            update_user_registration_stats(user_id, event_date)

        stats['processed'] += 1

    # Update event counts
    update_event_counts(event_id, registrations=stats['registrations_created'])

    if progress_callback:
        progress_callback(1.0)

    stats['event_id'] = event_id
    logger.info(f"Luma parsing complete: {stats}")
    return stats


# =============================================================================
# ZOOM PARSER
# =============================================================================

def parse_zoom_csv(
    file_obj,
    event_date: str,
    file_name: str = "zoom_upload.csv",
    progress_callback=None
) -> Dict[str, Any]:
    """
    Parse a Zoom meeting attendance CSV file.

    Expected columns:
    - Name (original name)
    - Email
    - Join time
    - Leave time
    - Duration (minutes) - participant's duration, not meeting duration
    - Host name - to skip the host

    Aggregates multiple join/leave sessions for the same user.

    Returns:
        Dict with stats: total_rows, unique_attendees, total_duration, etc.
    """
    try:
        df = pd.read_csv(file_obj, encoding='utf-8-sig')
    except Exception as e:
        logger.error(f"Error reading Zoom CSV: {e}")
        return {'error': str(e)}

    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()

    # Zoom has duplicate column names - pandas auto-renames them with .1 suffix
    # The columns are: 'duration (minutes)' [meeting], 'duration (minutes).1' [participant]
    cols = list(df.columns)
    for i, col in enumerate(cols):
        if col == 'duration (minutes)':
            cols[i] = 'meeting_duration'
        elif col == 'duration (minutes).1':
            cols[i] = 'participant_duration'
    df.columns = cols

    # Check for required columns
    required = ['name (original name)', 'email', 'join time', 'leave time']
    missing = [col for col in required if col not in df.columns]
    if missing:
        # Try alternate column names
        alt_mapping = {
            'name (original name)': 'name',
        }
        for col in missing:
            if col in alt_mapping and alt_mapping[col] in df.columns:
                df[col] = df[alt_mapping[col]]

        # Check again
        missing = [col for col in required if col not in df.columns]
        if missing:
            return {'error': f"Missing required columns: {missing}"}

    stats = {
        'total_rows': len(df),
        'skipped_host': 0,
        'skipped_no_email': 0,
        'unique_attendees': 0,
        'new_users': 0,
        'existing_users': 0,
        'attendance_created': 0,
        'total_duration_minutes': 0
    }

    # Get host info to skip
    host_email = None
    if 'host email' in df.columns and len(df) > 0:
        host_email = normalize_email(df.iloc[0]['host email'])

    host_name = None
    if 'host name' in df.columns and len(df) > 0:
        host_name = df.iloc[0]['host name']

    # Check if event exists for this date
    existing_event_id = check_event_exists(event_date, 'zoom')

    # Get meeting ID and topic if available
    zoom_meeting_id = None
    event_name = None
    if 'id' in df.columns and len(df) > 0:
        zoom_meeting_id = str(df.iloc[0]['id'])
    if 'topic' in df.columns and len(df) > 0:
        event_name = df.iloc[0]['topic']

    if existing_event_id:
        event_id = existing_event_id
        logger.info(f"Using existing event ID: {event_id}")
    else:
        event_id = create_event(
            event_date=event_date,
            source='zoom',
            event_name=event_name,
            zoom_meeting_id=zoom_meeting_id,
            file_name=file_name
        )
        logger.info(f"Created new event ID: {event_id}")

    # Aggregate attendance by email
    # Structure: {email: {'name': str, 'sessions': [{'join': datetime, 'leave': datetime, 'duration': int}]}}
    attendance_by_email = defaultdict(lambda: {'name': None, 'sessions': []})

    for idx, row in df.iterrows():
        email = normalize_email(row.get('email'))

        # Skip rows without email
        if not email:
            stats['skipped_no_email'] += 1
            continue

        # Skip host
        if host_email and email == host_email:
            stats['skipped_host'] += 1
            continue

        name = row.get('name (original name)', row.get('name', ''))
        if host_name and name and host_name in str(name):
            # Additional check - skip if name contains "(Host)"
            if '(host)' in str(name).lower():
                stats['skipped_host'] += 1
                continue

        # Get duration - use participant_duration if available, else try to parse
        duration = 0
        if 'participant_duration' in df.columns:
            duration = int(row.get('participant_duration', 0) or 0)
        elif 'duration (minutes)' in df.columns:
            # This might be the meeting duration, but use it as fallback
            duration = int(row.get('duration (minutes)', 0) or 0)

        # Get join/leave times
        join_time = row.get('join time', '')
        leave_time = row.get('leave time', '')

        # Store session
        if not attendance_by_email[email]['name']:
            attendance_by_email[email]['name'] = normalize_name(name)

        attendance_by_email[email]['sessions'].append({
            'join_time': str(join_time),
            'leave_time': str(leave_time),
            'duration': duration
        })

    # Process aggregated attendance
    total = len(attendance_by_email)
    processed = 0

    for email, data in attendance_by_email.items():
        if progress_callback and processed % 10 == 0:
            progress_callback(processed / max(total, 1))

        name = data['name']
        sessions = data['sessions']

        # Aggregate metrics
        total_duration = sum(s['duration'] for s in sessions)
        join_frequency = len(sessions)

        # Get first join and last leave
        join_times = [s['join_time'] for s in sessions if s['join_time']]
        leave_times = [s['leave_time'] for s in sessions if s['leave_time']]

        first_join = min(join_times) if join_times else None
        last_leave = max(leave_times) if leave_times else None

        stats['total_duration_minutes'] += total_duration

        # Find or create unified user
        existing_user = find_user_by_email_or_phone(email, None)

        if existing_user:
            user_id = existing_user['id']
            merge_user_data(user_id, name, email, None)
            stats['existing_users'] += 1
        else:
            user_id = create_user(name, email, None)
            stats['new_users'] += 1

        # Create or update attendance record
        create_or_update_attendance(
            event_id=event_id,
            unified_user_id=user_id,
            total_duration_minutes=total_duration,
            join_frequency=join_frequency,
            first_join_time=first_join,
            last_leave_time=last_leave,
            raw_name=name,
            raw_email=email
        )
        stats['attendance_created'] += 1

        # Update user's attendance stats
        update_user_attendance_stats(user_id, event_date)

        processed += 1

    stats['unique_attendees'] = len(attendance_by_email)

    # Update event counts
    update_event_counts(event_id, attendees=stats['unique_attendees'])

    if progress_callback:
        progress_callback(1.0)

    stats['event_id'] = event_id
    logger.info(f"Zoom parsing complete: {stats}")
    return stats


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def detect_csv_type(file_obj) -> Optional[str]:
    """
    Detect whether a CSV is a Luma or Zoom file based on columns.

    Returns:
        'luma', 'zoom', or None if unknown
    """
    try:
        # Read just the header
        df = pd.read_csv(file_obj, nrows=0)
        file_obj.seek(0)  # Reset file pointer

        cols = set(c.lower().strip() for c in df.columns)

        # Luma indicators
        luma_indicators = {'api_id', 'approval_status', 'has_joined_event', 'phone_number'}
        if len(cols & luma_indicators) >= 2:
            return 'luma'

        # Zoom indicators
        zoom_indicators = {'host name', 'host email', 'join time', 'leave time', 'name (original name)'}
        if len(cols & zoom_indicators) >= 3:
            return 'zoom'

        return None

    except Exception as e:
        logger.error(f"Error detecting CSV type: {e}")
        return None


def extract_event_date_from_zoom(file_obj) -> Optional[str]:
    """
    Extract the event date from a Zoom CSV based on the Start time field.

    Returns:
        Date string in YYYY-MM-DD format, or None
    """
    try:
        df = pd.read_csv(file_obj, nrows=5)
        file_obj.seek(0)  # Reset file pointer

        df.columns = df.columns.str.strip().str.lower()

        if 'start time' in df.columns and len(df) > 0:
            start_time = df.iloc[0]['start time']
            # Format: "02/22/2026 10:51:37 AM"
            try:
                dt = datetime.strptime(str(start_time), "%m/%d/%Y %I:%M:%S %p")
                return dt.strftime('%Y-%m-%d')
            except:
                pass

        return None

    except Exception as e:
        logger.error(f"Error extracting date from Zoom CSV: {e}")
        return None


def extract_event_date_from_luma(file_obj) -> Optional[str]:
    """
    Extract event date from Luma CSV filename or created_at fields.

    Returns:
        Date string in YYYY-MM-DD format, or None
    """
    try:
        df = pd.read_csv(file_obj, nrows=5)
        file_obj.seek(0)  # Reset file pointer

        df.columns = df.columns.str.strip().str.lower()

        if 'created_at' in df.columns and len(df) > 0:
            # Get the earliest registration date
            dates = []
            for created_at in df['created_at']:
                try:
                    # Format: 2026-02-22T05:34:40.378Z
                    dt = datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
                    dates.append(dt.strftime('%Y-%m-%d'))
                except:
                    pass

            if dates:
                # Return the most common date (event date)
                return max(set(dates), key=dates.count)

        return None

    except Exception as e:
        logger.error(f"Error extracting date from Luma CSV: {e}")
        return None
