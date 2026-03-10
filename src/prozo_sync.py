"""
Prozo MIS Sync Orchestrator

Handles the complete Prozo sync workflow:
1. Download MIS CSV via browser automation
2. Validate the CSV has actual data
3. Parse and import to database
4. Run matching with Shopify orders

Clear error handling - fails explicitly rather than importing bad data.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Tuple, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

LAST_SYNC_FILE = "data/.prozo_last_sync"


# =============================================================================
# CUSTOM EXCEPTIONS (re-export from automation module)
# =============================================================================

try:
    from prozo_automation import (
        ProzoAutomationError,
        ProzoLoginError,
        ProzoNavigationError,
        ProzoReportGenerationError,
        ProzoDownloadError,
        ProzoEmptyReportError,
    )
except ImportError:
    from src.prozo_automation import (
        ProzoAutomationError,
        ProzoLoginError,
        ProzoNavigationError,
        ProzoReportGenerationError,
        ProzoDownloadError,
        ProzoEmptyReportError,
    )


# =============================================================================
# LAST SYNC TIMESTAMP
# =============================================================================

def save_last_prozo_sync_timestamp():
    """Save current timestamp as last Prozo sync time."""
    try:
        os.makedirs(os.path.dirname(LAST_SYNC_FILE), exist_ok=True)
        with open(LAST_SYNC_FILE, 'w') as f:
            f.write(datetime.now().isoformat())
    except Exception as e:
        logger.error(f"Error saving last sync timestamp: {e}")


def get_last_prozo_sync_timestamp() -> Optional[datetime]:
    """Get the last Prozo sync timestamp."""
    try:
        if os.path.exists(LAST_SYNC_FILE):
            with open(LAST_SYNC_FILE, 'r') as f:
                return datetime.fromisoformat(f.read().strip())
    except Exception as e:
        logger.error(f"Error reading last sync timestamp: {e}")
    return None


# =============================================================================
# SYNC ORCHESTRATOR
# =============================================================================

def sync_prozo_orders(
    start_date: str,
    end_date: str,
    progress_callback: Optional[Callable[[str, float], None]] = None,
    headless: bool = True
) -> Tuple[int, int, int]:
    """
    Main sync function: download MIS -> validate -> parse -> import to database.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        progress_callback: Optional callback(message, progress_pct)
        headless: Run browser in headless mode (default True)

    Returns:
        Tuple of (new_count, updated_count, failed_count)

    Raises:
        ProzoAutomationError (or subclass) if sync fails
    """
    # Import required modules
    try:
        from prozo_automation import download_prozo_mis, validate_csv_file
        from logistics_parsers import parse_prozo_csv
    except ImportError:
        from src.prozo_automation import download_prozo_mis, validate_csv_file
        from src.logistics_parsers import parse_prozo_csv

    if progress_callback:
        progress_callback("Initializing Prozo sync...", 0.05)

    # Step 1: Download MIS CSV via browser automation
    # This will raise ProzoAutomationError if it fails
    csv_path = download_prozo_mis(
        start_date=start_date,
        end_date=end_date,
        progress_callback=progress_callback,
        headless=headless
    )

    # csv_path is guaranteed to be valid if we reach here
    # (download_prozo_mis raises exceptions on failure)

    if progress_callback:
        progress_callback("CSV validated, importing to database...", 0.9)

    # Step 2: Parse and import the CSV
    result = parse_prozo_csv(csv_path)

    # Step 3: Cleanup downloaded file
    try:
        os.remove(csv_path)
        logger.info(f"Cleaned up temp file: {csv_path}")
    except Exception as e:
        logger.warning(f"Could not cleanup temp file: {e}")

    # Check parse result
    if not result.get('success', False):
        error_msg = result.get('error', 'Unknown parsing error')
        raise ProzoAutomationError(f"CSV parsing failed: {error_msg}")

    if progress_callback:
        new_count = result.get('records_new', 0)
        updated_count = result.get('records_updated', 0)
        progress_callback(
            f"Done: {new_count} new, {updated_count} updated",
            1.0
        )

    return (
        result.get('records_new', 0),
        result.get('records_updated', 0),
        result.get('records_failed', 0)
    )


def sync_prozo_from_file(
    file_path: str,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> Tuple[int, int, int]:
    """
    Sync from a local MIS CSV file (fallback if automation fails).

    Args:
        file_path: Path to the CSV file
        progress_callback: Optional callback(message, progress_pct)

    Returns:
        Tuple of (new_count, updated_count, failed_count)

    Raises:
        ProzoAutomationError if file is invalid or parsing fails
    """
    try:
        from prozo_automation import validate_csv_file
        from logistics_parsers import parse_prozo_csv
    except ImportError:
        from src.prozo_automation import validate_csv_file
        from src.logistics_parsers import parse_prozo_csv

    if progress_callback:
        progress_callback("Validating CSV file...", 0.3)

    if not os.path.exists(file_path):
        raise ProzoDownloadError(f"File not found: {file_path}")

    # Validate the file first
    is_valid, message, row_count = validate_csv_file(file_path)

    if not is_valid:
        raise ProzoEmptyReportError(f"Invalid CSV: {message}")

    if progress_callback:
        progress_callback(f"Importing {row_count} rows...", 0.5)

    result = parse_prozo_csv(file_path)

    if not result.get('success', False):
        error_msg = result.get('error', 'Unknown parsing error')
        raise ProzoAutomationError(f"CSV parsing failed: {error_msg}")

    if progress_callback:
        progress_callback(
            f"Done: {result.get('records_new', 0)} new, {result.get('records_updated', 0)} updated",
            1.0
        )

    return (
        result.get('records_new', 0),
        result.get('records_updated', 0),
        result.get('records_failed', 0)
    )


# =============================================================================
# TEST CONNECTION
# =============================================================================

def test_prozo_connection() -> Dict[str, Any]:
    """
    Test Prozo connection and credentials.

    Returns:
        Dict with 'success', 'message', and optionally 'email'
    """
    try:
        from prozo_automation import test_prozo_connection as _test
        return _test()
    except ImportError:
        from src.prozo_automation import test_prozo_connection as _test
        return _test()


def check_prozo_availability() -> Dict[str, Any]:
    """
    Check if Prozo sync is available (credentials configured, playwright installed).

    Returns:
        Dict with 'available', 'message', 'missing' (list of missing requirements)
    """
    missing = []

    # Check credentials
    try:
        from config import get_prozo_email, get_prozo_password
    except ImportError:
        from dotenv import load_dotenv
        load_dotenv()
        import os
        def get_prozo_email():
            return os.getenv('PROZO_EMAIL')
        def get_prozo_password():
            return os.getenv('PROZO_PASSWORD')

    if not get_prozo_email():
        missing.append('PROZO_EMAIL')
    if not get_prozo_password():
        missing.append('PROZO_PASSWORD')

    # Check playwright
    try:
        import playwright
    except ImportError:
        missing.append('playwright (pip install playwright && playwright install chromium)')

    if missing:
        return {
            'available': False,
            'message': f"Missing: {', '.join(missing)}",
            'missing': missing
        }

    return {
        'available': True,
        'message': 'Prozo sync is available',
        'missing': []
    }


def get_error_message(error: Exception) -> str:
    """
    Get a user-friendly error message from an exception.

    Args:
        error: The exception

    Returns:
        User-friendly error message
    """
    if isinstance(error, ProzoLoginError):
        return f"Login failed: {str(error)}"
    elif isinstance(error, ProzoNavigationError):
        return f"Could not access Prozo dashboard: {str(error)}"
    elif isinstance(error, ProzoReportGenerationError):
        return f"Report generation failed: {str(error)}"
    elif isinstance(error, ProzoDownloadError):
        return f"Download failed: {str(error)}"
    elif isinstance(error, ProzoEmptyReportError):
        return f"No data: {str(error)}"
    elif isinstance(error, ProzoAutomationError):
        return f"Prozo error: {str(error)}"
    else:
        return f"Unexpected error: {str(error)}"


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    # Check availability
    status = check_prozo_availability()
    print(f"Availability: {status}")

    if status['available']:
        # Test connection
        conn = test_prozo_connection()
        print(f"Connection: {conn}")

        if conn['success']:
            # Test sync with last 7 days
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            print(f"\nSyncing {start_date} to {end_date}...")

            def progress_cb(msg, pct):
                print(f"[{pct*100:.0f}%] {msg}")

            try:
                new_count, updated_count, failed_count = sync_prozo_orders(
                    start_date, end_date, progress_cb, headless=False
                )
                print(f"\n SUCCESS: {new_count} new, {updated_count} updated, {failed_count} failed")

            except ProzoAutomationError as e:
                print(f"\n FAILED: {get_error_message(e)}")
            except Exception as e:
                print(f"\n UNEXPECTED: {str(e)}")
