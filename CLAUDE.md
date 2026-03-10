# GuitarBro Shopify Analytics Dashboard

## Project Overview

A comprehensive analytics dashboard for GuitarBro's Shopify store and Facebook advertising operations. Built with Streamlit, this dashboard provides:

- **Order Analytics**: Shopify order tracking, COD vs Prepaid analysis
- **FB Ads Analytics**: Campaign performance, ROAS tracking, scaling recommendations
- **FB Comment Bot**: Automated comment fetching, AI classification, and reply management
- **User Journey Tracking**: Order → Zoom attendance matching
- **Logistics Reconciliation**: Shopify + Prozo data matching, delivery tracking
- **Live Learning**: Luma registrations → Zoom attendance → Shopify order matching

## Project Structure

```
shopify-dashboard/
├── src/
│   ├── app.py                    # Main Streamlit app with navigation
│   ├── config.py                 # Secrets helper (supports .env + Streamlit Cloud)
│   ├── shared_styles.py          # SHARED CSS - Import in ALL modules
│   │
│   │   # FB Comment Bot
│   ├── fb_comment_bot_module.py  # Comment Bot UI (fetch, classify, reply)
│   ├── supabase_db.py            # Supabase database operations (cloud storage)
│   ├── comment_classifier.py     # Claude API integration for classification
│   ├── comment_fetcher.py        # Orchestrates fetch → classify → store
│   ├── facebook_api.py           # Facebook Graph API v21.0 wrapper
│   │
│   │   # FB Ads
│   ├── fb_ads_module.py          # Facebook Ads analytics UI
│   ├── ad_scaling_logic.py       # Ad scaling decision engine
│   │
│   │   # User Journey
│   ├── user_journey_module.py    # Order → Attendance matching UI
│   │
│   │   # Logistics Reconciliation
│   ├── logistics_module.py       # Logistics UI (Dashboard, Journey, Line Items)
│   ├── logistics_db.py           # Database schema & CRUD operations
│   ├── logistics_parsers.py      # CSV parsers for Shopify & Prozo
│   ├── logistics_engine.py       # Matching engine & metrics calculation
│   ├── prozo_automation.py       # Playwright browser automation for Prozo MIS
│   ├── prozo_sync.py             # Prozo sync orchestration (download → parse → import)
│   │
│   │   # Live Learning
│   ├── live_learning_module.py   # Live Learning UI (Dashboard, Upload, Events)
│   ├── live_learning_db.py       # Database schema & user deduplication
│   └── live_learning_parsers.py  # CSV parsers for Luma & Zoom
│
├── .streamlit/
│   ├── config.toml               # Streamlit theme configuration
│   └── secrets.toml.example      # Template for Streamlit Cloud secrets
│
├── data/
│   ├── orders.db                 # Shopify orders (SQLite)
│   ├── fb_ads.db                 # FB Ads data (SQLite)
│   ├── fb_comments.db            # Comment bot data (SQLite)
│   ├── journey.db                # User journey tracking (SQLite)
│   ├── logistics.db              # Logistics reconciliation (SQLite)
│   └── ad_comments.csv           # Manual ad notes
│
├── docs/
│   ├── USER_JOURNEY_PRD.md       # PRD for user journey module
│   └── PHASE1_LOGISTICS_OUTLINE.md  # Phase 1 logistics specs
│
├── CLAUDE.md                     # This file - project documentation
├── UI_GUIDELINES.md              # UI development guidelines
├── STYLING_GUIDE.md              # Visual CSS reference guide
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables (not in git)
├── .env.example                  # Template for environment variables
└── .gitignore
```

---

## Streamlit Cloud Deployment

### GitHub Repository
- **URL**: https://github.com/shubham373/guitarbro-dashboard
- **Branch**: `main`
- **Main file**: `src/app.py`

### Streamlit Cloud App
- **URL**: https://guitarbro-dashboard-appzp3wkdhdyoc6kappppzb8v.streamlit.app

### Authentication (Viewer Access Control)
To restrict access to approved emails only:
1. Go to Streamlit Cloud → Your App → Settings → Sharing
2. Change from "Public" to "Private"
3. Select "Email allowlist"
4. Add approved email addresses or domains (e.g., `@guitarbro.com`)

### Secrets Configuration
Secrets are configured in Streamlit Cloud Settings → Secrets (TOML format):

```toml
# Facebook Graph API
FACEBOOK_PAGE_ID = "151712605546634"
FACEBOOK_PAGE_ACCESS_TOKEN = "your_token_here"
FACEBOOK_APP_ID = "883305767908950"
FACEBOOK_APP_SECRET = "your_secret_here"
FACEBOOK_AD_ACCOUNT_ID = "act_89400171"
FACEBOOK_USER_ACCESS_TOKEN = "your_token_here"

# Claude API
ANTHROPIC_API_KEY = "sk-ant-api03-your_key_here"

# Supabase (REQUIRED for persistent data)
SUPABASE_URL = "https://your-project-id.supabase.co"
SUPABASE_KEY = "your_service_role_key_here"
```

### Database Architecture (CRITICAL - ALL MODULES MUST FOLLOW)

**THIS IS A HARD REQUIREMENT FOR ALL MODULES**

#### Core Principle: Supabase is the Source of Truth

| Environment | Database Backend | When |
|-------------|------------------|------|
| **Streamlit Cloud** | **Supabase** (REQUIRED) | Production - all data must persist in cloud |
| **Local Development** | SQLite | Testing only - data is ephemeral |

#### Supabase Project Details
- **Project URL**: `https://ansuuhyoqddwtxqfoxsn.supabase.co`
- **Storage**: 500MB free tier (~2 years of data at current usage)

#### How Backend Selection Works

Every module that accesses data MUST:

1. **Check if Supabase is available** at module load time
2. **Use Supabase functions** when `USE_SUPABASE = True`
3. **Fall back to SQLite** only when Supabase is unavailable (local dev)

```python
# CORRECT PATTERN - Every *_db.py and *_engine.py must follow this:

import os

# Detect environment
IS_STREAMLIT_CLOUD = os.environ.get('STREAMLIT_CLOUD') or os.path.exists('/mount/src')

# Try Supabase first
USE_SUPABASE = False
try:
    from supabase_db import get_supabase_client, SUPABASE_AVAILABLE
    if SUPABASE_AVAILABLE:
        USE_SUPABASE = True
except ImportError:
    pass

def get_data():
    if USE_SUPABASE:
        return supabase_get_data()  # Use Supabase
    else:
        return sqlite_get_data()    # Fallback for local dev
```

#### Module Database Files

| Module | Supabase Helper | SQLite Fallback | Status |
|--------|----------------|-----------------|--------|
| FB Comment Bot | `supabase_db.py` | `fb_comments.db` | ✅ Done |
| FB Ads | `supabase_fb_ads_db.py` | `fb_ads.db` | ⚠️ Needs engine update |
| Logistics | `supabase_logistics_db.py` | `logistics.db` | ⚠️ Needs engine update |
| Live Learning | (needs creation) | `logistics.db` | ❌ Not implemented |
| User Journey | (needs creation) | `journey.db` | ❌ Not implemented |

#### Supabase Tables (Cloud Database)

**FB Comment Bot:**
- `fb_comments` - All FB/IG comments with classification
- `fb_bot_config` - Runtime settings (shadow_mode, etc.)
- `fb_commenter_history` - Repeat commenter tracking
- `fb_bot_log` - Audit and cost tracking
- `fb_posts_tracked` - Monitored posts/ads

**Logistics:**
- `raw_shopify_orders` - Shopify order data
- `raw_prozo_orders` - Prozo shipment data
- `unified_orders` - Matched orders with delivery status
- `order_line_items` - Individual product line items

**FB Ads:**
- `fb_ads_daily` - Daily ad performance metrics
- `fb_ads_campaigns` - Campaign metadata

#### IMPORTANT: Engine Files Must Use Supabase

The `*_engine.py` files (e.g., `logistics_engine.py`) contain the business logic for matching, metrics, and data processing. These files currently use SQLite directly via `get_db_connection()`.

**REQUIRED FIX**: All engine files must be updated to:
1. Import both Supabase and SQLite functions
2. Check `USE_SUPABASE` flag before every database operation
3. Call appropriate backend functions

Example fix needed for `logistics_engine.py`:
```python
# WRONG (current):
from logistics_db import get_db_connection
conn = get_db_connection()  # Always SQLite!

# CORRECT (required):
from logistics_db import USE_SUPABASE
if USE_SUPABASE:
    from supabase_logistics_db import get_unified_orders, upsert_unified_orders
    # Use Supabase functions
else:
    conn = get_db_connection()  # SQLite fallback
```

#### UI Indicator

All modules should show which database is active:
- ☁️ Green: "Supabase (Cloud)" - Data persists across reboots
- 💾 Yellow: "SQLite (Local)" - Data may be lost on reboot (local dev only)

#### SQLite Path Warning

**NEVER use relative paths for SQLite databases.** Use absolute paths:
```python
# WRONG:
DB_PATH = "data/logistics.db"  # Breaks depending on cwd

# CORRECT:
import os
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "logistics.db")
```

---

## Shared Styles (MUST FOLLOW)

**THIS IS A HARD REQUIREMENT FOR ALL MODULES**

### How to Apply Styles

**EVERY module MUST import and use the shared styles:**

```python
from shared_styles import inject_custom_css

def render_your_module():
    inject_custom_css()  # Call this FIRST in every render function
    # ... rest of your module code
```

### Color Contrast Rules

| Background Type | Text Color | Hex Code |
|-----------------|------------|----------|
| No pill/overlay (plain background) | **BLACK** | `#000000` |
| Blue pill/badge background | **BLACK** | `#000000` |
| Dark/Black/Gray pill background | **WHITE** | `#FFFFFF` |

### Color Palette

**Blues (for pills, borders, highlights):**
- Light Blue: `#DBEAFE` - Pill backgrounds, metric cards, tabs
- Medium Blue: `#93C5FD` - Borders, dividers
- Dark Blue: `#3B82F6` - Accents, links

**Status Colors (all use BLACK text):**
- Success: `#D1FAE5` background
- Error: `#FEE2E2` background
- Warning: `#FEF3C7` background
- Info: `#DBEAFE` background

### DO NOT

- Never use gray text on white background
- Never use white text on light background
- Never use inline CSS - always use shared_styles.py
- Never skip calling inject_custom_css()

### Dropdown / Selectbox Styling

**ALL dropdowns must have:**
- **Background**: White (`#FFFFFF`)
- **Text**: Black (`#000000`)
- **Border**: 2px solid blue (`#3B82F6`)
- **Hover**: Light blue background (`#DBEAFE`)

```css
/* Dropdown container */
[data-baseweb="select"] {
    background-color: #FFFFFF !important;
    border: 2px solid #3B82F6 !important;
}

/* Dropdown menu items */
[data-baseweb="menu"] li {
    background-color: #FFFFFF !important;
    color: #000000 !important;
}

/* Selected/hover state */
[data-baseweb="menu"] li:hover {
    background-color: #DBEAFE !important;
}
```

### Date Picker Styling

**Date picker must have:**
- **Input field**: White background, black text, blue border
- **Calendar popup**: White background, black text
- **Selected date**: Blue background (`#3B82F6`), white text
- **Hover**: Light blue (`#DBEAFE`)

```css
/* Date input */
[data-testid="stDateInput"] input {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    border: 2px solid #3B82F6 !important;
}

/* Calendar - WHITE bg, BLACK text */
[data-baseweb="calendar"] {
    background-color: #FFFFFF !important;
}

[data-baseweb="calendar"] * {
    color: #000000 !important;
}

/* Month name, year, day names - all BLACK */
[data-baseweb="calendar"] th,
[data-baseweb="calendar"] button {
    color: #000000 !important;
    background-color: #FFFFFF !important;
}

/* Selected day - BLUE bg, WHITE text */
[data-baseweb="calendar"] [aria-selected="true"] {
    background-color: #3B82F6 !important;
    color: #FFFFFF !important;
}
```

---

## Module Documentation

### 1. FB Comment Bot Module

**Files:** `fb_comment_bot_module.py`, `comment_classifier.py`, `comment_fetcher.py`, `facebook_api.py`

**Features:**
- **Fetch from Active Ads**: Fetches comments from ads with spend in last 7 days
- **Delivery-based filtering**: Uses Insights API with `time_range` to get ads with actual delivery
- **`filter=stream`**: Gets ALL comments including hidden/filtered ones
- **Instagram Support**: Fetches IG comments via `effective_instagram_media_id`
- **Parent Comments Only**: Only counts customer parent comments (not replies, not page's own comments)
- **Thread Display**: Shows conversation threads under each parent comment
- **AI Classification**: Uses Claude Haiku to categorize comments
- **Shadow Mode**: Generate replies without posting (default ON)
- **Reply Management**: Approve/Edit/Skip replies before posting

**Comment Filtering Logic:**
1. Skip comments that have a `parent` field (they are replies)
2. Skip comments where `from.id` equals GuitarBro page ID
3. Fetch thread replies separately and display under parent
4. Instagram: Skip comments from GuitarBro's IG username

**How Ad Comment Fetching Works:**
1. Uses Facebook Insights API with `time_range` (last 7 days INCLUDING today)
2. Filters to ads with `spend > 0` (actual delivery)
3. Gets `effective_object_story_id` and `effective_instagram_media_id` from creative
4. Fetches FB comments with `filter=stream` parameter
5. Fetches IG comments with `replies` field for threading
6. Classifies with Claude Haiku
7. Stores with `platform`, `parent_comment_id`, `thread_depth` fields

**Key API Parameters:**
- `time_range`: `{"since": "YYYY-MM-DD", "until": "YYYY-MM-DD"}` - includes today
- `filter=stream`: Gets ALL comments including hidden ones
- `effective_instagram_media_id`: For accessing IG comments on ad dark posts

**Ad Account:** `act_89400171` (Shubham Bansal)
**Page ID:** `151712605546634` (GuitarBro)

**Comment Categories:**
- `price_objection` - Price complaints, discount requests
- `doubt` - Skepticism, questioning legitimacy
- `product_question` - Sizing, material, shipping questions
- `positive` - Praise, gratitude, excitement
- `negative` - Complaints, disappointment
- `complaint` - Service issues, order problems
- `other` - Everything else

**Category Colors (UI):**
| Category | Background Color |
|----------|-----------------|
| price_objection | `#FEF3C7` (Yellow) |
| doubt | `#FED7AA` (Orange) |
| product_question | `#DBEAFE` (Blue) |
| positive | `#D1FAE5` (Green) |
| negative | `#FEE2E2` (Red) |
| complaint | `#FECACA` (Light Red) |
| other | `#E5E7EB` (Gray) |

**UI Features:**
- Commenter name with comment count badge
- Clickable Facebook/Instagram links on each comment
- Thread replies displayed indented under parent comment
- Platform icon (📘 Facebook, 📷 Instagram)

**Shadow Mode:**
- **ON (default)**: Replies are generated but NOT posted to Facebook
- **OFF**: Clicking "Approve" actually posts the reply to Facebook
- Toggle in: FB Comment Bot → ⚙️ Settings → Shadow Mode

**Known Issues:**
- Facebook API can have delay showing new comments (minutes to hours)
- Comments with profanity may be hidden by Facebook
- Different pages require separate tokens (e.g., page 112629158166593 shows permission errors)

### 2. FB Ads Module

**Files:** `fb_ads_module.py`, `ad_scaling_logic.py`

**Features:**
- Campaign performance tracking
- ROAS analysis with phase-based logic (Day 1-3, Day 4-7, Day 8+)
- Ad scaling recommendations: Continue / Monitor / Kill
- CSV upload for ad data
- Manual notes per ad

**Decision Logic:**
- **Continue**: ROAS > threshold, consistent performance
- **Monitor**: Mixed signals, needs more data
- **Kill**: ROAS < threshold, high spend, no conversions

### 3. Logistics Reconciliation Module

**Files:** `logistics_module.py`, `logistics_db.py`, `logistics_parsers.py`, `logistics_engine.py`, `supabase_logistics_db.py`, `prozo_automation.py`, `prozo_sync.py`

**Database:** Uses Supabase (cloud) with SQLite fallback for local development.

**Features:**
- **Data Sources**: Shopify Orders (API sync) + Prozo MIS (browser automation sync)
- **Matching**: Shopify.Name ↔ Prozo.channelOrderName
- **Payment Breakdown**: Full Prepaid / Partial Prepaid / COD
- **Delivery Status**: Delivered / In Transit / RTO / Cancelled / Not Shipped
- **Revenue Metrics**: Projected, Actual, Lost, Pending + AOV
- **Dispatch Time**: <24h (fast) / 24-48h (normal) / >48h (delayed)
- **Date Filters**: Today, Yesterday (default), This Month, Last Month, Custom (all calendar-based)

**Data Sync:**
- **Shopify**: API-based sync (automatic, uses Admin API)
- **Prozo**: Browser automation sync using Playwright
  - Logs into https://www.proship.in/
  - Downloads MIS CSV report for selected date range
  - Auto-imports and matches with Shopify orders
  - Requires: `PROZO_EMAIL` and `PROZO_PASSWORD` in .env
  - Requires: `pip install playwright && playwright install chromium`

**UI Tabs:**
- Dashboard: Metrics overview, payment/delivery breakdown, sync controls
- User Journey: Per-order timeline
- Line Items: Individual product details

**Prozo Sync Setup:**
1. Add to `.env`:
   ```
   PROZO_EMAIL=your_prozo_email@example.com
   PROZO_PASSWORD=your_prozo_password
   ```
2. Install Playwright: `pip install playwright && playwright install chromium`
3. Use "Sync from Prozo" section in Dashboard tab

### 4. User Journey Module

**Files:** `user_journey_module.py`

**Features:**
- Tracks: Shopify order → Zoom attendance → Upsell
- Imports Shopify orders CSV and Zoom attendance reports
- Waterfall matching:
  1. Exact email match (100% confidence)
  2. Fuzzy email match (85%+ threshold)
  3. Exact name match (70% confidence)
  4. Fuzzy name match (60%+ threshold)
- Journey stages: `ordered` → `engaged`
- Audit logging for all match decisions

**UI Tabs:**
- Upload & Preview
- Run Matching
- Unified Users
- Audit Log

### 5. Live Learning Module

**Files:** `live_learning_module.py`, `live_learning_db.py`, `live_learning_parsers.py`

**Purpose:** Track user journey from Luma event registrations → Zoom meeting attendance → Shopify orders.

**Features:**
- **Luma Import**: Parse guest list CSV exports, track registrations
- **Zoom Import**: Parse attendance reports, aggregate duration & join frequency
- **User Deduplication**: Match users by email OR phone across both sources
- **Order Matching**: Link users to Shopify orders (searches from latest orders first)
- **Date Range Filtering**: Filter dashboard by date range (not event dropdown)
- **Metrics**: Registrations, attendance rate, match rate, avg duration, repeat registrants

**Database Tables (in `logistics.db`):**
- `live_events`: Events from Luma or Zoom uploads
- `live_unified_users`: Deduplicated users with all emails/phones/names
- `live_event_registrations`: Registration records per user per event
- `live_event_attendance`: Attendance records with duration, join frequency

**User Deduplication Logic:**
1. Check if email exists in any user's `primary_email` or `all_emails` array
2. If no email match, check if phone exists in any user's `primary_phone` or `all_phones` array
3. If match found, merge new contact info into existing user
4. If no match, create new unified user

**Zoom Parsing:**
- Aggregates multiple join/leave sessions for same user
- Sums duration across sessions
- Counts join frequency (how many times user joined)
- Tracks first join time and last leave time
- Skips host entries

**Order Matching:**
- Matches `all_emails` and `all_phones` against `raw_shopify_orders` table
- Searches from latest orders first (most recent likely to match)
- Records match method: 'email', 'phone', or 'both'

**UI Tabs:**
- Dashboard: Metrics overview, user journey table with filtering
- Upload Data: Luma and Zoom CSV upload with preview
- Events: List of all uploaded events

---

## Tech Stack

- **Frontend**: Streamlit
- **Database**: SQLite (local), Supabase (cloud - planned)
- **Hosting**: Streamlit Cloud
- **APIs**:
  - Facebook Graph API v21.0
  - Claude API (Anthropic)
- **AI Model**: Claude Haiku (`claude-haiku-4-5-20251001`) for comment classification
- **Python Packages**: See requirements.txt

## Requirements

```
streamlit>=1.28.0
pandas>=2.0.0
plotly>=5.18.0
openpyxl>=3.1.2
requests>=2.31.0
python-dotenv>=1.0.0
anthropic>=0.18.0
```

---

## Environment Variables

Required in `.env` (local) or Streamlit Cloud Secrets:

```bash
# Facebook Graph API (Page Access)
FACEBOOK_PAGE_ID=151712605546634
FACEBOOK_PAGE_ACCESS_TOKEN=your_never_expiring_page_token
FACEBOOK_APP_ID=883305767908950
FACEBOOK_APP_SECRET=your_app_secret

# Facebook Ads API (for fetching comments from active ads)
FACEBOOK_AD_ACCOUNT_ID=act_89400171
FACEBOOK_USER_ACCESS_TOKEN=your_user_token_with_ads_read

# Database
FB_COMMENTS_DB_PATH=data/fb_comments.db

# Claude API (for comment classification)
ANTHROPIC_API_KEY=sk-ant-api03-...

# Prozo/Proship MIS Sync (browser automation)
PROZO_EMAIL=your_prozo_login_email
PROZO_PASSWORD=your_prozo_password
```

### Facebook Token Setup

**Two tokens are needed:**

1. **Page Access Token** (for reading/replying to comments):
   - Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
   - Select your App → Select Page → Generate Token
   - Permissions: `pages_read_engagement`, `pages_manage_engagement`

2. **User Access Token** (for accessing Ads API):
   - Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
   - Select your App → Select "User Token" (not Page)
   - Permissions: `ads_read`, `pages_read_engagement`, `pages_manage_engagement`
   - This token accesses your ad account to get active ads

**Ad Account ID:**
- Go to [Ads Manager](https://www.facebook.com/adsmanager/)
- Find `act_XXXXXXXXX` in URL or account settings

### Anthropic API Key

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Create API key
3. Add to `.env` as `ANTHROPIC_API_KEY`

---

## Running the App

### Local Development

```bash
cd shopify-dashboard

# Activate virtualenv (if using)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run Streamlit (use port 8503 for local)
streamlit run src/app.py --server.port 8503
```

The app will be available at `http://localhost:8503`

### Streamlit Cloud

1. Push to GitHub: `git push origin main`
2. App auto-deploys at: https://guitarbro-dashboard-appzp3wkdhdyoc6kappppzb8v.streamlit.app
3. Configure secrets in Streamlit Cloud Settings → Secrets

---

## Database Schemas

### fb_comments.db (Comment Bot)

| Table | Purpose |
|-------|---------|
| `fb_comments` | All fetched comments with classification |
| `fb_comment_tags` | Multi-tag support per comment |
| `fb_posts_tracked` | Monitored posts/ads |
| `fb_commenter_history` | Repeat commenter tracking |
| `fb_dashboard_actions` | Queued manual actions |
| `fb_bot_config` | Runtime configuration (shadow_mode, etc.) |
| `fb_bot_log` | Audit trail |

**Key fields in `fb_comments`:**
- `fb_comment_id` - Facebook comment ID
- `parent_comment_id` - Parent comment ID (for threading)
- `thread_depth` - 0 for parent, 1+ for replies
- `platform` - 'facebook' or 'instagram'
- `comment_text` - Original comment text
- `category` - AI classification result
- `sentiment` - positive/negative/neutral
- `confidence` - Classification confidence (0-1)
- `reply_text` - Suggested/approved reply
- `reply_status` - pending/approved/sent/skipped
- `commenter_name` - Name of the commenter
- `commenter_fb_id` - Facebook/Instagram ID of commenter
- `ad_name` - Name of the ad this comment is on

### SQLite Databases (Local Development Only)

**Note**: These SQLite files are for LOCAL DEVELOPMENT only. In production (Streamlit Cloud), all data MUST come from Supabase.

| SQLite File | Purpose | Supabase Equivalent |
|-------------|---------|---------------------|
| `fb_comments.db` | Comment bot data | ✅ Supabase tables |
| `fb_ads.db` | Daily ad performance metrics | ⚠️ Needs migration |
| `orders.db` | Shopify order data | (via logistics) |
| `journey.db` | User journey tracking | ❌ Needs creation |
| `logistics.db` | Logistics reconciliation | ✅ Supabase tables (but engine uses SQLite!) |

---

## Quick Reference

| Action | Location |
|--------|----------|
| Fetch FB comments | FB Comment Bot → Overview → Fetch Now |
| Test FB connection | FB Comment Bot → Overview → Test FB |
| Test Instagram connection | FB Comment Bot → Overview → Test IG |
| Test Claude API | FB Comment Bot → Overview → Test Claude |
| Toggle shadow mode | FB Comment Bot → ⚙️ Settings → Shadow Mode |
| View comment threads | FB Comment Bot → 💬 Comments |
| Upload Shopify CSV | Logistics → Dashboard → Upload |
| Upload Prozo CSV | Logistics → Dashboard → Upload |
| View ad recommendations | FB Ads → Recommendations |
| Match orders to attendance | User Journey → Run Matching |

---

## Troubleshooting

### "Facebook API not available"
- Check `.env` has valid `FACEBOOK_PAGE_ACCESS_TOKEN`
- Verify token hasn't expired (use never-expiring token)
- Check `FACEBOOK_PAGE_ID` is correct

### "Permission denied" errors for some ads
- Some ads are on different Facebook pages (e.g., page ID `112629158166593`)
- You need separate page tokens for each page
- These ads are skipped but IG comments may still work

### "Classifier not ready"
- Check `.env` has valid `ANTHROPIC_API_KEY`
- Verify API key has credits available
- Check network connectivity

### CSS not applying
- Ensure `inject_custom_css()` is called first in render function
- Check import: `from shared_styles import inject_custom_css`
- Clear Streamlit cache: `st.cache_data.clear()`

### "No comments found" but comments exist
- Facebook API can have **delay** (minutes to hours)
- Comments with profanity may be **hidden by Facebook**
- Use `filter=stream` parameter (already implemented)

### Data lost after Streamlit Cloud reboot
- SQLite uses ephemeral storage on Streamlit Cloud
- **Solution**: Ensure module uses Supabase backend (see Database Architecture section)

### Zero orders / Missing data in Logistics or other modules
- **Likely cause**: Module is using SQLite instead of Supabase
- Check if `USE_SUPABASE = True` is being set
- Check if engine files (`*_engine.py`) are calling Supabase functions
- Verify no duplicate SQLite files exist (e.g., `src/data/` vs `data/`)
- **Debug**: Add logging to confirm which backend is active

### Wrong database being used (relative path issue)
- SQLite paths like `data/logistics.db` resolve based on current working directory
- Running from `src/` creates `src/data/logistics.db` (different file!)
- **Solution**: Use absolute paths or ensure Supabase is primary backend

---

## Session Context (Important - Do Not Lose)

### Active Ad Account Setup
- **Ad Account ID**: `act_89400171` (Shubham Bansal)
- **Page ID**: `151712605546634` (GuitarBro)
- **User has 25 ad accounts** total, but main one for GuitarBro is `act_89400171`

### Token Configuration
Two tokens are needed in `.env`:
1. **FACEBOOK_PAGE_ACCESS_TOKEN** - Page token for reading/posting comments
2. **FACEBOOK_USER_ACCESS_TOKEN** - User token with `ads_read` permission for Ads API

### Comment Counting Logic
- **Only parent comments count** as "comments"
- Replies (thread_depth > 0) are displayed but not counted separately
- Page's own replies are filtered out
- This matches Business Manager's comment count

### Facebook API Structure
```
Ad Account
 └── Campaign (status)
      └── Ad Set (status)
           └── Ad (status) → effective_status considers all parents
                └── Creative
                     ├── effective_object_story_id → FB Post → Comments
                     └── effective_instagram_media_id → IG Media → Comments
```

### Key Fixes Implemented (Feb 2026)
1. **`date_preset=last_7d` excludes today** → Fixed with `time_range` parameter
2. **Missing comments** → Added `filter=stream` to get hidden comments
3. **Instagram comments** → Use `effective_instagram_media_id` from ad creative
4. **Page's own replies counted** → Filter by `commenter_id != page_id`
5. **Replies counted as comments** → Only count `thread_depth=0` or no parent

---

## Next Steps (TODO)

### 1. Supabase Migration - ALL MODULES (IN PROGRESS)

**FB Comment Bot**: ✅ Complete
- [x] Create Supabase tables
- [x] Create `supabase_db.py` helper
- [x] Update module to use Supabase when available

**Logistics Module**: ✅ Complete
- [x] Create Supabase tables
- [x] Create `supabase_logistics_db.py` helper
- [x] Update `logistics_engine.py` to use Supabase backend
- [x] Update `logistics_parsers.py` to use Supabase backend
- [x] Update `logistics_db.py` to use absolute paths
- [x] Migrate existing SQLite data to Supabase (9,534 orders)
- [x] Test matching engine with Supabase backend

**FB Ads Module**: ⚠️ Partial - NEEDS COMPLETION
- [x] Create `supabase_fb_ads_db.py` helper
- [ ] Update `fb_ads_module.py` to use Supabase backend
- [ ] Migrate ad scaling logic to use Supabase

**Live Learning Module**: ❌ NOT STARTED
- [ ] Create Supabase tables for live events
- [ ] Create `supabase_live_learning_db.py` helper
- [ ] Update `live_learning_db.py` to support dual backends
- [ ] Update module to use Supabase when available

**User Journey Module**: ❌ NOT STARTED
- [ ] Create Supabase tables for journey data
- [ ] Create `supabase_journey_db.py` helper
- [ ] Update module to use Supabase when available

### 2. Authentication
- [x] Enable Streamlit Cloud viewer authentication
- [ ] Add email allowlist in Streamlit Cloud settings

### 3. Deploy & Test
- [x] Add Supabase secrets to Streamlit Cloud
- [x] Verify Logistics module uses Supabase in production
- [x] Delete stale `src/data/` directory (duplicate SQLite files)

### 4. Future Enhancements
- [ ] Auto-refresh comments every X minutes
- [ ] Email notifications for new comments
- [ ] Bulk approve/skip actions
- [ ] Export comments to CSV
