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
from datetime import datetime, timedelta
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
        'language_detected', 'reply_text', 'reply_status', 'platform'
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
        filters: Same filters as get_comments()

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
                    if result.get('instagram_comments', 0) > 0:
                        st.info(f"Instagram: {result['instagram_comments']} comments")
                    if result['total_cost_inr'] > 0:
                        st.info(f"Claude cost: ₹{result['total_cost_inr']:.2f}")
                else:
                    st.error(result['message'])
                    for err in result.get('errors', [])[:3]:
                        st.warning(err)
            else:
                st.error("Fetcher module not available")

    st.markdown("<br>", unsafe_allow_html=True)

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

    # Category breakdown chart
    st.markdown("<br>", unsafe_allow_html=True)
    render_section_header("Category Breakdown")

    if stats['category_breakdown']:
        df_cat = pd.DataFrame([
            {'Category': k or 'Uncategorized', 'Count': v}
            for k, v in stats['category_breakdown'].items()
        ])
        st.bar_chart(df_cat.set_index('Category'))
    else:
        st.info("No comments categorized yet")

    # Sentiment breakdown
    render_section_header("Sentiment Breakdown")

    if stats['sentiment_breakdown']:
        df_sent = pd.DataFrame([
            {'Sentiment': k or 'Unknown', 'Count': v}
            for k, v in stats['sentiment_breakdown'].items()
        ])
        st.bar_chart(df_sent.set_index('Sentiment'))
    else:
        st.info("No sentiment data yet")


def render_comments_tab():
    """Render the comments review tab."""
    render_section_header("Comment Review Queue")

    # Filters
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        status_filter = st.selectbox(
            "Reply Status",
            ["all", "pending", "approved", "sent", "skipped", "failed"],
            index=1  # Default to pending
        )

    with col2:
        category_filter = st.selectbox(
            "Category",
            ["all"] + [cat for cat, _, _ in COMMENT_CATEGORIES]
        )

    with col3:
        ad_names = get_unique_ad_names()
        ad_filter = st.selectbox("Ad Name", ["all"] + ad_names)

    with col4:
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

    # Get parent comments only (not replies)
    comments = get_parent_comments(filters)

    if not comments:
        st.info("No comments found matching the filters")
        return

    st.markdown(f"<p style='color: #1A1A1A; font-weight: 600; margin: 16px 0; background-color: #F0F7FF; padding: 10px; border-radius: 8px;'>📊 Showing {len(comments)} parent comments</p>", unsafe_allow_html=True)

    # Debug: Show raw data in a simple table first
    if len(comments) > 0:
        import pandas as pd
        df_preview = pd.DataFrame([{
            'Name': c.get('commenter_name', 'Unknown'),
            'Comment': (c.get('comment_text', '') or '')[:50] + '...',
            'Category': c.get('category', '-'),
            'Status': c.get('reply_status', '-')
        } for c in comments[:10]])
        st.dataframe(df_preview, use_container_width=True, hide_index=True)

        st.markdown("<hr style='border-color: #E5E7EB; margin: 20px 0;'>", unsafe_allow_html=True)

    # Display parent comments with their threads
    for comment in comments[:50]:  # Limit to 50 for performance
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
            ad_link = ""
            if fb_post_id and not fb_post_id.startswith('ig_'):
                # Construct Facebook post URL
                # Format: page_id_post_id or just post_id
                if '_' in fb_post_id:
                    page_id, post_id = fb_post_id.split('_', 1)
                    ad_link = f"https://www.facebook.com/{page_id}/posts/{post_id}"
                else:
                    ad_link = f"https://www.facebook.com/{fb_post_id}"
            elif fb_post_id:
                # Instagram media
                ad_link = f"https://www.instagram.com/p/{fb_post_id}/"

            if ad_link:
                st.markdown(f"<span style='color: #6B7280 !important; font-size: 13px;'>📢 Ad: {comment['ad_name']} · <a href='{ad_link}' target='_blank' style='color: #3B82F6 !important;'>View on Facebook ↗</a></span>", unsafe_allow_html=True)
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

    histories = get_all_commenter_histories(limit=100)

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
        with st.expander(f"👤 {h['commenter_name']} ({h['total_comments']} comments)"):
            st.markdown(f"""
            <div style="display: flex; gap: 24px; flex-wrap: wrap; padding: 12px 0;">
                <div style="flex: 1; min-width: 150px;">
                    <p style="color: #1A1A1A; font-weight: 600; margin-bottom: 12px;">Stats</p>
                    <div style="background-color: #F0F7FF; padding: 12px; border-radius: 8px; margin-bottom: 8px;">
                        <span style="color: #528FF0; font-size: 24px; font-weight: 700;">{h['total_comments']}</span>
                        <span style="color: #6B7280; font-size: 13px; display: block;">Total Comments</span>
                    </div>
                    <div style="background-color: #F9FAFB; padding: 12px; border-radius: 8px;">
                        <span style="color: #1A1A1A; font-size: 24px; font-weight: 700;">{h['unique_ads_count']}</span>
                        <span style="color: #6B7280; font-size: 13px; display: block;">Unique Ads</span>
                    </div>
                </div>
                <div style="flex: 1; min-width: 200px;">
                    <p style="color: #1A1A1A; font-weight: 600; margin-bottom: 12px;">Category Counts</p>
            """, unsafe_allow_html=True)

            # Category counts
            for cat, label, emoji in COMMENT_CATEGORIES:
                count = h.get(f'{cat}_count', 0)
                if count > 0:
                    st.markdown(f"<div style='color: #1A1A1A; padding: 4px 0;'>{emoji} {label}: <strong>{count}</strong></div>", unsafe_allow_html=True)

            st.markdown("""
                </div>
                <div style="flex: 1; min-width: 150px;">
                    <p style="color: #1A1A1A; font-weight: 600; margin-bottom: 12px;">Flags</p>
            """, unsafe_allow_html=True)

            # Flags
            has_flags = False
            if h.get('is_repeat_objector'):
                st.markdown("<div style='background-color: #FEE2E2; color: #991B1B; padding: 6px 10px; border-radius: 4px; margin-bottom: 6px; display: inline-block;'>🔴 Repeat Objector</div>", unsafe_allow_html=True)
                has_flags = True
            if h.get('is_potential_customer'):
                st.markdown("<div style='background-color: #D1FAE5; color: #065F46; padding: 6px 10px; border-radius: 4px; margin-bottom: 6px; display: inline-block;'>🟢 Potential Customer</div>", unsafe_allow_html=True)
                has_flags = True
            if h.get('is_troll'):
                st.markdown("<div style='background-color: #FEF3C7; color: #92400E; padding: 6px 10px; border-radius: 4px; margin-bottom: 6px; display: inline-block;'>⚠️ Possible Troll</div>", unsafe_allow_html=True)
                has_flags = True
            if not has_flags:
                st.markdown("<span style='color: #9CA3AF;'>No flags</span>", unsafe_allow_html=True)

            st.markdown("</div></div>", unsafe_allow_html=True)

            # Timestamps
            st.markdown(f"""
            <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #E5E7EB;">
                <span style="color: #6B7280; font-size: 13px;">First seen: {format_datetime(h.get('first_comment_at'))} · Last seen: {format_datetime(h.get('last_comment_at'))}</span>
            </div>
            """, unsafe_allow_html=True)


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
