"""
Supabase Database Helper for GuitarBro Dashboard

This module provides database operations using Supabase instead of SQLite.
Data persists in the cloud and survives app reboots.
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

# Import config helper for secrets
try:
    from config import get_secret
except ImportError:
    from dotenv import load_dotenv
    load_dotenv()
    def get_secret(key, default=None):
        return os.getenv(key, default)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import supabase
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None  # Define Client as None for type hints when supabase not available
    logger.warning("supabase package not installed. Run: pip install supabase")

# Supabase client singleton
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    """Get or create Supabase client singleton."""
    global _supabase_client

    if not SUPABASE_AVAILABLE:
        logger.error("Supabase package not available")
        return None

    if _supabase_client is not None:
        return _supabase_client

    url = get_secret('SUPABASE_URL')
    key = get_secret('SUPABASE_KEY')

    if not url or not key:
        logger.error("SUPABASE_URL or SUPABASE_KEY not set")
        return None

    try:
        _supabase_client = create_client(url, key)
        logger.info("Supabase client created successfully")
        return _supabase_client
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None


def check_supabase_connection() -> Dict[str, Any]:
    """Check if Supabase connection is working."""
    client = get_supabase_client()

    if not client:
        return {
            "connected": False,
            "error": "Supabase client not available"
        }

    try:
        # Try to fetch from config table
        result = client.table('fb_bot_config').select('key').limit(1).execute()
        return {
            "connected": True,
            "error": None
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e)
        }


# =============================================================================
# COMMENTS CRUD
# =============================================================================

def insert_comment(comment_dict: Dict[str, Any]) -> bool:
    """Insert a new comment into Supabase."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        # Map fields to match Supabase schema
        data = {
            'fb_comment_id': comment_dict.get('fb_comment_id'),
            'parent_comment_id': comment_dict.get('parent_comment_id'),
            'thread_depth': comment_dict.get('thread_depth', 0),
            'fb_post_id': comment_dict.get('fb_post_id'),
            'post_type': comment_dict.get('post_type'),
            'campaign_name': comment_dict.get('campaign_name'),
            'ad_set_name': comment_dict.get('ad_set_name'),
            'ad_name': comment_dict.get('ad_name'),
            'commenter_name': comment_dict.get('commenter_name'),
            'commenter_fb_id': comment_dict.get('commenter_fb_id'),
            'comment_text': comment_dict.get('comment_text'),
            'comment_time': comment_dict.get('comment_time'),
            'category': comment_dict.get('category'),
            'sentiment': comment_dict.get('sentiment'),
            'confidence': comment_dict.get('confidence'),
            'claude_reasoning': comment_dict.get('claude_reasoning'),
            'language_detected': comment_dict.get('language_detected', 'en'),
            'reply_text': comment_dict.get('reply_text'),
            'reply_status': comment_dict.get('reply_status', 'pending'),
            'platform': comment_dict.get('platform', 'facebook'),
        }

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        # Upsert (insert or update)
        client.table('fb_comments').upsert(data, on_conflict='fb_comment_id').execute()
        logger.info(f"Inserted comment {comment_dict.get('fb_comment_id')}")
        return True
    except Exception as e:
        logger.error(f"Error inserting comment: {e}")
        return False


def get_comments(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Query comments with optional filters."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        query = client.table('fb_comments').select('*')

        if filters:
            if filters.get('reply_status'):
                query = query.eq('reply_status', filters['reply_status'])
            if filters.get('category'):
                query = query.eq('category', filters['category'])
            if filters.get('ad_name'):
                query = query.eq('ad_name', filters['ad_name'])
            if filters.get('commenter_fb_id'):
                query = query.eq('commenter_fb_id', filters['commenter_fb_id'])
            if filters.get('fb_post_id'):
                query = query.eq('fb_post_id', filters['fb_post_id'])
            if filters.get('search_text'):
                query = query.ilike('comment_text', f"%{filters['search_text']}%")

        query = query.order('comment_time', desc=True)
        result = query.execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching comments: {e}")
        return []


def get_parent_comments(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Query only parent comments (not replies)."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        query = client.table('fb_comments').select('*')

        # Filter for parent comments only
        query = query.or_('thread_depth.eq.0,thread_depth.is.null')
        query = query.or_('parent_comment_id.eq.,parent_comment_id.is.null')

        if filters:
            if filters.get('reply_status'):
                query = query.eq('reply_status', filters['reply_status'])
            if filters.get('category'):
                query = query.eq('category', filters['category'])
            if filters.get('ad_name'):
                query = query.eq('ad_name', filters['ad_name'])
            if filters.get('search_text'):
                query = query.ilike('comment_text', f"%{filters['search_text']}%")

        query = query.order('comment_time', desc=True)
        result = query.execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching parent comments: {e}")
        return []


def get_thread_replies(parent_comment_id: str) -> List[Dict[str, Any]]:
    """Get all replies to a parent comment."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        result = client.table('fb_comments').select('*').eq(
            'parent_comment_id', parent_comment_id
        ).order('comment_time').execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching replies: {e}")
        return []


def update_comment(fb_comment_id: str, updates: Dict[str, Any]) -> bool:
    """Update fields for a specific comment."""
    client = get_supabase_client()
    if not client or not updates:
        return False

    try:
        client.table('fb_comments').update(updates).eq(
            'fb_comment_id', fb_comment_id
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating comment: {e}")
        return False


def get_comment_by_id(fb_comment_id: str) -> Optional[Dict[str, Any]]:
    """Get a single comment by its Facebook ID."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        result = client.table('fb_comments').select('*').eq(
            'fb_comment_id', fb_comment_id
        ).limit(1).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error fetching comment: {e}")
        return None


def get_commenter_comment_count(commenter_fb_id: str) -> int:
    """Get total number of comments by a commenter."""
    client = get_supabase_client()
    if not client or not commenter_fb_id:
        return 0

    try:
        result = client.table('fb_comments').select(
            'id', count='exact'
        ).eq('commenter_fb_id', commenter_fb_id).execute()
        return result.count or 0
    except Exception as e:
        logger.error(f"Error counting comments: {e}")
        return 0


# =============================================================================
# CONFIG CRUD
# =============================================================================

def get_config(key: str) -> Optional[str]:
    """Get a configuration value."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        result = client.table('fb_bot_config').select('value').eq('key', key).limit(1).execute()
        return result.data[0]['value'] if result.data else None
    except Exception as e:
        logger.error(f"Error fetching config: {e}")
        return None


def set_config(key: str, value: Any) -> bool:
    """Set a configuration value."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        import json
        if not isinstance(value, str):
            value = json.dumps(value)

        client.table('fb_bot_config').upsert({
            'key': key,
            'value': value,
            'updated_at': datetime.now().isoformat()
        }, on_conflict='key').execute()
        return True
    except Exception as e:
        logger.error(f"Error setting config: {e}")
        return False


def get_all_config() -> Dict[str, Any]:
    """Get all configuration as a dictionary."""
    client = get_supabase_client()
    if not client:
        return {}

    try:
        import json
        result = client.table('fb_bot_config').select('*').execute()
        config = {}
        for row in result.data:
            key = row['key']
            value = row['value']
            try:
                config[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                config[key] = value
        return config
    except Exception as e:
        logger.error(f"Error fetching all config: {e}")
        return {}


# =============================================================================
# COMMENTER HISTORY
# =============================================================================

def upsert_commenter_history(
    commenter_fb_id: str,
    commenter_name: str,
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    ad_name: Optional[str] = None
) -> bool:
    """Create or update commenter history record."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        # Check if exists
        result = client.table('fb_commenter_history').select('*').eq(
            'commenter_fb_id', commenter_fb_id
        ).limit(1).execute()

        now = datetime.now().isoformat()

        if result.data:
            # Update existing
            existing = result.data[0]
            updates = {
                'commenter_name': commenter_name,
                'total_comments': (existing.get('total_comments') or 0) + 1,
                'last_comment_at': now,
                'updated_at': now
            }

            # Increment category count
            if category:
                count_key = f"{category}_count"
                if count_key in existing:
                    updates[count_key] = (existing.get(count_key) or 0) + 1

            client.table('fb_commenter_history').update(updates).eq(
                'commenter_fb_id', commenter_fb_id
            ).execute()
        else:
            # Insert new
            data = {
                'commenter_fb_id': commenter_fb_id,
                'commenter_name': commenter_name,
                'total_comments': 1,
                'first_comment_at': now,
                'last_comment_at': now
            }

            if category:
                data[f"{category}_count"] = 1

            client.table('fb_commenter_history').insert(data).execute()

        return True
    except Exception as e:
        logger.error(f"Error upserting commenter history: {e}")
        return False


def get_commenter_history(commenter_fb_id: str) -> Optional[Dict[str, Any]]:
    """Get full history for a commenter."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        result = client.table('fb_commenter_history').select('*').eq(
            'commenter_fb_id', commenter_fb_id
        ).limit(1).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error fetching commenter history: {e}")
        return None


def get_all_commenter_histories(limit: int = 100) -> List[Dict[str, Any]]:
    """Get all commenter histories ordered by total comments."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        result = client.table('fb_commenter_history').select('*').order(
            'total_comments', desc=True
        ).limit(limit).execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching all histories: {e}")
        return []


# =============================================================================
# LOGGING
# =============================================================================

def log_event(
    event_type: str,
    detail: Optional[str] = None,
    fb_comment_id: Optional[str] = None,
    fb_post_id: Optional[str] = None,
    error: Optional[str] = None,
    tokens: int = 0,
    cost: float = 0
) -> bool:
    """Log a bot event."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table('fb_bot_log').insert({
            'event_type': event_type,
            'event_detail': detail,
            'fb_comment_id': fb_comment_id,
            'fb_post_id': fb_post_id,
            'error_message': error,
            'api_tokens_used': tokens,
            'api_cost_inr': cost
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Error logging event: {e}")
        return False


def get_recent_logs(limit: int = 100, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get recent log entries."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        query = client.table('fb_bot_log').select('*')
        if event_type:
            query = query.eq('event_type', event_type)
        result = query.order('created_at', desc=True).limit(limit).execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        return []


# =============================================================================
# TRACKED POSTS
# =============================================================================

def upsert_tracked_post(post_dict: Dict[str, Any]) -> bool:
    """Insert or update a tracked post."""
    client = get_supabase_client()
    if not client:
        return False

    fb_post_id = post_dict.get('fb_post_id')
    if not fb_post_id:
        return False

    try:
        data = {
            'fb_post_id': fb_post_id,
            'post_type': post_dict.get('post_type'),
            'campaign_name': post_dict.get('campaign_name'),
            'ad_set_name': post_dict.get('ad_set_name'),
            'ad_name': post_dict.get('ad_name'),
            'post_message': post_dict.get('post_message'),
            'is_active': post_dict.get('is_active', True)
        }
        data = {k: v for k, v in data.items() if v is not None}

        client.table('fb_posts_tracked').upsert(data, on_conflict='fb_post_id').execute()
        return True
    except Exception as e:
        logger.error(f"Error upserting tracked post: {e}")
        return False


def update_tracked_post(fb_post_id: str, updates: Dict[str, Any]) -> bool:
    """Update a tracked post."""
    client = get_supabase_client()
    if not client or not updates:
        return False

    try:
        client.table('fb_posts_tracked').update(updates).eq(
            'fb_post_id', fb_post_id
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating tracked post: {e}")
        return False


def get_active_tracked_posts() -> List[Dict[str, Any]]:
    """Get all active posts being tracked."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        result = client.table('fb_posts_tracked').select('*').eq(
            'is_active', True
        ).order('last_checked_at', desc=True, nullsfirst=False).execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching tracked posts: {e}")
        return []


# =============================================================================
# STATISTICS
# =============================================================================

def get_stats(date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
    """Get dashboard statistics."""
    client = get_supabase_client()
    if not client:
        return {
            'total_comments': 0,
            'pending': 0,
            'sent': 0,
            'skipped': 0,
            'today_comments': 0,
            'today_replies': 0,
            'status_breakdown': {},
            'category_breakdown': {},
            'sentiment_breakdown': {},
            'total_api_tokens': 0,
            'total_api_cost_inr': 0
        }

    try:
        # Get all parent comments for stats
        query = client.table('fb_comments').select('*')
        query = query.or_('thread_depth.eq.0,thread_depth.is.null')
        result = query.execute()
        comments = result.data

        # Calculate stats
        total = len(comments)
        status_breakdown = {}
        category_breakdown = {}
        sentiment_breakdown = {}
        today = datetime.now().strftime('%Y-%m-%d')
        today_comments = 0
        today_replies = 0

        for c in comments:
            # Status
            status = c.get('reply_status', 'pending')
            status_breakdown[status] = status_breakdown.get(status, 0) + 1

            # Category
            cat = c.get('category', 'other')
            category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

            # Sentiment
            sent = c.get('sentiment', 'neutral')
            sentiment_breakdown[sent] = sentiment_breakdown.get(sent, 0) + 1

            # Today's comments
            comment_time = c.get('comment_time', '')
            if comment_time and today in str(comment_time):
                today_comments += 1

            # Today's replies
            replied_at = c.get('replied_at', '')
            if replied_at and today in str(replied_at) and c.get('reply_status') == 'sent':
                today_replies += 1

        # Get API costs from logs
        logs = client.table('fb_bot_log').select('api_tokens_used,api_cost_inr').execute()
        total_tokens = sum(l.get('api_tokens_used', 0) or 0 for l in logs.data)
        total_cost = sum(l.get('api_cost_inr', 0) or 0 for l in logs.data)

        return {
            'total_comments': total,
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
            'total_api_tokens': total_tokens,
            'total_api_cost_inr': total_cost
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {
            'total_comments': 0,
            'pending': 0,
            'sent': 0,
            'skipped': 0,
            'today_comments': 0,
            'today_replies': 0,
            'status_breakdown': {},
            'category_breakdown': {},
            'sentiment_breakdown': {},
            'total_api_tokens': 0,
            'total_api_cost_inr': 0
        }


def get_unique_ad_names() -> List[str]:
    """Get list of unique ad names from comments."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        result = client.table('fb_comments').select('ad_name').not_.is_('ad_name', 'null').execute()
        names = list(set(c['ad_name'] for c in result.data if c.get('ad_name')))
        return sorted(names)
    except Exception as e:
        logger.error(f"Error fetching ad names: {e}")
        return []
