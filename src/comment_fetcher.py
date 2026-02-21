"""
Comment Fetcher - Orchestrates the fetch → classify → store pipeline

This module connects:
1. Facebook API (fetch comments)
2. Claude Classifier (categorize + generate replies)
3. Database (store results)
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

# Import config helper for secrets
try:
    from config import get_secret
except ImportError:
    import os as _os
    from dotenv import load_dotenv
    load_dotenv()
    def get_secret(key, default=None):
        return _os.getenv(key, default)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import our modules
try:
    from facebook_api import FacebookAPI, format_comment_for_storage, FacebookAPIError
    FACEBOOK_API_AVAILABLE = True
except ImportError as e:
    logger.warning(f"facebook_api not available: {e}")
    FACEBOOK_API_AVAILABLE = False

try:
    from comment_classifier import get_classifier, check_classifier_status
    CLASSIFIER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"comment_classifier not available: {e}")
    CLASSIFIER_AVAILABLE = False

from fb_comment_bot_module import (
    insert_comment,
    get_comment_by_id,
    upsert_commenter_history,
    upsert_tracked_post,
    update_tracked_post,
    log_event,
    get_config_typed
)


# =============================================================================
# CONNECTION STATUS
# =============================================================================

def check_facebook_connection() -> Dict[str, Any]:
    """
    Check if Facebook API connection is working.

    Returns:
        {
            "connected": bool,
            "page_name": str or None,
            "page_id": str or None,
            "error": str or None
        }
    """
    if not FACEBOOK_API_AVAILABLE:
        return {
            "connected": False,
            "page_name": None,
            "page_id": None,
            "error": "facebook_api module not available"
        }

    page_id = get_secret('FACEBOOK_PAGE_ID')
    token = get_secret('FACEBOOK_PAGE_ACCESS_TOKEN')

    if not page_id or not token:
        return {
            "connected": False,
            "page_name": None,
            "page_id": None,
            "error": "FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN not set in .env"
        }

    try:
        api = FacebookAPI(page_id=page_id, access_token=token)
        page_info = api.get_page_info()

        return {
            "connected": True,
            "page_name": page_info.get('name'),
            "page_id": page_info.get('id'),
            "error": None
        }
    except FacebookAPIError as e:
        return {
            "connected": False,
            "page_name": None,
            "page_id": None,
            "error": str(e)
        }
    except Exception as e:
        return {
            "connected": False,
            "page_name": None,
            "page_id": None,
            "error": f"Unexpected error: {str(e)}"
        }


def check_all_connections() -> Dict[str, Any]:
    """Check all API connections."""
    fb_status = check_facebook_connection()
    ig_status = check_instagram_connection()
    claude_status = check_classifier_status() if CLASSIFIER_AVAILABLE else {
        "ready": False,
        "message": "Classifier module not available"
    }

    return {
        "facebook": fb_status,
        "instagram": ig_status,
        "claude": claude_status,
        "all_ready": fb_status["connected"] and claude_status.get("ready", False)
    }


# =============================================================================
# HELPER: FETCH ACTIVE ADS
# =============================================================================

def get_active_ad_posts() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetch post IDs from ads that had delivery (spend > 0) in the last 7 days.
    Also fetches Instagram media IDs for ads with Instagram placements.

    Returns:
        Tuple of (list of ad post info, error message or None)
    """
    import requests

    user_token = get_secret('FACEBOOK_USER_ACCESS_TOKEN')
    ad_account_id = get_secret('FACEBOOK_AD_ACCOUNT_ID')
    page_id = get_secret('FACEBOOK_PAGE_ID')

    if not user_token or not ad_account_id:
        return [], "FACEBOOK_USER_ACCESS_TOKEN or FACEBOOK_AD_ACCOUNT_ID not set in .env"

    try:
        # Step 1: Get ads that had delivery (spend > 0) in the last 7 days INCLUDING today
        # Use time_range instead of date_preset to include today's date
        import json
        today = datetime.now().strftime('%Y-%m-%d')
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        insights_url = f"https://graph.facebook.com/v21.0/{ad_account_id}/insights"
        insights_params = {
            'level': 'ad',
            'fields': 'ad_id,ad_name,spend',
            'time_range': json.dumps({'since': seven_days_ago, 'until': today}),
            'limit': 500,
            'access_token': user_token
        }

        insights_resp = requests.get(insights_url, params=insights_params)
        insights_data = insights_resp.json()

        if 'error' in insights_data:
            return [], f"Insights API error: {insights_data['error'].get('message', 'Unknown')}"

        # Filter ads with actual spend > 0
        ads_with_delivery = {}
        for insight in insights_data.get('data', []):
            spend = float(insight.get('spend', 0))
            if spend > 0:
                ad_id = insight.get('ad_id')
                ads_with_delivery[ad_id] = {
                    'ad_id': ad_id,
                    'ad_name': insight.get('ad_name', 'Unknown'),
                    'spend': spend
                }

        if not ads_with_delivery:
            logger.info("No ads with delivery in the last 7 days")
            return [], None

        logger.info(f"Found {len(ads_with_delivery)} ads with delivery in last 7 days")

        # Step 2: Get creative details (post IDs) for these ads
        ad_ids = list(ads_with_delivery.keys())
        ads = []

        # Batch fetch ad details (up to 50 per request to avoid URL length limits)
        for i in range(0, len(ad_ids), 50):
            batch_ids = ad_ids[i:i+50]
            url = f"https://graph.facebook.com/v21.0/"
            params = {
                'ids': ','.join(batch_ids),
                'fields': 'id,name,status,effective_status,creative{object_story_id,effective_object_story_id,effective_instagram_media_id}',
                'access_token': user_token
            }

            resp = requests.get(url, params=params)
            data = resp.json()

            if 'error' in data:
                logger.warning(f"Error fetching ad batch: {data['error'].get('message', 'Unknown')}")
                continue

            # data is a dict keyed by ad_id
            for ad_id, ad_data in data.items():
                if isinstance(ad_data, dict) and 'id' in ad_data:
                    ads.append(ad_data)

        # Extract unique post IDs and IG media IDs
        ad_posts = []
        seen_post_ids = set()
        seen_ig_media_ids = set()

        for ad in ads:
            creative = ad.get('creative', {})
            post_id = creative.get('object_story_id') or creative.get('effective_object_story_id')
            ig_media_id = creative.get('effective_instagram_media_id')

            # Skip posts from pages we don't have access to
            if post_id:
                post_page_id = post_id.split('_')[0]
                if post_page_id != page_id:
                    # This post is on a different page - skip FB but keep IG
                    if ig_media_id and ig_media_id not in seen_ig_media_ids:
                        seen_ig_media_ids.add(ig_media_id)
                        ad_posts.append({
                            'post_id': None,  # Skip FB fetch
                            'ad_name': ad.get('name', 'Unknown Ad'),
                            'ad_id': ad.get('id'),
                            'ig_media_id': ig_media_id
                        })
                    continue

            ad_info = {
                'post_id': post_id,
                'ad_name': ad.get('name', 'Unknown Ad'),
                'ad_id': ad.get('id'),
                'ig_media_id': ig_media_id
            }

            # Add if we have either a new FB post or a new IG media
            if post_id and post_id not in seen_post_ids:
                seen_post_ids.add(post_id)
                if ig_media_id:
                    seen_ig_media_ids.add(ig_media_id)
                ad_posts.append(ad_info)
            elif ig_media_id and ig_media_id not in seen_ig_media_ids:
                # Ad with only IG placement (no FB post)
                seen_ig_media_ids.add(ig_media_id)
                ad_posts.append(ad_info)

        logger.info(f"Found {len(ad_posts)} unique posts from {len(ads)} active ads ({len(seen_ig_media_ids)} with IG)")
        return ad_posts, None

    except Exception as e:
        return [], f"Error fetching active ads: {str(e)}"


# =============================================================================
# HELPER: FETCH INSTAGRAM COMMENTS FROM AD MEDIA
# =============================================================================

def _get_ig_business_username() -> Optional[str]:
    """Get the Instagram Business Account username for the connected page."""
    import requests

    user_token = get_secret('FACEBOOK_USER_ACCESS_TOKEN')
    page_id = get_secret('FACEBOOK_PAGE_ID')

    if not user_token or not page_id:
        return None

    try:
        # Get Instagram Business Account linked to the page
        url = f"https://graph.facebook.com/v21.0/{page_id}?fields=instagram_business_account{{username}}&access_token={user_token}"
        resp = requests.get(url)
        data = resp.json()

        if 'instagram_business_account' in data:
            return data['instagram_business_account'].get('username')
        return None
    except Exception as e:
        logger.warning(f"Could not get IG business username: {e}")
        return None


def _fetch_ig_comments_for_media(
    ig_media_id: str,
    ad_name: Optional[str] = None,
    ad_id: Optional[str] = None,
    since: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Fetch Instagram comments for a specific media ID (from ad creative).
    Only fetches PARENT comments (not replies) from customers (not page's own replies).

    Args:
        ig_media_id: The Instagram media ID from the ad's effective_instagram_media_id
        ad_name: Name of the ad for context
        ad_id: ID of the ad
        since: Only fetch comments after this datetime

    Returns:
        List of comment data dicts ready for storage
    """
    import requests

    user_token = get_secret('FACEBOOK_USER_ACCESS_TOKEN')
    if not user_token:
        return []

    # Get our Instagram username to filter out our own replies
    ig_username = _get_ig_business_username()

    try:
        # Fetch comments with replies field to get thread info
        url = f"https://graph.facebook.com/v21.0/{ig_media_id}/comments"
        params = {
            'fields': 'id,text,timestamp,username,replies{id,text,timestamp,username}',
            'access_token': user_token
        }
        resp = requests.get(url, params=params)
        data = resp.json()

        if 'error' in data:
            logger.warning(f"Error fetching IG comments for {ig_media_id}: {data['error'].get('message')}")
            return []

        comments = data.get('data', [])
        result = []

        for comment in comments:
            username = comment.get('username', '')

            # Skip if this comment is from our own Instagram account
            if ig_username and username.lower() == ig_username.lower():
                continue

            # Filter by date if specified
            timestamp_str = comment.get('timestamp', '')
            if timestamp_str and since:
                try:
                    comment_time = datetime.fromisoformat(timestamp_str.replace('+0000', '+00:00').replace('Z', '+00:00'))
                    if comment_time.replace(tzinfo=None) < since:
                        continue  # Skip old comments
                except Exception as e:
                    logger.warning(f"Error parsing IG timestamp {timestamp_str}: {e}")

            ig_comment_id = f"ig_{comment.get('id')}"

            # Add parent comment
            comment_data = {
                'fb_comment_id': ig_comment_id,
                'fb_post_id': f"ig_{ig_media_id}",
                'comment_text': comment.get('text', ''),
                'commenter_name': username or 'Unknown',
                'commenter_fb_id': username,  # Instagram uses username
                'comment_time': timestamp_str,
                'post_type': 'instagram_ad',
                'ad_name': ad_name or 'Instagram Ad',
                'ad_id': ad_id,
                'platform': 'instagram',
                'parent_comment_id': None,
                'thread_depth': 0
            }
            result.append(comment_data)

            # Fetch and add replies (threaded comments) - skip page's own replies
            replies = comment.get('replies', {}).get('data', [])
            for reply in replies:
                reply_username = reply.get('username', '')

                # Skip if this reply is from our own Instagram account
                if ig_username and reply_username.lower() == ig_username.lower():
                    continue

                reply_timestamp = reply.get('timestamp', '')
                # Filter replies by date too
                if reply_timestamp and since:
                    try:
                        reply_time = datetime.fromisoformat(reply_timestamp.replace('+0000', '+00:00').replace('Z', '+00:00'))
                        if reply_time.replace(tzinfo=None) < since:
                            continue
                    except Exception:
                        pass

                reply_data = {
                    'fb_comment_id': f"ig_{reply.get('id')}",
                    'fb_post_id': f"ig_{ig_media_id}",
                    'comment_text': reply.get('text', ''),
                    'commenter_name': reply_username or 'Unknown',
                    'commenter_fb_id': reply_username,
                    'comment_time': reply_timestamp,
                    'post_type': 'instagram_ad',
                    'ad_name': ad_name or 'Instagram Ad',
                    'ad_id': ad_id,
                    'platform': 'instagram',
                    'parent_comment_id': ig_comment_id,
                    'thread_depth': 1
                }
                result.append(reply_data)

        parent_count = len([c for c in result if c['thread_depth'] == 0])
        logger.info(f"Fetched {parent_count} IG parent comments for media {ig_media_id}")
        return result

    except Exception as e:
        logger.error(f"Error fetching IG comments for {ig_media_id}: {e}")
        return []


# =============================================================================
# HELPER: FETCH INSTAGRAM COMMENTS (ORGANIC POSTS)
# =============================================================================

def get_instagram_comments(hours_back: int = 48) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetch comments from Instagram media using the Instagram Graph API.

    Args:
        hours_back: How many hours back to fetch comments

    Returns:
        Tuple of (list of comment data, error message or None)
    """
    import requests
    from datetime import datetime, timedelta

    user_token = get_secret('FACEBOOK_USER_ACCESS_TOKEN')
    page_id = get_secret('FACEBOOK_PAGE_ID')

    if not user_token or not page_id:
        return [], "FACEBOOK_USER_ACCESS_TOKEN or FACEBOOK_PAGE_ID not set in .env"

    try:
        # Get Instagram Business Account ID linked to the page
        url = f"https://graph.facebook.com/v21.0/{page_id}?fields=instagram_business_account&access_token={user_token}"
        resp = requests.get(url)
        data = resp.json()

        if 'error' in data:
            return [], f"Instagram API error: {data['error'].get('message', 'Unknown')}"

        if 'instagram_business_account' not in data:
            return [], "No Instagram Business Account linked to this Facebook Page"

        ig_account_id = data['instagram_business_account']['id']
        logger.info(f"Found Instagram Account ID: {ig_account_id}")

        # Get recent media from Instagram (last 30 posts)
        media_url = f"https://graph.facebook.com/v21.0/{ig_account_id}/media?fields=id,caption,timestamp,permalink,comments_count&limit=30&access_token={user_token}"
        media_resp = requests.get(media_url)
        media_data = media_resp.json()

        if 'error' in media_data:
            return [], f"Instagram Media API error: {media_data['error'].get('message', 'Unknown')}"

        media_list = media_data.get('data', [])
        comments_since = datetime.now() - timedelta(hours=hours_back)
        all_comments = []

        for media in media_list:
            media_id = media.get('id')
            comments_count = media.get('comments_count', 0)
            permalink = media.get('permalink', '')
            caption = media.get('caption', '')[:100] if media.get('caption') else ''

            if comments_count == 0:
                continue

            # Fetch comments for this media
            comments_url = f"https://graph.facebook.com/v21.0/{media_id}/comments?fields=id,text,timestamp,username&access_token={user_token}"
            comments_resp = requests.get(comments_url)
            comments_data = comments_resp.json()

            if 'error' in comments_data:
                logger.warning(f"Error fetching comments for media {media_id}: {comments_data['error']}")
                continue

            for comment in comments_data.get('data', []):
                # Parse timestamp and filter by hours_back
                timestamp_str = comment.get('timestamp', '')
                if timestamp_str:
                    try:
                        comment_time = datetime.fromisoformat(timestamp_str.replace('+0000', '+00:00').replace('Z', '+00:00'))
                        # Convert to naive datetime for comparison
                        comment_time_naive = comment_time.replace(tzinfo=None)
                        if comment_time_naive < comments_since:
                            continue  # Skip old comments
                    except Exception as e:
                        logger.warning(f"Error parsing timestamp {timestamp_str}: {e}")

                comment_data = {
                    'fb_comment_id': f"ig_{comment.get('id')}",  # Prefix with ig_ to distinguish
                    'fb_post_id': media_id,
                    'comment_text': comment.get('text', ''),
                    'commenter_name': comment.get('username', 'Unknown'),
                    'commenter_fb_id': comment.get('username', ''),  # Instagram uses username
                    'commented_at': timestamp_str,
                    'post_type': 'instagram',
                    'ad_name': f"Instagram: {caption}" if caption else "Instagram Post",
                    'permalink': permalink,
                    'platform': 'instagram'
                }
                all_comments.append(comment_data)

        logger.info(f"Found {len(all_comments)} Instagram comments from {len(media_list)} posts")
        return all_comments, None

    except Exception as e:
        return [], f"Error fetching Instagram comments: {str(e)}"


def check_instagram_connection() -> Dict[str, Any]:
    """
    Check if Instagram API connection is working.

    Returns:
        {
            "connected": bool,
            "ig_account_id": str or None,
            "ig_username": str or None,
            "error": str or None
        }
    """
    import requests

    user_token = get_secret('FACEBOOK_USER_ACCESS_TOKEN')
    page_id = get_secret('FACEBOOK_PAGE_ID')

    if not user_token or not page_id:
        return {
            "connected": False,
            "ig_account_id": None,
            "ig_username": None,
            "error": "FACEBOOK_USER_ACCESS_TOKEN or FACEBOOK_PAGE_ID not set"
        }

    try:
        # Get Instagram Business Account
        url = f"https://graph.facebook.com/v21.0/{page_id}?fields=instagram_business_account&access_token={user_token}"
        resp = requests.get(url)
        data = resp.json()

        if 'error' in data:
            return {
                "connected": False,
                "ig_account_id": None,
                "ig_username": None,
                "error": data['error'].get('message', 'Unknown error')
            }

        if 'instagram_business_account' not in data:
            return {
                "connected": False,
                "ig_account_id": None,
                "ig_username": None,
                "error": "No Instagram Business Account linked"
            }

        ig_id = data['instagram_business_account']['id']

        # Get Instagram account info
        ig_url = f"https://graph.facebook.com/v21.0/{ig_id}?fields=username,name&access_token={user_token}"
        ig_resp = requests.get(ig_url)
        ig_data = ig_resp.json()

        return {
            "connected": True,
            "ig_account_id": ig_id,
            "ig_username": ig_data.get('username', 'Unknown'),
            "error": None
        }

    except Exception as e:
        return {
            "connected": False,
            "ig_account_id": None,
            "ig_username": None,
            "error": f"Unexpected error: {str(e)}"
        }


# =============================================================================
# FETCH COMMENTS
# =============================================================================

def fetch_and_process_comments(
    hours_back: int = 48,
    posts_limit: int = 25,
    classify_comments: bool = True,
    progress_callback: Optional[callable] = None,
    fetch_from_ads: bool = True,
    fetch_instagram: bool = True
) -> Dict[str, Any]:
    """
    Main function to fetch comments from Facebook and Instagram, classify them, and store in database.

    Args:
        hours_back: How many hours back to fetch comments (default 48 hours)
        posts_limit: Maximum number of posts to check (for organic posts mode)
        classify_comments: Whether to classify with Claude (set False to skip)
        progress_callback: Optional callback function(status_text, progress_pct)
        fetch_from_ads: If True, fetch from active ads; if False, fetch from organic posts
        fetch_instagram: If True, also fetch Instagram comments

    Returns:
        {
            "success": bool,
            "posts_checked": int,
            "comments_fetched": int,
            "comments_new": int,
            "comments_classified": int,
            "instagram_comments": int,
            "total_cost_inr": float,
            "errors": list,
            "message": str
        }
    """
    import requests

    def update_progress(text: str, pct: float = 0):
        if progress_callback:
            progress_callback(text, pct)
        logger.info(text)

    result = {
        "success": False,
        "posts_checked": 0,
        "comments_fetched": 0,
        "comments_new": 0,
        "comments_classified": 0,
        "instagram_comments": 0,
        "total_cost_inr": 0.0,
        "errors": [],
        "message": ""
    }

    # Check connections
    update_progress("Checking connections...", 0.05)

    if not FACEBOOK_API_AVAILABLE:
        result["message"] = "Facebook API module not available"
        result["errors"].append(result["message"])
        return result

    fb_status = check_facebook_connection()
    if not fb_status["connected"]:
        result["message"] = f"Facebook connection failed: {fb_status['error']}"
        result["errors"].append(result["message"])
        return result

    # Log fetch start
    log_event("fetch_started", f"Fetching comments from last {hours_back} hours (ads={fetch_from_ads})")

    try:
        # Initialize Facebook API
        update_progress("Connecting to Facebook...", 0.1)
        api = FacebookAPI()

        comments_since_date = datetime.now() - timedelta(hours=hours_back)

        # Determine which posts to check
        if fetch_from_ads:
            # FETCH FROM ACTIVE ADS
            update_progress("Fetching active ads...", 0.15)
            ad_posts, error = get_active_ad_posts()

            if error:
                result["errors"].append(error)
                logger.warning(f"Could not fetch ads: {error}, falling back to organic posts")
                posts = api.get_page_posts(limit=posts_limit)
                post_info = [{'post_id': p.get('id'), 'ad_name': None} for p in posts]
            else:
                post_info = ad_posts
        else:
            # FETCH FROM ORGANIC POSTS
            update_progress("Fetching organic posts...", 0.15)
            posts = api.get_page_posts(limit=posts_limit)
            post_info = [{'post_id': p.get('id'), 'ad_name': None, 'ad_id': None} for p in posts]

        result["posts_checked"] = len(post_info)

        if not post_info:
            result["success"] = True
            result["message"] = "No posts/ads found to check"
            return result

        update_progress(f"Found {len(post_info)} ad posts, fetching comments...", 0.2)

        # Get classifier if needed
        classifier = None
        if classify_comments and CLASSIFIER_AVAILABLE:
            claude_status = check_classifier_status()
            if claude_status.get("ready"):
                classifier = get_classifier()
            else:
                logger.warning(f"Classifier not ready: {claude_status.get('message')}")
                result["errors"].append(f"Classifier not ready: {claude_status.get('message')}")

        # Process each post/ad
        all_new_comments = []

        for i, info in enumerate(post_info):
            post_id = info.get('post_id')
            ad_name = info.get('ad_name')
            ad_id = info.get('ad_id')
            post_type = "ad" if ad_name else "organic"

            # Calculate progress
            progress = 0.2 + (0.5 * (i / len(post_info)))
            if ad_name:
                update_progress(f"Checking ad {i+1}/{len(post_info)}: {ad_name[:30]}...", progress)
            else:
                update_progress(f"Checking post {i+1}/{len(post_info)}...", progress)

            # Track this post
            upsert_tracked_post({
                "fb_post_id": post_id,
                "post_type": post_type,
                "post_message": ad_name or ""
            })

            try:
                # Fetch FACEBOOK comments for this post (only from last hours_back hours)
                if post_id:
                    page_id = get_secret('FACEBOOK_PAGE_ID')
                    comments = api.get_post_comments(post_id, since=comments_since_date, limit=100)
                    result["comments_fetched"] += len(comments)

                    # Process each Facebook comment - ONLY parent comments (not replies)
                    for comment in comments:
                        fb_comment_id = comment.get('id')
                        from_data = comment.get('from', {})
                        commenter_id = from_data.get('id', '')
                        parent = comment.get('parent')

                        # Skip if this is a reply (has parent) - we'll fetch replies separately
                        if parent:
                            continue

                        # Skip if this comment is from the GuitarBro page itself
                        if commenter_id == page_id:
                            continue

                        # Check if already in database
                        existing = get_comment_by_id(fb_comment_id)
                        if existing:
                            continue  # Skip already processed comments

                        # Format for storage
                        comment_data = format_comment_for_storage(
                            comment=comment,
                            post_id=post_id,
                            post_type=post_type
                        )

                        # Add ad info if available
                        comment_data['platform'] = 'facebook'
                        if ad_name:
                            comment_data['ad_name'] = ad_name
                        if ad_id:
                            comment_data['ad_id'] = ad_id

                        all_new_comments.append(comment_data)
                        result["comments_new"] += 1

                        # Fetch replies (thread) for this parent comment
                        reply_count = comment.get('comment_count', 0)
                        if reply_count > 0:
                            try:
                                replies = api.get_comment_replies(fb_comment_id, limit=50)
                                for reply in replies:
                                    reply_id = reply.get('id')
                                    reply_from = reply.get('from', {})
                                    reply_commenter_id = reply_from.get('id', '')

                                    # Skip page's own replies
                                    if reply_commenter_id == page_id:
                                        continue

                                    # Check if reply already in database
                                    if get_comment_by_id(reply_id):
                                        continue

                                    # Format reply for storage
                                    reply_data = format_comment_for_storage(
                                        comment=reply,
                                        post_id=post_id,
                                        post_type=post_type
                                    )
                                    reply_data['parent_comment_id'] = fb_comment_id
                                    reply_data['thread_depth'] = 1
                                    reply_data['platform'] = 'facebook'
                                    if ad_name:
                                        reply_data['ad_name'] = ad_name
                                    if ad_id:
                                        reply_data['ad_id'] = ad_id

                                    all_new_comments.append(reply_data)
                            except Exception as e:
                                logger.warning(f"Error fetching replies for {fb_comment_id}: {e}")

                    # Update tracked post
                    update_tracked_post(post_id, {
                        "last_checked_at": datetime.now().isoformat(),
                        "total_comments_fetched": len(comments)
                    })

                # Fetch INSTAGRAM comments if ad has IG placement
                ig_media_id = info.get('ig_media_id')
                if ig_media_id and fetch_instagram:
                    ig_comments = _fetch_ig_comments_for_media(
                        ig_media_id=ig_media_id,
                        ad_name=ad_name,
                        ad_id=ad_id,
                        since=comments_since_date
                    )
                    for ig_comment in ig_comments:
                        existing = get_comment_by_id(ig_comment['fb_comment_id'])
                        if existing:
                            continue
                        all_new_comments.append(ig_comment)
                        result["comments_new"] += 1
                        result["instagram_comments"] += 1

            except FacebookAPIError as e:
                logger.error(f"Error fetching comments for post {post_id}: {e}")
                result["errors"].append(f"Post {post_id}: {str(e)}")
                continue

        # Note: Instagram comments from ads are now fetched per-ad above using ig_media_id
        # This section could be used for organic IG posts if needed in the future
        if result["instagram_comments"] > 0:
            logger.info(f"Fetched {result['instagram_comments']} Instagram comments from ad placements")

        update_progress(f"Found {result['comments_new']} new comments (FB + IG), classifying...", 0.7)

        # Classify new comments
        if classifier and all_new_comments:
            for i, comment_data in enumerate(all_new_comments):
                progress = 0.7 + (0.25 * (i / len(all_new_comments)))
                update_progress(f"Classifying comment {i+1}/{len(all_new_comments)}...", progress)

                # Classify
                classification = classifier.classify_comment(
                    comment_text=comment_data.get('comment_text', ''),
                    commenter_name=comment_data.get('commenter_name', 'User'),
                    ad_context=comment_data.get('ad_name') or "Facebook Post"
                )

                if classification.get("success"):
                    comment_data['category'] = classification['category']
                    comment_data['sentiment'] = classification['sentiment']
                    comment_data['confidence'] = classification['confidence']
                    comment_data['claude_reasoning'] = classification.get('reasoning', '')
                    comment_data['reply_text'] = classification.get('suggested_reply', '')
                    comment_data['reply_status'] = 'pending' if classification.get('should_reply', True) else 'skipped'

                    result["comments_classified"] += 1
                    result["total_cost_inr"] += classification.get('cost_inr', 0)
                else:
                    comment_data['category'] = 'other'
                    comment_data['sentiment'] = 'neutral'
                    comment_data['reply_status'] = 'pending'
                    result["errors"].append(f"Classification failed: {classification.get('error', 'Unknown')}")

                # Store in database
                insert_comment(comment_data)

                # Update commenter history
                if comment_data.get('commenter_fb_id'):
                    upsert_commenter_history(
                        commenter_fb_id=comment_data['commenter_fb_id'],
                        commenter_name=comment_data.get('commenter_name', 'Unknown'),
                        category=comment_data.get('category'),
                        sentiment=comment_data.get('sentiment'),
                        ad_name=comment_data.get('ad_name')
                    )
        else:
            # Store without classification
            for comment_data in all_new_comments:
                comment_data['category'] = 'other'
                comment_data['sentiment'] = 'neutral'
                comment_data['reply_status'] = 'pending'
                insert_comment(comment_data)

        update_progress("Complete!", 1.0)

        # Log completion
        log_event(
            "fetch_completed",
            f"Fetched {result['comments_new']} new comments, classified {result['comments_classified']}",
            tokens=classifier.total_input_tokens + classifier.total_output_tokens if classifier else 0,
            cost=result["total_cost_inr"]
        )

        result["success"] = True
        ig_msg = f" ({result['instagram_comments']} from Instagram)" if result['instagram_comments'] > 0 else ""
        result["message"] = (
            f"Processed {result['posts_checked']} FB posts, "
            f"found {result['comments_new']} new comments{ig_msg}, "
            f"classified {result['comments_classified']}"
        )

        return result

    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        result["message"] = f"Fetch failed: {str(e)}"
        result["errors"].append(str(e))
        log_event("fetch_error", error=str(e))
        return result


# =============================================================================
# REPLY TO COMMENT
# =============================================================================

def post_reply_to_facebook(
    fb_comment_id: str,
    reply_text: str,
    shadow_mode: bool = True
) -> Dict[str, Any]:
    """
    Post a reply to a Facebook comment.

    Args:
        fb_comment_id: The comment ID to reply to
        reply_text: The reply message
        shadow_mode: If True, don't actually post (just simulate)

    Returns:
        {
            "success": bool,
            "reply_fb_id": str or None (the new reply's ID),
            "shadow_mode": bool,
            "error": str or None
        }
    """
    if not reply_text or not reply_text.strip():
        return {
            "success": False,
            "reply_fb_id": None,
            "shadow_mode": shadow_mode,
            "error": "Reply text is empty"
        }

    if shadow_mode:
        logger.info(f"[SHADOW MODE] Would reply to {fb_comment_id}: {reply_text[:50]}...")
        log_event("reply_shadow", f"Shadow reply to {fb_comment_id}", fb_comment_id=fb_comment_id)
        return {
            "success": True,
            "reply_fb_id": None,
            "shadow_mode": True,
            "error": None
        }

    if not FACEBOOK_API_AVAILABLE:
        return {
            "success": False,
            "reply_fb_id": None,
            "shadow_mode": False,
            "error": "Facebook API not available"
        }

    try:
        api = FacebookAPI()
        response = api.reply_to_comment(fb_comment_id, reply_text)

        reply_fb_id = response.get('id')
        log_event("reply_sent", f"Replied to {fb_comment_id}", fb_comment_id=fb_comment_id)

        return {
            "success": True,
            "reply_fb_id": reply_fb_id,
            "shadow_mode": False,
            "error": None
        }

    except FacebookAPIError as e:
        log_event("reply_failed", fb_comment_id=fb_comment_id, error=str(e))
        return {
            "success": False,
            "reply_fb_id": None,
            "shadow_mode": False,
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "reply_fb_id": None,
            "shadow_mode": False,
            "error": f"Unexpected error: {str(e)}"
        }
