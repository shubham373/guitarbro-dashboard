"""
Facebook Graph API Module for FB Comment Bot

This module handles all Facebook Graph API interactions including:
- Fetching posts from a Facebook Page
- Fetching comments on posts/ads
- Posting replies to comments
- Thread tracking (nested replies)

Uses Facebook Graph API v21.0
"""

import os
import time
import logging
import requests
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime

# Import config helper for secrets
try:
    from config import get_secret
except ImportError:
    # Fallback for direct imports
    from dotenv import load_dotenv
    load_dotenv()
    def get_secret(key, default=None):
        return os.getenv(key, default)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

GRAPH_API_BASE_URL = "https://graph.facebook.com/v21.0"
DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


# =============================================================================
# EXCEPTIONS
# =============================================================================

class FacebookAPIError(Exception):
    """Custom exception for Facebook API errors."""

    def __init__(self, message: str, error_code: Optional[int] = None,
                 error_subcode: Optional[int] = None, fb_trace_id: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.fb_trace_id = fb_trace_id


class RateLimitError(FacebookAPIError):
    """Raised when rate limit is hit."""
    pass


class AuthenticationError(FacebookAPIError):
    """Raised when authentication fails."""
    pass


# =============================================================================
# FACEBOOK API CLASS
# =============================================================================

class FacebookAPI:
    """
    Facebook Graph API wrapper for comment bot operations.

    Usage:
        api = FacebookAPI(page_id, access_token)
        posts = api.get_page_posts()
        for post in posts:
            comments = api.get_post_comments(post['id'])
    """

    def __init__(self, page_id: Optional[str] = None, access_token: Optional[str] = None):
        """
        Initialize the Facebook API client.

        Args:
            page_id: Facebook Page ID (falls back to FACEBOOK_PAGE_ID env var)
            access_token: Page Access Token (falls back to FACEBOOK_PAGE_ACCESS_TOKEN env var)
        """
        self.page_id = page_id or get_secret('FACEBOOK_PAGE_ID')
        self.access_token = access_token or get_secret('FACEBOOK_PAGE_ACCESS_TOKEN')

        if not self.page_id:
            raise ValueError("page_id is required. Set FACEBOOK_PAGE_ID environment variable or pass directly.")
        if not self.access_token:
            raise ValueError("access_token is required. Set FACEBOOK_PAGE_ACCESS_TOKEN environment variable or pass directly.")

        self.base_url = GRAPH_API_BASE_URL
        self.session = requests.Session()
        self._rate_limit_remaining = None
        self._rate_limit_reset = None

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = 'GET',
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a request to the Facebook Graph API with error handling and rate limiting.

        Args:
            endpoint: API endpoint (e.g., '/me/posts' or '/{post_id}/comments')
            params: Query parameters
            method: HTTP method (GET, POST, DELETE)
            data: Request body data (for POST requests)

        Returns:
            API response as dictionary

        Raises:
            FacebookAPIError: On API errors
            RateLimitError: When rate limit is exceeded
            AuthenticationError: When token is invalid
        """
        url = f"{self.base_url}{endpoint}"

        # Always include access token
        if params is None:
            params = {}
        params['access_token'] = self.access_token

        retries = 0
        while retries < MAX_RETRIES:
            try:
                logger.debug(f"Making {method} request to {endpoint}")

                if method == 'GET':
                    response = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
                elif method == 'POST':
                    response = self.session.post(url, params=params, data=data, timeout=DEFAULT_TIMEOUT)
                elif method == 'DELETE':
                    response = self.session.delete(url, params=params, timeout=DEFAULT_TIMEOUT)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Check for rate limiting headers
                self._update_rate_limit_info(response.headers)

                # Parse response
                result = response.json()

                # Handle errors
                if 'error' in result:
                    self._handle_error(result['error'])

                return result

            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout, retry {retries + 1}/{MAX_RETRIES}")
                retries += 1
                time.sleep(RETRY_DELAY)

            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error: {e}, retry {retries + 1}/{MAX_RETRIES}")
                retries += 1
                time.sleep(RETRY_DELAY)

        raise FacebookAPIError(f"Max retries ({MAX_RETRIES}) exceeded for endpoint: {endpoint}")

    def _update_rate_limit_info(self, headers: Dict[str, str]):
        """Update rate limit tracking from response headers."""
        # Facebook uses x-app-usage and x-business-use-case-usage headers
        # These contain JSON with call_count, total_cputime, and total_time
        usage = headers.get('x-app-usage')
        if usage:
            try:
                import json
                usage_data = json.loads(usage)
                call_count = usage_data.get('call_count', 0)
                if call_count > 80:  # 80% of rate limit
                    logger.warning(f"Approaching rate limit: {call_count}% used")
            except (json.JSONDecodeError, TypeError):
                pass

    def _handle_error(self, error: Dict[str, Any]):
        """Handle Facebook API error responses."""
        message = error.get('message', 'Unknown error')
        code = error.get('code')
        subcode = error.get('error_subcode')
        fb_trace_id = error.get('fbtrace_id')

        logger.error(f"Facebook API error: {message} (code: {code}, subcode: {subcode})")

        # Rate limiting
        if code in [4, 17, 32, 613]:
            raise RateLimitError(message, code, subcode, fb_trace_id)

        # Authentication errors
        if code in [102, 190]:
            raise AuthenticationError(message, code, subcode, fb_trace_id)

        # Permission errors
        if code in [10, 200, 230, 270]:
            raise FacebookAPIError(f"Permission denied: {message}", code, subcode, fb_trace_id)

        raise FacebookAPIError(message, code, subcode, fb_trace_id)

    # =========================================================================
    # PAGE & POST METHODS
    # =========================================================================

    def get_page_info(self) -> Dict[str, Any]:
        """
        Get information about the connected page.

        Returns:
            Page information including id, name, and other details
        """
        response = self._make_request(
            f"/{self.page_id}",
            params={'fields': 'id,name,about,category,fan_count,link'}
        )
        return response

    def get_page_posts(
        self,
        limit: int = 25,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent posts from the page.

        Args:
            limit: Maximum number of posts to return (max 100)
            since: Only return posts after this time
            until: Only return posts before this time

        Returns:
            List of post dictionaries with id, message, created_time, etc.
        """
        params = {
            'fields': 'id,message,created_time,permalink_url,shares,attachments{type,title,description}',
            'limit': min(limit, 100)
        }

        if since:
            params['since'] = int(since.timestamp())
        if until:
            params['until'] = int(until.timestamp())

        response = self._make_request(f"/{self.page_id}/posts", params=params)
        posts = response.get('data', [])

        logger.info(f"Fetched {len(posts)} posts from page")
        return posts

    def get_ad_posts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch posts that are associated with ads (promoted posts).

        Note: This requires the ads_read permission and may need business integration.
        Falls back to regular posts if ad access is not available.

        Args:
            limit: Maximum number of posts

        Returns:
            List of ad post dictionaries
        """
        try:
            # Try to get promoted posts (requires ads permissions)
            response = self._make_request(
                f"/{self.page_id}/promotable_posts",
                params={
                    'fields': 'id,message,created_time,permalink_url,is_published,is_eligible_for_promotion',
                    'limit': min(limit, 100)
                }
            )
            posts = response.get('data', [])
            logger.info(f"Fetched {len(posts)} promotable posts")
            return posts
        except FacebookAPIError as e:
            # Fall back to regular posts if ads permissions not available
            logger.warning(f"Could not fetch ad posts (may need ads_read permission): {e}")
            return self.get_page_posts(limit=limit)

    def get_post_details(self, post_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific post.

        Args:
            post_id: The Facebook post ID

        Returns:
            Post details dictionary
        """
        response = self._make_request(
            f"/{post_id}",
            params={
                'fields': 'id,message,created_time,permalink_url,shares,comments.summary(true),attachments'
            }
        )
        return response

    # =========================================================================
    # COMMENT METHODS
    # =========================================================================

    def get_post_comments(
        self,
        post_id: str,
        since: Optional[datetime] = None,
        limit: int = 100,
        order: str = 'reverse_chronological'
    ) -> List[Dict[str, Any]]:
        """
        Fetch comments on a post.

        Args:
            post_id: The Facebook post ID
            since: Only fetch comments after this time
            limit: Maximum number of comments (will paginate if needed)
            order: 'chronological' or 'reverse_chronological'

        Returns:
            List of comment dictionaries with id, message, from, created_time, etc.
        """
        all_comments = []

        params = {
            'fields': 'id,message,from{id,name},created_time,comment_count,parent,attachment',
            'filter': 'stream',  # Include all comments (including hidden/filtered ones)
            'limit': min(limit, 100),
            'order': order
        }

        if since:
            params['since'] = int(since.timestamp())

        # Initial request
        response = self._make_request(f"/{post_id}/comments", params=params)
        comments = response.get('data', [])
        all_comments.extend(comments)

        # Handle pagination
        while 'paging' in response and 'next' in response['paging'] and len(all_comments) < limit:
            # Extract cursor from next URL
            next_url = response['paging']['next']
            # Make request with the after cursor
            after_cursor = response['paging'].get('cursors', {}).get('after')
            if after_cursor:
                params['after'] = after_cursor
                response = self._make_request(f"/{post_id}/comments", params=params)
                comments = response.get('data', [])
                if not comments:
                    break
                all_comments.extend(comments)
            else:
                break

        logger.info(f"Fetched {len(all_comments)} comments for post {post_id}")
        return all_comments[:limit]

    def get_comment_replies(
        self,
        comment_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get replies to a specific comment (thread tracking).

        Args:
            comment_id: The parent comment ID
            limit: Maximum number of replies

        Returns:
            List of reply dictionaries
        """
        response = self._make_request(
            f"/{comment_id}/comments",
            params={
                'fields': 'id,message,from{id,name},created_time,parent',
                'limit': min(limit, 100)
            }
        )

        replies = response.get('data', [])
        logger.info(f"Fetched {len(replies)} replies for comment {comment_id}")
        return replies

    def get_comment(self, comment_id: str) -> Dict[str, Any]:
        """
        Get details of a specific comment.

        Args:
            comment_id: The Facebook comment ID

        Returns:
            Comment details dictionary
        """
        response = self._make_request(
            f"/{comment_id}",
            params={
                'fields': 'id,message,from{id,name},created_time,comment_count,parent,attachment'
            }
        )
        return response

    def reply_to_comment(
        self,
        comment_id: str,
        message: str
    ) -> Dict[str, Any]:
        """
        Post a reply to a comment.

        Args:
            comment_id: The comment ID to reply to
            message: The reply message text

        Returns:
            Response with the new comment ID

        Raises:
            FacebookAPIError: If posting fails
        """
        if not message or not message.strip():
            raise ValueError("Reply message cannot be empty")

        # Ensure message doesn't exceed Facebook's limit
        max_length = 8000  # Facebook's comment limit
        if len(message) > max_length:
            logger.warning(f"Message truncated from {len(message)} to {max_length} characters")
            message = message[:max_length]

        response = self._make_request(
            f"/{comment_id}/comments",
            method='POST',
            data={'message': message}
        )

        new_comment_id = response.get('id')
        logger.info(f"Posted reply to comment {comment_id}, new comment ID: {new_comment_id}")

        return response

    def delete_comment(self, comment_id: str) -> bool:
        """
        Delete a comment (only works for comments made by the page).

        Args:
            comment_id: The comment ID to delete

        Returns:
            True if deletion was successful
        """
        response = self._make_request(
            f"/{comment_id}",
            method='DELETE'
        )

        success = response.get('success', False)
        if success:
            logger.info(f"Deleted comment {comment_id}")

        return success

    def hide_comment(self, comment_id: str, is_hidden: bool = True) -> bool:
        """
        Hide or unhide a comment.

        Args:
            comment_id: The comment ID
            is_hidden: True to hide, False to unhide

        Returns:
            True if operation was successful
        """
        response = self._make_request(
            f"/{comment_id}",
            method='POST',
            data={'is_hidden': str(is_hidden).lower()}
        )

        success = response.get('success', False)
        action = "Hidden" if is_hidden else "Unhidden"
        if success:
            logger.info(f"{action} comment {comment_id}")

        return success

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def validate_token(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate the access token and return info about it.

        Returns:
            Tuple of (is_valid, token_info)
        """
        try:
            response = self._make_request(
                "/debug_token",
                params={
                    'input_token': self.access_token
                }
            )

            data = response.get('data', {})
            is_valid = data.get('is_valid', False)

            token_info = {
                'is_valid': is_valid,
                'app_id': data.get('app_id'),
                'type': data.get('type'),
                'expires_at': data.get('expires_at'),
                'scopes': data.get('scopes', [])
            }

            if is_valid:
                logger.info(f"Token is valid. Scopes: {token_info['scopes']}")
            else:
                logger.warning("Token is invalid!")

            return is_valid, token_info

        except FacebookAPIError as e:
            logger.error(f"Token validation failed: {e}")
            return False, {'error': str(e)}

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status.

        Returns:
            Dictionary with rate limit information
        """
        # Make a lightweight request to get rate limit headers
        try:
            self._make_request(f"/{self.page_id}", params={'fields': 'id'})
            return {
                'status': 'ok',
                'remaining': self._rate_limit_remaining,
                'reset': self._rate_limit_reset
            }
        except RateLimitError:
            return {
                'status': 'exceeded',
                'remaining': 0,
                'reset': self._rate_limit_reset
            }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_facebook_datetime(fb_datetime: str) -> datetime:
    """
    Parse Facebook's datetime format to Python datetime.

    Args:
        fb_datetime: Facebook datetime string (ISO 8601)

    Returns:
        Python datetime object
    """
    # Facebook uses ISO 8601 format: 2024-01-15T10:30:00+0000
    try:
        # Try parsing with timezone
        return datetime.fromisoformat(fb_datetime.replace('+0000', '+00:00'))
    except ValueError:
        # Fallback without timezone
        return datetime.strptime(fb_datetime[:19], '%Y-%m-%dT%H:%M:%S')


def format_comment_for_storage(
    comment: Dict[str, Any],
    post_id: str,
    post_type: Optional[str] = None,
    campaign_name: Optional[str] = None,
    ad_set_name: Optional[str] = None,
    ad_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Format a Facebook comment response for database storage.

    Args:
        comment: Raw comment from Facebook API
        post_id: The post ID this comment belongs to
        post_type: Type of post (organic, ad, etc.)
        campaign_name: Ad campaign name if applicable
        ad_set_name: Ad set name if applicable
        ad_name: Ad name if applicable

    Returns:
        Dictionary formatted for insert_comment()
    """
    from_data = comment.get('from', {})
    parent = comment.get('parent', {})

    return {
        'fb_comment_id': comment.get('id'),
        'parent_comment_id': parent.get('id') if parent else None,
        'thread_depth': 1 if parent else 0,
        'fb_post_id': post_id,
        'post_type': post_type,
        'campaign_name': campaign_name,
        'ad_set_name': ad_set_name,
        'ad_name': ad_name,
        'commenter_name': from_data.get('name', 'Unknown'),
        'commenter_fb_id': from_data.get('id'),
        'comment_text': comment.get('message', ''),
        'comment_time': comment.get('created_time'),
        'reply_status': 'pending'
    }


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTION
# =============================================================================

def get_facebook_api() -> FacebookAPI:
    """
    Get a FacebookAPI instance using environment variables.

    Returns:
        Configured FacebookAPI instance

    Raises:
        ValueError: If required environment variables are not set
    """
    return FacebookAPI()
