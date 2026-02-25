"""
Shopify Admin API Module for Logistics Reconciliation

Handles fetching orders from Shopify Admin API and transforming them
to match the expected CSV format for the logistics module.
"""

import os
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple, Callable

# Import config helper for secrets
try:
    from config import get_shopify_store_url, get_shopify_access_token
except ImportError:
    from dotenv import load_dotenv
    load_dotenv()
    def get_shopify_store_url():
        return os.getenv('SHOPIFY_STORE_URL')
    def get_shopify_access_token():
        return os.getenv('SHOPIFY_ACCESS_TOKEN')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

API_VERSION = "2024-01"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2
ORDERS_PER_PAGE = 250  # Shopify max is 250


# =============================================================================
# SHOPIFY API CLASS
# =============================================================================

class ShopifyAPI:
    """
    Shopify Admin API wrapper for fetching orders.

    Usage:
        api = ShopifyAPI()
        orders = api.fetch_orders('2026-01-01', '2026-02-25')
    """

    def __init__(self, store_url: Optional[str] = None,
                 access_token: Optional[str] = None):
        """
        Initialize the Shopify API client.

        Args:
            store_url: Shopify store URL (e.g., 'playguitarbro.myshopify.com')
            access_token: Admin API access token (starts with 'shpat_')
        """
        self.store_url = store_url or get_shopify_store_url()
        self.access_token = access_token or get_shopify_access_token()

        if not self.store_url:
            raise ValueError("store_url is required. Set SHOPIFY_STORE_URL env var.")
        if not self.access_token:
            raise ValueError("access_token is required. Set SHOPIFY_ACCESS_TOKEN env var.")

        # Remove protocol if included
        if self.store_url.startswith('https://'):
            self.store_url = self.store_url[8:]
        if self.store_url.startswith('http://'):
            self.store_url = self.store_url[7:]

        self.base_url = f"https://{self.store_url}/admin/api/{API_VERSION}"
        self.session = requests.Session()
        self.session.headers.update({
            'X-Shopify-Access-Token': self.access_token,
            'Content-Type': 'application/json'
        })

    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Make a request to the Shopify Admin API.

        Args:
            endpoint: API endpoint (e.g., '/orders.json')
            params: Query parameters

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}{endpoint}"

        retries = 0
        while retries < MAX_RETRIES:
            try:
                response = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', RETRY_DELAY))
                    logger.warning(f"Rate limited, waiting {retry_after}s...")
                    import time
                    time.sleep(retry_after)
                    retries += 1
                    continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout, retry {retries + 1}/{MAX_RETRIES}")
                retries += 1
                import time
                time.sleep(RETRY_DELAY)
            except requests.exceptions.HTTPError as e:
                if response.status_code == 401:
                    raise Exception("Authentication failed. Check your access token.")
                raise Exception(f"HTTP error: {e}")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error: {e}, retry {retries + 1}/{MAX_RETRIES}")
                retries += 1
                import time
                time.sleep(RETRY_DELAY)

        raise Exception(f"Max retries ({MAX_RETRIES}) exceeded")

    def fetch_orders(
        self,
        start_date: str,
        end_date: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> List[Dict]:
        """
        Fetch orders for a date range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            progress_callback: Optional callback(message, progress_pct)

        Returns:
            List of order dictionaries
        """
        if progress_callback:
            progress_callback("Connecting to Shopify API...", 0.1)

        all_orders = []

        # Convert dates to ISO format with time
        start_iso = f"{start_date}T00:00:00+05:30"  # IST timezone
        end_iso = f"{end_date}T23:59:59+05:30"

        params = {
            'created_at_min': start_iso,
            'created_at_max': end_iso,
            'limit': ORDERS_PER_PAGE,
            'status': 'any',  # Include all orders (open, closed, cancelled)
        }

        if progress_callback:
            progress_callback(f"Fetching orders from {start_date} to {end_date}...", 0.2)

        page = 1
        while True:
            logger.info(f"Fetching orders page {page}...")

            response = self._make_request('/orders.json', params)
            orders = response.get('orders', [])

            if not orders:
                break

            all_orders.extend(orders)
            logger.info(f"Fetched {len(orders)} orders (page {page}, total: {len(all_orders)})")

            if progress_callback:
                progress_callback(f"Fetched {len(all_orders)} orders...", min(0.2 + (page * 0.1), 0.8))

            # Check for pagination
            link_header = None  # Shopify uses Link header for pagination
            # For simplicity, use the since_id approach
            if len(orders) < ORDERS_PER_PAGE:
                break

            # Get the last order's ID for pagination
            last_order_id = orders[-1]['id']
            params['since_id'] = last_order_id
            page += 1

            # Safety limit
            if page > 100:
                logger.warning("Reached page limit (100), stopping pagination")
                break

        if progress_callback:
            progress_callback(f"Fetched {len(all_orders)} total orders", 0.9)

        logger.info(f"Total orders fetched: {len(all_orders)}")
        return all_orders


# =============================================================================
# TRANSFORM TO CSV FORMAT
# =============================================================================

def transform_orders_to_csv_format(orders: List[Dict]) -> pd.DataFrame:
    """
    Transform Shopify API orders to match the expected CSV format.

    The logistics module expects columns like:
    - Name (order number like #1234)
    - Id (Shopify order ID)
    - Email, Phone, Billing Phone
    - Billing Name, Shipping Name/City/Province/Zip
    - Subtotal, Total, Discount Code/Amount, Refunded Amount
    - Financial Status, Fulfillment Status, Payment Method
    - Created at, Cancelled at
    - Source, Tags
    - Lineitem name/sku/quantity/price/discount

    Args:
        orders: List of order dicts from Shopify API

    Returns:
        DataFrame matching the CSV format
    """
    if not orders:
        return pd.DataFrame()

    rows = []

    for order in orders:
        # Get common order fields
        order_number = order.get('name', '')  # e.g., "#1234"
        order_id = order.get('id', '')
        email = order.get('email', '')
        phone = order.get('phone', '')

        # Billing address
        billing = order.get('billing_address') or {}
        billing_name = billing.get('name', '')
        billing_phone = billing.get('phone', '')

        # Shipping address
        shipping = order.get('shipping_address') or {}
        shipping_name = shipping.get('name', '')
        shipping_city = shipping.get('city', '')
        shipping_state = shipping.get('province', '')
        shipping_zip = shipping.get('zip', '')

        # Financial details
        subtotal = order.get('subtotal_price', 0)
        total = order.get('total_price', 0)
        financial_status = order.get('financial_status', '')
        fulfillment_status = order.get('fulfillment_status', '') or ''

        # Discounts
        discount_codes = order.get('discount_codes', [])
        discount_code = discount_codes[0].get('code', '') if discount_codes else ''
        discount_amount = order.get('total_discounts', 0)

        # Refunds
        refund_amount = sum(
            float(refund.get('transactions', [{}])[0].get('amount', 0))
            for refund in order.get('refunds', [])
            if refund.get('transactions')
        ) if order.get('refunds') else 0

        # Payment method
        payment_gateway = ''
        if order.get('payment_gateway_names'):
            payment_gateway = ', '.join(order.get('payment_gateway_names', []))

        # Dates
        created_at = order.get('created_at', '')
        cancelled_at = order.get('cancelled_at', '')

        # Source and tags
        source = order.get('source_name', '')
        tags = order.get('tags', '')

        # Line items - create one row per line item
        line_items = order.get('line_items', [])

        if not line_items:
            # Order with no line items - create single row
            rows.append({
                'Name': order_number,
                'Id': order_id,
                'Email': email,
                'Phone': phone,
                'Billing Phone': billing_phone,
                'Billing Name': billing_name,
                'Shipping Name': shipping_name,
                'Shipping City': shipping_city,
                'Shipping Province': shipping_state,
                'Shipping Zip': shipping_zip,
                'Subtotal': subtotal,
                'Total': total,
                'Discount Code': discount_code,
                'Discount Amount': discount_amount,
                'Refunded Amount': refund_amount,
                'Financial Status': financial_status,
                'Fulfillment Status': fulfillment_status,
                'Payment Method': payment_gateway,
                'Created at': created_at,
                'Cancelled at': cancelled_at,
                'Source': source,
                'Tags': tags,
                'Lineitem name': '',
                'Lineitem sku': '',
                'Lineitem quantity': 0,
                'Lineitem price': 0,
                'Lineitem discount': 0,
            })
        else:
            # Create one row per line item
            for item in line_items:
                # Calculate line item discount
                line_discount = sum(
                    float(disc.get('amount', 0))
                    for disc in item.get('discount_allocations', [])
                )

                rows.append({
                    'Name': order_number,
                    'Id': order_id,
                    'Email': email,
                    'Phone': phone,
                    'Billing Phone': billing_phone,
                    'Billing Name': billing_name,
                    'Shipping Name': shipping_name,
                    'Shipping City': shipping_city,
                    'Shipping Province': shipping_state,
                    'Shipping Zip': shipping_zip,
                    'Subtotal': subtotal,
                    'Total': total,
                    'Discount Code': discount_code,
                    'Discount Amount': discount_amount,
                    'Refunded Amount': refund_amount,
                    'Financial Status': financial_status,
                    'Fulfillment Status': fulfillment_status,
                    'Payment Method': payment_gateway,
                    'Created at': created_at,
                    'Cancelled at': cancelled_at,
                    'Source': source,
                    'Tags': tags,
                    'Lineitem name': item.get('title', ''),
                    'Lineitem sku': item.get('sku', ''),
                    'Lineitem quantity': item.get('quantity', 1),
                    'Lineitem price': item.get('price', 0),
                    'Lineitem discount': line_discount,
                })

    df = pd.DataFrame(rows)
    logger.info(f"Transformed {len(orders)} orders into {len(df)} rows")
    return df


# =============================================================================
# SYNC ORCHESTRATOR
# =============================================================================

def sync_shopify_orders(
    start_date: str,
    end_date: str,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> Tuple[int, int, int]:
    """
    Main sync function: fetch from API -> transform -> import to database.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        progress_callback: Optional callback(message, progress_pct)

    Returns:
        Tuple of (new_count, updated_count, failed_count)
    """
    # Import the parser function
    try:
        from logistics_parsers import parse_shopify_csv
    except ImportError:
        from src.logistics_parsers import parse_shopify_csv

    import io

    if progress_callback:
        progress_callback("Initializing Shopify API...", 0.05)

    # Fetch orders from API
    api = ShopifyAPI()
    orders = api.fetch_orders(start_date, end_date, progress_callback)

    if not orders:
        if progress_callback:
            progress_callback("No orders found in date range", 1.0)
        return (0, 0, 0)

    if progress_callback:
        progress_callback(f"Transforming {len(orders)} orders...", 0.85)

    # Transform to CSV format
    df = transform_orders_to_csv_format(orders)

    if df.empty:
        if progress_callback:
            progress_callback("No data to import", 1.0)
        return (0, 0, 0)

    if progress_callback:
        progress_callback("Importing to database...", 0.9)

    # Convert DataFrame to CSV buffer for the parser
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)

    # Use existing parser to import
    result = parse_shopify_csv(csv_buffer)

    if progress_callback:
        if result.get('success', True):
            progress_callback(
                f"Done: {result.get('records_new', 0)} new, {result.get('records_updated', 0)} updated",
                1.0
            )
        else:
            progress_callback(f"Error: {result.get('error', 'Unknown error')}", 1.0)

    return (
        result.get('records_new', 0),
        result.get('records_updated', 0),
        result.get('records_failed', 0)
    )


# =============================================================================
# LAST SYNC TIMESTAMP
# =============================================================================

LAST_SYNC_FILE = "data/.shopify_last_sync"

def save_last_sync_timestamp():
    """Save current timestamp as last sync time."""
    try:
        os.makedirs(os.path.dirname(LAST_SYNC_FILE), exist_ok=True)
        with open(LAST_SYNC_FILE, 'w') as f:
            f.write(datetime.now().isoformat())
    except Exception as e:
        logger.error(f"Error saving last sync timestamp: {e}")


def get_last_sync_timestamp() -> Optional[datetime]:
    """Get the last sync timestamp."""
    try:
        if os.path.exists(LAST_SYNC_FILE):
            with open(LAST_SYNC_FILE, 'r') as f:
                return datetime.fromisoformat(f.read().strip())
    except Exception as e:
        logger.error(f"Error reading last sync timestamp: {e}")
    return None


# =============================================================================
# TEST CONNECTION
# =============================================================================

def test_shopify_connection() -> Dict[str, Any]:
    """
    Test Shopify API connection.

    Returns:
        Dict with 'success', 'message', and optionally 'shop_name'
    """
    try:
        api = ShopifyAPI()
        response = api._make_request('/shop.json')
        shop = response.get('shop', {})
        return {
            'success': True,
            'message': 'Connected successfully',
            'shop_name': shop.get('name', 'Unknown'),
            'shop_domain': shop.get('domain', ''),
        }
    except Exception as e:
        return {
            'success': False,
            'message': str(e)
        }


if __name__ == "__main__":
    # Test the API
    result = test_shopify_connection()
    print(f"Connection test: {result}")

    if result['success']:
        # Test fetching recent orders
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        print(f"\nFetching orders from {start_date} to {end_date}...")

        api = ShopifyAPI()
        orders = api.fetch_orders(start_date, end_date)
        print(f"Fetched {len(orders)} orders")

        if orders:
            df = transform_orders_to_csv_format(orders)
            print(f"Transformed to {len(df)} rows")
            print(df.head())
