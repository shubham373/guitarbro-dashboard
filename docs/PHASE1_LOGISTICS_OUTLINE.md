# Phase 1: Logistics Reconciliation Dashboard - Feature Outline

## Scope Summary

**Data Sources (Phase 1):**
- Shopify Orders CSV
- Prozo MIS Report CSV

**NOT in Phase 1:**
- Razorpay reconciliation
- Prozo Passbook/billing
- Customer identity fuzzy matching
- Zoom attendance matching

---

## 1. Payment Method Classification

### Source: Shopify `Financial Status` + `Payment Method`

| Shopify Financial Status | Shopify Payment Method | Our Classification |
|--------------------------|------------------------|-------------------|
| `paid` | Razorpay / any | **Full Prepaid** |
| `partially_paid` | Razorpay + COD | **Partial Prepaid** |
| `pending` | Cash on Delivery | **COD** |
| `voided` | any | Cancelled (pre-ship) |
| `refunded` | any | Refunded |
| `partially_refunded` | any | Partially Refunded |

### Consolidated Payment Modes (3 categories):
1. **Full Prepaid** - Customer paid 100% online
2. **Partial Prepaid** - Customer paid partial (e.g., ₹149) + balance COD
3. **COD** - Customer pays full amount on delivery

---

## 2. Delivery Status Classification

### Source: Prozo `Status` field

| Prozo Status | Our Classification | Revenue Impact |
|--------------|-------------------|----------------|
| `DELIVERED` | **Delivered** | ✅ Actual Revenue |
| `SHIPMENT_DELAYED` | **In Transit** | ⏳ Pending Revenue |
| `OUT_FOR_DELIVERY` | **In Transit** | ⏳ Pending Revenue |
| `FAILED_DELIVERY` | **In Transit** | ⏳ Pending Revenue |
| `CANCELLED_ORDER` | **Cancelled** | ❌ Lost Revenue (never shipped) |
| `RTO_DELIVERED` | **RTO** | ❌ Lost Revenue |
| `RTO_REQUESTED` | **RTO** | ❌ Lost Revenue |
| `RTO_INTRANSIT` | **RTO** | ❌ Lost Revenue |
| `RTO_OUT_FOR_DELIVERY` | **RTO** | ❌ Lost Revenue |

### Final 5 Delivery Categories:
1. **Delivered** - Successfully delivered → Actual Revenue
2. **In Transit** - On the way to customer (forward only) → Pending Revenue
3. **Cancelled** - Cancelled before shipping → Lost Revenue
4. **RTO** - All RTO stages (requested/in-transit/delivered back) → Lost Revenue
5. **Not Shipped** - In Shopify but not in Prozo yet → Pending

### Note:
- No separate "In Transit Return" - all RTO stages grouped as "RTO"
- RTO is lost revenue regardless of whether product returned to warehouse or not

---

## 3. Revenue Metrics

### Definitions:

| Metric | Formula | Description |
|--------|---------|-------------|
| **Projected Revenue** | SUM(Total) for all orders in date range | What we could earn if all delivered |
| **Projected AOV** | Projected Revenue / Total Orders | Average order value (all orders) |
| **Actual Revenue** | SUM(Total) for DELIVERED orders only | What we actually earned |
| **Actual AOV** | Actual Revenue / Delivered Orders | Average of successful orders |
| **Pending Revenue** | SUM(Total) for In-Transit + Not Shipped | Still in delivery pipeline |
| **Lost Revenue** | SUM(Total) for RTO + Cancelled + Refunded | Revenue we lost |

### Revenue Breakdown Visual:
```
┌─────────────────────────────────────────────────────────────┐
│                    PROJECTED REVENUE                        │
│                      (All Orders)                           │
├─────────────────┬─────────────────┬─────────────────────────┤
│  ACTUAL REVENUE │  PENDING REVENUE│     LOST REVENUE        │
│   (Delivered)   │ (In Transit +   │ (RTO + Cancelled +      │
│                 │  Not Shipped)   │  Refunded)              │
└─────────────────┴─────────────────┴─────────────────────────┘
```

---

## 4. Key Metrics Dashboard

### Summary Cards:
| Card | Value | Sub-info |
|------|-------|----------|
| Total Orders | Count | Date range filter |
| Projected Revenue | ₹ Amount | Projected AOV below |
| Actual Revenue | ₹ Amount | Actual AOV below |
| Lost Revenue | ₹ Amount | % of projected |
| Delivery Rate | % | Delivered / (Total - Cancelled Pre-ship) |
| RTO Rate | % | RTO / Shipped Orders |

### Payment Method Breakdown:
| Mode | Orders | % | Revenue |
|------|--------|---|---------|
| Full Prepaid | X | X% | ₹X |
| Partial Prepaid | X | X% | ₹X |
| COD | X | X% | ₹X |

### Delivery Status Breakdown:
| Status | Orders | % | Revenue Impact |
|--------|--------|---|----------------|
| ✅ Delivered | X | X% | ₹X (Actual) |
| 🚚 In Transit | X | X% | ₹X (Pending) |
| ↩️ RTO | X | X% | ₹X (Lost) |
| ❌ Cancelled | X | X% | ₹X (Lost) |
| 🕐 Not Shipped | X | X% | ₹X (Pending) |

**Note:** Refunded orders are tracked separately via Shopify `financial_status = refunded` and counted as Lost Revenue.

---

## 5. User Journey Tab (Simplified)

### Table Columns:
| Column | Source | Description |
|--------|--------|-------------|
| Order ID | Shopify `Name` | Primary identifier |
| Order Date | Shopify `Created at` | When order placed |
| Customer Phone | Shopify `Phone` / `Billing Phone` | Normalized |
| Customer Email | Shopify `Email` | |
| City | Shopify `Shipping City` | Delivery city |
| State | Shopify `Shipping Province` | Delivery state |
| Amount | Shopify `Total` | Order value |
| Payment Mode | Derived | COD / Prepaid / Partial |
| Delivery Status | Prozo `Status` mapped | Current status |
| AWB | Prozo `AWB` | Tracking number |

### Filters:
- Date range
- Payment mode
- Delivery status

### Search:
- Single search bar that searches across: Order ID, Phone, Email
	
---

## 6. Database Schema (Future-Proof)

### Design Principles:
1. **Separate raw tables** - One per data source (easy to add new sources)
2. **Unified view table** - Consolidated order data
3. **Lookup tables** - For status mappings, payment methods (extendable)
4. **Audit tables** - Track data imports

### Tables:

```sql
-- ============================================
-- RAW DATA TABLES (one per source)
-- ============================================

-- Shopify orders (raw import)
CREATE TABLE raw_shopify_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE,              -- "Name" field (#GB1234)
    shopify_id TEXT,                   -- "Id" field (internal Shopify ID)

    -- Customer
    email TEXT,
    phone TEXT,                        -- Normalized 10-digit
    billing_phone TEXT,
    billing_name TEXT,
    shipping_name TEXT,

    -- Location
    shipping_city TEXT,
    shipping_state TEXT,
    shipping_pincode TEXT,

    -- Financials
    subtotal REAL,
    total REAL,
    discount_code TEXT,
    discount_amount REAL,
    refunded_amount REAL,

    -- Status
    financial_status TEXT,             -- pending, paid, voided, etc.
    fulfillment_status TEXT,           -- fulfilled, pending

    -- Payment
    payment_method_raw TEXT,           -- Original value
    payment_method TEXT,               -- Normalized: cod, prepaid, partial

    -- Product
    lineitem_name TEXT,
    lineitem_quantity INTEGER,
    lineitem_sku TEXT,

    -- Dates
    order_date TEXT,                   -- Created at
    cancelled_at TEXT,

    -- Meta
    source TEXT,                       -- Channel source
    tags TEXT,

    -- Import tracking
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
    import_batch_id TEXT
);

-- Prozo MIS (raw import)
CREATE TABLE raw_prozo_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    awb TEXT,                          -- Unique per shipment
    order_id TEXT,                     -- Maps to Shopify order_id

    -- Status
    status TEXT,                       -- DELIVERED, RTO_DELIVERED, etc.
    status_category TEXT,              -- delivered, rto, in_transit_fwd, in_transit_rtn, cancelled

    -- Customer (from Prozo)
    drop_name TEXT,
    drop_phone TEXT,
    drop_email TEXT,
    drop_city TEXT,
    drop_state TEXT,
    drop_pincode TEXT,

    -- Logistics
    courier_partner TEXT,
    payment_mode TEXT,                 -- COD or Prepaid

    -- Dates
    pickup_date TEXT,
    delivery_date TEXT,
    rto_delivery_date TEXT,

    -- TAT
    min_tat INTEGER,
    max_tat INTEGER,

    -- NDR
    ndr_status TEXT,
    total_attempts INTEGER,
    latest_remark TEXT,

    -- Costs (for future)
    merchant_price REAL,
    merchant_price_rto REAL,

    -- Import tracking
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
    import_batch_id TEXT,

    UNIQUE(awb, import_batch_id)       -- Allow status updates
);

-- ============================================
-- FUTURE: Additional payment sources
-- ============================================

-- Razorpay (Phase 2)
CREATE TABLE raw_razorpay_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT UNIQUE,
    order_receipt TEXT,                -- Maps to Shopify order_id
    type TEXT,                         -- payment, refund
    amount REAL,
    fee REAL,
    settled INTEGER,
    settlement_utr TEXT,
    method TEXT,
    created_at TEXT,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Snapmint (Future)
CREATE TABLE raw_snapmint_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT UNIQUE,
    order_id TEXT,                     -- Maps to Shopify order_id
    amount REAL,
    status TEXT,
    created_at TEXT,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- GoQuick (Future)
CREATE TABLE raw_goquick_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT UNIQUE,
    order_id TEXT,
    amount REAL,
    status TEXT,
    created_at TEXT,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- UNIFIED VIEW
-- ============================================

CREATE TABLE unified_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE,              -- Shopify Order ID (master key)

    -- Customer
    customer_email TEXT,
    customer_phone TEXT,
    customer_name TEXT,
    customer_city TEXT,
    customer_state TEXT,
    customer_pincode TEXT,

    -- Order
    order_date TEXT,
    total_amount REAL,
    subtotal REAL,
    discount_amount REAL,
    lineitem_name TEXT,

    -- Payment (consolidated)
    payment_mode TEXT,                 -- cod, prepaid, partial
    payment_source TEXT,               -- razorpay, snapmint, goquick, cod
    financial_status TEXT,

    -- Delivery
    prozo_awb TEXT,
    delivery_status TEXT,              -- delivered, in_transit, rto, cancelled, not_shipped
    delivery_status_raw TEXT,          -- Original Prozo status
    courier_partner TEXT,
    pickup_date TEXT,
    delivery_date TEXT,
    rto_date TEXT,

    -- Dispatch Time
    dispatch_hours REAL,               -- Hours between order and pickup
    dispatch_category TEXT,            -- fast (<24h), normal (24-48h), delayed (>48h), not_dispatched

    -- Computed
    is_delivered INTEGER DEFAULT 0,
    is_rto INTEGER DEFAULT 0,
    is_cancelled INTEGER DEFAULT 0,
    is_refunded INTEGER DEFAULT 0,
    is_in_transit INTEGER DEFAULT 0,
    revenue_category TEXT,             -- actual, pending, lost

    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- LOOKUP TABLES (for extensibility)
-- ============================================

CREATE TABLE payment_method_mapping (
    id INTEGER PRIMARY KEY,
    source_value TEXT,                 -- Original value from source
    source_system TEXT,                -- shopify, razorpay, etc.
    normalized_value TEXT,             -- cod, prepaid, partial
    display_name TEXT                  -- "Cash on Delivery", "Full Prepaid", etc.
);

CREATE TABLE delivery_status_mapping (
    id INTEGER PRIMARY KEY,
    source_value TEXT,                 -- DELIVERED, RTO_DELIVERED, etc.
    source_system TEXT,                -- prozo, shiprocket, etc.
    normalized_value TEXT,             -- delivered, in_transit, rto, cancelled, not_shipped
    is_revenue INTEGER,                -- 1 = counts as actual revenue
    is_pending INTEGER,                -- 1 = counts as pending revenue
    is_lost INTEGER,                   -- 1 = counts as lost revenue
    display_name TEXT
);

-- ============================================
-- LINE ITEMS (for detailed breakdown)
-- ============================================

CREATE TABLE order_line_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT,                     -- Shopify Order ID
    lineitem_name TEXT,
    lineitem_sku TEXT,
    lineitem_quantity INTEGER,
    lineitem_price REAL,
    lineitem_discount REAL,
    FOREIGN KEY (order_id) REFERENCES unified_orders(order_id)
);

-- ============================================
-- AUDIT & IMPORT TRACKING
-- ============================================

CREATE TABLE import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT UNIQUE,
    source TEXT,                       -- shopify, prozo, razorpay
    file_name TEXT,
    records_total INTEGER,
    records_new INTEGER,
    records_updated INTEGER,
    records_failed INTEGER,
    date_range_start TEXT,
    date_range_end TEXT,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. Dispatch Time Tracking (NEW)

### Definition:
**Dispatch Time** = Prozo `Pickup Date` - Shopify `Created at`

### Categories:
| Category | Condition | Status |
|----------|-----------|--------|
| **Fast Dispatch** | ≤ 24 hours | ✅ Good |
| **Normal Dispatch** | 24-48 hours | ⚠️ Acceptable |
| **Delayed Dispatch** | > 48 hours | ❌ Too slow |
| **Not Dispatched** | No Pickup Date yet | 🕐 Pending |

### Dashboard Metrics:
- % orders dispatched within 24h
- % orders dispatched within 24-48h
- % orders delayed (>48h)
- % orders not yet dispatched
- Average dispatch time (hours)

### Use Cases:
- Identify warehouse bottlenecks
- Track dispatch SLA compliance
- Flag orders pending dispatch too long

---

## 8. Matching Logic (Phase 1)

### Order ID Matching:
```
Shopify.Name = Prozo.channelOrderName
```

**Confirmed:**
- Shopify: `Name` field (e.g., `#GB1234`)
- Prozo: `channelOrderName` field (same as Shipping Label)
- May need to handle `#` prefix difference

### Handling Multiple Line Items:
- Shopify CSV has one row per line item
- **For unified_orders table**: Aggregate by `order_id` (Name field)
  - Sum `lineitem_quantity` across all rows
  - Take first occurrence for customer details
  - Concatenate `lineitem_name` or take first
- **For line_items table**: Keep individual rows for detailed breakdown

### Line Item Breakdown View (Separate Table):
| Order ID | Line Item Name | SKU | Quantity | Price |
|----------|----------------|-----|----------|-------|
| #GB1234  | Guitar Kit     | SKU1| 1        | ₹2,499|
| #GB1234  | Picks Set      | SKU2| 2        | ₹250  |
| #GB1235  | Capo           | SKU3| 1        | ₹499  |

---

## 8. UI Layout

### Tab: Logistics Dashboard

```
┌────────────────────────────────────────────────────────────────────┐
│  [Date Range Picker: Start ─ End]    [Upload Shopify] [Upload Prozo] │
├────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐│
│  │ Total Orders │ │ Projected    │ │ Actual       │ │ Lost         ││
│  │    1,234     │ │ Revenue      │ │ Revenue      │ │ Revenue      ││
│  │              │ │ ₹12,34,567   │ │ ₹10,23,456   │ │ ₹2,11,111    ││
│  │              │ │ AOV: ₹1,000  │ │ AOV: ₹1,050  │ │ 17.1%        ││
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘│
│                                                                      │
│  ┌─────────────────────────────┐ ┌─────────────────────────────────┐│
│  │ PAYMENT METHOD BREAKDOWN    │ │ DELIVERY STATUS BREAKDOWN       ││
│  │ ───────────────────────────│ │ ────────────────────────────────││
│  │ Full Prepaid   45%  ████▌  │ │ ✅ Delivered      72%  ███████▏  ││
│  │ Partial Prepaid 15%  █▌    │ │ 🚚 In Transit     12%  █▏        ││
│  │ COD            40%  ████   │ │ ↩️ RTO            10%  █          ││
│  │                            │ │ ❌ Cancelled       4%  ▍         ││
│  │                            │ │ 🕐 Not Shipped     2%  ▏         ││
│  └─────────────────────────────┘ └─────────────────────────────────┘│
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │ DISPATCH TIME BREAKDOWN                              Avg: 18 hrs ││
│  │ ─────────────────────────────────────────────────────────────────││
│  │ ✅ Within 24h      65%  ██████▌                                  ││
│  │ ⚠️  24-48 hours     25%  ██▌                                      ││
│  │ ❌ Over 48 hours    5%   ▌                                        ││
│  │ 🕐 Not Dispatched   5%   ▌                                        ││
│  └──────────────────────────────────────────────────────────────────┘│
│                                                                      │
└────────────────────────────────────────────────────────────────────┘
```

### Tab: User Journey (Order List)

```
┌────────────────────────────────────────────────────────────────────┐
│  🔍 [Search: Order ID, Phone, or Email________________]            │
│  Filters: [Date Range] [Payment Mode ▼] [Delivery Status ▼]       │
├────────────────────────────────────────────────────────────────────┤
│ Order ID │ Date   │ Phone      │ Email          │ City    │ Amount │ Payment │ Status       │ Dispatch │
│──────────│────────│────────────│────────────────│─────────│────────│─────────│──────────────│──────────│
│ #GB1234  │ 18 Feb │ 9876543210 │ john@mail.com  │ Mumbai  │ ₹2,999 │ Prepaid │ ✅ Delivered │ ✅ 18h   │
│ #GB1235  │ 18 Feb │ 9876543211 │ jane@mail.com  │ Delhi   │ ₹3,499 │ COD     │ 🚚 In Transit│ ⚠️ 36h   │
│ #GB1236  │ 17 Feb │ 9876543212 │ bob@mail.com   │ Chennai │ ₹1,999 │ Partial │ ↩️ RTO       │ ❌ 52h   │
│ #GB1237  │ 18 Feb │ 9876543213 │ sam@mail.com   │ Pune    │ ₹2,499 │ COD     │ 🕐 Not Ship  │ -        │
│ ...      │        │            │                │         │        │         │              │          │
└────────────────────────────────────────────────────────────────────┘
```

### Tab: Line Items Breakdown

```
┌────────────────────────────────────────────────────────────────────┐
│  🔍 [Search: Order ID, SKU________________]                        │
├────────────────────────────────────────────────────────────────────┤
│ Order ID │ Line Item Name              │ SKU      │ Qty │ Price   │
│──────────│─────────────────────────────│──────────│─────│─────────│
│ #GB1234  │ Guitar Kit - Beginner       │ GK-BEG-1 │ 1   │ ₹2,499  │
│ #GB1234  │ Guitar Picks (Pack of 10)   │ GP-10    │ 2   │ ₹250    │
│ #GB1235  │ Electric Guitar - Pro       │ EG-PRO-1 │ 1   │ ₹3,499  │
│ #GB1236  │ Capo - Premium              │ CAP-PRE  │ 1   │ ₹499    │
│ #GB1236  │ Strings Set - Steel         │ STR-STL  │ 3   │ ₹500    │
│ ...      │                             │          │     │         │
└────────────────────────────────────────────────────────────────────┘
```

---

## 9. Confirmed Requirements

| Question | Answer |
|----------|--------|
| Prozo Order ID Field | `channelOrderName` |
| Order ID Format | May have `#` prefix difference - normalize |
| Partial Payment Amount | Varies (₹49, ₹149, etc.) |
| Refund Handling | **Lost Revenue** (not removed from metrics) |
| Multiple Line Items | Sum quantities, first customer details |
| City/State Filter | Not needed |
| Search | Single bar: Order ID, Phone, Email |

---

## 10. Implementation Plan

### Step 1: Database Setup
- Create all tables (raw + unified + line_items + lookup)
- Populate status/payment mapping tables

### Step 2: CSV Parsers
- Shopify CSV parser with:
  - Phone normalization
  - Line item aggregation (sum qty, first customer details)
  - Line items stored separately
  - Order ID normalization (handle `#` prefix)
- Prozo MIS CSV parser with:
  - Status mapping to categories
  - `channelOrderName` as match key

### Step 3: Matching Engine
- Match Shopify.Name → Prozo.channelOrderName
- Update unified_orders table
- Calculate:
  - Delivery status category
  - Dispatch time (hours)
  - Dispatch category (fast/normal/delayed/not dispatched)

### Step 4: Metrics Calculation
- Revenue: Projected, Actual, Lost, Pending, At-Risk
- AOV: Projected AOV, Actual AOV
- Payment breakdown: Prepaid %, Partial %, COD %
- Delivery breakdown: Delivered %, In-Transit %, RTO %, etc.
- Dispatch breakdown: <24h %, 24-48h %, >48h %, Not dispatched %

### Step 5: UI - 3 Tabs
1. **Logistics Dashboard**
   - Date range picker
   - Upload buttons (Shopify, Prozo)
   - Metric cards (Orders, Revenue, Lost Revenue)
   - Payment method breakdown (bar chart)
   - Delivery status breakdown (bar chart)
   - Dispatch time breakdown (bar chart)

2. **User Journey**
   - Single search bar (Order ID, Phone, Email)
   - Filters: Date range, Payment mode, Delivery status
   - Table: Order ID, Date, Phone, Email, City, Amount, Payment, Status, Dispatch Time

3. **Line Items**
   - Search bar (Order ID, SKU)
   - Table: Order ID, Line Item Name, SKU, Qty, Price

---

## 11. Future Extensibility

### Adding new payment source (e.g., Snapmint):
1. Create `raw_snapmint_payments` table
2. Add entries to `payment_method_mapping`
3. Update matching logic to check Snapmint
4. Unified orders auto-populated

### Adding new delivery partner (e.g., Shiprocket):
1. Create `raw_shiprocket_orders` table
2. Add entries to `delivery_status_mapping`
3. Update matching logic
4. Status normalization handles rest

### Adding Razorpay reconciliation (Phase 2):
1. Already have `raw_razorpay_payments` table
2. Add matching by `order_receipt`
3. Add payment verification flags
4. New reconciliation tab

---

*Ready to code once you confirm the Order ID matching question!*
