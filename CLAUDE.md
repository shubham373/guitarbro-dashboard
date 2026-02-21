# GuitarBro Shopify Analytics Dashboard

## Project Overview

A comprehensive analytics dashboard for GuitarBro's Shopify store and Facebook advertising operations. Built with Streamlit, this dashboard provides:

- **Order Analytics**: Shopify order tracking, COD vs Prepaid analysis
- **FB Ads Analytics**: Campaign performance, ROAS tracking, scaling recommendations
- **FB Comment Bot**: Automated comment fetching, AI classification, and reply management
- **User Journey Tracking**: Order → Zoom attendance matching
- **Logistics Reconciliation**: Shopify + Prozo data matching, delivery tracking

## Project Structure

```
shopify-dashboard/
├── src/
│   ├── app.py                    # Main Streamlit app with navigation
│   ├── shared_styles.py          # SHARED CSS - Import in ALL modules
│   │
│   │   # FB Comment Bot
│   ├── fb_comment_bot_module.py  # Comment Bot UI (fetch, classify, reply)
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
│   └── logistics_engine.py       # Matching engine & metrics calculation
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
├── user-journey-tracker/         # Standalone journey tracker (legacy)
│
├── CLAUDE.md                     # This file - project documentation
├── UI_GUIDELINES.md              # UI development guidelines
├── STYLING_GUIDE.md              # Visual CSS reference guide
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables (not in git)
└── .gitignore
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

---

## Module Documentation

### 1. FB Comment Bot Module

**Files:** `fb_comment_bot_module.py`, `comment_classifier.py`, `comment_fetcher.py`, `facebook_api.py`

**Features:**
- **Fetch from Active Ads**: Fetches comments from active Facebook ads (not organic posts)
- **48-hour window**: Only fetches comments from the last 48 hours
- **AI Classification**: Uses Claude Haiku to categorize comments
- **Shadow Mode**: Generate replies without posting (default)
- **Reply Management**: Approve/Edit/Skip replies before posting
- **Commenter History**: Track repeat commenters and patterns

**How Ad Comment Fetching Works:**
1. Uses Facebook Ads API with User Access Token + `ads_read` permission
2. Fetches ads with these effective statuses: `ACTIVE`, `ADSET_PAUSED`, `CAMPAIGN_PAUSED`
   - This catches all ads where the AD itself is active, even if parent adset/campaign is paused
3. For each ad, gets `effective_object_story_id` (the post ID linked to the ad creative)
4. Fetches comments on each post using Page Access Token
5. Filters to only comments from last 48 hours
6. Stores ad_id and ad_name with each comment for tracking

**Important: Facebook API Limitations:**
- Comments are on POSTS, not directly on ADS
- Each ad's creative links to a post via `effective_object_story_id`
- New comments can take minutes to hours to appear in the API (caching delay)
- Some comments may be hidden by Facebook's content filters

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

**Workflow:**
1. Click "Fetch Now" → Gets active ads from Ads API
2. For each ad → Gets post ID from creative → Fetches comments (last 48h)
3. Claude classifies each comment (category, sentiment, confidence)
4. Claude generates suggested reply
5. Comments stored in database with `reply_status = pending`, `ad_id`, `ad_name`
6. Review in dashboard → Approve/Edit/Skip
7. Approved replies posted to Facebook (or shadow mode)

**UI Tabs:**
- Overview: Connection status, fetch button, recent stats
- Comments: Browse/filter/action comments
- Analytics: Category breakdown, sentiment trends
- Config: Shadow mode toggle, notification settings

**Known Issues:**
- Facebook API can have delay showing new comments (minutes to hours)
- Comments with profanity may be hidden by Facebook
- Dynamic creative ads show one `effective_object_story_id` even with multiple creatives

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

**Files:** `logistics_module.py`, `logistics_db.py`, `logistics_parsers.py`, `logistics_engine.py`

**Features:**
- **Data Sources**: Shopify Orders CSV + Prozo MIS CSV
- **Matching**: Shopify.Name ↔ Prozo.channelOrderName
- **Payment Breakdown**: Full Prepaid / Partial Prepaid / COD
- **Delivery Status**: Delivered / In Transit / RTO / Cancelled / Not Shipped
- **Revenue Metrics**: Projected, Actual, Lost, Pending + AOV
- **Dispatch Time**: <24h (fast) / 24-48h (normal) / >48h (delayed)
- **Date Filters**: Yesterday (default), Last 7/14 days, Last Month, This Month, Custom

**UI Tabs:**
- Dashboard: Metrics overview, payment/delivery breakdown
- User Journey: Per-order timeline
- Line Items: Individual product details

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

---

## Tech Stack

- **Frontend**: Streamlit
- **Database**: SQLite (multiple .db files)
- **APIs**:
  - Facebook Graph API v21.0
  - Claude API (Anthropic)
- **AI Model**: Claude Haiku (`claude-haiku-4-5-20251001`) for comment classification
- **Python Packages**: See requirements.txt

## Requirements

```
streamlit
pandas
plotly
openpyxl
requests
python-dotenv
anthropic
```

---

## Environment Variables

Required in `.env`:

```bash
# Facebook Graph API (Page Access)
FACEBOOK_PAGE_ID=your_page_id
FACEBOOK_PAGE_ACCESS_TOKEN=your_never_expiring_page_token
FACEBOOK_APP_ID=your_app_id
FACEBOOK_APP_SECRET=your_app_secret

# Facebook Ads API (for fetching comments from active ads)
FACEBOOK_AD_ACCOUNT_ID=act_XXXXXXXXX
FACEBOOK_USER_ACCESS_TOKEN=your_user_token_with_ads_read

# Database
FB_COMMENTS_DB_PATH=data/fb_comments.db

# Claude API (for comment classification)
ANTHROPIC_API_KEY=sk-ant-api03-...
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

**IMPORTANT: Always use port 8503. Do not create new hosts on other ports.**

```bash
cd shopify-dashboard

# Activate virtualenv (if using)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run Streamlit (ALWAYS use port 8503)
streamlit run src/app.py --server.port 8503
```

The app will be available at `http://localhost:8503`

### Port Rules
- **8503** - ONLY port to use for this dashboard
- Never start new Streamlit instances on 8501, 8502, or other ports
- If 8503 is already running, refresh the browser instead of starting a new instance
- To restart: Kill existing process first, then start on 8503

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
- `comment_text` - Original comment text
- `category` - AI classification result
- `sentiment` - positive/negative/neutral
- `confidence` - Classification confidence (0-1)
- `reply_text` - Suggested/approved reply
- `reply_status` - pending/approved/sent/skipped
- `claude_reasoning` - AI reasoning for classification

### fb_ads.db (Ads Analytics)

| Table | Purpose |
|-------|---------|
| `fb_ads_data` | Daily ad performance metrics |

### orders.db (Shopify)

| Table | Purpose |
|-------|---------|
| `orders` | Shopify order data (JSON storage) |

### journey.db (User Journey)

| Table | Purpose |
|-------|---------|
| `raw_shopify_orders` | Imported orders (normalized phone/email) |
| `raw_zoom_attendance` | Raw Zoom participant records |
| `zoom_participants_deduped` | Deduplicated participants per meeting |
| `unified_users` | Merged customer profiles |
| `match_audit_log` | Matching decision audit trail |

### logistics.db (Logistics Reconciliation)

| Table | Purpose |
|-------|---------|
| `raw_shopify_orders` | Shopify orders (normalized) |
| `raw_prozo_orders` | Prozo MIS data |
| `unified_orders` | Matched orders with delivery status |
| `order_line_items` | Individual line items |
| `payment_method_mapping` | Payment classification lookup |
| `delivery_status_mapping` | Status normalization lookup |
| `import_log` | Import audit trail |

---

## Adding New Modules

1. Create `src/new_module.py` following existing module patterns
2. Add database init function if needed
3. Create main render function: `render_new_module()`
4. Import shared_styles:
   ```python
   from shared_styles import inject_custom_css

   def render_new_module():
       inject_custom_css()  # REQUIRED - call first
       st.title("New Module")
       # ... rest of code
   ```
5. Import in `app.py`
6. Add to `nav_items` list in `render_sidebar()`
7. Add to `page_map` dictionary in `main()`

---

## Cost Estimates

### Claude API (Comment Classification)

Using Claude Haiku model:
- ~$0.25/million input tokens
- ~$1.25/million output tokens
- **Per comment**: ~₹0.02 INR
- **100 comments/day**: ~₹60/month

### Facebook API

- **Free** for page management
- Only requires Page Access Token with appropriate permissions

---

## Quick Reference

| Action | Location |
|--------|----------|
| Fetch FB comments | FB Comment Bot → Overview → Fetch Now |
| Test FB connection | FB Comment Bot → Overview → Test Connection |
| Test Claude API | FB Comment Bot → Overview → Test Claude |
| Toggle shadow mode | FB Comment Bot → Config → Shadow Mode |
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

### "Classifier not ready"
- Check `.env` has valid `ANTHROPIC_API_KEY`
- Verify API key has credits available
- Check network connectivity

### CSS not applying
- Ensure `inject_custom_css()` is called first in render function
- Check import: `from shared_styles import inject_custom_css`
- Clear Streamlit cache: `st.cache_data.clear()`

### Database errors
- Check `data/` directory exists
- Verify write permissions on db files
- Check `FB_COMMENTS_DB_PATH` in `.env`

### "No comments found" but comments exist on Facebook
- Facebook API can have **delay** (minutes to hours) before new comments appear
- Comments with profanity (like "BC") may be **hidden by Facebook's content filter**
- Try refreshing/fetching again after some time

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

### Current Ad Fetching Logic
The system fetches ads with these effective statuses:
- `ACTIVE` - Currently running ads
- `ADSET_PAUSED` - Ad is active but ad set is paused
- `CAMPAIGN_PAUSED` - Ad is active but campaign is paused

This ensures we catch comments on ALL ad posts where the ad itself is active.

### Key Post IDs and Their Ads (as of Feb 2026)
| Post ID | Ad ID | Ad Name |
|---------|-------|---------|
| 1070927281717969 | 6928554023939 | Ad 1084 (RL) - Pichle 20 saalo |
| 1052305276913503 | 6928553350139 | Ad 1083 (RL) - Tech Shuffle |
| 1336214625189232 | 6915744574939 | Flexiple Ad 700 (has recent comments) |
| 1049374640539900 | 6928551298539 | Ad 1080 (RL) - Ankit Joshi |

### Facebook API Structure
```
Ad Account
 └── Campaign (status)
      └── Ad Set (status)
           └── Ad (status) → effective_status considers all parents
                └── Creative → effective_object_story_id → Post
                     └── Comments (what we fetch)
```

### Port Configuration
- **ALWAYS use port 8503** for Streamlit
- Never start new instances on 8501, 8502, or other ports
- URL: `http://localhost:8503`

### Comment Fetching Workflow
1. `get_active_ad_posts()` → Fetches ads from Ads API
2. For each ad → Extract `effective_object_story_id` from creative
3. `get_post_comments()` → Fetch comments from each post
4. Filter to last 48 hours only
5. Skip duplicates (already in database)
6. Classify with Claude Haiku
7. Store in `fb_comments.db`

### Known Facebook API Limitations
1. **New comments delay**: Can take minutes to hours to appear in API
2. **Profanity filter**: Comments like "BC" may be hidden
3. **Privacy settings**: Some commenter names show as "Unknown"
4. **Rate limits**: ~200 calls/hour for standard apps
5. **Dynamic creative**: Multiple creatives share one `effective_object_story_id`
