"""
Prozo MIS Browser Automation

Automates downloading MIS reports from Proship/Prozo dashboard using Playwright.

Workflow:
1. Login to https://www.proship.in/
2. Click "Reports" in left sidebar
3. Click yellow "Create a new report" button
4. Select "MIS" from Report Name dropdown
5. Set date range (From Oct 1 to today)
6. Click "Get a report" multiple times (it often requires 2-3 clicks)
7. Download the generated CSV
8. Validate CSV has actual data
"""

import os
import logging
import asyncio
import tempfile
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import config helper for credentials
try:
    from config import get_prozo_email, get_prozo_password
except ImportError:
    from dotenv import load_dotenv
    load_dotenv()
    def get_prozo_email():
        return os.getenv('PROZO_EMAIL')
    def get_prozo_password():
        return os.getenv('PROZO_PASSWORD')


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class ProzoAutomationError(Exception):
    """Base exception for Prozo automation errors."""
    pass

class ProzoLoginError(ProzoAutomationError):
    """Login to Prozo failed."""
    pass

class ProzoNavigationError(ProzoAutomationError):
    """Navigation to Reports page failed."""
    pass

class ProzoReportGenerationError(ProzoAutomationError):
    """Report generation failed after multiple retries."""
    pass

class ProzoDownloadError(ProzoAutomationError):
    """Download failed or file is invalid."""
    pass

class ProzoEmptyReportError(ProzoAutomationError):
    """Downloaded report has no data."""
    pass


# =============================================================================
# CONSTANTS
# =============================================================================

PROSHIP_LOGIN_URL = "https://www.proship.in/"
PROSHIP_REPORTS_URL = "https://www.proship.in/reports"
DEFAULT_TIMEOUT = 60000  # 60 seconds
DOWNLOAD_TIMEOUT = 180000  # 3 minutes for download
GENERATE_RETRY_COUNT = 8  # Click "Get Report" up to 8 times (user says 3-5+ needed)
GENERATE_RETRY_DELAY = 3  # Wait 3 seconds between retries
MIN_EXPECTED_ROWS = 1  # Minimum rows expected in CSV


# =============================================================================
# CSV VALIDATION
# =============================================================================

def validate_csv_file(file_path: str) -> Tuple[bool, str, int]:
    """
    Validate that the downloaded CSV file has actual data.

    Args:
        file_path: Path to the CSV file

    Returns:
        Tuple of (is_valid, message, row_count)
    """
    if not os.path.exists(file_path):
        return False, f"File does not exist: {file_path}", 0

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        return False, "Downloaded file is empty (0 bytes)", 0

    if file_size < 100:
        return False, f"File too small ({file_size} bytes) - likely empty or error page", 0

    try:
        # Try to read as CSV
        df = pd.read_csv(file_path, low_memory=False, nrows=10)

        if df.empty:
            return False, "CSV file has no data rows", 0

        # Check for required columns
        required_columns = ['AWB', 'Status']
        missing_cols = [col for col in required_columns if col not in df.columns]

        if missing_cols:
            # Check alternate column names
            col_names_lower = [col.lower() for col in df.columns]
            alt_awb = any('awb' in col for col in col_names_lower)
            alt_status = any('status' in col for col in col_names_lower)

            if not alt_awb or not alt_status:
                return False, f"CSV missing required columns. Found: {list(df.columns)[:10]}", 0

        # Count all rows
        df_full = pd.read_csv(file_path, low_memory=False)
        row_count = len(df_full)

        if row_count < MIN_EXPECTED_ROWS:
            return False, f"CSV has only {row_count} rows - report may not have generated properly", row_count

        return True, f"Valid CSV with {row_count} rows", row_count

    except pd.errors.EmptyDataError:
        return False, "CSV file is empty or corrupted", 0
    except pd.errors.ParserError as e:
        return False, f"CSV parsing error: {str(e)}", 0
    except Exception as e:
        return False, f"Error validating CSV: {str(e)}", 0


# =============================================================================
# PROZO AUTOMATION CLASS
# =============================================================================

class ProzoAutomation:
    """
    Browser automation for Prozo/Proship MIS downloads.

    Follows the exact workflow:
    1. Login
    2. Go to Reports
    3. Click "Create a new report"
    4. Select "MIS" from dropdown
    5. Set date range
    6. Click "Get a report" (multiple times if needed)
    7. Download and validate
    """

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        headless: bool = True,
        download_dir: Optional[str] = None
    ):
        self.email = email or get_prozo_email()
        self.password = password or get_prozo_password()
        self.headless = headless
        self.download_dir = download_dir or tempfile.mkdtemp(prefix='prozo_downloads_')
        self.last_error = None

        if not self.email:
            raise ValueError("email is required. Set PROZO_EMAIL env var.")
        if not self.password:
            raise ValueError("password is required. Set PROZO_PASSWORD env var.")

        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None

    async def _init_browser(self):
        """Initialize Playwright browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ProzoAutomationError(
                "playwright is required. Install with: pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=self.headless)

        self.context = await self.browser.new_context(
            accept_downloads=True,
            viewport={'width': 1920, 'height': 1080}
        )
        self.page = await self.context.new_page()
        self.page.set_default_timeout(DEFAULT_TIMEOUT)

        logger.info(f"Browser initialized (headless={self.headless})")

    async def _close_browser(self):
        """Close browser and cleanup."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("Browser closed")
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")

    async def _take_screenshot(self, name: str = "debug") -> str:
        """Take screenshot for debugging."""
        try:
            screenshot_path = os.path.join(self.download_dir, f'{name}_{datetime.now().strftime("%H%M%S")}.png')
            await self.page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"Screenshot saved: {screenshot_path}")
            return screenshot_path
        except Exception as e:
            logger.warning(f"Could not take screenshot: {e}")
            return ""

    async def _login(
        self,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> bool:
        """Log into Proship dashboard."""
        if progress_callback:
            progress_callback("Opening Proship login page...", 0.1)

        try:
            await self.page.goto(PROSHIP_LOGIN_URL, wait_until='networkidle')
            await self.page.wait_for_load_state('domcontentloaded')
            await asyncio.sleep(2)

            if progress_callback:
                progress_callback("Entering credentials...", 0.15)

            # Find email input
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[name="username"]',
                'input[placeholder*="email" i]',
                '#email',
            ]

            email_input = None
            for selector in email_selectors:
                try:
                    email_input = await self.page.wait_for_selector(selector, timeout=5000)
                    if email_input:
                        break
                except:
                    continue

            if not email_input:
                await self._take_screenshot("login_no_email_field")
                raise ProzoLoginError("Could not find email input field")

            await email_input.click()
            await email_input.fill('')
            await email_input.type(self.email, delay=50)

            # Find password input
            password_input = await self.page.wait_for_selector('input[type="password"]', timeout=5000)
            if not password_input:
                raise ProzoLoginError("Could not find password input field")

            await password_input.click()
            await password_input.fill('')
            await password_input.type(self.password, delay=50)

            if progress_callback:
                progress_callback("Submitting login...", 0.2)

            # Click submit
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Login")',
                'button:has-text("Sign in")',
            ]

            for selector in submit_selectors:
                try:
                    submit_btn = await self.page.wait_for_selector(selector, timeout=3000)
                    if submit_btn:
                        await submit_btn.click()
                        break
                except:
                    continue

            await self.page.wait_for_load_state('networkidle')
            await asyncio.sleep(3)

            current_url = self.page.url

            if 'login' not in current_url.lower():
                if progress_callback:
                    progress_callback("Login successful!", 0.25)
                logger.info("Login successful")
                return True

            await self._take_screenshot("login_failed")
            raise ProzoLoginError("Login failed - still on login page")

        except ProzoLoginError:
            raise
        except Exception as e:
            raise ProzoLoginError(f"Login error: {str(e)}")

    async def _navigate_to_reports(
        self,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> bool:
        """Navigate to Reports section in left sidebar."""
        if progress_callback:
            progress_callback("Navigating to Reports...", 0.3)

        try:
            # First, make sure we're on the dashboard (not login page)
            current_url = self.page.url
            if 'login' in current_url.lower():
                raise ProzoNavigationError("Session expired - redirected to login")

            await self._take_screenshot("dashboard_before_reports")

            # Look for Reports in left sidebar
            # The sidebar may have "Reports" or "Reports and support"
            report_selectors = [
                # Exact text matches
                'text=Reports',
                'a:has-text("Reports")',
                'span:has-text("Reports")',
                'div:has-text("Reports")',
                # Reports and support
                'text="Reports and support"',
                'a:has-text("Reports and support")',
                # Navigation/sidebar specific
                'nav a:has-text("Reports")',
                '[class*="sidebar"] :has-text("Reports")',
                '[class*="nav"] :has-text("Reports")',
                '[class*="menu"] :has-text("Reports")',
                # MUI specific
                '.MuiListItem-root:has-text("Reports")',
                '.MuiListItemText-root:has-text("Reports")',
            ]

            reports_clicked = False
            for selector in report_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=3000)
                    if el:
                        # Check if it's visible
                        is_visible = await el.is_visible()
                        if is_visible:
                            await el.click(force=True)
                            await self.page.wait_for_load_state('networkidle')
                            await asyncio.sleep(2)
                            logger.info(f"Clicked Reports: {selector}")
                            reports_clicked = True
                            break
                except:
                    continue

            if not reports_clicked:
                # Try direct URL as fallback
                await self.page.goto(PROSHIP_REPORTS_URL, wait_until='networkidle')
                await asyncio.sleep(2)

            await self._take_screenshot("reports_page")

            if progress_callback:
                progress_callback("On Reports page", 0.35)

            return True

        except ProzoNavigationError:
            raise
        except Exception as e:
            await self._take_screenshot("reports_navigation_error")
            raise ProzoNavigationError(f"Navigation error: {str(e)}")

    async def _create_mis_report(
        self,
        start_date: str,
        end_date: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> bool:
        """
        Prozo Report Generation Flow:
        1. Click "Create new report" button
        2. Popup shows with "Report Name" DROPDOWN (must be clicked to open)
        3. Select "MIS" from dropdown options
        4. Set From date (Oct 1, 2025) and To date (today)
        5. Click "GET REPORT" button multiple times until download starts
        """
        if progress_callback:
            progress_callback("Looking for 'Create new report' button...", 0.4)

        try:
            # Step 1: Click "Create new report" button
            create_selectors = [
                'button:has-text("CREATE NEW REPORT")',
                'button:has-text("Create new report")',
                'button:text-is("Create new report")',
                'button:has-text("Create a new report")',
                '.MuiButton-root:has-text("Create new report")',
                '.MuiButton-root:has-text("CREATE NEW REPORT")',
                'button:has-text("New report")',
            ]

            create_btn = None
            for selector in create_selectors:
                try:
                    create_btn = await self.page.wait_for_selector(selector, timeout=5000)
                    if create_btn and await create_btn.is_visible():
                        logger.info(f"Found 'Create new report' button: {selector}")
                        break
                except:
                    continue

            if not create_btn:
                await self._take_screenshot("no_create_button")
                raise ProzoReportGenerationError("Could not find 'Create new report' button")

            await create_btn.click(force=True)
            await asyncio.sleep(3)  # Wait for popup

            await self._take_screenshot("popup_opened")

            if progress_callback:
                progress_callback("Opening Report Name dropdown...", 0.45)

            # Step 2: Click the "Report Name" dropdown to OPEN it first
            # The dropdown shows "Report Name" label and needs to be clicked
            dropdown_selectors = [
                # MUI Select component
                '.MuiDialog-root .MuiSelect-select',
                '.MuiDialog-root [role="combobox"]',
                '.MuiDialog-root [aria-haspopup="listbox"]',
                # By label text
                '.MuiDialog-root .MuiFormControl-root:has-text("Report Name")',
                '.MuiDialog-root .MuiInputBase-root',
                # Generic selects in dialog
                '.MuiDialog-root select',
                '[role="dialog"] .MuiSelect-select',
            ]

            dropdown = None
            for selector in dropdown_selectors:
                try:
                    dropdown = await self.page.wait_for_selector(selector, timeout=3000)
                    if dropdown and await dropdown.is_visible():
                        logger.info(f"Found dropdown: {selector}")
                        break
                except:
                    continue

            if not dropdown:
                # Try clicking on any input in the dialog
                await self._take_screenshot("dropdown_not_found")
                logger.warning("Could not find dropdown directly, trying to click on form control")
                dropdown = await self.page.query_selector('.MuiDialog-root .MuiInputBase-root')
                if not dropdown:
                    dropdown = await self.page.query_selector('.MuiDialog-root input')

            if dropdown:
                await dropdown.click(force=True)
                await asyncio.sleep(1)  # Wait for dropdown options to appear
                logger.info("Clicked dropdown to open it")
            else:
                logger.warning("No dropdown found, will try to find MIS directly")

            await self._take_screenshot("dropdown_opened")

            if progress_callback:
                progress_callback("Selecting MIS report type...", 0.48)

            # Step 3: Select "MIS" from the dropdown options
            # After clicking dropdown, options should appear as MuiMenuItem or listbox options

            # First, let's see what options are visible
            try:
                # Check for MUI listbox/menu
                options = await self.page.query_selector_all('[role="listbox"] [role="option"], .MuiMenu-list .MuiMenuItem-root, .MuiPopover-root .MuiMenuItem-root, [role="presentation"] .MuiMenuItem-root')
                logger.info(f"Found {len(options)} dropdown options")
                for i, opt in enumerate(options):
                    text = await opt.text_content()
                    logger.info(f"  Option {i}: '{text}'")
            except:
                pass

            # Look for MIS in the dropdown options
            mis_selectors = [
                # MUI MenuItem options (most likely after dropdown is opened)
                '.MuiMenuItem-root:text-is("MIS")',
                '[role="option"]:text-is("MIS")',
                '[role="listbox"] [role="option"]:has-text("MIS")',
                '.MuiMenu-list li:text-is("MIS")',
                '.MuiPopover-root li:text-is("MIS")',
                '[role="presentation"] li:text-is("MIS")',
                # Text match
                'li:text-is("MIS")',
                'text="MIS"',
            ]

            mis_clicked = False
            for selector in mis_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for el in elements:
                        text = await el.text_content()
                        text = text.strip() if text else ""
                        # EXACT match - only "MIS", not "MIS-FWD" or "MIS-RVP"
                        if text == "MIS":
                            await el.click(force=True)
                            logger.info(f"Clicked 'MIS' report type from dropdown")
                            mis_clicked = True
                            break
                    if mis_clicked:
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not mis_clicked:
                # Try finding all visible list items
                logger.info("Trying fallback: find all visible list items...")
                all_items = await self.page.query_selector_all('li, [role="option"], .MuiMenuItem-root')
                for item in all_items:
                    try:
                        is_visible = await item.is_visible()
                        if is_visible:
                            text = await item.text_content()
                            text = text.strip() if text else ""
                            logger.info(f"Visible item: '{text}'")
                            if text == "MIS":
                                await item.click(force=True)
                                logger.info("Clicked 'MIS' from fallback search")
                                mis_clicked = True
                                break
                    except:
                        continue

            if not mis_clicked:
                await self._take_screenshot("mis_not_found")
                raise ProzoReportGenerationError("Could not find 'MIS' report type in dropdown. Check screenshot.")

            # Wait for dropdown to close and date fields to become active
            await asyncio.sleep(2)

            # Verify MIS is still selected by checking dropdown text
            try:
                dropdown_value = await self.page.query_selector('.MuiDialog-root .MuiSelect-select')
                if dropdown_value:
                    current_value = await dropdown_value.text_content()
                    logger.info(f"Dropdown current value: '{current_value}'")
                    if current_value and current_value.strip() != "MIS":
                        logger.warning(f"Dropdown changed from MIS to '{current_value}', re-selecting...")
                        # Re-open dropdown and select MIS
                        await dropdown_value.click(force=True)
                        await asyncio.sleep(1)
                        mis_option = await self.page.query_selector('.MuiMenuItem-root:text-is("MIS"), [role="option"]:text-is("MIS")')
                        if mis_option:
                            await mis_option.click(force=True)
                            await asyncio.sleep(1)
            except Exception as e:
                logger.debug(f"Could not verify dropdown selection: {e}")

            if progress_callback:
                progress_callback(f"Setting date range: {start_date} to {end_date}...", 0.5)

            # Step 4: Set date range
            # The dialog has "From Date" and "To Date" input fields
            await self._take_screenshot("before_dates")

            # Find date inputs in the dialog
            # Date inputs have type="tel" and placeholder="dd/mm/yyyy"
            date_inputs = await self.page.query_selector_all('.MuiDialog-root input[placeholder*="dd"]')
            if len(date_inputs) < 2:
                date_inputs = await self.page.query_selector_all('.MuiDialog-root input[type="tel"]')
            if len(date_inputs) < 2:
                # Try any input in dialog and filter
                all_inputs = await self.page.query_selector_all('.MuiDialog-root input, [role="dialog"] input')
                date_inputs = []
                for inp in all_inputs:
                    placeholder = await inp.get_attribute('placeholder')
                    input_type = await inp.get_attribute('type')
                    # Only include inputs that look like date inputs
                    if placeholder and 'dd' in placeholder.lower():
                        date_inputs.append(inp)
                    elif input_type == 'tel':
                        date_inputs.append(inp)

            logger.info(f"Found {len(date_inputs)} date inputs in dialog")
            for i, inp in enumerate(date_inputs):
                placeholder = await inp.get_attribute('placeholder')
                input_type = await inp.get_attribute('type')
                logger.info(f"  Date input {i}: type={input_type}, placeholder={placeholder}")

            # Convert dates to different formats for compatibility
            # YYYY-MM-DD -> DD/MM/YYYY or DD-MM-YYYY
            try:
                from datetime import datetime as dt
                start_dt = dt.strptime(start_date, '%Y-%m-%d')
                end_dt = dt.strptime(end_date, '%Y-%m-%d')
                start_date_dmy = start_dt.strftime('%d/%m/%Y')  # 01/10/2025
                end_date_dmy = end_dt.strftime('%d/%m/%Y')      # 04/03/2026
                start_date_mdy = start_dt.strftime('%m/%d/%Y')  # 10/01/2025
                end_date_mdy = end_dt.strftime('%m/%d/%Y')      # 03/04/2026
            except:
                start_date_dmy = start_date
                end_date_dmy = end_date
                start_date_mdy = start_date
                end_date_mdy = end_date

            if len(date_inputs) >= 2:
                # First date input = From date, Second = To date
                from_input = date_inputs[0]
                to_input = date_inputs[1]

                # Method 1: Try using JavaScript to set values directly
                # This is more reliable for React/MUI inputs
                logger.info(f"Setting dates via JavaScript: {start_date_dmy} to {end_date_dmy}")

                try:
                    # Set From Date using JavaScript
                    await self.page.evaluate('''(args) => {
                        const [fromValue, toValue] = args;
                        const inputs = document.querySelectorAll('.MuiDialog-root input[placeholder*="dd"]');
                        if (inputs.length >= 2) {
                            // Trigger React's synthetic events
                            const setNativeValue = (element, value) => {
                                const valueSetter = Object.getOwnPropertyDescriptor(element, 'value')?.set;
                                const prototype = Object.getPrototypeOf(element);
                                const prototypeValueSetter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;

                                if (valueSetter && valueSetter !== prototypeValueSetter) {
                                    prototypeValueSetter.call(element, value);
                                } else if (valueSetter) {
                                    valueSetter.call(element, value);
                                } else {
                                    element.value = value;
                                }
                                element.dispatchEvent(new Event('input', { bubbles: true }));
                                element.dispatchEvent(new Event('change', { bubbles: true }));
                            };

                            setNativeValue(inputs[0], fromValue);
                            setNativeValue(inputs[1], toValue);
                        }
                    }''', [start_date_dmy, end_date_dmy])
                    await asyncio.sleep(1)
                    logger.info("JavaScript date setting completed")
                except Exception as e:
                    logger.warning(f"JavaScript date setting failed: {e}, falling back to typing")

                # Method 2: Also type the dates to be safe
                logger.info(f"Also typing dates: From={start_date_dmy}, To={end_date_dmy}")

                # Click and fill From Date
                await from_input.click(force=True)
                await asyncio.sleep(0.3)
                # Triple click to select all
                await from_input.click(click_count=3, force=True)
                await asyncio.sleep(0.2)
                await from_input.type(start_date_dmy, delay=50)
                await asyncio.sleep(0.5)

                # Tab to To Date
                await self.page.keyboard.press('Tab')
                await asyncio.sleep(0.5)

                # Fill To Date
                await to_input.click(force=True)
                await asyncio.sleep(0.3)
                await to_input.click(click_count=3, force=True)
                await asyncio.sleep(0.2)
                await to_input.type(end_date_dmy, delay=50)
                await asyncio.sleep(0.5)

                # Tab out to trigger validation
                await self.page.keyboard.press('Tab')
                await asyncio.sleep(0.5)

            else:
                logger.warning("Could not find 2 date inputs, trying alternative selectors")
                # Try finding by label or specific selectors
                # Look for inputs with From Date / To Date labels nearby
                from_input = await self.page.query_selector('.MuiDialog-root input[placeholder*="dd/mm/yyyy"]:first-of-type')
                to_input = await self.page.query_selector('.MuiDialog-root input[placeholder*="dd/mm/yyyy"]:last-of-type')

                if from_input:
                    await from_input.click(force=True)
                    await asyncio.sleep(0.2)
                    await from_input.fill('')
                    await from_input.type(start_date_dmy, delay=100)
                    logger.info(f"Set From date: {start_date_dmy}")

                if to_input:
                    await to_input.click(force=True)
                    await asyncio.sleep(0.2)
                    await to_input.fill('')
                    await to_input.type(end_date_dmy, delay=100)
                    logger.info(f"Set To date: {end_date_dmy}")

            await self._take_screenshot("dates_filled")

            if progress_callback:
                progress_callback("Clicking 'GET REPORT' button...", 0.55)

            # Step 5: Click "GET REPORT" button multiple times
            get_report_selectors = [
                '.MuiDialog-root button:has-text("GET REPORT")',
                '.MuiDialog-root button:has-text("Get Report")',
                '.MuiDialog-root button:text-is("GET REPORT")',
                'button:has-text("GET REPORT")',
                'button:has-text("Get Report")',
                '.MuiButton-root:has-text("GET REPORT")',
                '.MuiButton-root:has-text("Get Report")',
                'button:has-text("Generate")',
                'button:has-text("Submit")',
            ]

            # Find the GET REPORT button
            get_btn = None
            for selector in get_report_selectors:
                try:
                    get_btn = await self.page.wait_for_selector(selector, timeout=5000)
                    if get_btn and await get_btn.is_visible():
                        btn_text = await get_btn.text_content()
                        logger.info(f"Found GET REPORT button: '{btn_text}'")
                        break
                except:
                    continue

            if not get_btn:
                # List all buttons in dialog for debugging
                dialog_btns = await self.page.query_selector_all('.MuiDialog-root button')
                logger.info(f"Buttons in dialog ({len(dialog_btns)}):")
                for i, btn in enumerate(dialog_btns):
                    t = await btn.text_content()
                    logger.info(f"  Button {i}: '{t}'")

                await self._take_screenshot("no_get_report_button")
                raise ProzoReportGenerationError("Could not find 'GET REPORT' button in dialog")

            # Click multiple times QUICKLY - Prozo needs 3-5+ clicks
            # The dialog tends to close after showing toast, so click fast!
            clicks_made = 0

            if progress_callback:
                progress_callback("Clicking 'GET REPORT' multiple times (rapidly)...", 0.55)

            # Strategy: Click rapidly 5 times with minimal delay
            for attempt in range(1, 6):
                logger.info(f"Rapid click 'GET REPORT' - attempt {attempt}")

                try:
                    # Try to click even if visibility check is slow
                    await get_btn.click(force=True, timeout=2000)
                    clicks_made += 1
                except Exception as e:
                    logger.info(f"Click {attempt} failed: {e}")
                    # Try JavaScript click as backup
                    try:
                        await self.page.evaluate('''() => {
                            const btn = document.querySelector('.MuiDialog-root button');
                            if (btn && btn.textContent.toLowerCase().includes('get')) {
                                btn.click();
                            }
                        }''')
                        clicks_made += 1
                        logger.info(f"JS click {attempt} succeeded")
                    except:
                        break

                # Very short delay between clicks
                await asyncio.sleep(0.5)

            logger.info(f"Rapid clicks completed: {clicks_made} clicks")

            # Now wait a bit and continue clicking if dialog is still open
            await asyncio.sleep(2)

            for attempt in range(6, GENERATE_RETRY_COUNT + 1):
                try:
                    dialog = await self.page.query_selector('.MuiDialog-root')
                    if not dialog or not await dialog.is_visible():
                        logger.info("Dialog closed")
                        break

                    if progress_callback:
                        progress_callback(f"Clicking 'GET REPORT' (attempt {attempt}/{GENERATE_RETRY_COUNT})...", 0.55 + (attempt * 0.02))

                    logger.info(f"Additional click 'GET REPORT' - attempt {attempt}")
                    await get_btn.click(force=True)
                    clicks_made += 1
                    await asyncio.sleep(GENERATE_RETRY_DELAY)

                except Exception as e:
                    logger.info(f"Additional click {attempt} failed: {e}")
                    break

            logger.info(f"Total clicks made: {clicks_made}")
            await self._take_screenshot("after_get_report_clicks")

            if progress_callback:
                progress_callback("Report request submitted, waiting for auto-download...", 0.7)

            # Prozo auto-downloads to system Downloads folder
            # We need to watch for new MIS*.csv files there
            import glob
            downloads_folder = os.path.expanduser("~/Downloads")

            # Get existing MIS files before waiting
            existing_files = set(glob.glob(os.path.join(downloads_folder, "MIS_*.csv")))
            logger.info(f"Existing MIS files in Downloads: {len(existing_files)}")

            # Store for download phase
            self._existing_download_files = existing_files
            self._downloads_folder = downloads_folder

            # Wait for new file to appear
            if progress_callback:
                progress_callback("Waiting for report to auto-download...", 0.72)

            max_wait_seconds = 90  # Wait up to 90 seconds
            new_file_found = None

            for wait_count in range(max_wait_seconds // 3):
                await asyncio.sleep(3)

                # Check for new MIS files
                current_files = set(glob.glob(os.path.join(downloads_folder, "MIS_*.csv")))
                new_files = current_files - existing_files

                if new_files:
                    # Found new file!
                    new_file_found = max(new_files, key=os.path.getctime)
                    logger.info(f"New MIS file auto-downloaded: {new_file_found}")
                    break

                if progress_callback:
                    progress_callback(f"Waiting for auto-download... ({(wait_count+1)*3}s)", 0.72 + (wait_count * 0.005))

            if new_file_found:
                self._auto_downloaded_file = new_file_found
                logger.info(f"Auto-download successful: {new_file_found}")
            else:
                self._auto_downloaded_file = None
                logger.warning(f"No auto-download detected after {max_wait_seconds}s")

            return True

        except (ProzoReportGenerationError, ProzoEmptyReportError):
            raise
        except Exception as e:
            logger.error(f"Report generation error: {e}")
            await self._take_screenshot("generation_error")
            raise ProzoReportGenerationError(f"Report generation error: {str(e)}")

    async def _download_and_validate(
        self,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> str:
        """
        Get the downloaded file.

        Prozo auto-downloads to system Downloads folder.
        We check for the auto-downloaded file first, then fall back to manual download.
        """
        if progress_callback:
            progress_callback("Checking for downloaded file...", 0.75)

        try:
            download_path = None

            # First, check if we have an auto-downloaded file
            auto_downloaded = getattr(self, '_auto_downloaded_file', None)
            if auto_downloaded and os.path.exists(auto_downloaded):
                logger.info(f"Using auto-downloaded file: {auto_downloaded}")
                # Copy to our download dir for consistency
                import shutil
                filename = os.path.basename(auto_downloaded)
                download_path = os.path.join(self.download_dir, filename)
                shutil.copy2(auto_downloaded, download_path)
                logger.info(f"Copied to: {download_path}")

                if progress_callback:
                    progress_callback("Auto-download found!", 0.85)

                # Skip to validation
                return await self._validate_and_return(download_path, progress_callback)

            # No auto-download - set up listener for manual download
            download_started = False

            async def handle_download(download):
                nonlocal download_path, download_started
                download_started = True
                filename = download.suggested_filename or f"prozo_mis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                download_path = os.path.join(self.download_dir, filename)
                await download.save_as(download_path)
                logger.info(f"Download saved to: {download_path}")

            self.page.on("download", handle_download)

            # Wait briefly for download
            for i in range(10):
                if download_started:
                    break
                await asyncio.sleep(1)

            # If no automatic download, look for DOWNLOAD button in reports list
            if not download_started:
                if progress_callback:
                    progress_callback("Looking for report in list...", 0.78)

                logger.info("No automatic download - looking for DOWNLOAD button in reports table")

                # Wait for page to update with new report
                await asyncio.sleep(3)
                await self._take_screenshot("reports_list_before_download")

                # The reports page shows a table with reports
                # We need to find the NEW report (not the old one)
                # The new report should have the Oct date range

                # First, let's see all rows in the table
                all_rows_text = []
                try:
                    # Try different table selectors
                    rows = await self.page.query_selector_all('table tbody tr')
                    if not rows or len(rows) == 0:
                        rows = await self.page.query_selector_all('tr:has(button)')

                    logger.info(f"Found {len(rows)} report rows in table")
                    for i, row in enumerate(rows):
                        row_text = await row.text_content()
                        all_rows_text.append(row_text)
                        logger.info(f"  Row {i}: {row_text[:120]}...")
                except Exception as e:
                    logger.warning(f"Could not enumerate rows: {e}")

                # Look for the NEW report (with Oct date range)
                download_btn = None
                try:
                    rows = await self.page.query_selector_all('table tbody tr, tr:has(button)')
                    for row in rows:
                        row_text = await row.text_content()
                        row_text_lower = row_text.lower()

                        # The new report should have "Oct" in the date range
                        # Old report has "01 Mar - 02 Mar" (no Oct)
                        if 'oct' in row_text_lower:
                            btn = await row.query_selector('button:has-text("DOWNLOAD"), button:has-text("Download")')
                            if btn:
                                download_btn = btn
                                logger.info(f"Found NEW report with Oct date: {row_text[:100]}...")
                                break

                    if not download_btn:
                        # If no Oct report found, check if there are multiple reports
                        # and get the FIRST one (most recent)
                        initial_count = getattr(self, '_initial_report_count', 0)
                        current_buttons = await self.page.query_selector_all('button:has-text("DOWNLOAD"), button:has-text("Download")')

                        if len(current_buttons) > initial_count:
                            # New report was added - it should be at the top
                            download_btn = current_buttons[0]
                            logger.info(f"New report found at top of list (count: {len(current_buttons)} > {initial_count})")
                        else:
                            logger.warning(f"No new report found. Count: {len(current_buttons)}, Initial: {initial_count}")

                except Exception as e:
                    logger.warning(f"Error finding specific report: {e}")

                # Fallback: find any DOWNLOAD button
                if not download_btn:
                    download_selectors = [
                        'button:has-text("DOWNLOAD")',
                        'button:has-text("Download")',
                        'a:has-text("DOWNLOAD")',
                        'a:has-text("Download")',
                        '.MuiButton-root:has-text("DOWNLOAD")',
                    ]

                    for selector in download_selectors:
                        try:
                            buttons = await self.page.query_selector_all(selector)
                            if buttons and len(buttons) > 0:
                                download_btn = buttons[0]
                                btn_text = await download_btn.text_content()
                                logger.info(f"Found DOWNLOAD button (fallback): '{btn_text}'")
                                break
                        except:
                            continue

                if download_btn:
                    if progress_callback:
                        progress_callback("Clicking DOWNLOAD button...", 0.82)

                    # Try clicking the download button
                    for attempt in range(3):
                        try:
                            logger.info(f"Clicking DOWNLOAD button - attempt {attempt + 1}")

                            async with self.page.expect_download(timeout=60000) as download_info:
                                await download_btn.click(force=True)

                            download = await download_info.value
                            filename = download.suggested_filename or f"prozo_mis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                            download_path = os.path.join(self.download_dir, filename)
                            await download.save_as(download_path)
                            download_started = True
                            logger.info(f"Downloaded via DOWNLOAD button to: {download_path}")
                            break

                        except Exception as e:
                            logger.warning(f"DOWNLOAD button attempt {attempt+1} failed: {e}")
                            await asyncio.sleep(2)
                else:
                    logger.error("Could not find DOWNLOAD button")
                    await self._take_screenshot("no_download_button")

            # Check if we got a download
            if not download_path or not os.path.exists(download_path):
                # Check the downloads folder for any recent CSV
                import glob
                csv_files = glob.glob(os.path.join(self.download_dir, "*.csv"))
                if csv_files:
                    # Get most recent
                    download_path = max(csv_files, key=os.path.getctime)
                    logger.info(f"Found CSV file in downloads folder: {download_path}")

            if not download_path or not os.path.exists(download_path):
                # Last resort - check Downloads folder again
                import glob
                downloads_folder = getattr(self, '_downloads_folder', os.path.expanduser("~/Downloads"))
                existing_files = getattr(self, '_existing_download_files', set())
                current_files = set(glob.glob(os.path.join(downloads_folder, "MIS_*.csv")))
                new_files = current_files - existing_files

                if new_files:
                    download_path = max(new_files, key=os.path.getctime)
                    logger.info(f"Found new file in Downloads: {download_path}")

            if not download_path or not os.path.exists(download_path):
                await self._take_screenshot("no_download")
                raise ProzoDownloadError("Download did not happen. Please try manually generating the report in Prozo.")

            return await self._validate_and_return(download_path, progress_callback)

        except (ProzoDownloadError, ProzoEmptyReportError):
            raise
        except Exception as e:
            raise ProzoDownloadError(f"Download error: {str(e)}")

    async def _validate_and_return(
        self,
        download_path: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> str:
        """Validate CSV and return path."""
        if progress_callback:
            progress_callback("Validating downloaded file...", 0.9)

        is_valid, message, row_count = validate_csv_file(download_path)

        if not is_valid:
            await self._take_screenshot("invalid_csv")
            raise ProzoEmptyReportError(f"Downloaded file validation failed: {message}")

        if progress_callback:
            progress_callback(f"Downloaded valid CSV with {row_count} rows", 0.95)

        logger.info(f"CSV validated: {row_count} rows")
        return download_path

    async def download_mis_report(
        self,
        start_date: str,
        end_date: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> str:
        """
        Complete flow: Login -> Reports -> Create MIS Report -> Download.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            progress_callback: Optional callback(message, progress_pct)

        Returns:
            Path to validated CSV file

        Raises:
            ProzoAutomationError (or subclass) with clear error message
        """
        try:
            if progress_callback:
                progress_callback("Initializing browser...", 0.05)

            await self._init_browser()

            # Login
            await self._login(progress_callback)

            # Navigate to Reports
            await self._navigate_to_reports(progress_callback)

            # Create and generate MIS report
            await self._create_mis_report(start_date, end_date, progress_callback)

            # Download and validate
            csv_path = await self._download_and_validate(progress_callback)

            if progress_callback:
                progress_callback("Download complete!", 1.0)

            return csv_path

        except ProzoAutomationError:
            raise
        except Exception as e:
            logger.error(f"MIS download error: {e}")
            raise ProzoAutomationError(f"Unexpected error: {str(e)}")

        finally:
            await self._close_browser()


# =============================================================================
# SYNC WRAPPER
# =============================================================================

def download_prozo_mis(
    start_date: str,
    end_date: str,
    progress_callback: Optional[Callable[[str, float], None]] = None,
    headless: bool = True
) -> str:
    """
    Synchronous wrapper for downloading Prozo MIS report.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        progress_callback: Optional callback(message, progress_pct)
        headless: Run browser in headless mode (default True)

    Returns:
        Path to validated CSV file

    Raises:
        ProzoAutomationError (or subclass) with clear error message
    """
    automation = ProzoAutomation(headless=headless)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(
        automation.download_mis_report(start_date, end_date, progress_callback)
    )


# =============================================================================
# TEST CONNECTION
# =============================================================================

def test_prozo_connection() -> Dict[str, Any]:
    """Test Prozo connection and credentials."""
    try:
        email = get_prozo_email()
        password = get_prozo_password()

        if not email or not password:
            return {
                'success': False,
                'message': 'PROZO_EMAIL and PROZO_PASSWORD not configured in .env'
            }

        try:
            import playwright
        except ImportError:
            return {
                'success': False,
                'message': 'playwright not installed. Run: pip install playwright && playwright install chromium'
            }

        return {
            'success': True,
            'message': 'Prozo credentials configured',
            'email': email
        }

    except Exception as e:
        return {
            'success': False,
            'message': str(e)
        }


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    result = test_prozo_connection()
    print(f"Connection test: {result}")

    if result['success']:
        # Default: Oct 1, 2025 to today (as per user workflow)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = "2025-10-01"
        print(f"\nAttempting to download MIS for {start_date} to {end_date}...")

        def progress_cb(msg, pct):
            print(f"[{pct*100:.0f}%] {msg}")

        try:
            csv_path = download_prozo_mis(start_date, end_date, progress_cb, headless=False)
            print(f"\nSUCCESS: Downloaded to {csv_path}")

            is_valid, message, row_count = validate_csv_file(csv_path)
            print(f"Validation: {message}")

        except ProzoAutomationError as e:
            print(f"\nFAILED: {type(e).__name__}: {str(e)}")
        except Exception as e:
            print(f"\nUNEXPECTED ERROR: {str(e)}")
