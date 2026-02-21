 # User Journey Dashboard - Product Requirements Document (PRD)

## 1. Executive Summary

Build a comprehensive User Journey tracking system that unifies data from **Shopify** (orders), **Prozo** (3PL delivery), and **Razorpay** (payments) to provide end-to-end visibility into customer orders, from placement to delivery/RTO, with payment reconciliation.

---

## 2. Data Sources Overview

### 2.1 Shopify (Source of Truth for Orders)
**File**: Shopify Orders Export CSV
**Key Fields**:
| Field | Purpose |
|-------|---------|
| `Name` | **Order ID** (e.g., #GB1234) - Primary key for matching |
| `Email` | Customer email |
| `Phone`, `Billing Phone`, `Shipping Phone` | Customer phone (needs normalization) |
| `Billing Name`, `Shipping Name` | Customer name |
| `Financial Status` | Payment status: `pending`, `paid`, `voided`, `partially_paid`, `refunded`, `partially_refunded` |
| `Fulfillment Status` | Delivery status: `fulfilled`, `pending` |
| `Payment Method` | COD, Razorpay, Snapmint, Manual |
| `Total`, `Subtotal`, `Discount Amount` | Order financials |
| `Created at` | Order date |
| `Lineitem name`, `Lineitem quantity` | Product SKU details |
| `Billing/Shipping City, Zip, Province` | Location data |

**Financial Status Definitions**:
- `pending`: COD order (payment not yet received)
- `paid`: Prepaid via Razorpay/Snapmint/GoQuick
- `voided`: Cancelled by customer before shipping
- `partially_paid`: Partial payment captured (e.g., ₹149 booking)
- `refunded`: Full refund processed
- `partially_refunded`: Partial refund against partial payment

---

### 2.2 Prozo (3PL Delivery Logistics)
**Files**: MIS Report CSV, Passbook CSV
**Key Fields**:
| Field | Purpose |
|-------|---------|
| `Reference Number` / `channelOrderName` | **Shopify Order ID** - Match key |
| `AWB` | Airway Bill Number (shipment tracking) |
| `Status` | Real-time delivery status (changes daily) |
| `Payment Mode` | COD or Prepaid |
| `Drop Name`, `Drop Phone`, `Drop Email` | Customer details |
| `Drop City`, `Drop Pincode`, `Drop State` | Delivery location |
| `Pickup Date` | When shipped from warehouse |
| `Delivery Date` | Actual delivery date |
| `RTO Delivery Date` | When RTO received back |
| `Min Tat`, `Max Tat` | Promised delivery TAT |
| `Merchant Price` | Delivery charges (includes COD handling + GST) |
| `Merchant Price RTO` | RTO charges (no COD component) |
| `NDR Status` | Non-Delivery Report status |
| `Total Attempts` | Delivery attempts count |
| `Courier Partner` | Bluedart, Ecom Express, etc. |

**Status Definitions**:
| Status | Type | Meaning |
|--------|------|---------|
| `DELIVERED` | Final | Successfully delivered |
| `RTO_DELIVERED` | Final | RTO received back at warehouse |
| `CANCELLED_ORDER` | Final | Cancelled before shipping |
| `SHIPMENT_DELAYED` | In-Transit | Delayed but not RTO |
| `FAILED_DELIVERY` | In-Transit | Delivery attempt failed (address/phone/timing issue) |
| `RTO_INTRANSIT` | In-Transit | Customer rejected, returning to warehouse |
| `RTO_OUT_FOR_DELIVERY` | In-Transit | RTO shipment out for delivery to warehouse |
| `RTO_REQUESTED` | In-Transit | RTO marked, not yet picked up |

**Passbook Fields** (for cost reconciliation):
| Field | Purpose |
|-------|---------|
| `AWB Number` | Match to shipment |
| `Credit Amount` | Money returned (cancelled/RTO COD refund) |
| `Debit Amount` | Charges deducted |
| `Description` | Transaction type: "Order placed successfully", "Credit for Cancelled Order", "Credit for COD charge" |

---

### 2.3 Razorpay (Payment Gateway)
**Files**: Combined Report, Settlement Report, Refund Report
**Key Fields**:
| Field | Purpose |
|-------|---------|
| `order_receipt` | **Shopify Order ID** - Match key |
| `entity_id` | Razorpay payment ID |
| `type` | `payment`, `refund`, `settlement` |
| `amount`, `credit`, `debit` | Transaction amounts |
| `fee`, `tax` | Razorpay charges (~2% + 18% GST) |
| `settled` | 0/1 - Whether settled to bank |
| `settlement_id`, `settlement_utr` | Bank settlement reference |
| `method` | UPI, Card, Wallet, Netbanking |
| `created_at`, `settled_at` | Timestamps |

**Notes**:
- `order_receipt` is empty for direct link payments (non-Shopify)
- `description` contains "QRv2 Payment" for direct link payments
- Settlement UTR can be matched with bank statements

---

## 3. User Journey Stages

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              USER JOURNEY FLOW                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

[ORDER PLACED] ──► [PAYMENT STATUS] ──► [SHIPPED] ──► [IN TRANSIT] ──► [DELIVERED]
     │                   │                  │              │               │
     │              ┌────┴────┐             │         ┌────┴────┐          │
     │              │         │             │         │         │          │
     ▼              ▼         ▼             ▼         ▼         ▼          ▼
  Shopify       Prepaid    COD          Prozo    Delayed    NDR      Success
  Created       (Razorpay) (Pending)    Pickup              (Failed)
                                                              │
                                                         ┌────┴────┐
                                                         │         │
                                                         ▼         ▼
                                                      Reattempt   RTO
                                                                   │
                                                              ┌────┴────┐
                                                              │         │
                                                              ▼         ▼
                                                         RTO Transit  RTO Delivered
```

### Stage Definitions

| Stage | Source | Condition |
|-------|--------|-----------|
| `order_placed` | Shopify | Order created |
| `payment_pending` | Shopify | Financial Status = 'pending' (COD) |
| `payment_captured` | Shopify + Razorpay | Financial Status = 'paid' AND Razorpay payment exists |
| `cancelled_pre_ship` | Shopify | Financial Status = 'voided' |
| `shipped` | Prozo | Pickup Date exists |
| `in_transit` | Prozo | Status in ['SHIPMENT_DELAYED', 'OUT_FOR_DELIVERY'] |
| `delivery_failed` | Prozo | Status = 'FAILED_DELIVERY' |
| `delivered` | Prozo | Status = 'DELIVERED' |
| `rto_initiated` | Prozo | Status in ['RTO_REQUESTED', 'RTO_INTRANSIT', 'RTO_OUT_FOR_DELIVERY'] |
| `rto_completed` | Prozo | Status = 'RTO_DELIVERED' |
| `refunded` | Shopify + Razorpay | Financial Status = 'refunded' AND Razorpay refund exists |

---

## 4. Matching Logic

### 4.1 Order ID Matching (Primary)
```
Shopify.Name = Prozo.Reference_Number = Razorpay.order_receipt
```

### 4.2 Customer Identity Matching (Secondary)
**Waterfall approach for fuzzy matching**:
1. **Exact Email Match** (100% confidence)
2. **Exact Phone Match** (95% confidence) - After normalization
3. **Fuzzy Email Match** (85%+ similarity threshold)
4. **Fuzzy Name + City Match** (70% confidence)
5. **Fuzzy Name + Pincode Match** (65% confidence)

### 4.3 Phone Normalization Rules
```python
# Remove: +91, 91, 0 prefix
# Keep: 10 digits only
# Examples:
#   +919876543210 → 9876543210
#   09876543210   → 9876543210
#   919876543210  → 9876543210
```

---

## 5. Reconciliation & Flags

### 5.1 Payment Reconciliation (Razorpay ↔ Shopify)
| Check | Flag If |
|-------|---------|
| Order exists in Razorpay | Shopify `paid` order missing in Razorpay |
| Amount matches | Razorpay amount ≠ Shopify Total |
| Settlement status | Order settled = 0 for >7 days |
| Refund sync | Shopify refunded but no Razorpay refund |

### 5.2 Delivery Reconciliation (Prozo ↔ Shopify)
| Check | Flag If |
|-------|---------|
| Order shipped | Shopify order not in Prozo after 2 days |
| Delivery status sync | Prozo DELIVERED but Shopify Fulfillment ≠ fulfilled |
| RTO tracking | RTO_DELIVERED but no inventory adjustment |
| TAT breach | Delivery Date > Max TAT |

### 5.3 Cost Reconciliation (Prozo Passbook)
| Check | Flag If |
|-------|---------|
| Cancelled order credit | Cancelled order but no "Credit for Cancelled Order" |
| COD RTO credit | RTO on COD order but no "Credit for COD charge" |
| Weight discrepancy | WD Status = disputed/pending |

---

## 6. Database Schema (Proposed)

### 6.1 Core Tables

```sql
-- Raw data imports
CREATE TABLE raw_shopify_orders (
    id INTEGER PRIMARY KEY,
    order_id TEXT UNIQUE,          -- "Name" field
    email TEXT,
    phone TEXT,                     -- Normalized
    billing_phone TEXT,             -- Normalized
    billing_name TEXT,
    shipping_name TEXT,
    financial_status TEXT,
    fulfillment_status TEXT,
    payment_method TEXT,
    total REAL,
    subtotal REAL,
    discount_amount REAL,
    lineitem_name TEXT,
    lineitem_quantity INTEGER,
    billing_city TEXT,
    billing_zip TEXT,
    billing_province TEXT,
    shipping_city TEXT,
    shipping_zip TEXT,
    shipping_province TEXT,
    created_at TEXT,
    cancelled_at TEXT,
    refunded_amount REAL,
    source TEXT,
    tags TEXT,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE raw_prozo_orders (
    id INTEGER PRIMARY KEY,
    awb TEXT UNIQUE,
    order_id TEXT,                  -- Reference Number / channelOrderName
    status TEXT,
    payment_mode TEXT,
    courier_partner TEXT,
    drop_name TEXT,
    drop_phone TEXT,                -- Normalized
    drop_email TEXT,
    drop_city TEXT,
    drop_pincode TEXT,
    drop_state TEXT,
    pickup_date TEXT,
    delivery_date TEXT,
    rto_delivery_date TEXT,
    min_tat INTEGER,
    max_tat INTEGER,
    merchant_price REAL,
    merchant_price_rto REAL,
    ndr_status TEXT,
    total_attempts INTEGER,
    latest_timestamp TEXT,
    latest_remark TEXT,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE raw_razorpay_transactions (
    id INTEGER PRIMARY KEY,
    entity_id TEXT UNIQUE,
    type TEXT,                      -- payment, refund, settlement
    order_id TEXT,                  -- Razorpay order_id
    order_receipt TEXT,             -- Shopify order_id
    amount REAL,
    fee REAL,
    tax REAL,
    credit REAL,
    debit REAL,
    settled INTEGER,                -- 0 or 1
    settlement_id TEXT,
    settlement_utr TEXT,
    method TEXT,
    created_at TEXT,
    settled_at TEXT,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Unified order view
CREATE TABLE unified_orders (
    id INTEGER PRIMARY KEY,
    order_id TEXT UNIQUE,           -- Shopify Order ID (primary key)

    -- Customer Identity
    customer_email TEXT,
    customer_phone TEXT,
    customer_name TEXT,
    customer_city TEXT,
    customer_state TEXT,
    customer_pincode TEXT,

    -- Order Details
    order_date TEXT,
    total_amount REAL,
    payment_method TEXT,            -- COD, Razorpay, Snapmint
    lineitem_name TEXT,
    lineitem_quantity INTEGER,

    -- Shopify Status
    shopify_financial_status TEXT,
    shopify_fulfillment_status TEXT,

    -- Prozo Status
    prozo_awb TEXT,
    prozo_status TEXT,
    prozo_courier TEXT,
    prozo_pickup_date TEXT,
    prozo_delivery_date TEXT,
    prozo_rto_date TEXT,
    prozo_attempts INTEGER,
    prozo_ndr_status TEXT,

    -- Razorpay Status
    razorpay_payment_id TEXT,
    razorpay_amount REAL,
    razorpay_fee REAL,
    razorpay_settled INTEGER,
    razorpay_settlement_utr TEXT,

    -- Computed Journey
    journey_stage TEXT,             -- See stage definitions
    journey_updated_at TEXT,

    -- Reconciliation Flags
    has_payment_mismatch INTEGER DEFAULT 0,
    has_delivery_mismatch INTEGER DEFAULT 0,
    has_amount_mismatch INTEGER DEFAULT 0,
    needs_review INTEGER DEFAULT 0,
    flag_details TEXT,              -- JSON array of flag messages

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Flag/Alert tracking
CREATE TABLE reconciliation_flags (
    id INTEGER PRIMARY KEY,
    order_id TEXT,
    flag_type TEXT,                 -- payment, delivery, amount, refund
    flag_message TEXT,
    severity TEXT,                  -- high, medium, low
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT,
    resolved_by TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Audit log for data imports
CREATE TABLE import_audit_log (
    id INTEGER PRIMARY KEY,
    source TEXT,                    -- shopify, prozo, razorpay
    file_name TEXT,
    records_imported INTEGER,
    records_updated INTEGER,
    records_failed INTEGER,
    import_date TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. UI Modules

### 7.1 Tab 1: Data Upload
- Upload Shopify Orders CSV
- Upload Prozo MIS Report CSV
- Upload Prozo Passbook CSV
- Upload Razorpay Combined Report CSV
- Show import stats and last upload date

### 7.2 Tab 2: Order Journey View
- Unified order list with all statuses
- Filter by: date range, payment method, journey stage, flags
- Order detail modal showing complete journey timeline
- Visual journey stage indicator

### 7.3 Tab 3: Reconciliation Dashboard
**Payment Reconciliation**:
- Orders with payment mismatch
- Pending settlements (>7 days)
- Refund discrepancies

**Delivery Reconciliation**:
- Orders not shipped (>2 days)
- TAT breaches
- Stuck in transit (>10 days)
- RTO analysis

**Financial Summary**:
- Total orders vs delivered vs RTO
- Payment collected vs pending
- Razorpay fees summary
- Prozo charges summary

### 7.4 Tab 4: Flags & Alerts
- All active flags grouped by type
- Flag resolution workflow
- Historical flag trends

### 7.5 Tab 5: Customer 360
- Unified customer profile
- All orders by customer
- Payment history
- Delivery success rate
- LTV calculation

---

## 8. Development Phases

### Phase 1: Data Foundation
- [ ] Create database schema
- [ ] Build CSV parsers for all 3 sources
- [ ] Phone/email normalization utilities
- [ ] Data upload UI with validation

### Phase 2: Order Matching & Journey
- [ ] Order ID matching across sources
- [ ] Journey stage computation
- [ ] Unified orders table population
- [ ] Basic order list view

### Phase 3: Reconciliation Engine
- [ ] Payment reconciliation logic
- [ ] Delivery reconciliation logic
- [ ] Flag generation system
- [ ] Reconciliation dashboard

### Phase 4: Advanced Features
- [ ] Customer identity matching (fuzzy)
- [ ] Customer 360 view
- [ ] Trend analytics
- [ ] Export/reporting

---

## 9. Key Metrics to Track

| Metric | Formula |
|--------|---------|
| Order Delivery Rate | Delivered / (Total - Cancelled) |
| RTO Rate | RTO_DELIVERED / Shipped |
| COD Collection Rate | COD Collected / COD Orders Delivered |
| Payment Capture Rate | Prepaid Orders / Total Orders |
| Avg Delivery TAT | Avg(Delivery Date - Order Date) |
| Razorpay Settlement Pending | Sum(Unsettled Amounts) |
| Flag Resolution Rate | Resolved Flags / Total Flags |

---

## 10. Open Questions

1. How to handle direct link payments (no Shopify order_id)?
2. What is the source of truth for refund: Shopify or Razorpay?
3. How often should data be refreshed (manual upload vs API)?
4. Should we integrate with Snapmint/GoQuick in future?
5. How to handle weight discrepancy disputes with Prozo?

---

## 11. Files Reference

| Source | File Location | Update Frequency |
|--------|---------------|------------------|
| Shopify | Downloads/Shopify Reports Understanding.xlsx | Weekly |
| Prozo MIS | Downloads/Prozo Understanding.xlsx | Weekly (real-time status) |
| Prozo Passbook | Downloads/Prozo Understanding.xlsx (Passbook sheet) | Monthly |
| Razorpay | Downloads/Razorpay Report Understanding.xlsx | Every 15 days |

---

## 12. INCOMPLETE ITEMS & TODO

### 12.1 Data Gaps (Need Clarity)
| Item | Issue | Action Needed |
|------|-------|---------------|
| Direct Link Payments | Razorpay has payments without `order_receipt` (non-Shopify). How to track these? | Need product name mapping or separate tracking |
| Snapmint Integration | Snapmint payments not in Razorpay. How to reconcile? | Get Snapmint report format |
| GoQuick Integration | Future payment method. Report format unknown | Get sample report when available |
| Bank Direct Payments | Customers paying directly to bank account | Need bank statement parser |
| QR Code Payments | Direct QR payments show as "QRv2 Payment" in Razorpay | Need mapping to product/customer |
| Digital SKUs | Fulfillment status always "pending" for digital products | Need list of digital SKU codes |

### 12.2 Field Mapping Gaps
| Shopify Field | Prozo Field | Issue |
|---------------|-------------|-------|
| `Name` (Order ID) | `Reference Number` OR `channelOrderName` OR `Order ID` | Which Prozo field is the correct match? Need to verify |
| `Phone` | `Drop Phone` | Format differences, need normalization rules |
| `Fulfillment Status` | `Status` | Prozo RTO shows as "fulfilled" in Shopify? Need to verify |
| `Cancelled at` | `CANCELLED_ORDER` status | Does Shopify cancel timestamp match Prozo status change? |

### 12.3 Logic Gaps
| Area | Gap | Impact |
|------|-----|--------|
| Multiple Line Items | One Shopify order can have multiple line items (rows in CSV). How to aggregate? | Over-counting orders |
| Partial Shipments | Can one order have multiple AWBs? | Incomplete tracking |
| Order Amendments | Customer changes order after placement | Status confusion |
| Duplicate Orders | Same customer, same product, same day | False identity matches |

---

## 13. DEFINITION CONFUSIONS (Need Your Input)

### 13.1 Status Mapping Confusion

**Question 1: RTO vs Cancelled**
```
Scenario: Customer cancels AFTER order is shipped
- Shopify shows: Financial Status = ?
- Prozo shows: Status = RTO_REQUESTED
- What should Journey Stage be?
```

**Question 2: Prepaid RTO**
```
Scenario: Prepaid order goes RTO
- Razorpay: Payment captured (settled = 1)
- Prozo: RTO_DELIVERED
- Shopify: Fulfillment = fulfilled? or pending?
- When/how is refund triggered?
```

**Question 3: COD Delivered but Not Collected**
```
Scenario: COD order marked DELIVERED but cash not collected
- How do we know? (Prozo Passbook?)
- What status should this be?
```

**Question 4: Failed Delivery vs RTO**
```
- FAILED_DELIVERY: Delivery agent couldn't reach customer
- RTO_REQUESTED: Customer rejected
- How many FAILED_DELIVERY attempts before auto-RTO?
- Is this 3 attempts as per NDR process?
```

### 13.2 Amount Matching Confusion

**Question 5: Which "Total" to match?**
```
Shopify has:
- Subtotal (after discount, before tax)
- Total (after discount, after tax)
- What about shipping charges?

Razorpay has:
- Amount (what customer paid)
- Credit (after Razorpay fee deduction)

Which to compare for reconciliation?
```

**Question 6: Partial Payment Matching**
```
Shopify: Total = ₹3999, Financial Status = partially_paid
Razorpay: Amount = ₹149

- Is the remaining ₹3850 collected as COD?
- Or does customer pay balance online later?
- How to reconcile?
```

### 13.3 Date/Time Confusion

**Question 7: Which date is "Order Date"?**
```
- Shopify `Created at`: When order placed
- Prozo `Created at`: When Prozo received order
- Prozo `Pickup Date`: When shipped

For TAT calculation, which is the start date?
```

**Question 8: RTO Timeline**
```
- RTO Mark Date: First time RTO marked? Or final?
- RTO Delivery Date: When received at Prozo warehouse? Or our warehouse?
```

### 13.4 Identity Matching Confusion

**Question 9: Multiple Identities**
```
Same customer places 2 orders:
- Order 1: email = john@gmail.com, phone = 9876543210
- Order 2: email = johnny@gmail.com, phone = 9876543210

Should these be linked as same customer?
Matching on phone = yes, but emails different.
```

**Question 10: Gifting Scenario**
```
Billing Name: John (payer)
Shipping Name: Jane (recipient)
Which is the "customer"?
```

---

## 14. COMPLETE RED FLAGS LIST

### 14.1 Payment Flags (Razorpay ↔ Shopify)

| Flag ID | Flag Name | Condition | Severity | Action |
|---------|-----------|-----------|----------|--------|
| PAY-001 | Missing Payment | Shopify `paid` order not found in Razorpay | HIGH | Verify payment source |
| PAY-002 | Amount Mismatch | Razorpay amount ≠ Shopify Total (±₹10 tolerance) | HIGH | Investigate discrepancy |
| PAY-003 | Unsettled >7 Days | Razorpay `settled=0` for >7 days | MEDIUM | Check with Razorpay |
| PAY-004 | Refund Mismatch | Shopify `refunded` but no Razorpay refund | HIGH | Process refund |
| PAY-005 | Partial Refund Gap | Shopify `partially_refunded` amount ≠ Razorpay refund | MEDIUM | Verify amounts |
| PAY-006 | Double Payment | Multiple Razorpay payments for same order_receipt | HIGH | Investigate duplicate |
| PAY-007 | Fee Anomaly | Razorpay fee > 3% of amount | LOW | Verify fee structure |
| PAY-008 | Orphan Payment | Razorpay payment with no Shopify order | MEDIUM | Identify source |
| PAY-009 | Settlement UTR Missing | Settled = 1 but no UTR | MEDIUM | Get UTR from Razorpay |
| PAY-010 | Method Mismatch | Shopify says COD, Razorpay has payment | HIGH | Verify payment method |

### 14.2 Delivery Flags (Prozo ↔ Shopify)

| Flag ID | Flag Name | Condition | Severity | Action |
|---------|-----------|-----------|----------|--------|
| DEL-001 | Not Shipped >2 Days | Shopify order not in Prozo after 2 days | HIGH | Check warehouse |
| DEL-002 | TAT Breach | Delivery Date > Order Date + Max TAT | MEDIUM | Escalate to courier |
| DEL-003 | Stuck in Transit | In-transit status for >10 days | HIGH | Track shipment |
| DEL-004 | Multiple NDR | NDR attempts ≥ 2 | MEDIUM | Call customer |
| DEL-005 | High Delivery Attempts | Total Attempts > 3 | MEDIUM | Review delivery area |
| DEL-006 | Status Sync Error | Prozo DELIVERED but Shopify Fulfillment ≠ fulfilled | MEDIUM | Update Shopify |
| DEL-007 | RTO Not Received | RTO_DELIVERED >7 days ago, no inventory update | HIGH | Check warehouse |
| DEL-008 | Courier Performance | Same courier, RTO rate >30% for region | LOW | Review courier allocation |
| DEL-009 | Address Issue | Multiple failed deliveries, same pincode | MEDIUM | Verify serviceability |
| DEL-010 | Pickup Delayed | No Pickup Date after 2 days of order | HIGH | Check warehouse ops |

### 14.3 RTO Flags

| Flag ID | Flag Name | Condition | Severity | Action |
|---------|-----------|-----------|----------|--------|
| RTO-001 | High RTO Rate | Customer has >2 RTO orders | HIGH | Blacklist consideration |
| RTO-002 | Region RTO Spike | Pincode RTO rate >40% | MEDIUM | Review serviceability |
| RTO-003 | COD RTO Refund | RTO on COD, no "Credit for COD charge" in Passbook | HIGH | Claim from Prozo |
| RTO-004 | Prepaid RTO | Prepaid order RTO, refund not processed | HIGH | Process refund |
| RTO-005 | RTO Reason Missing | RTO with no Latest Remark | LOW | Get reason |
| RTO-006 | Quick RTO | RTO within 1 day of shipping | HIGH | Investigate (fake order?) |
| RTO-007 | RTO After OFD | RTO after "Out for Delivery" scan | MEDIUM | Customer rejection analysis |

### 14.4 Cost/Reconciliation Flags (Prozo Passbook)

| Flag ID | Flag Name | Condition | Severity | Action |
|---------|-----------|-----------|----------|--------|
| COST-001 | Weight Discrepancy | WD Status = pending/disputed | HIGH | Submit weight proof |
| COST-002 | Cancelled No Credit | Order cancelled, no "Credit for Cancelled Order" | HIGH | Claim from Prozo |
| COST-003 | COD Charge on Prepaid | COD handling fee charged on prepaid order | HIGH | Dispute with Prozo |
| COST-004 | Duplicate Charge | Same AWB charged twice | HIGH | Claim refund |
| COST-005 | Missing Passbook Entry | AWB exists in MIS, not in Passbook | MEDIUM | Verify billing |
| COST-006 | Revised Price Spike | Revised Merchant Price > Original + 50% | HIGH | Dispute weight |

### 14.5 Data Quality Flags

| Flag ID | Flag Name | Condition | Severity | Action |
|---------|-----------|-----------|----------|--------|
| DATA-001 | Duplicate Order ID | Same order_id appears multiple times | HIGH | Deduplicate |
| DATA-002 | Missing Email+Phone | Order has neither email nor phone | MEDIUM | Cannot contact customer |
| DATA-003 | Invalid Phone | Phone not 10 digits after normalization | LOW | Data cleanup |
| DATA-004 | Future Date | Order date > today | HIGH | Data error |
| DATA-005 | Negative Amount | Total or Subtotal < 0 | HIGH | Data error |
| DATA-006 | Unknown Status | Status value not in defined list | MEDIUM | Add to definitions |
| DATA-007 | Orphan Prozo Order | Prozo order not in Shopify | MEDIUM | Verify source |

### 14.6 Business Flags

| Flag ID | Flag Name | Condition | Severity | Action |
|---------|-----------|-----------|----------|--------|
| BIZ-001 | Pending >15 Days | Fulfillment pending for >15 days | HIGH | Investigate |
| BIZ-002 | Refund Request Spike | >5 refund requests in a day | MEDIUM | Quality check |
| BIZ-003 | Same Customer Multi-Order | >3 orders same customer same day | MEDIUM | Verify (fraud?) |
| BIZ-004 | High Discount | Discount > 50% of subtotal | LOW | Verify coupon |
| BIZ-005 | Zero Value Order | Total = 0 | HIGH | Verify |

---

## 15. QUESTIONS FOR YOU

Please provide clarity on the following:

### Identity & Matching
1. **Order ID Format**: Does Shopify `Name` (e.g., "#GB1234") match Prozo `Reference Number` exactly? Or need to strip "#" prefix?

2. **Multiple Prozo Fields**: Prozo has `Reference Number`, `Order ID`, and `channelOrderName`. Which one matches Shopify `Name`?

3. **Customer Linking**: Should we link orders by:
   - Only exact email match?
   - Or also phone match?
   - Or fuzzy name + location match?

### Status & Flow
4. **Fulfillment Source**: Is Shopify `Fulfillment Status` auto-updated from Prozo? Or manual?

5. **RTO Refund Flow**: When a prepaid order goes RTO:
   - Who initiates refund? (Manual on Shopify? Auto from Razorpay?)
   - What's the timeline?

6. **Partial Payment COD**: When customer pays ₹149 partial:
   - Does remaining come as COD?
   - How is it tracked?

### Amounts
7. **Amount to Match**: For reconciliation, should we compare:
   - Shopify `Total` vs Razorpay `amount`?
   - Or Shopify `Subtotal` vs something else?

8. **Tolerance**: What amount difference is acceptable? (₹1? ₹10? ₹0?)

### Timing
9. **TAT Start**: For delivery TAT calculation:
   - Start from Shopify `Created at`?
   - Or Prozo `Pickup Date`?

10. **Flag Thresholds**:
    - "Not shipped" flag: After 2 days or 3 days?
    - "Stuck in transit": After 7 days or 10 days?

### Products
11. **Digital Products**: Which SKUs are digital (no physical delivery)?

12. **Multiple Line Items**: How to handle orders with 2+ products?
    - Combine into one unified order?
    - Or track separately?

---

## 16. NEXT STEPS

After you provide answers to Section 15:

1. **Finalize Field Mappings** - Exact field-to-field mapping
2. **Finalize Status Mapping** - Journey stage definitions
3. **Finalize Flag Rules** - Thresholds and conditions
4. **Create Technical Design** - Database schema refinement
5. **Build Phase 1** - Data upload and parsing

---

*Document Version: 1.1*
*Created: 2026-02-18*
*Last Updated: 2026-02-18*
*Author: Claude Code*
