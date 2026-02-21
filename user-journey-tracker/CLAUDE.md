# User Journey Tracker

## Project Overview
Customer lifecycle tracking system that matches users across Shopify orders and Zoom attendance to build unified user profiles.

## Architecture

### Database (SQLite - data/journey.db)
- `raw_shopify_orders` - Imported Shopify order data with normalized fields
- `raw_zoom_attendance` - Raw Zoom attendance records
- `zoom_participants_deduped` - Aggregated participant records per meeting
- `unified_users` - Merged user profiles with journey stage tracking
- `match_audit_log` - Audit trail for all matching decisions

### Core Modules
1. **schema.py** - Database initialization and connection management
2. **data_loader.py** - CSV parsers for Shopify and Zoom with deduplication
3. **matching_engine.py** - Waterfall matching algorithm
4. **app.py** - Streamlit web interface

## Matching Waterfall
1. Exact email match (confidence: 1.0)
2. Fuzzy email match using SequenceMatcher (confidence: 0.85+)
3. Exact name match (confidence: 0.7)
4. Fuzzy name match (confidence: 0.6+)
5. No match - requires manual review

## Key Normalization Rules

### Phone Numbers
- Strip all non-digits
- Remove prefixes: +91, 0, 091
- Must be exactly 10 digits

### Emails
- Lowercase
- Validate contains @

### Names
- Lowercase
- Remove titles (Mr, Mrs, Dr, Shri, etc.)
- Remove special characters
- Collapse whitespace

## Journey Stages
- `ordered` - Has placed an order but not attended events
- `engaged` - Has attended at least one event

## Running the App
```bash
cd user-journey-tracker
streamlit run app.py
```

## Data Import Flow
1. Upload Shopify Orders CSV (from Shopify Admin > Orders > Export)
2. Upload Zoom Attendance CSV (from Zoom > Reports > Meeting)
3. Run matching algorithm for each meeting
4. Import remaining unmatched orders as unified users
5. Review low-confidence matches in Audit Log

## UI Guidelines
- Light theme with #F7F8FA background
- Text color: #1A1A1A (dark gray)
- Accent color: #528FF0 (blue)
- All text must be visible on light background

## Phase 2 Roadmap (Future)
- Add more data sources (Shiprocket, Razorpay)
- Implement purchase-to-upsell tracking
- Add cohort analysis
- Export to Google Sheets
