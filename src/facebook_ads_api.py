"""
Facebook Ads API Module for FB Ads Analytics

Handles fetching ad insights from the Facebook Marketing API.
Uses User Access Token with ads_read permission.

This module is separate from facebook_api.py which handles Page operations (comments).
"""

import os
import json
import time
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple, Callable

# Import config helper for secrets
try:
    from config import get_facebook_user_token, get_facebook_ad_account_id
except ImportError:
    from dotenv import load_dotenv
    load_dotenv()
    def get_facebook_user_token():
        return os.getenv('FACEBOOK_USER_ACCESS_TOKEN')
    def get_facebook_ad_account_id():
        return os.getenv('FACEBOOK_AD_ACCOUNT_ID')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

GRAPH_API_BASE_URL = "https://graph.facebook.com/v21.0"
DEFAULT_TIMEOUT = 60  # Longer timeout for insights queries
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Fields to fetch from Insights API
# Note: video_view (3-sec views) is in 'actions' array, not a separate field
INSIGHTS_FIELDS = [
    'ad_id', 'ad_name', 'adset_name', 'campaign_name',
    'date_start', 'date_stop',
    'spend', 'impressions', 'reach', 'frequency',
    'clicks', 'cpc', 'cpm', 'ctr',
    'actions', 'action_values', 'cost_per_action_type',
    'video_play_actions',              # Video plays (starts)
    'video_thruplay_watched_actions',  # ThruPlays (15s or complete)
    'video_avg_time_watched_actions',
    'video_p25_watched_actions', 'video_p50_watched_actions',
    'video_p75_watched_actions', 'video_p95_watched_actions',
    'video_p100_watched_actions',
    'engagement_rate_ranking'
]

# Action types for purchases (FB uses different names)
PURCHASE_ACTION_TYPES = [
    'purchase',
    'omni_purchase',
    'offsite_conversion.fb_pixel_purchase',
    'onsite_conversion.purchase'
]

ADD_TO_CART_ACTION_TYPES = [
    'add_to_cart',
    'omni_add_to_cart',
    'offsite_conversion.fb_pixel_add_to_cart'
]

LANDING_PAGE_VIEW_ACTION_TYPES = [
    'landing_page_view',
    'omni_landing_page_view'
]

CHECKOUT_ACTION_TYPES = [
    'initiated_checkout',
    'omni_initiated_checkout',
    'offsite_conversion.fb_pixel_initiate_checkout'
]

LINK_CLICK_ACTION_TYPES = [
    'link_click'
]

POST_ENGAGEMENT_ACTION_TYPES = [
    'post_engagement',
    'page_engagement'
]

VIDEO_VIEW_ACTION_TYPES = [
    'video_view'  # 3-second video views
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def extract_action_value(actions: List[Dict], action_types: List[str]) -> float:
    """
    Extract value from actions array, checking multiple action_types.

    Args:
        actions: List of action dictionaries from FB API
        action_types: List of action_type strings to look for

    Returns:
        Float value or 0.0 if not found
    """
    if not actions:
        return 0.0
    for action in actions:
        if action.get('action_type') in action_types:
            return float(action.get('value', 0))
    return 0.0


def extract_video_metric(video_actions: List[Dict]) -> float:
    """
    Extract video metric value from video actions array.

    Args:
        video_actions: List like [{"action_type": "video_view", "value": "123"}]

    Returns:
        Float value or 0.0
    """
    if not video_actions:
        return 0.0
    if isinstance(video_actions, list) and len(video_actions) > 0:
        return float(video_actions[0].get('value', 0))
    return 0.0


def safe_divide(numerator: float, denominator: float) -> Optional[float]:
    """
    Safely divide two numbers, returning None if denominator is 0.
    """
    if denominator and denominator > 0:
        return numerator / denominator
    return None


def calculate_derived_metrics(row: Dict, actions: Dict) -> Dict:
    """
    Calculate the 8 derived metrics from raw API data.

    Args:
        row: Raw row data from API
        actions: Parsed actions dictionary

    Returns:
        Dictionary with calculated metrics
    """
    impressions = float(row.get('impressions', 0) or 0)
    reach = float(row.get('reach', 0) or 0)
    spend = float(row.get('spend', 0) or 0)

    link_clicks = actions.get('link_clicks', 0)
    lp_views = actions.get('landing_page_views', 0)
    add_to_cart = actions.get('adds_to_cart', 0)
    purchases = actions.get('purchases', 0)
    post_engagements = actions.get('post_engagements', 0)

    video_3s_plays = float(row.get('video_3_sec_watched', 0) or 0)
    thruplays = float(row.get('thruplays', 0) or 0)

    return {
        # 1. Hook Rate = 3-second video plays / Impressions
        'Hook rate': safe_divide(video_3s_plays, impressions),

        # 2. Hold Rate = ThruPlays / Impressions
        'Hold Rate': safe_divide(thruplays, impressions),

        # 3. FTIR = (Reach / Impressions) × 100
        'FTIR': safe_divide(reach, impressions) * 100 if impressions > 0 else None,

        # 4. ATC Cost = Spend / Adds to Cart
        'ATC Cost': safe_divide(spend, add_to_cart),

        # 5. Click To LP Visit % = LP Views / Link Clicks
        'Click To LP Visit %': safe_divide(lp_views, link_clicks),

        # 6. ATC to Purchase = Purchases / Adds to Cart
        'ATC to Purchase': safe_divide(purchases, add_to_cart),

        # 7. LP Conversion = Purchases / LP Views
        'LP Conversion': safe_divide(purchases, lp_views),

        # 8. Engagement Ratio = Post Engagements / Impressions
        'Engagement Ratio': safe_divide(post_engagements, impressions),
    }


# =============================================================================
# FACEBOOK ADS API CLASS
# =============================================================================

class FacebookAdsAPI:
    """
    Facebook Ads API wrapper for fetching ad insights.

    Usage:
        api = FacebookAdsAPI()
        insights = api.fetch_ad_insights('2026-02-01', '2026-02-25')
    """

    def __init__(self, ad_account_id: Optional[str] = None,
                 user_access_token: Optional[str] = None):
        """
        Initialize the Facebook Ads API client.

        Args:
            ad_account_id: Facebook Ad Account ID (e.g., 'act_89400171')
            user_access_token: User Access Token with ads_read permission
        """
        self.ad_account_id = ad_account_id or get_facebook_ad_account_id()
        self.access_token = user_access_token or get_facebook_user_token()

        if not self.ad_account_id:
            raise ValueError("ad_account_id is required. Set FACEBOOK_AD_ACCOUNT_ID env var.")
        if not self.access_token:
            raise ValueError("access_token is required. Set FACEBOOK_USER_ACCESS_TOKEN env var.")

        self.base_url = GRAPH_API_BASE_URL
        self.session = requests.Session()

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a request to the Facebook Graph API.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}{endpoint}"
        params['access_token'] = self.access_token

        retries = 0
        while retries < MAX_RETRIES:
            try:
                logger.debug(f"Making request to {endpoint}")
                response = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
                result = response.json()

                if 'error' in result:
                    error = result['error']
                    error_code = error.get('code')
                    error_msg = error.get('message', 'Unknown error')

                    # Rate limiting - wait and retry
                    if error_code in [4, 17, 32, 613]:
                        logger.warning(f"Rate limited, waiting {RETRY_DELAY * (retries + 1)}s...")
                        time.sleep(RETRY_DELAY * (retries + 1))
                        retries += 1
                        continue

                    # Auth errors - don't retry
                    if error_code in [102, 190]:
                        raise Exception(f"Authentication error: {error_msg}")

                    raise Exception(f"API error ({error_code}): {error_msg}")

                return result

            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout, retry {retries + 1}/{MAX_RETRIES}")
                retries += 1
                time.sleep(RETRY_DELAY)
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error: {e}, retry {retries + 1}/{MAX_RETRIES}")
                retries += 1
                time.sleep(RETRY_DELAY)

        raise Exception(f"Max retries ({MAX_RETRIES}) exceeded")

    def fetch_ad_insights(
        self,
        start_date: str,
        end_date: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> List[Dict]:
        """
        Fetch ad-level insights for a date range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            progress_callback: Optional callback(message, progress_pct)

        Returns:
            List of insight dictionaries
        """
        if progress_callback:
            progress_callback("Connecting to Facebook Ads API...", 0.1)

        all_insights = []

        params = {
            'level': 'ad',
            'fields': ','.join(INSIGHTS_FIELDS),
            'time_range': json.dumps({'since': start_date, 'until': end_date}),
            'time_increment': 1,  # Daily breakdown
            'limit': 500
        }

        endpoint = f"/{self.ad_account_id}/insights"

        if progress_callback:
            progress_callback(f"Fetching insights for {start_date} to {end_date}...", 0.2)

        # Initial request
        response = self._make_request(endpoint, params)
        insights = response.get('data', [])
        all_insights.extend(insights)

        logger.info(f"Fetched {len(insights)} insights (batch 1)")

        # Handle pagination
        batch = 1
        while 'paging' in response and 'next' in response['paging']:
            batch += 1

            if progress_callback:
                progress_callback(f"Fetching batch {batch}...", min(0.2 + (batch * 0.1), 0.8))

            # Get cursor from paging
            cursors = response.get('paging', {}).get('cursors', {})
            after = cursors.get('after')

            if not after:
                break

            params['after'] = after
            response = self._make_request(endpoint, params)
            insights = response.get('data', [])

            if not insights:
                break

            all_insights.extend(insights)
            logger.info(f"Fetched {len(insights)} insights (batch {batch})")

        if progress_callback:
            progress_callback(f"Fetched {len(all_insights)} total records", 0.9)

        logger.info(f"Total insights fetched: {len(all_insights)}")
        return all_insights


# =============================================================================
# TRANSFORM TO CSV SCHEMA
# =============================================================================

def transform_to_csv_schema(api_rows: List[Dict]) -> pd.DataFrame:
    """
    Transform API response rows to match the existing CSV column schema.

    Args:
        api_rows: List of dictionaries from fetch_ad_insights()

    Returns:
        DataFrame matching the upload_fb_ads_data() expected format
    """
    if not api_rows:
        return pd.DataFrame()

    transformed_rows = []

    for row in api_rows:
        # Parse actions arrays
        actions_list = row.get('actions', [])
        action_values_list = row.get('action_values', [])
        cost_per_action_list = row.get('cost_per_action_type', [])

        # Extract action values
        purchases = extract_action_value(actions_list, PURCHASE_ACTION_TYPES)
        purchase_value = extract_action_value(action_values_list, PURCHASE_ACTION_TYPES)
        cost_per_purchase = extract_action_value(cost_per_action_list, PURCHASE_ACTION_TYPES)
        adds_to_cart = extract_action_value(actions_list, ADD_TO_CART_ACTION_TYPES)
        link_clicks = extract_action_value(actions_list, LINK_CLICK_ACTION_TYPES)
        landing_page_views = extract_action_value(actions_list, LANDING_PAGE_VIEW_ACTION_TYPES)
        checkouts = extract_action_value(actions_list, CHECKOUT_ACTION_TYPES)
        post_engagements = extract_action_value(actions_list, POST_ENGAGEMENT_ACTION_TYPES)
        video_views_3s = extract_action_value(actions_list, VIDEO_VIEW_ACTION_TYPES)  # 3-sec video views

        # Extract video metrics from separate fields
        thruplays = extract_video_metric(row.get('video_thruplay_watched_actions'))
        video_avg_time = extract_video_metric(row.get('video_avg_time_watched_actions'))
        video_p25 = extract_video_metric(row.get('video_p25_watched_actions'))
        video_p50 = extract_video_metric(row.get('video_p50_watched_actions'))
        video_p75 = extract_video_metric(row.get('video_p75_watched_actions'))
        video_p95 = extract_video_metric(row.get('video_p95_watched_actions'))
        video_p100 = extract_video_metric(row.get('video_p100_watched_actions'))

        # Prepare data for derived metrics calculation
        row_data = {
            'impressions': row.get('impressions', 0),
            'reach': row.get('reach', 0),
            'spend': row.get('spend', 0),
            'video_3_sec_watched': video_views_3s,  # From actions[video_view]
            'thruplays': thruplays,
        }

        actions_data = {
            'link_clicks': link_clicks,
            'landing_page_views': landing_page_views,
            'adds_to_cart': adds_to_cart,
            'purchases': purchases,
            'post_engagements': post_engagements,
        }

        # Calculate derived metrics
        derived = calculate_derived_metrics(row_data, actions_data)

        # Calculate ROAS
        spend = float(row.get('spend', 0) or 0)
        roas = safe_divide(purchase_value, spend) if spend > 0 else None

        # Build the transformed row matching CSV column names
        transformed = {
            'Reporting starts': row.get('date_start'),
            'Reporting ends': row.get('date_stop'),
            'Ad name': row.get('ad_name'),
            'Campaign name': row.get('campaign_name'),
            'Ad set name': row.get('adset_name'),
            'Ad delivery': 'Active',  # API returns data for active ads
            'Amount spent (INR)': spend,
            'Impressions': int(float(row.get('impressions', 0) or 0)),
            'Reach': int(float(row.get('reach', 0) or 0)),
            'Frequency': float(row.get('frequency', 0) or 0),
            'Link clicks': int(link_clicks),
            'CTR (link click-through rate)': float(row.get('ctr', 0) or 0),
            'CPC (cost per link click) (INR)': float(row.get('cpc', 0) or 0),
            'CPM (cost per 1,000 impressions) (INR)': float(row.get('cpm', 0) or 0),
            'Purchases': purchases,
            'Purchases conversion value': purchase_value,
            'Cost per purchase (INR)': cost_per_purchase if cost_per_purchase else None,
            'Purchase ROAS (return on ad spend)': roas,
            'Adds to cart': adds_to_cart,
            'Landing page views': int(landing_page_views),
            'Checkouts initiated': checkouts,
            'Video average play time': int(video_avg_time),
            'Percentage 25% Video': video_p25,
            'Percentage 50% Video': video_p50,
            'Percentage 75% Video': video_p75,
            'Percentage 95% Video': video_p95,
            'Percentage 100% Video': video_p100,
            'Engagement rate ranking': row.get('engagement_rate_ranking'),
            # Derived metrics
            'Hook rate': derived['Hook rate'],
            'Hold Rate': derived['Hold Rate'],
            'FTIR': derived['FTIR'],
            'ATC Cost': derived['ATC Cost'],
            'Click To LP Visit %': derived['Click To LP Visit %'],
            'ATC to Purchase': derived['ATC to Purchase'],
            'LP Conversion': derived['LP Conversion'],
            'Engagement Ratio': derived['Engagement Ratio'],
        }

        transformed_rows.append(transformed)

    df = pd.DataFrame(transformed_rows)
    logger.info(f"Transformed {len(df)} rows to CSV schema")
    return df


# =============================================================================
# SYNC ORCHESTRATOR
# =============================================================================

def sync_fb_ads_data(
    start_date: str,
    end_date: str,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> Tuple[int, int, int]:
    """
    Main sync function: fetch from API -> transform -> upload to database.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        progress_callback: Optional callback(message, progress_pct)

    Returns:
        Tuple of (new_count, updated_count, unchanged_count)
    """
    # Import upload function here to avoid circular imports
    try:
        from fb_ads_module import upload_fb_ads_data
    except ImportError:
        from src.fb_ads_module import upload_fb_ads_data

    if progress_callback:
        progress_callback("Initializing sync...", 0.05)

    # Fetch from API
    api = FacebookAdsAPI()
    raw_data = api.fetch_ad_insights(start_date, end_date, progress_callback)

    if not raw_data:
        if progress_callback:
            progress_callback("No data found for date range", 1.0)
        return (0, 0, 0)

    if progress_callback:
        progress_callback("Transforming data...", 0.9)

    # Transform to CSV schema
    df = transform_to_csv_schema(raw_data)

    if df.empty:
        if progress_callback:
            progress_callback("No data to upload", 1.0)
        return (0, 0, 0)

    if progress_callback:
        progress_callback(f"Uploading {len(df)} records to database...", 0.95)

    # Upload to database
    new_count, updated_count, unchanged_count = upload_fb_ads_data(df)

    if progress_callback:
        progress_callback("Sync complete!", 1.0)

    logger.info(f"Sync complete: {new_count} new, {updated_count} updated, {unchanged_count} unchanged")
    return (new_count, updated_count, unchanged_count)


# =============================================================================
# LAST SYNC TIMESTAMP
# =============================================================================

# Simple file-based storage for last sync timestamp
LAST_SYNC_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', '.fb_ads_last_sync')

def save_last_sync_timestamp():
    """Save current timestamp as last sync time."""
    try:
        os.makedirs(os.path.dirname(LAST_SYNC_FILE), exist_ok=True)
        with open(LAST_SYNC_FILE, 'w') as f:
            f.write(datetime.now().isoformat())
    except Exception as e:
        logger.warning(f"Could not save last sync timestamp: {e}")


def get_last_sync_timestamp() -> Optional[datetime]:
    """Get the last sync timestamp."""
    try:
        if os.path.exists(LAST_SYNC_FILE):
            with open(LAST_SYNC_FILE, 'r') as f:
                return datetime.fromisoformat(f.read().strip())
    except Exception as e:
        logger.warning(f"Could not read last sync timestamp: {e}")
    return None


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    # Test the API connection
    print("Testing Facebook Ads API connection...")

    try:
        api = FacebookAdsAPI()

        # Test with last 3 days
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')

        print(f"Fetching insights from {start} to {end}...")
        insights = api.fetch_ad_insights(start, end)

        print(f"Fetched {len(insights)} records")

        if insights:
            print("\nSample record:")
            sample = insights[0]
            print(f"  Ad: {sample.get('ad_name')}")
            print(f"  Spend: {sample.get('spend')}")
            print(f"  Impressions: {sample.get('impressions')}")

            # Test transformation
            df = transform_to_csv_schema(insights[:5])
            print(f"\nTransformed DataFrame columns: {list(df.columns)}")
            print(f"Sample Hook Rate: {df['Hook rate'].iloc[0]}")
            print(f"Sample Hold Rate: {df['Hold Rate'].iloc[0]}")

    except Exception as e:
        print(f"Error: {e}")
