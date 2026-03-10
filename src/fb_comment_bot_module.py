"""
FB Comment Bot Module for GuitarBro Dashboard

This module provides automated Facebook comment management with:
- Comment fetching and storage from Facebook posts/ads
- AI-powered categorization and sentiment analysis
- Auto-reply functionality with shadow mode
- Commenter history tracking
- Dashboard for review and manual intervention

Database Backend:
- Primary: Supabase (cloud, persistent)
- Fallback: SQLite (local, ephemeral on Streamlit Cloud)

Database Tables:
- fb_comments: All fetched comments with classification
- fb_comment_tags: Multi-tag support for comments
- fb_posts_tracked: Posts/ads being monitored
- fb_commenter_history: Repeat commenter analytics
- fb_dashboard_actions: Queued manual actions
- fb_bot_config: Runtime configuration
- fb_bot_log: Audit and cost tracking
"""

import streamlit as st
import pandas as pd
import sqlite3
import os
import json
import logging
from datetime import datetime, timedelta, timezone

# IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))
from typing import Optional, Dict, List, Any, Tuple

# Import shared styles
from shared_styles import inject_custom_css

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE BACKEND SELECTION
# =============================================================================

# Try to use Supabase first, fall back to SQLite
USE_SUPABASE = False

try:
    from supabase_db import (
        check_supabase_connection,
        insert_comment as supabase_insert_comment,
        get_comments as supabase_get_comments,
        get_parent_comments as supabase_get_parent_comments,
        get_thread_replies as supabase_get_thread_replies,
        update_comment as supabase_update_comment,
        get_comment_by_id as supabase_get_comment_by_id,
        get_commenter_comment_count as supabase_get_commenter_comment_count,
        get_config as supabase_get_config,
        set_config as supabase_set_config,
        get_all_config as supabase_get_all_config,
        upsert_commenter_history as supabase_upsert_commenter_history,
        get_commenter_history as supabase_get_commenter_history,
        get_all_commenter_histories as supabase_get_all_commenter_histories,
        log_event as supabase_log_event,
        get_recent_logs as supabase_get_recent_logs,
        upsert_tracked_post as supabase_upsert_tracked_post,
        update_tracked_post as supabase_update_tracked_post,
        get_active_tracked_posts as supabase_get_active_tracked_posts,
        get_stats as supabase_get_stats,
        get_unique_ad_names as supabase_get_unique_ad_names,
        get_instagram_comments_debug as supabase_get_instagram_comments_debug,
    )

    # Check if Supabase is actually connected
    conn_status = check_supabase_connection()
    if conn_status.get('connected'):
        USE_SUPABASE = True
        logger.info("Using Supabase database backend")
    else:
        logger.warning(f"Supabase not connected: {conn_status.get('error')}. Falling back to SQLite.")
except ImportError as e:
    logger.warning(f"Supabase module not available: {e}. Using SQLite.")

# Import fetcher functions (lazy import to avoid circular deps)
def _get_fetcher_functions():
    """Lazy import of fetcher functions."""
    try:
        from comment_fetcher import (
            check_facebook_connection,
            check_all_connections,
            fetch_and_process_comments,
            post_reply_to_facebook
        )
        return {
            'check_facebook_connection': check_facebook_connection,
            'check_all_connections': check_all_connections,
            'fetch_and_process_comments': fetch_and_process_comments,
            'post_reply_to_facebook': post_reply_to_facebook,
            'available': True
        }
    except ImportError as e:
        logger.warning(f"Could not import comment_fetcher: {e}")
        return {'available': False}

# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

FB_COMMENTS_DB_PATH = "data/fb_comments.db"

# Default bot configuration values
DEFAULT_CONFIG = {
    "shadow_mode": "true",
    "confidence_threshold": "0.80",
    "polling_interval_seconds": "90",
    "claude_model": "claude-haiku-4-5-20251001",
    "max_reply_length": "300",
    "auto_reply_categories": '["price_objection","doubt","product_question","positive"]',
    "never_auto_reply_categories": '["negative","complaint"]',
    "bot_active": "true",
    "system_prompt": "You are GuitarBro's Facebook comment reply assistant. Friendly, encouraging, Hindi-English mix. Categories: price_objection, doubt, product_question, negative, positive, complaint, other.",
    "system_prompt_version": "1"
}

# Category definitions for UI
COMMENT_CATEGORIES = [
    ("price_objection", "Price Objection", "💰"),
    ("doubt", "Doubt/Skepticism", "🤔"),
    ("product_question", "Product Question", "❓"),
    ("positive", "Positive/Interest", "😊"),
    ("negative", "Negative Feedback", "😞"),
    ("complaint", "Complaint", "😤"),
    ("other", "Other", "📝"),
]

SENTIMENT_OPTIONS = ["positive", "neutral", "negative"]

REPLY_STATUS_OPTIONS = ["pending", "approved", "sent", "failed", "skipped"]

# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

def get_db_connection() -> sqlite3.Connection:
    """Get SQLite connection with row factory."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(FB_COMMENTS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_comment_bot_db():
    """
    Initialize all database tables for the FB Comment Bot.
    Creates 7 tables with proper indexes and default config values.
    Skipped when using Supabase (tables already exist in cloud).
    """
    if USE_SUPABASE:
        logger.info("Using Supabase - skipping SQLite initialization")
        return

    # SQLite initialization
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(FB_COMMENTS_DB_PATH)
    cursor = conn.cursor()

    # 1. fb_comments - Main comments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fb_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fb_comment_id TEXT UNIQUE NOT NULL,
            parent_comment_id TEXT,
            thread_depth INTEGER DEFAULT 0,
            fb_post_id TEXT NOT NULL,
            post_type TEXT,
            campaign_name TEXT,
            ad_set_name TEXT,
            ad_name TEXT,
            commenter_name TEXT,
            commenter_fb_id TEXT,
            comment_text TEXT,
            comment_time DATETIME,
            category TEXT,
            sentiment TEXT,
            confidence REAL,
            claude_reasoning TEXT,
            language_detected TEXT DEFAULT 'en',
            reply_text TEXT,
            reply_status TEXT DEFAULT 'pending',
            replied_at DATETIME,
            reply_fb_id TEXT,
            manually_edited_reply TEXT,
            reviewed_by TEXT,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME
        )
    """)

    # 2. fb_comment_tags - Multi-tag support
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fb_comment_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fb_comment_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            source TEXT DEFAULT 'claude',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fb_comment_id, tag)
        )
    """)

    # 3. fb_posts_tracked - Posts being monitored
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fb_posts_tracked (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fb_post_id TEXT UNIQUE NOT NULL,
            post_type TEXT,
            campaign_name TEXT,
            ad_set_name TEXT,
            ad_name TEXT,
            post_message TEXT,
            is_active INTEGER DEFAULT 1,
            last_checked_at DATETIME,
            total_comments_fetched INTEGER DEFAULT 0,
            first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 4. fb_commenter_history - Repeat commenter tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fb_commenter_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commenter_fb_id TEXT UNIQUE NOT NULL,
            commenter_name TEXT,
            total_comments INTEGER DEFAULT 0,
            first_comment_at DATETIME,
            last_comment_at DATETIME,
            price_objection_count INTEGER DEFAULT 0,
            doubt_count INTEGER DEFAULT 0,
            product_question_count INTEGER DEFAULT 0,
            negative_count INTEGER DEFAULT 0,
            positive_count INTEGER DEFAULT 0,
            complaint_count INTEGER DEFAULT 0,
            other_count INTEGER DEFAULT 0,
            dominant_category TEXT,
            dominant_sentiment TEXT,
            avg_sentiment_score REAL DEFAULT 0,
            languages_used TEXT DEFAULT '[]',
            ads_commented_on TEXT DEFAULT '[]',
            unique_ads_count INTEGER DEFAULT 0,
            is_repeat_objector INTEGER DEFAULT 0,
            is_potential_customer INTEGER DEFAULT 0,
            is_troll INTEGER DEFAULT 0,
            manual_notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 5. fb_dashboard_actions - Queued actions from dashboard
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fb_dashboard_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            fb_comment_id TEXT,
            reply_text TEXT,
            status TEXT DEFAULT 'queued',
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            executed_at DATETIME
        )
    """)

    # 6. fb_bot_config - Runtime configuration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fb_bot_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 7. fb_bot_log - Audit and cost tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fb_bot_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            event_detail TEXT,
            fb_comment_id TEXT,
            fb_post_id TEXT,
            error_message TEXT,
            api_tokens_used INTEGER DEFAULT 0,
            api_cost_inr REAL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add platform column if not exists (for existing databases)
    try:
        cursor.execute("ALTER TABLE fb_comments ADD COLUMN platform TEXT DEFAULT 'facebook'")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add ig_permalink column if not exists (for Instagram links)
    try:
        cursor.execute("ALTER TABLE fb_comments ADD COLUMN ig_permalink TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Create indexes for frequently queried columns
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_comments_post_id ON fb_comments(fb_post_id)",
        "CREATE INDEX IF NOT EXISTS idx_comments_reply_status ON fb_comments(reply_status)",
        "CREATE INDEX IF NOT EXISTS idx_comments_category ON fb_comments(category)",
        "CREATE INDEX IF NOT EXISTS idx_comments_comment_time ON fb_comments(comment_time)",
        "CREATE INDEX IF NOT EXISTS idx_comments_commenter_fb_id ON fb_comments(commenter_fb_id)",
        "CREATE INDEX IF NOT EXISTS idx_comments_ad_name ON fb_comments(ad_name)",
        "CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON fb_comments(parent_comment_id)",
        "CREATE INDEX IF NOT EXISTS idx_comments_thread_depth ON fb_comments(thread_depth)",
        "CREATE INDEX IF NOT EXISTS idx_tags_comment_id ON fb_comment_tags(fb_comment_id)",
        "CREATE INDEX IF NOT EXISTS idx_tags_tag ON fb_comment_tags(tag)",
        "CREATE INDEX IF NOT EXISTS idx_posts_is_active ON fb_posts_tracked(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_history_commenter_id ON fb_commenter_history(commenter_fb_id)",
        "CREATE INDEX IF NOT EXISTS idx_actions_status ON fb_dashboard_actions(status)",
        "CREATE INDEX IF NOT EXISTS idx_log_event_type ON fb_bot_log(event_type)",
        "CREATE INDEX IF NOT EXISTS idx_log_created_at ON fb_bot_log(created_at)",
    ]

    for idx_sql in indexes:
        cursor.execute(idx_sql)

    # Insert default config values
    for key, value in DEFAULT_CONFIG.items():
        cursor.execute("""
            INSERT OR IGNORE INTO fb_bot_config (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (key, value))

    conn.commit()
    conn.close()
    logger.info("FB Comment Bot database initialized successfully")


# =============================================================================
# COMMENTS CRUD FUNCTIONS
# =============================================================================

def insert_comment(comment_dict: Dict[str, Any]) -> int:
    """
    Insert a new comment into the database.

    Args:
        comment_dict: Dictionary with comment fields

    Returns:
        The inserted row id (or True for Supabase)
    """
    if USE_SUPABASE:
        return supabase_insert_comment(comment_dict)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    # Build dynamic insert
    fields = [
        'fb_comment_id', 'parent_comment_id', 'thread_depth', 'fb_post_id',
        'post_type', 'campaign_name', 'ad_set_name', 'ad_name',
        'commenter_name', 'commenter_fb_id', 'comment_text', 'comment_time',
        'category', 'sentiment', 'confidence', 'claude_reasoning',
        'language_detected', 'reply_text', 'reply_status', 'platform', 'ig_permalink'
    ]

    present_fields = [f for f in fields if f in comment_dict]
    placeholders = ', '.join(['?' for _ in present_fields])
    field_names = ', '.join(present_fields)
    values = [comment_dict.get(f) for f in present_fields]

    cursor.execute(f"""
        INSERT OR REPLACE INTO fb_comments ({field_names})
        VALUES ({placeholders})
    """, values)

    row_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Inserted comment {comment_dict.get('fb_comment_id')}")
    return row_id


def get_comments(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Query comments with optional filters.

    Args:
        filters: Dictionary with optional keys:
            - reply_status: str
            - category: str
            - date_from: datetime or str
            - date_to: datetime or str
            - ad_name: str
            - commenter_fb_id: str
            - fb_post_id: str
            - search_text: str (searches comment_text)

    Returns:
        List of comment dictionaries
    """
    if USE_SUPABASE:
        return supabase_get_comments(filters)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM fb_comments WHERE 1=1"
    params = []

    if filters:
        if filters.get('reply_status'):
            query += " AND reply_status = ?"
            params.append(filters['reply_status'])

        if filters.get('category'):
            query += " AND category = ?"
            params.append(filters['category'])

        if filters.get('date_from'):
            query += " AND comment_time >= ?"
            params.append(str(filters['date_from']))

        if filters.get('date_to'):
            query += " AND comment_time <= ?"
            params.append(str(filters['date_to']))

        if filters.get('ad_name'):
            query += " AND ad_name = ?"
            params.append(filters['ad_name'])

        if filters.get('commenter_fb_id'):
            query += " AND commenter_fb_id = ?"
            params.append(filters['commenter_fb_id'])

        if filters.get('fb_post_id'):
            query += " AND fb_post_id = ?"
            params.append(filters['fb_post_id'])

        if filters.get('search_text'):
            query += " AND comment_text LIKE ?"
            params.append(f"%{filters['search_text']}%")

    query += " ORDER BY comment_time DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_comment(fb_comment_id: str, updates: Dict[str, Any]) -> bool:
    """
    Update fields for a specific comment.

    Args:
        fb_comment_id: The Facebook comment ID
        updates: Dictionary of field:value pairs to update

    Returns:
        True if update was successful
    """
    if not updates:
        return False

    if USE_SUPABASE:
        return supabase_update_comment(fb_comment_id, updates)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [fb_comment_id]

    cursor.execute(f"""
        UPDATE fb_comments
        SET {set_clause}
        WHERE fb_comment_id = ?
    """, values)

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return success


def get_comment_by_id(fb_comment_id: str) -> Optional[Dict[str, Any]]:
    """Get a single comment by its Facebook ID."""
    if USE_SUPABASE:
        return supabase_get_comment_by_id(fb_comment_id)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM fb_comments WHERE fb_comment_id = ?", (fb_comment_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_commenter_comment_count(commenter_fb_id: str) -> int:
    """Get total number of comments by a commenter."""
    if not commenter_fb_id:
        return 0

    if USE_SUPABASE:
        return supabase_get_commenter_comment_count(commenter_fb_id)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM fb_comments WHERE commenter_fb_id = ?", (commenter_fb_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_thread_replies(parent_comment_id: str) -> List[Dict[str, Any]]:
    """Get all replies to a parent comment."""
    if USE_SUPABASE:
        return supabase_get_thread_replies(parent_comment_id)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM fb_comments
        WHERE parent_comment_id = ?
        ORDER BY comment_time ASC
    """, (parent_comment_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_parent_comments(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Query only parent comments (thread_depth = 0 or parent_comment_id is NULL).

    Args:
        filters: Same filters as get_comments() plus date_from, date_to

    Returns:
        List of parent comment dictionaries
    """
    if USE_SUPABASE:
        return supabase_get_parent_comments(filters)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    # Only get parent comments (not replies)
    query = "SELECT * FROM fb_comments WHERE (thread_depth = 0 OR thread_depth IS NULL) AND (parent_comment_id IS NULL OR parent_comment_id = '')"
    params = []

    if filters:
        if filters.get('reply_status'):
            query += " AND reply_status = ?"
            params.append(filters['reply_status'])

        if filters.get('category'):
            query += " AND category = ?"
            params.append(filters['category'])

        if filters.get('date_from'):
            query += " AND comment_time >= ?"
            params.append(str(filters['date_from']))

        if filters.get('date_to'):
            query += " AND comment_time < ?"
            params.append(str(filters['date_to']))

        if filters.get('ad_name'):
            query += " AND ad_name = ?"
            params.append(filters['ad_name'])

        if filters.get('commenter_fb_id'):
            query += " AND commenter_fb_id = ?"
            params.append(filters['commenter_fb_id'])

        if filters.get('fb_post_id'):
            query += " AND fb_post_id = ?"
            params.append(filters['fb_post_id'])

        if filters.get('search_text'):
            query += " AND comment_text LIKE ?"
            params.append(f"%{filters['search_text']}%")

    query += " ORDER BY comment_time DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# =============================================================================
# TAGS CRUD FUNCTIONS
# =============================================================================

def insert_tag(fb_comment_id: str, tag: str, source: str = 'manual') -> bool:
    """
    Add a tag to a comment.

    Args:
        fb_comment_id: The Facebook comment ID
        tag: Tag string to add
        source: 'claude' or 'manual'

    Returns:
        True if tag was added (False if duplicate)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO fb_comment_tags (fb_comment_id, tag, source)
            VALUES (?, ?, ?)
        """, (fb_comment_id, tag, source))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False  # Duplicate tag

    conn.close()
    return success


def get_tags(fb_comment_id: str) -> List[str]:
    """Get all tags for a comment."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT tag FROM fb_comment_tags
        WHERE fb_comment_id = ?
        ORDER BY created_at
    """, (fb_comment_id,))

    tags = [row['tag'] for row in cursor.fetchall()]
    conn.close()

    return tags


def delete_tag(fb_comment_id: str, tag: str) -> bool:
    """Remove a tag from a comment."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM fb_comment_tags
        WHERE fb_comment_id = ? AND tag = ?
    """, (fb_comment_id, tag))

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return success


# =============================================================================
# COMMENTER HISTORY FUNCTIONS
# =============================================================================

def upsert_commenter_history(
    commenter_fb_id: str,
    commenter_name: str,
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    ad_name: Optional[str] = None
) -> bool:
    """
    Create or update commenter history record.
    Increments category counts and recalculates flags.

    Args:
        commenter_fb_id: Facebook user ID
        commenter_name: Display name
        category: Comment category (for incrementing count)
        sentiment: Comment sentiment
        ad_name: Ad name (for tracking unique ads)

    Returns:
        True if successful
    """
    if USE_SUPABASE:
        return supabase_upsert_commenter_history(commenter_fb_id, commenter_name, category, sentiment, ad_name)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if commenter exists
    cursor.execute("""
        SELECT * FROM fb_commenter_history WHERE commenter_fb_id = ?
    """, (commenter_fb_id,))
    existing = cursor.fetchone()

    now = datetime.now().isoformat()

    if existing:
        # Update existing record
        existing = dict(existing)

        # Increment total comments
        total = existing['total_comments'] + 1

        # Increment category count
        category_counts = {
            'price_objection_count': existing['price_objection_count'],
            'doubt_count': existing['doubt_count'],
            'product_question_count': existing['product_question_count'],
            'negative_count': existing['negative_count'],
            'positive_count': existing['positive_count'],
            'complaint_count': existing['complaint_count'],
            'other_count': existing['other_count'],
        }

        if category:
            count_key = f"{category}_count"
            if count_key in category_counts:
                category_counts[count_key] += 1

        # Update ads list
        ads_list = json.loads(existing['ads_commented_on'] or '[]')
        if ad_name and ad_name not in ads_list:
            ads_list.append(ad_name)

        # Calculate dominant category
        max_count = max(category_counts.values())
        dominant = None
        for cat, count in category_counts.items():
            if count == max_count and count > 0:
                dominant = cat.replace('_count', '')
                break

        # Calculate flags
        is_repeat_objector = 1 if category_counts['price_objection_count'] >= 3 else 0
        is_potential_customer = 1 if (
            category_counts['product_question_count'] >= 2 or
            category_counts['positive_count'] >= 2
        ) else 0
        is_troll = 1 if (
            category_counts['negative_count'] >= 3 or
            category_counts['complaint_count'] >= 3
        ) else 0

        cursor.execute("""
            UPDATE fb_commenter_history SET
                commenter_name = ?,
                total_comments = ?,
                last_comment_at = ?,
                price_objection_count = ?,
                doubt_count = ?,
                product_question_count = ?,
                negative_count = ?,
                positive_count = ?,
                complaint_count = ?,
                other_count = ?,
                dominant_category = ?,
                dominant_sentiment = COALESCE(?, dominant_sentiment),
                ads_commented_on = ?,
                unique_ads_count = ?,
                is_repeat_objector = ?,
                is_potential_customer = ?,
                is_troll = ?,
                updated_at = ?
            WHERE commenter_fb_id = ?
        """, (
            commenter_name, total, now,
            category_counts['price_objection_count'],
            category_counts['doubt_count'],
            category_counts['product_question_count'],
            category_counts['negative_count'],
            category_counts['positive_count'],
            category_counts['complaint_count'],
            category_counts['other_count'],
            dominant, sentiment,
            json.dumps(ads_list), len(ads_list),
            is_repeat_objector, is_potential_customer, is_troll,
            now, commenter_fb_id
        ))
    else:
        # Insert new record
        category_counts = {k: 0 for k in [
            'price_objection_count', 'doubt_count', 'product_question_count',
            'negative_count', 'positive_count', 'complaint_count', 'other_count'
        ]}
        if category:
            count_key = f"{category}_count"
            if count_key in category_counts:
                category_counts[count_key] = 1

        ads_list = [ad_name] if ad_name else []

        cursor.execute("""
            INSERT INTO fb_commenter_history (
                commenter_fb_id, commenter_name, total_comments,
                first_comment_at, last_comment_at,
                price_objection_count, doubt_count, product_question_count,
                negative_count, positive_count, complaint_count, other_count,
                dominant_category, dominant_sentiment,
                ads_commented_on, unique_ads_count
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            commenter_fb_id, commenter_name, now, now,
            category_counts['price_objection_count'],
            category_counts['doubt_count'],
            category_counts['product_question_count'],
            category_counts['negative_count'],
            category_counts['positive_count'],
            category_counts['complaint_count'],
            category_counts['other_count'],
            category, sentiment,
            json.dumps(ads_list), len(ads_list)
        ))

    conn.commit()
    conn.close()
    return True


def get_commenter_history(commenter_fb_id: str) -> Optional[Dict[str, Any]]:
    """Get full history for a commenter."""
    if USE_SUPABASE:
        return supabase_get_commenter_history(commenter_fb_id)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM fb_commenter_history WHERE commenter_fb_id = ?
    """, (commenter_fb_id,))

    row = cursor.fetchone()
    conn.close()

    if row:
        result = dict(row)
        # Parse JSON fields
        result['ads_commented_on'] = json.loads(result.get('ads_commented_on') or '[]')
        result['languages_used'] = json.loads(result.get('languages_used') or '[]')
        return result
    return None


def get_all_commenter_histories(limit: int = 100) -> List[Dict[str, Any]]:
    """Get all commenter histories ordered by total comments."""
    if USE_SUPABASE:
        return supabase_get_all_commenter_histories(limit)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM fb_commenter_history
        ORDER BY total_comments DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        r['ads_commented_on'] = json.loads(r.get('ads_commented_on') or '[]')
        r['languages_used'] = json.loads(r.get('languages_used') or '[]')
        results.append(r)

    return results


# =============================================================================
# DASHBOARD ACTIONS FUNCTIONS
# =============================================================================

def insert_dashboard_action(
    action_type: str,
    fb_comment_id: str,
    reply_text: Optional[str] = None
) -> int:
    """
    Queue a manual action from the dashboard.

    Args:
        action_type: 'reply', 'skip', 'hide', 'delete', etc.
        fb_comment_id: The comment to act on
        reply_text: Reply text if action_type is 'reply'

    Returns:
        The action ID
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO fb_dashboard_actions (action_type, fb_comment_id, reply_text)
        VALUES (?, ?, ?)
    """, (action_type, fb_comment_id, reply_text))

    action_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return action_id


def get_pending_actions() -> List[Dict[str, Any]]:
    """Get all queued actions waiting to be executed."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM fb_dashboard_actions
        WHERE status = 'queued'
        ORDER BY created_at ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_action_status(
    action_id: int,
    status: str,
    error_message: Optional[str] = None
) -> bool:
    """Update the status of a dashboard action."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if status in ['completed', 'failed']:
        cursor.execute("""
            UPDATE fb_dashboard_actions
            SET status = ?, error_message = ?, executed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, error_message, action_id))
    else:
        cursor.execute("""
            UPDATE fb_dashboard_actions
            SET status = ?, error_message = ?
            WHERE id = ?
        """, (status, error_message, action_id))

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return success


# =============================================================================
# CONFIG FUNCTIONS
# =============================================================================

def get_config(key: str) -> Optional[str]:
    """Get a configuration value."""
    if USE_SUPABASE:
        return supabase_get_config(key)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT value FROM fb_bot_config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()

    return row['value'] if row else None


def get_config_typed(key: str, default: Any = None) -> Any:
    """Get a configuration value with type inference."""
    value = get_config(key)
    if value is None:
        return default

    # Try to parse as JSON (for lists, dicts, booleans)
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try to parse as number
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


def set_config(key: str, value: Any) -> bool:
    """Set a configuration value."""
    if USE_SUPABASE:
        return supabase_set_config(key, value)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    # Convert non-strings to JSON
    if not isinstance(value, str):
        value = json.dumps(value)

    cursor.execute("""
        INSERT INTO fb_bot_config (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
    """, (key, value))

    conn.commit()
    conn.close()
    return True


def get_all_config() -> Dict[str, Any]:
    """Get all configuration as a dictionary."""
    if USE_SUPABASE:
        return supabase_get_all_config()

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT key, value FROM fb_bot_config")
    rows = cursor.fetchall()
    conn.close()

    config = {}
    for row in rows:
        key = row['key']
        value = row['value']
        # Try to parse JSON values
        try:
            config[key] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            config[key] = value

    return config


# =============================================================================
# TRACKED POSTS FUNCTIONS
# =============================================================================

def upsert_tracked_post(post_dict: Dict[str, Any]) -> bool:
    """
    Insert or update a tracked post.

    Args:
        post_dict: Dictionary with post fields including fb_post_id

    Returns:
        True if successful
    """
    if USE_SUPABASE:
        return supabase_upsert_tracked_post(post_dict)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    fb_post_id = post_dict.get('fb_post_id')
    if not fb_post_id:
        return False

    cursor.execute("""
        INSERT INTO fb_posts_tracked (
            fb_post_id, post_type, campaign_name, ad_set_name, ad_name,
            post_message, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fb_post_id) DO UPDATE SET
            post_type = COALESCE(excluded.post_type, post_type),
            campaign_name = COALESCE(excluded.campaign_name, campaign_name),
            ad_set_name = COALESCE(excluded.ad_set_name, ad_set_name),
            ad_name = COALESCE(excluded.ad_name, ad_name),
            post_message = COALESCE(excluded.post_message, post_message),
            is_active = COALESCE(excluded.is_active, is_active)
    """, (
        fb_post_id,
        post_dict.get('post_type'),
        post_dict.get('campaign_name'),
        post_dict.get('ad_set_name'),
        post_dict.get('ad_name'),
        post_dict.get('post_message'),
        post_dict.get('is_active', 1)
    ))

    conn.commit()
    conn.close()
    return True


def get_active_tracked_posts() -> List[Dict[str, Any]]:
    """Get all active posts being tracked."""
    if USE_SUPABASE:
        return supabase_get_active_tracked_posts()

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM fb_posts_tracked
        WHERE is_active = 1
        ORDER BY last_checked_at DESC NULLS LAST
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_tracked_post(fb_post_id: str, updates: Dict[str, Any]) -> bool:
    """Update a tracked post."""
    if not updates:
        return False

    if USE_SUPABASE:
        return supabase_update_tracked_post(fb_post_id, updates)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [fb_post_id]

    cursor.execute(f"""
        UPDATE fb_posts_tracked
        SET {set_clause}
        WHERE fb_post_id = ?
    """, values)

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return success


# =============================================================================
# LOGGING FUNCTIONS
# =============================================================================

def log_event(
    event_type: str,
    detail: Optional[str] = None,
    fb_comment_id: Optional[str] = None,
    fb_post_id: Optional[str] = None,
    error: Optional[str] = None,
    tokens: int = 0,
    cost: float = 0
) -> int:
    """
    Log a bot event for audit trail.

    Args:
        event_type: Type of event (fetch, classify, reply, error, etc.)
        detail: Additional details
        fb_comment_id: Related comment ID
        fb_post_id: Related post ID
        error: Error message if any
        tokens: API tokens used
        cost: Cost in INR

    Returns:
        Log entry ID
    """
    if USE_SUPABASE:
        return supabase_log_event(event_type, detail, fb_comment_id, fb_post_id, error, tokens, cost)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO fb_bot_log (
            event_type, event_detail, fb_comment_id, fb_post_id,
            error_message, api_tokens_used, api_cost_inr
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (event_type, detail, fb_comment_id, fb_post_id, error, tokens, cost))

    log_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return log_id


def get_recent_logs(limit: int = 100, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get recent log entries."""
    if USE_SUPABASE:
        return supabase_get_recent_logs(limit, event_type)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    if event_type:
        cursor.execute("""
            SELECT * FROM fb_bot_log
            WHERE event_type = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (event_type, limit))
    else:
        cursor.execute("""
            SELECT * FROM fb_bot_log
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# =============================================================================
# STATISTICS FUNCTIONS
# =============================================================================

def get_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get dashboard statistics.

    Args:
        date_from: Start date filter (ISO format)
        date_to: End date filter (ISO format)

    Returns:
        Dictionary with stats including totals, breakdowns, etc.
    """
    if USE_SUPABASE:
        return supabase_get_stats(date_from, date_to)

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    # Build date filter
    date_filter = ""
    params = []
    if date_from:
        date_filter += " AND comment_time >= ?"
        params.append(date_from)
    if date_to:
        date_filter += " AND comment_time <= ?"
        params.append(date_to)

    # Total parent comments only (not replies)
    parent_filter = " AND (thread_depth = 0 OR thread_depth IS NULL) AND (parent_comment_id IS NULL OR parent_comment_id = '')"
    cursor.execute(f"SELECT COUNT(*) as count FROM fb_comments WHERE 1=1 {parent_filter} {date_filter}", params)
    total_comments = cursor.fetchone()['count']

    # Reply status breakdown
    cursor.execute(f"""
        SELECT reply_status, COUNT(*) as count
        FROM fb_comments
        WHERE 1=1 {date_filter}
        GROUP BY reply_status
    """, params)
    status_breakdown = {row['reply_status']: row['count'] for row in cursor.fetchall()}

    # Category breakdown
    cursor.execute(f"""
        SELECT category, COUNT(*) as count
        FROM fb_comments
        WHERE 1=1 {date_filter}
        GROUP BY category
    """, params)
    category_breakdown = {row['category']: row['count'] for row in cursor.fetchall()}

    # Sentiment breakdown
    cursor.execute(f"""
        SELECT sentiment, COUNT(*) as count
        FROM fb_comments
        WHERE 1=1 {date_filter}
        GROUP BY sentiment
    """, params)
    sentiment_breakdown = {row['sentiment']: row['count'] for row in cursor.fetchall()}

    # Today's stats
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT COUNT(*) as count FROM fb_comments
        WHERE DATE(comment_time) = ?
    """, (today,))
    today_comments = cursor.fetchone()['count']

    cursor.execute("""
        SELECT COUNT(*) as count FROM fb_comments
        WHERE DATE(replied_at) = ? AND reply_status = 'sent'
    """, (today,))
    today_replies = cursor.fetchone()['count']

    # API costs (from logs)
    cursor.execute("""
        SELECT
            SUM(api_tokens_used) as total_tokens,
            SUM(api_cost_inr) as total_cost
        FROM fb_bot_log
    """)
    cost_row = cursor.fetchone()

    conn.close()

    return {
        'total_comments': total_comments,
        'pending': status_breakdown.get('pending', 0),
        'approved': status_breakdown.get('approved', 0),
        'sent': status_breakdown.get('sent', 0),
        'skipped': status_breakdown.get('skipped', 0),
        'failed': status_breakdown.get('failed', 0),
        'status_breakdown': status_breakdown,
        'category_breakdown': category_breakdown,
        'sentiment_breakdown': sentiment_breakdown,
        'today_comments': today_comments,
        'today_replies': today_replies,
        'total_api_tokens': cost_row['total_tokens'] or 0,
        'total_api_cost_inr': cost_row['total_cost'] or 0,
    }


def get_unique_ad_names() -> List[str]:
    """Get list of unique ad names from comments."""
    if USE_SUPABASE:
        return supabase_get_unique_ad_names()

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT ad_name FROM fb_comments
        WHERE ad_name IS NOT NULL AND ad_name != ''
        ORDER BY ad_name
    """)

    names = [row['ad_name'] for row in cursor.fetchall()]
    conn.close()

    return names


# =============================================================================
# UI HELPER FUNCTIONS
# =============================================================================

def render_metric_card(value: str, label: str, sublabel: str = "", color: str = "blue"):
    """Render a metric card matching the dashboard style."""
    color_class = "metric-blue" if color == "blue" else "metric-gray"
    st.markdown(f"""
        <div class="metric-card {color_class}">
            <div class="metric-value">{value}</div>
            <div class="metric-label">{label}</div>
            {f'<div class="metric-sublabel">{sublabel}</div>' if sublabel else ''}
        </div>
    """, unsafe_allow_html=True)


def render_section_header(title: str):
    """Render a section header."""
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)


def format_datetime(dt_str: Optional[str]) -> str:
    """Format datetime string for display."""
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime("%b %d, %Y %I:%M %p")
    except (ValueError, AttributeError):
        return str(dt_str)


def get_category_emoji(category: str) -> str:
    """Get emoji for a category."""
    for cat, name, emoji in COMMENT_CATEGORIES:
        if cat == category:
            return emoji
    return "📝"


def get_sentiment_color(sentiment: str) -> str:
    """Get color for sentiment display."""
    colors = {
        'positive': '#22c55e',
        'neutral': '#6b7280',
        'negative': '#ef4444'
    }
    return colors.get(sentiment, '#6b7280')


# =============================================================================
# MAIN UI COMPONENTS
# =============================================================================

def render_overview_tab():
    """Render the overview/stats tab."""

    # Database backend indicator
    if USE_SUPABASE:
        st.markdown("""
        <div style="background-color: #D1FAE5; padding: 8px 16px; border-radius: 8px; margin-bottom: 16px; border-left: 4px solid #22C55E;">
            <span style="color: #065F46; font-weight: 600;">☁️ Database: Supabase (Cloud)</span>
            <span style="color: #065F46;"> - Data persists across reboots</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background-color: #FEF3C7; padding: 8px 16px; border-radius: 8px; margin-bottom: 16px; border-left: 4px solid #F59E0B;">
            <span style="color: #92400E; font-weight: 600;">💾 Database: SQLite (Local)</span>
            <span style="color: #92400E;"> - Data may be lost on Streamlit Cloud reboot</span>
        </div>
        """, unsafe_allow_html=True)

    # Connection Status & Fetch Section
    render_section_header("Connection & Fetch")

    fetcher = _get_fetcher_functions()

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    with col1:
        st.markdown("<p style='color: #000000; font-weight: 600; margin-bottom: 8px;'>Facebook</p>", unsafe_allow_html=True)
        if st.button("Test FB", key="test_fb_connection", use_container_width=True):
            if fetcher.get('available'):
                with st.spinner("Testing..."):
                    fb_status = fetcher['check_facebook_connection']()
                    if fb_status['connected']:
                        st.success(f"Page: {fb_status['page_name']}")
                        st.session_state['fb_connected'] = True
                    else:
                        st.error(f"Failed: {fb_status['error']}")
                        st.session_state['fb_connected'] = False
            else:
                st.error("Fetcher module not available")

        if st.session_state.get('fb_connected'):
            st.markdown("<span style='color: #22c55e;'>Connected</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='color: #6B7280;'>Not tested</span>", unsafe_allow_html=True)

    with col2:
        st.markdown("<p style='color: #000000; font-weight: 600; margin-bottom: 8px;'>Instagram</p>", unsafe_allow_html=True)
        if st.button("Test IG", key="test_ig_connection", use_container_width=True):
            try:
                from comment_fetcher import check_instagram_connection
                ig_status = check_instagram_connection()
                if ig_status['connected']:
                    st.success(f"@{ig_status['ig_username']}")
                    st.session_state['ig_connected'] = True
                else:
                    st.error(f"{ig_status['error']}")
                    st.session_state['ig_connected'] = False
            except Exception as e:
                st.error(f"Error: {e}")
                st.session_state['ig_connected'] = False

        if st.session_state.get('ig_connected'):
            st.markdown("<span style='color: #22c55e;'>Connected</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='color: #6B7280;'>Not tested</span>", unsafe_allow_html=True)

    with col3:
        st.markdown("<p style='color: #000000; font-weight: 600; margin-bottom: 8px;'>Claude API</p>", unsafe_allow_html=True)
        if st.button("Test Claude", key="test_claude", use_container_width=True):
            try:
                from comment_classifier import check_classifier_status
                status = check_classifier_status()
                if status.get('ready'):
                    st.success("Claude API ready!")
                    st.session_state['claude_ready'] = True
                else:
                    st.warning(status.get('message', 'Not ready'))
                    st.session_state['claude_ready'] = False
            except Exception as e:
                st.error(f"Error: {e}")
                st.session_state['claude_ready'] = False

        if st.session_state.get('claude_ready'):
            st.markdown("<span style='color: #22c55e;'>Ready</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='color: #6B7280;'>Not tested</span>", unsafe_allow_html=True)

    with col4:
        st.markdown("<p style='color: #000000; font-weight: 600; margin-bottom: 8px;'>Fetch All</p>", unsafe_allow_html=True)
        if st.button("Fetch Now", key="fetch_comments", type="primary", use_container_width=True):
            if fetcher.get('available'):
                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_progress(text, pct):
                    status_text.text(text)
                    progress_bar.progress(pct)

                result = fetcher['fetch_and_process_comments'](
                    hours_back=48,
                    posts_limit=50,
                    classify_comments=True,
                    progress_callback=update_progress,
                    fetch_from_ads=True,
                    fetch_instagram=True
                )

                progress_bar.empty()
                status_text.empty()

                if result['success']:
                    st.success(result['message'])
                    # Show detailed breakdown
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        st.metric("Ads Checked", result.get('ads_checked', 0))
                    with col_b:
                        st.metric("FB Comments (New)", result.get('comments_new', 0) - result.get('instagram_comments', 0))
                    with col_c:
                        st.metric("IG Comments (New)", result.get('instagram_comments', 0))

                    # Show IG API details
                    ig_from_api = result.get('ig_comments_from_api', 0)
                    ig_skipped = result.get('ig_comments_skipped_existing', 0)
                    if ig_from_api > 0 or ig_skipped > 0:
                        st.info(f"📷 Instagram API returned {ig_from_api} comments total ({ig_skipped} already in DB)")
                    elif result.get('ads_with_ig', 0) > 0:
                        st.warning(f"📷 {result.get('ads_with_ig', 0)} ads have IG placements but API returned 0 comments")
                    else:
                        st.warning("⚠️ No ads have Instagram media IDs")

                    if result['total_cost_inr'] > 0:
                        st.info(f"Claude cost: ₹{result['total_cost_inr']:.2f}")

                    # Debug: Show Instagram comments in DB
                    if USE_SUPABASE:
                        with st.expander("🔍 Debug: Instagram comments in DB"):
                            try:
                                ig_comments = supabase_get_instagram_comments_debug()
                                if ig_comments:
                                    for c in ig_comments:
                                        st.markdown(f"**@{c.get('commenter_name')}** - `{(c.get('comment_text') or '')[:50]}...`")
                                        st.caption(f"Ad: {(c.get('ad_name') or 'N/A')[:40]} | thread_depth: {c.get('thread_depth')} | time: {c.get('comment_time')}")
                                else:
                                    st.warning("No Instagram comments found in database")
                            except Exception as e:
                                st.error(f"Error: {e}")
                else:
                    st.error(result['message'])
                    for err in result.get('errors', [])[:3]:
                        st.warning(err)
            else:
                st.error("Fetcher module not available")

    st.markdown("<br>", unsafe_allow_html=True)

    # DEBUG: Ads API Inspection
    with st.expander("🔧 Debug: Ads API Inspection"):
        st.markdown("""
        <p style='color: #1A1A1A; margin-bottom: 12px;'>
        Use this to see exactly what the Facebook Ads API returns at each step.
        This helps identify where ads are being filtered out.
        </p>
        """, unsafe_allow_html=True)

        if st.button("🔍 Debug Ads API", key="debug_ads_api"):
            with st.spinner("Fetching detailed API data..."):
                try:
                    from comment_fetcher import debug_ads_api
                    debug_result = debug_ads_api()

                    # Show summary first
                    st.markdown("### Summary")
                    summary = debug_result['summary']
                    cols = st.columns(5)
                    with cols[0]:
                        st.metric("Insights Rows", summary['total_from_insights'])
                    with cols[1]:
                        st.metric("Spend > 0", summary['with_spend_gt_0'])
                    with cols[2]:
                        st.metric("Creative Fetched", summary['creative_fetched'])
                    with cols[3]:
                        st.metric("FB Comments", summary['final_for_fb_comments'])
                    with cols[4]:
                        st.metric("With IG Media", summary['final_with_ig_media'])

                    # Show errors
                    if debug_result['errors']:
                        st.error("**Errors:**")
                        for err in debug_result['errors']:
                            st.warning(err)

                    # Step 1: Insights API
                    st.markdown("### Step 1: Insights API (ads with delivery)")
                    step1 = debug_result['step1_insights_api']
                    st.caption(f"Time range: {step1['request'].get('time_range', 'N/A')}")
                    st.caption(f"Total rows returned: {step1['response'].get('total_rows', 0)}")

                    if step1['ads_with_spend']:
                        df1 = pd.DataFrame(step1['ads_with_spend'])
                        df1 = df1.sort_values('spend', ascending=False)
                        st.dataframe(df1, use_container_width=True, height=200)
                    else:
                        st.warning("No ads with spend > 0")

                    # Step 2: Creative Details
                    st.markdown("### Step 2: Creative Details")
                    step2 = debug_result['step2_creative_details']

                    if step2['ads_by_status']:
                        st.markdown("**Ads by effective_status:**")
                        status_text = ", ".join([f"{k}: {v}" for k, v in step2['ads_by_status'].items()])
                        st.caption(status_text)

                    if step2['ads_fetched']:
                        df2 = pd.DataFrame(step2['ads_fetched'])
                        st.dataframe(df2, use_container_width=True, height=250)
                    else:
                        st.warning("No creative details fetched")

                    # Step 3: Filtering
                    st.markdown("### Step 3: Filtering Results")
                    step3 = debug_result['step3_filtering']

                    st.caption(f"Your Page ID: `{step3['page_id']}`")

                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        skipped = len(step3['ads_skipped_wrong_page'])
                        st.metric("Skipped (wrong page)", skipped, delta_color="inverse" if skipped > 0 else "off")
                    with col_b:
                        no_post = len(step3['ads_no_post_id'])
                        st.metric("No FB Post ID", no_post, delta_color="inverse" if no_post > 0 else "off")
                    with col_c:
                        no_ig = len(step3['ads_no_ig_media_id'])
                        st.metric("No IG Media ID", no_ig)

                    if step3['ads_skipped_wrong_page']:
                        st.markdown("**Ads on different pages (FB comments skipped):**")
                        for ad in step3['ads_skipped_wrong_page'][:5]:
                            st.caption(f"• {ad['ad_name']} - Page: `{ad['post_page_id']}` (yours: `{ad['your_page_id']}`) - IG: {'✓' if ad['has_ig_media'] else '✗'}")

                    # Final ads for comments
                    st.markdown("### Final: Ads to check for comments")
                    if step3['final_ads_for_comments']:
                        df3 = pd.DataFrame(step3['final_ads_for_comments'])
                        st.dataframe(df3, use_container_width=True, height=200)
                    else:
                        st.error("No ads available for comment fetching!")

                except ImportError as e:
                    st.error(f"Could not import debug function: {e}")
                except Exception as e:
                    st.error(f"Debug error: {e}")

    # Stats section
    stats = get_stats()

    render_section_header("Today's Activity")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_metric_card(str(stats['today_comments']), "New Comments", "today")
    with col2:
        render_metric_card(str(stats['today_replies']), "Replies Sent", "today")
    with col3:
        render_metric_card(str(stats['pending']), "Pending Review", "total")
    with col4:
        shadow_mode = get_config_typed('shadow_mode', True)
        mode_text = "Shadow Mode" if shadow_mode else "Live Mode"
        render_metric_card(mode_text, "Bot Status", "auto-reply disabled" if shadow_mode else "auto-reply enabled")

    st.markdown("<br>", unsafe_allow_html=True)
    render_section_header("Overall Statistics")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_metric_card(str(stats['total_comments']), "Total Comments", "all time", "gray")
    with col2:
        render_metric_card(str(stats['sent']), "Replies Sent", "all time", "gray")
    with col3:
        render_metric_card(f"₹{stats['total_api_cost_inr']:.2f}", "API Cost", "all time", "gray")
    with col4:
        render_metric_card(f"{stats['total_api_tokens']:,}", "Tokens Used", "all time", "gray")



def render_comments_tab():
    """Render the comments review tab."""
    render_section_header("Comment Review Queue")

    # Filters - Row 1: Status, Category, Ad Name
    col1, col2, col3 = st.columns(3)

    with col1:
        status_filter = st.selectbox(
            "Reply Status",
            ["all", "pending", "approved", "sent", "skipped", "failed"],
            index=0  # Default to all
        )

    with col2:
        category_filter = st.selectbox(
            "Category",
            ["all"] + [cat for cat, _, _ in COMMENT_CATEGORIES]
        )

    with col3:
        ad_names = get_unique_ad_names()
        ad_filter = st.selectbox("Ad Name", ["all"] + ad_names)

    # Filters - Row 2: Date Range and Search
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        # Date filter - From
        date_from = st.date_input(
            "From Date",
            value=datetime.now() - timedelta(days=7),
            key='comments_date_from'
        )

    with col2:
        # Date filter - To
        date_to = st.date_input(
            "To Date",
            value=datetime.now(),
            key='comments_date_to'
        )

    with col3:
        search_text = st.text_input("Search comments", placeholder="keyword...")

    # Build filters
    filters = {}
    if status_filter != "all":
        filters['reply_status'] = status_filter
    if category_filter != "all":
        filters['category'] = category_filter
    if ad_filter != "all":
        filters['ad_name'] = ad_filter
    if search_text:
        filters['search_text'] = search_text
    if date_from:
        # Convert IST date to UTC for database query (IST is UTC+5:30)
        # Start of day in IST = previous day 18:30 UTC
        date_from_utc = datetime.combine(date_from, datetime.min.time()) - timedelta(hours=5, minutes=30)
        filters['date_from'] = date_from_utc.strftime('%Y-%m-%dT%H:%M:%S+00:00')
    if date_to:
        # End of day in IST = current day 18:30 UTC
        date_to_utc = datetime.combine(date_to + timedelta(days=1), datetime.min.time()) - timedelta(hours=5, minutes=30)
        filters['date_to'] = date_to_utc.strftime('%Y-%m-%dT%H:%M:%S+00:00')

    # Get parent comments only (not replies)
    comments = get_parent_comments(filters)

    # Debug: Show what filters are being applied
    with st.expander("🔍 Debug: Query Info"):
        # Show date range in IST for clarity
        st.write(f"**Date range (IST):** {date_from.strftime('%d %b %Y')} 12:00 AM to {(date_to + timedelta(days=1)).strftime('%d %b %Y')} 12:00 AM")
        st.write(f"**Comments returned:** {len(comments)}")
        if comments:
            # Show platform breakdown
            fb_count = len([c for c in comments if c.get('platform', 'facebook') == 'facebook'])
            ig_count = len([c for c in comments if c.get('platform') == 'instagram'])
            st.write(f"**Facebook:** {fb_count}, **Instagram:** {ig_count}")

        # Also get ALL comments without filters to compare
        if USE_SUPABASE:
            all_comments = supabase_get_instagram_comments_debug()
            st.write(f"**Total IG comments in DB (no filter):** {len(all_comments)}")

    if not comments:
        st.info("No comments found matching the filters")
        return

    # Show total count
    st.markdown(f"""
    <div style='background-color: #F0F7FF; padding: 12px 16px; border-radius: 8px; margin: 16px 0; border-left: 4px solid #3B82F6;'>
        <span style='color: #1A1A1A; font-weight: 600; font-size: 16px;'>📊 Total: {len(comments)} comments</span>
        <span style='color: #6B7280; font-size: 14px; margin-left: 12px;'>({date_from.strftime('%d %b')} - {date_to.strftime('%d %b %Y')})</span>
    </div>
    """, unsafe_allow_html=True)

    # Display parent comments with their threads (one by one)
    for comment in comments[:100]:  # Limit to 100 for performance
        render_comment_card(comment, show_thread=True)


def render_comment_card(comment: Dict[str, Any], show_thread: bool = False):
    """Render a single comment card with actions and optional thread replies."""
    fb_comment_id = comment['fb_comment_id']

    # Get commenter's total comment count
    commenter_fb_id = comment.get('commenter_fb_id', '')
    commenter_count = get_commenter_comment_count(commenter_fb_id) if commenter_fb_id else 0

    # Get thread replies if showing threads
    thread_replies = []
    if show_thread:
        thread_replies = get_thread_replies(fb_comment_id)

    with st.container():
        # Card container with explicit styling
        st.markdown("""
        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px;
                    padding: 16px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
        """, unsafe_allow_html=True)

        # Header row
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            name = comment.get('commenter_name', 'Unknown')
            time = format_datetime(comment.get('comment_time'))
            platform = comment.get('platform', 'facebook')
            platform_icon = '📷' if platform == 'instagram' else '📘'
            # Show commenter name with comment count badge
            count_badge = f"<span style='background-color: #DBEAFE; color: #000000 !important; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin-left: 6px;'>{commenter_count} comments</span>" if commenter_count > 1 else ""
            st.markdown(f"{platform_icon} <span style='color: #1A1A1A; font-weight: 600;'>{name}</span>{count_badge} <span style='color: #6B7280;'>· {time}</span>", unsafe_allow_html=True)

        with col2:
            category = comment.get('category', 'uncategorized')
            emoji = get_category_emoji(category)
            # Category pill with proper colors - Blue background, BLACK text per CSS guidelines
            category_colors = {
                'price_objection': '#FEF3C7',  # Yellow
                'doubt': '#FED7AA',  # Orange
                'product_question': '#DBEAFE',  # Blue
                'positive': '#D1FAE5',  # Green
                'negative': '#FEE2E2',  # Red
                'complaint': '#FECACA',  # Light red
                'other': '#E5E7EB',  # Gray
            }
            bg_color = category_colors.get(category, '#E5E7EB')
            st.markdown(f"<span style='background-color: {bg_color}; color: #000000 !important; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 500;'>{emoji} {category}</span>", unsafe_allow_html=True)

        with col3:
            sentiment = comment.get('sentiment', 'unknown')
            color = get_sentiment_color(sentiment)
            st.markdown(f"<span style='color: {color} !important; font-weight: 500;'>{sentiment}</span>", unsafe_allow_html=True)

        # Comment text - blue for visibility
        comment_text = comment.get('comment_text', '')
        st.markdown(f"""
        <div style="background-color: #F0F7FF; border-left: 4px solid #528FF0; padding: 12px;
                    margin: 12px 0; border-radius: 4px; color: #1A1A1A;">
            <span style="color: #528FF0 !important; font-weight: 500;">💬 Comment:</span><br>
            <span style="color: #1A1A1A !important;">{comment_text}</span>
        </div>
        """, unsafe_allow_html=True)

        # Thread Replies Section (show conversation under parent comment)
        if thread_replies:
            st.markdown(f"""
            <div style="margin: 8px 0 16px 24px; padding-left: 16px; border-left: 2px solid #93C5FD;">
                <span style="color: #6B7280; font-size: 12px; font-weight: 600;">💬 {len(thread_replies)} Thread Replies</span>
            </div>
            """, unsafe_allow_html=True)

            for reply in thread_replies:
                reply_name = reply.get('commenter_name', 'Unknown')
                reply_text = reply.get('comment_text', '')
                reply_time = format_datetime(reply.get('comment_time'))
                reply_platform = reply.get('platform', 'facebook')
                reply_icon = '📷' if reply_platform == 'instagram' else '📘'

                st.markdown(f"""
                <div style="margin: 8px 0 8px 24px; padding: 10px 12px; background-color: #F9FAFB;
                            border-left: 3px solid #93C5FD; border-radius: 4px;">
                    <div style="margin-bottom: 6px;">
                        {reply_icon} <span style="color: #374151; font-weight: 600; font-size: 13px;">{reply_name}</span>
                        <span style="color: #9CA3AF; font-size: 12px;">· {reply_time}</span>
                    </div>
                    <div style="color: #1A1A1A; font-size: 13px;">{reply_text}</div>
                </div>
                """, unsafe_allow_html=True)

        # Ad info with clickable link
        if comment.get('ad_name'):
            fb_post_id = comment.get('fb_post_id', '')
            platform = comment.get('platform', 'facebook')
            ad_link = ""
            link_text = "View on Facebook"

            if platform == 'instagram' or fb_post_id.startswith('ig_'):
                # Instagram - use stored permalink if available
                ig_permalink = comment.get('ig_permalink', '')
                if ig_permalink:
                    ad_link = ig_permalink
                    link_text = "View on Instagram"
            elif fb_post_id:
                # Construct Facebook post URL
                # Format: page_id_post_id or just post_id
                if '_' in fb_post_id:
                    page_id, post_id = fb_post_id.split('_', 1)
                    ad_link = f"https://www.facebook.com/{page_id}/posts/{post_id}"
                else:
                    ad_link = f"https://www.facebook.com/{fb_post_id}"

            if ad_link:
                st.markdown(f"<span style='color: #6B7280 !important; font-size: 13px;'>📢 Ad: {comment['ad_name']} · <a href='{ad_link}' target='_blank' style='color: #3B82F6 !important;'>{link_text} ↗</a></span>", unsafe_allow_html=True)
            else:
                st.markdown(f"<span style='color: #6B7280 !important; font-size: 13px;'>📢 Ad: {comment['ad_name']}</span>", unsafe_allow_html=True)

        # Suggested reply
        if comment.get('reply_text'):
            st.markdown(f"""
            <div style="margin-top: 12px;">
                <span style="color: #1A1A1A; font-weight: 600;">Suggested Reply:</span>
                <div style="background-color: #F0FDF4; border-left: 4px solid #22C55E; padding: 12px;
                            margin-top: 8px; border-radius: 4px; color: #1A1A1A;">
                    {comment.get('reply_text')}
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Actions
        action_col1, action_col2, action_col3, action_col4 = st.columns(4)

        with action_col1:
            if st.button("✅ Approve", key=f"approve_{fb_comment_id}"):
                # Check shadow mode
                shadow_mode = get_config_typed('shadow_mode', True)
                reply_text = comment.get('manually_edited_reply') or comment.get('reply_text', '')

                if reply_text:
                    fetcher = _get_fetcher_functions()
                    if fetcher.get('available'):
                        result = fetcher['post_reply_to_facebook'](
                            fb_comment_id=fb_comment_id,
                            reply_text=reply_text,
                            shadow_mode=shadow_mode
                        )

                        if result['success']:
                            if shadow_mode:
                                update_comment(fb_comment_id, {
                                    'reply_status': 'approved',
                                    'replied_at': datetime.now().isoformat()
                                })
                                st.success("Approved (Shadow mode - not posted)")
                            else:
                                update_comment(fb_comment_id, {
                                    'reply_status': 'sent',
                                    'replied_at': datetime.now().isoformat(),
                                    'reply_fb_id': result.get('reply_fb_id')
                                })
                                st.success("Reply posted to Facebook!")
                        else:
                            st.error(f"Failed: {result.get('error')}")
                    else:
                        update_comment(fb_comment_id, {'reply_status': 'approved'})
                else:
                    st.warning("No reply text to send")

                insert_dashboard_action('reply', fb_comment_id, reply_text)
                st.rerun()

        with action_col2:
            if st.button("⏭️ Skip", key=f"skip_{fb_comment_id}"):
                update_comment(fb_comment_id, {'reply_status': 'skipped'})
                st.rerun()

        with action_col3:
            if st.button("✏️ Edit", key=f"edit_{fb_comment_id}"):
                st.session_state[f'editing_{fb_comment_id}'] = True

        with action_col4:
            # Show commenter history link
            commenter_id = comment.get('commenter_fb_id')
            if commenter_id:
                history = get_commenter_history(commenter_id)
                if history and history['total_comments'] > 1:
                    st.markdown(f"<span style='color: #6B7280; font-size: 13px;'>👤 {history['total_comments']} comments</span>", unsafe_allow_html=True)

        # Edit mode
        if st.session_state.get(f'editing_{fb_comment_id}'):
            new_reply = st.text_area(
                "Edit reply",
                value=comment.get('reply_text', ''),
                key=f"edit_text_{fb_comment_id}"
            )
            if st.button("Save Edit", key=f"save_{fb_comment_id}"):
                update_comment(fb_comment_id, {
                    'manually_edited_reply': new_reply,
                    'reply_text': new_reply
                })
                st.session_state[f'editing_{fb_comment_id}'] = False
                st.rerun()

        # Close card container
        st.markdown("</div>", unsafe_allow_html=True)


def render_commenters_tab():
    """Render the commenter history tab."""
    render_section_header("Commenter History")

    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        filter_type = st.selectbox(
            "Show",
            ["All Commenters", "Repeat Objectors", "Potential Customers", "Trolls"]
        )

    with col2:
        sort_by = st.selectbox(
            "Sort by",
            ["Total Comments", "Recent Activity", "Price Objections"]
        )

    try:
        histories = get_all_commenter_histories(limit=100)
    except Exception as e:
        st.error(f"Error loading commenter histories: {e}")
        return

    # Apply filters
    if filter_type == "Repeat Objectors":
        histories = [h for h in histories if h.get('is_repeat_objector')]
    elif filter_type == "Potential Customers":
        histories = [h for h in histories if h.get('is_potential_customer')]
    elif filter_type == "Trolls":
        histories = [h for h in histories if h.get('is_troll')]

    if not histories:
        st.info("No commenter history available")
        return

    st.markdown(f"<p style='color: #1A1A1A; font-weight: 600;'>{len(histories)} commenters</p>", unsafe_allow_html=True)

    for h in histories:
        try:
            commenter_name = h.get('commenter_name', 'Unknown')
            total_comments = h.get('total_comments', 0)
            unique_ads_count = h.get('unique_ads_count', 0)

            with st.expander(f"👤 {commenter_name} ({total_comments} comments)"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.markdown("<p style='color: #1A1A1A; font-weight: 600;'>Stats</p>", unsafe_allow_html=True)
                    st.metric("Total Comments", total_comments)
                    st.metric("Unique Ads", unique_ads_count)

                with col2:
                    st.markdown("<p style='color: #1A1A1A; font-weight: 600;'>Category Counts</p>", unsafe_allow_html=True)
                    for cat, label, emoji in COMMENT_CATEGORIES:
                        count = h.get(f'{cat}_count', 0) or 0
                        if count > 0:
                            st.markdown(f"{emoji} {label}: **{count}**")

                with col3:
                    st.markdown("<p style='color: #1A1A1A; font-weight: 600;'>Flags</p>", unsafe_allow_html=True)
                    has_flags = False
                    if h.get('is_repeat_objector'):
                        st.markdown("🔴 Repeat Objector")
                        has_flags = True
                    if h.get('is_potential_customer'):
                        st.markdown("🟢 Potential Customer")
                        has_flags = True
                    if h.get('is_troll'):
                        st.markdown("⚠️ Possible Troll")
                        has_flags = True
                    if not has_flags:
                        st.markdown("No flags")

                st.markdown(f"**First seen:** {format_datetime(h.get('first_comment_at'))} · **Last seen:** {format_datetime(h.get('last_comment_at'))}")
        except Exception as e:
            st.warning(f"Error rendering commenter: {e}")


def render_settings_tab():
    """Render the bot settings tab."""
    render_section_header("Bot Configuration")

    config = get_all_config()

    # Shadow Mode Toggle
    st.markdown("<h3 style='color: #1A1A1A;'>🔒 Shadow Mode</h3>", unsafe_allow_html=True)
    shadow_mode = st.toggle(
        "Enable Shadow Mode",
        value=config.get('shadow_mode', True),
        help="In shadow mode, replies are generated but NOT posted to Facebook"
    )
    if shadow_mode != config.get('shadow_mode'):
        set_config('shadow_mode', shadow_mode)
        st.success("Shadow mode updated!")

    if shadow_mode:
        st.info("🔒 Shadow Mode is ON - No replies will be posted to Facebook")
    else:
        st.warning("⚠️ Shadow Mode is OFF - Replies WILL be posted to Facebook")

    st.markdown("---")

    # Confidence Threshold
    st.markdown("<h3 style='color: #1A1A1A;'>🎯 Classification Settings</h3>", unsafe_allow_html=True)

    confidence = st.slider(
        "Confidence Threshold",
        min_value=0.5,
        max_value=1.0,
        value=float(config.get('confidence_threshold', 0.8)),
        step=0.05,
        help="Minimum confidence score for auto-reply"
    )
    if confidence != float(config.get('confidence_threshold', 0.8)):
        set_config('confidence_threshold', str(confidence))

    # Auto-reply categories
    st.markdown("<h3 style='color: #1A1A1A;'>🤖 Auto-Reply Categories</h3>", unsafe_allow_html=True)

    auto_reply_cats = config.get('auto_reply_categories', [])
    if isinstance(auto_reply_cats, str):
        auto_reply_cats = json.loads(auto_reply_cats)

    selected_auto = st.multiselect(
        "Categories that can auto-reply (when not in shadow mode)",
        options=[cat for cat, _, _ in COMMENT_CATEGORIES],
        default=auto_reply_cats
    )
    if selected_auto != auto_reply_cats:
        set_config('auto_reply_categories', selected_auto)

    # Never auto-reply categories
    never_reply_cats = config.get('never_auto_reply_categories', [])
    if isinstance(never_reply_cats, str):
        never_reply_cats = json.loads(never_reply_cats)

    selected_never = st.multiselect(
        "Categories that should NEVER auto-reply",
        options=[cat for cat, _, _ in COMMENT_CATEGORIES],
        default=never_reply_cats
    )
    if selected_never != never_reply_cats:
        set_config('never_auto_reply_categories', selected_never)

    st.markdown("---")

    # Polling settings
    st.markdown("<h3 style='color: #1A1A1A;'>⏱️ Polling Settings</h3>", unsafe_allow_html=True)

    polling_interval = st.number_input(
        "Polling Interval (seconds)",
        min_value=30,
        max_value=600,
        value=int(config.get('polling_interval_seconds', 90)),
        help="How often to check for new comments"
    )
    if polling_interval != int(config.get('polling_interval_seconds', 90)):
        set_config('polling_interval_seconds', str(polling_interval))

    max_reply_length = st.number_input(
        "Max Reply Length (characters)",
        min_value=50,
        max_value=1000,
        value=int(config.get('max_reply_length', 300))
    )
    if max_reply_length != int(config.get('max_reply_length', 300)):
        set_config('max_reply_length', str(max_reply_length))

    st.markdown("---")

    # System Prompt
    st.markdown("<h3 style='color: #1A1A1A;'>📝 System Prompt</h3>", unsafe_allow_html=True)

    current_prompt = config.get('system_prompt', DEFAULT_CONFIG['system_prompt'])
    new_prompt = st.text_area(
        "System prompt for Claude",
        value=current_prompt,
        height=150
    )
    if new_prompt != current_prompt:
        set_config('system_prompt', new_prompt)
        version = int(config.get('system_prompt_version', 1)) + 1
        set_config('system_prompt_version', str(version))
        st.success(f"System prompt updated to version {version}")


def render_logs_tab():
    """Render the activity logs tab."""
    render_section_header("Activity Logs")

    # Filter by event type
    event_type = st.selectbox(
        "Event Type",
        ["all", "fetch", "classify", "reply", "error", "config_change"]
    )

    event_filter = event_type if event_type != "all" else None
    logs = get_recent_logs(limit=100, event_type=event_filter)

    if not logs:
        st.info("No log entries found")
        return

    # Display as table
    df = pd.DataFrame(logs)
    df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')

    # Select columns to display
    display_cols = ['created_at', 'event_type', 'event_detail', 'error_message', 'api_tokens_used']
    available_cols = [c for c in display_cols if c in df.columns]

    st.dataframe(
        df[available_cols],
        use_container_width=True,
        hide_index=True
    )

    # Cost summary
    total_cost = sum(log.get('api_cost_inr', 0) for log in logs)
    total_tokens = sum(log.get('api_tokens_used', 0) for log in logs)

    st.markdown(f"<p style='color: #1A1A1A; font-weight: 600;'>Recent API Usage: {total_tokens:,} tokens · ₹{total_cost:.2f}</p>", unsafe_allow_html=True)


def render_posts_tab():
    """Render the tracked posts tab."""
    render_section_header("Tracked Posts & Ads")

    posts = get_active_tracked_posts()

    if not posts:
        st.info("No posts being tracked. Posts will be added automatically when comments are fetched.")
        return

    for post in posts:
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                ad_name = post.get('ad_name') or post.get('fb_post_id')
                st.markdown(f"<p style='color: #1A1A1A; font-weight: 600; margin: 0;'>{ad_name}</p>", unsafe_allow_html=True)
                if post.get('post_message'):
                    msg = post['post_message'][:100] + "..." if len(post.get('post_message', '')) > 100 else post.get('post_message', '')
                    st.markdown(f"<span style='color: #6B7280; font-size: 13px;'>{msg}</span>", unsafe_allow_html=True)

            with col2:
                st.metric("Comments", post.get('total_comments_fetched', 0))

            with col3:
                last_checked = format_datetime(post.get('last_checked_at'))
                st.markdown(f"<span style='color: #6B7280; font-size: 13px;'>Last checked: {last_checked}</span>", unsafe_allow_html=True)

            st.markdown("<hr style='margin: 5px 0; border-color: #E5E7EB;'>", unsafe_allow_html=True)


# =============================================================================
# MAIN MODULE ENTRY POINT
# =============================================================================

def render_fb_comment_bot_module():
    """
    Main entry point for the FB Comment Bot module.
    Called from app.py when the user navigates to this page.
    """
    # Initialize database on first load
    init_comment_bot_db()

    # Inject shared CSS styles
    inject_custom_css()

    # Add module-specific CSS
    st.markdown("""
        <style>
        .metric-card {
            background-color: #FFFFFF;
            border-radius: 12px;
            padding: 24px;
            text-align: center;
            margin-bottom: 16px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
            border: 1px solid #93C5FD;
        }
        .metric-blue {
            border-left: 4px solid #3B82F6;
        }
        .metric-gray {
            border-left: 4px solid #9CA3AF;
        }
        .metric-value {
            font-size: 32px;
            font-weight: 700;
            color: #000000;
            margin: 0;
            line-height: 1.2;
        }
        .metric-blue .metric-value {
            color: #3B82F6;
        }
        .metric-label {
            font-size: 14px;
            color: #000000;
            margin-top: 8px;
            font-weight: 500;
        }
        .metric-sublabel {
            font-size: 12px;
            color: #374151;
            margin-top: 4px;
        }
        .section-header {
            font-size: 18px;
            font-weight: 600;
            color: #000000;
            margin: 24px 0 16px 0;
            padding-bottom: 8px;
            border-bottom: 1px solid #93C5FD;
        }
        </style>
    """, unsafe_allow_html=True)

    # Tab navigation
    tabs = st.tabs([
        "📊 Overview",
        "💬 Comments",
        "👥 Commenters",
        "📢 Posts",
        "⚙️ Settings",
        "📋 Logs"
    ])

    with tabs[0]:
        render_overview_tab()

    with tabs[1]:
        render_comments_tab()

    with tabs[2]:
        render_commenters_tab()

    with tabs[3]:
        render_posts_tab()

    with tabs[4]:
        render_settings_tab()

    with tabs[5]:
        render_logs_tab()
