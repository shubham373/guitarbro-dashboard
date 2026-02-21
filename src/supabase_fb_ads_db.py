"""
Supabase Database Helper for FB Ads Analytics

This module provides database operations using Supabase instead of SQLite.
Data persists in the cloud and survives app reboots.
"""

import logging
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

# Import the shared Supabase client
try:
    from supabase_db import get_supabase_client, SUPABASE_AVAILABLE
except ImportError:
    SUPABASE_AVAILABLE = False
    def get_supabase_client():
        return None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Column mapping: Original SQLite names -> Supabase column names
COLUMN_MAP_TO_SUPABASE = {
    "Reporting starts": "reporting_starts",
    "Reporting ends": "reporting_ends",
    "Ad name": "ad_name",
    "Ad delivery": "ad_delivery",
    "Amount spent (INR)": "amount_spent",
    "Purchase ROAS (return on ad spend)": "purchase_roas",
    "Purchases": "purchases",
    "CTR (link click-through rate)": "ctr",
    "CPC (cost per link click) (INR)": "cpc",
    "CPM (cost per 1,000 impressions) (INR)": "cpm",
    "Hook rate": "hook_rate",
    "Hold Rate": "hold_rate",
    "Impressions": "impressions",
    "Reach": "reach",
    "Frequency": "frequency",
    "Adds to cart": "adds_to_cart",
    "ATC Cost": "atc_cost",
    "FTIR": "ftir",
    "Link clicks": "link_clicks",
    "Landing page views": "landing_page_views",
    "Click To LP Visit %": "click_to_lp_percent",
    "Checkouts initiated": "checkouts_initiated",
    "Cost per purchase (INR)": "cost_per_purchase",
    "Purchases conversion value": "purchases_conversion_value",
    "Engagement rate ranking": "engagement_rate_ranking",
    "Engagement Ratio": "engagement_ratio",
    "ATC to Purchase": "atc_to_purchase",
    "LP Conversion": "lp_conversion",
    "Campaign name": "campaign_name",
    "Ad set name": "ad_set_name",
    "Video average play time": "video_avg_play_time",
    "Percentage 25% Video": "video_25_percent",
    "Percentage 50% Video": "video_50_percent",
    "Percentage 75% Video": "video_75_percent",
    "Percentage 95% Video": "video_95_percent",
    "Percentage 100% Video": "video_100_percent",
    "composite_key": "composite_key",
}

# Reverse mapping: Supabase -> Original names
COLUMN_MAP_FROM_SUPABASE = {v: k for k, v in COLUMN_MAP_TO_SUPABASE.items()}


def check_fb_ads_supabase_connection() -> Dict[str, Any]:
    """Check if Supabase connection is working for fb_ads_data table."""
    client = get_supabase_client()

    if not client:
        return {"connected": False, "error": "Supabase client not available"}

    try:
        result = client.table('fb_ads_data').select('id').limit(1).execute()
        return {"connected": True, "error": None}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _convert_row_to_supabase(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a row with original column names to Supabase column names."""
    result = {}
    for orig_name, supabase_name in COLUMN_MAP_TO_SUPABASE.items():
        if orig_name in row:
            value = row[orig_name]
            # Convert NaN to None
            if pd.isna(value):
                value = None
            result[supabase_name] = value
    return result


def _convert_row_from_supabase(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a row with Supabase column names to original column names."""
    result = {}
    for supabase_name, orig_name in COLUMN_MAP_FROM_SUPABASE.items():
        if supabase_name in row:
            result[orig_name] = row[supabase_name]
    # Also copy the id if present
    if 'id' in row:
        result['id'] = row['id']
    return result


def upload_fb_ads_data(df: pd.DataFrame) -> Tuple[int, int, int]:
    """
    Upload FB Ads data to Supabase with UPSERT logic.

    Returns:
        Tuple of (new_count, updated_count, unchanged_count)
    """
    client = get_supabase_client()
    if not client:
        logger.error("Supabase client not available")
        return (0, 0, 0)

    new_count = 0
    updated_count = 0
    unchanged_count = 0

    for _, row in df.iterrows():
        # Generate composite key
        ad_name = str(row.get("Ad name", ""))
        campaign_name = str(row.get("Campaign name", ""))
        ad_set_name = str(row.get("Ad set name", ""))
        reporting_starts = str(row.get("Reporting starts", ""))
        composite_key = f"{ad_name}||{campaign_name}||{ad_set_name}||{reporting_starts}"

        # Check if exists
        try:
            existing = client.table('fb_ads_data').select('id').eq(
                'composite_key', composite_key
            ).limit(1).execute()
            exists = len(existing.data) > 0
        except Exception:
            exists = False

        # Prepare row data
        row_dict = row.to_dict()
        row_dict["composite_key"] = composite_key

        # Convert to Supabase format
        supabase_row = _convert_row_to_supabase(row_dict)

        try:
            client.table('fb_ads_data').upsert(
                supabase_row, on_conflict='composite_key'
            ).execute()

            if exists:
                updated_count += 1
            else:
                new_count += 1

        except Exception as e:
            logger.error(f"Error upserting row: {e}")
            unchanged_count += 1

    logger.info(f"FB Ads upload: {new_count} new, {updated_count} updated, {unchanged_count} unchanged")
    return (new_count, updated_count, unchanged_count)


def load_fb_ads_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    campaigns: Optional[List[str]] = None,
    ad_sets: Optional[List[str]] = None,
    ad_name: Optional[str] = None
) -> pd.DataFrame:
    """
    Load FB Ads data from Supabase with filters.

    Returns:
        DataFrame with original column names
    """
    client = get_supabase_client()
    if not client:
        return pd.DataFrame()

    try:
        query = client.table('fb_ads_data').select('*')

        if start_date:
            query = query.gte('reporting_starts', start_date)
        if end_date:
            query = query.lte('reporting_starts', end_date)
        if ad_name:
            query = query.eq('ad_name', ad_name)
        if campaigns and len(campaigns) > 0:
            query = query.in_('campaign_name', campaigns)
        if ad_sets and len(ad_sets) > 0:
            query = query.in_('ad_set_name', ad_sets)

        query = query.order('reporting_starts', desc=True)
        result = query.execute()

        if not result.data:
            return pd.DataFrame()

        # Convert to DataFrame with original column names
        rows = [_convert_row_from_supabase(row) for row in result.data]
        return pd.DataFrame(rows)

    except Exception as e:
        logger.error(f"Error loading FB ads data: {e}")
        return pd.DataFrame()


def get_unique_campaigns() -> List[str]:
    """Get list of unique campaign names."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        result = client.table('fb_ads_data').select('campaign_name').execute()
        campaigns = list(set(row['campaign_name'] for row in result.data if row.get('campaign_name')))
        return sorted(campaigns)
    except Exception as e:
        logger.error(f"Error fetching campaigns: {e}")
        return []


def get_unique_ad_sets(campaigns: Optional[List[str]] = None) -> List[str]:
    """Get list of unique ad set names, optionally filtered by campaigns."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        query = client.table('fb_ads_data').select('ad_set_name')
        if campaigns and len(campaigns) > 0:
            query = query.in_('campaign_name', campaigns)

        result = query.execute()
        ad_sets = list(set(row['ad_set_name'] for row in result.data if row.get('ad_set_name')))
        return sorted(ad_sets)
    except Exception as e:
        logger.error(f"Error fetching ad sets: {e}")
        return []


def get_unique_ad_names() -> List[str]:
    """Get list of unique ad names."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        result = client.table('fb_ads_data').select('ad_name').execute()
        names = list(set(row['ad_name'] for row in result.data if row.get('ad_name')))
        return sorted(names)
    except Exception as e:
        logger.error(f"Error fetching ad names: {e}")
        return []


def get_ad_history(ad_name: str) -> pd.DataFrame:
    """Get historical data for a specific ad."""
    client = get_supabase_client()
    if not client:
        return pd.DataFrame()

    try:
        result = client.table('fb_ads_data').select('*').eq(
            'ad_name', ad_name
        ).order('reporting_starts').execute()

        if not result.data:
            return pd.DataFrame()

        rows = [_convert_row_from_supabase(row) for row in result.data]
        return pd.DataFrame(rows)
    except Exception as e:
        logger.error(f"Error fetching ad history: {e}")
        return pd.DataFrame()


def get_date_range() -> Tuple[Optional[str], Optional[str]]:
    """Get the min and max reporting dates in the database."""
    client = get_supabase_client()
    if not client:
        return (None, None)

    try:
        # Get min date
        min_result = client.table('fb_ads_data').select('reporting_starts').order(
            'reporting_starts'
        ).limit(1).execute()

        # Get max date
        max_result = client.table('fb_ads_data').select('reporting_starts').order(
            'reporting_starts', desc=True
        ).limit(1).execute()

        min_date = min_result.data[0]['reporting_starts'] if min_result.data else None
        max_date = max_result.data[0]['reporting_starts'] if max_result.data else None

        return (min_date, max_date)
    except Exception as e:
        logger.error(f"Error fetching date range: {e}")
        return (None, None)


def get_fb_ads_stats() -> Dict[str, Any]:
    """Get summary statistics for FB Ads data."""
    client = get_supabase_client()
    if not client:
        return {
            'total_records': 0,
            'total_spend': 0,
            'total_purchases': 0,
            'unique_ads': 0,
            'unique_campaigns': 0
        }

    try:
        result = client.table('fb_ads_data').select('*').execute()
        data = result.data

        total_spend = sum(row.get('amount_spent', 0) or 0 for row in data)
        total_purchases = sum(row.get('purchases', 0) or 0 for row in data)
        unique_ads = len(set(row.get('ad_name') for row in data if row.get('ad_name')))
        unique_campaigns = len(set(row.get('campaign_name') for row in data if row.get('campaign_name')))

        return {
            'total_records': len(data),
            'total_spend': total_spend,
            'total_purchases': total_purchases,
            'unique_ads': unique_ads,
            'unique_campaigns': unique_campaigns
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {
            'total_records': 0,
            'total_spend': 0,
            'total_purchases': 0,
            'unique_ads': 0,
            'unique_campaigns': 0
        }


def clear_fb_ads_data() -> bool:
    """Clear all FB Ads data."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table('fb_ads_data').delete().neq('id', 0).execute()
        return True
    except Exception as e:
        logger.error(f"Error clearing FB ads data: {e}")
        return False
