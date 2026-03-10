"""
Logistics Reconciliation - Streamlit UI Module

Main entry point for the Logistics Dashboard.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from logistics_db import init_database, get_table_counts, get_last_import_info
from logistics_parsers import parse_shopify_csv, parse_prozo_csv
from logistics_engine import (
    run_matching,
    get_dashboard_metrics,
    get_user_journey_data,
    get_line_items_data,
    get_date_range,
    get_sku_level_sales
)
from shared_styles import inject_custom_css


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_currency(amount):
    """Format amount as Indian currency."""
    if amount is None:
        return "₹0"
    if amount >= 10000000:  # 1 crore
        return f"₹{amount/10000000:.2f} Cr"
    elif amount >= 100000:  # 1 lakh
        return f"₹{amount/100000:.2f} L"
    elif amount >= 1000:
        return f"₹{amount/1000:.1f}K"
    else:
        return f"₹{amount:.0f}"


def format_number(num):
    """Format number with commas."""
    if num is None:
        return "0"
    return f"{num:,}"


def get_status_emoji(status):
    """Get emoji for delivery status."""
    emojis = {
        'delivered': '✅',
        'in_transit': '🚚',
        'rto': '↩️',
        'cancelled': '❌',
        'not_shipped': '🕐',
        'refunded': '💸',
    }
    return emojis.get(status, '❓')


def get_dispatch_emoji(category):
    """Get emoji for dispatch category."""
    emojis = {
        'fast': '✅',
        'normal': '⚠️',
        'delayed': '❌',
        'not_dispatched': '🕐',
    }
    return emojis.get(category, '❓')


# =============================================================================
# MAIN MODULE FUNCTION
# =============================================================================

def render_logistics_module():
    """Main function to render the Logistics Reconciliation module."""

    # Initialize database
    init_database()

    # Inject shared CSS styles
    inject_custom_css()

    st.title("📦 Logistics Reconciliation")

    # Create tabs
    tab_dashboard, tab_journey, tab_items = st.tabs([
        "📊 Dashboard",
        "👤 User Journey",
        "📋 Line Items"
    ])

    # =========================================================================
    # TAB 1: DASHBOARD
    # =========================================================================
    with tab_dashboard:
        render_dashboard_tab()

    # =========================================================================
    # TAB 2: USER JOURNEY
    # =========================================================================
    with tab_journey:
        render_user_journey_tab()

    # =========================================================================
    # TAB 3: LINE ITEMS
    # =========================================================================
    with tab_items:
        render_line_items_tab()


# =============================================================================
# TAB 1: DASHBOARD
# =============================================================================

def render_dashboard_tab():
    """Render the dashboard tab."""

    # =========================================
    # SHOPIFY SYNC SECTION
    # =========================================
    st.subheader("🔄 Sync from Shopify")

    # Import sync functions
    try:
        from shopify_api import (
            sync_shopify_orders,
            get_last_sync_timestamp,
            save_last_sync_timestamp,
            test_shopify_connection
        )
        shopify_api_available = True
    except Exception as e:
        shopify_api_available = False
        st.warning(f"⚠️ Shopify API not configured: {e}")

    if shopify_api_available:
        # Show last sync timestamp
        last_sync = get_last_sync_timestamp()
        if last_sync:
            st.caption(f"Last synced: {last_sync.strftime('%d %b %Y, %I:%M %p')}")
        else:
            st.caption("Never synced")

        col_sync1, col_sync2 = st.columns([1, 1])

        with col_sync1:
            # Quick Sync button (last 7 days)
            if st.button("🔄 Quick Sync (Last 7 days)", type="primary", use_container_width=True, key="shopify_quick_sync"):
                st.session_state['run_shopify_quick_sync'] = True

        with col_sync2:
            # Test connection
            if st.button("🔌 Test Connection", use_container_width=True, key="shopify_test_conn"):
                with st.spinner("Testing Shopify connection..."):
                    result = test_shopify_connection()
                    if result['success']:
                        st.success(f"✅ Connected to: {result.get('shop_name', 'Unknown')} ({result.get('shop_domain', '')})")
                    else:
                        st.error(f"❌ Connection failed: {result['message']}")

        # Handle quick sync outside of button to avoid nesting issues
        if st.session_state.get('run_shopify_quick_sync'):
            st.session_state['run_shopify_quick_sync'] = False
            with st.status("Syncing Shopify orders...", expanded=True) as status:
                try:
                    end_date = datetime.now().strftime('%Y-%m-%d')
                    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

                    def progress_cb(msg, pct):
                        status.update(label=msg)

                    new_count, updated_count, failed_count = sync_shopify_orders(
                        start_date, end_date, progress_cb
                    )
                    save_last_sync_timestamp()

                    # Auto-run matching
                    match_result = run_matching()

                    status.update(label=f"✅ Done: {new_count} new, {updated_count} updated, {match_result['matched']} matched", state="complete")
                except Exception as e:
                    status.update(label=f"❌ Error: {str(e)}", state="error")

        # Custom date range (expandable)
        with st.expander("📅 Custom Date Range (for backfills)"):
            col_d1, col_d2 = st.columns([1, 1])
            with col_d1:
                sync_start = st.date_input(
                    "Start Date",
                    value=datetime.now() - timedelta(days=30),
                    key="shopify_sync_start"
                )
            with col_d2:
                sync_end = st.date_input(
                    "End Date",
                    value=datetime.now(),
                    key="shopify_sync_end"
                )

            if st.button("🔄 Sync Custom Range", key="shopify_custom_sync", use_container_width=True):
                st.session_state['run_shopify_custom_sync'] = True
                st.session_state['shopify_custom_start'] = sync_start.strftime('%Y-%m-%d')
                st.session_state['shopify_custom_end'] = sync_end.strftime('%Y-%m-%d')

        # Handle custom sync outside expander
        if st.session_state.get('run_shopify_custom_sync'):
            st.session_state['run_shopify_custom_sync'] = False
            custom_start = st.session_state.get('shopify_custom_start')
            custom_end = st.session_state.get('shopify_custom_end')

            with st.status(f"Syncing {custom_start} to {custom_end}...", expanded=True) as status:
                try:
                    def progress_cb(msg, pct):
                        status.update(label=msg)

                    new_count, updated_count, failed_count = sync_shopify_orders(
                        custom_start, custom_end, progress_cb
                    )
                    save_last_sync_timestamp()

                    # Auto-run matching
                    match_result = run_matching()

                    status.update(label=f"✅ Done: {new_count} new, {updated_count} updated, {match_result['matched']} matched", state="complete")
                except Exception as e:
                    status.update(label=f"❌ Error: {str(e)}", state="error")

    st.divider()

    # =========================================
    # PROZO SYNC SECTION
    # =========================================
    st.subheader("📦 Sync from Prozo")

    # Import sync functions and exceptions
    try:
        from prozo_sync import (
            sync_prozo_orders,
            get_last_prozo_sync_timestamp,
            save_last_prozo_sync_timestamp,
            test_prozo_connection,
            check_prozo_availability,
            get_error_message,
            ProzoAutomationError,
            ProzoLoginError,
            ProzoEmptyReportError,
        )
        # run_matching is already imported at module level
        prozo_sync_available = True
    except Exception as e:
        prozo_sync_available = False
        st.warning(f"⚠️ Prozo sync not configured: {e}")

    if prozo_sync_available:
        # Check availability (credentials + playwright)
        availability = check_prozo_availability()

        if not availability['available']:
            st.warning(f"⚠️ {availability['message']}")
            st.caption("Configure PROZO_EMAIL and PROZO_PASSWORD in .env, then run: pip install playwright && playwright install chromium")
        else:
            # Show last sync timestamp
            last_sync = get_last_prozo_sync_timestamp()
            if last_sync:
                st.caption(f"Last synced: {last_sync.strftime('%d %b %Y, %I:%M %p')}")
            else:
                st.caption("Never synced")

            col_psync1, col_psync2 = st.columns([1, 1])

            with col_psync1:
                # Full Sync button (Oct 1, 2025 to today)
                if st.button("📦 Full Sync (Oct 1 - Today)", type="primary", use_container_width=True, key="prozo_quick_sync"):
                    st.session_state['run_prozo_quick_sync'] = True

            with col_psync2:
                # Test connection
                if st.button("🔌 Test Connection", use_container_width=True, key="prozo_test_conn"):
                    with st.spinner("Testing Prozo connection..."):
                        result = test_prozo_connection()
                        if result['success']:
                            st.success(f"✅ Prozo configured: {result.get('email', 'Unknown')}")
                        else:
                            st.error(f"❌ {result['message']}")

            # Handle quick sync outside of button to avoid nesting issues
            if st.session_state.get('run_prozo_quick_sync'):
                st.session_state['run_prozo_quick_sync'] = False
                with st.status("Syncing Prozo MIS...", expanded=True) as status:
                    try:
                        # Always sync from Oct 1, 2025 to today (full history)
                        end_date = datetime.now().strftime('%Y-%m-%d')
                        start_date = "2025-10-01"

                        def progress_cb(msg, pct):
                            status.update(label=msg)

                        new_count, updated_count, failed_count = sync_prozo_orders(
                            start_date, end_date, progress_cb, headless=True
                        )
                        save_last_prozo_sync_timestamp()

                        # Auto-run matching
                        match_result = run_matching()

                        status.update(label=f"✅ Done: {new_count} new, {updated_count} updated, {match_result['matched']} matched", state="complete")

                    except ProzoLoginError as e:
                        status.update(label=f"❌ Login Failed", state="error")
                        st.error(f"**Login Error:** {str(e)}")
                        st.info("Check your PROZO_EMAIL and PROZO_PASSWORD in .env file")

                    except ProzoEmptyReportError as e:
                        status.update(label=f"❌ No Data", state="error")
                        st.warning(f"**No Data Found:** {str(e)}")
                        st.info("The report generated but contained no data for the selected date range")

                    except ProzoAutomationError as e:
                        status.update(label=f"❌ Sync Failed", state="error")
                        st.error(f"**Prozo Sync Error:** {get_error_message(e)}")
                        st.info("The Prozo dashboard may be down or the page structure may have changed. Try again later or use manual upload.")

                    except Exception as e:
                        status.update(label=f"❌ Unexpected Error", state="error")
                        st.error(f"**Unexpected Error:** {str(e)}")

            # Custom date range (expandable)
            with st.expander("📅 Custom Date Range"):
                col_pd1, col_pd2 = st.columns([1, 1])
                with col_pd1:
                    # Default to Oct 1, 2025 (when Prozo started)
                    prozo_sync_start = st.date_input(
                        "Start Date",
                        value=datetime(2025, 10, 1),
                        key="prozo_sync_start"
                    )
                with col_pd2:
                    prozo_sync_end = st.date_input(
                        "End Date",
                        value=datetime.now(),
                        key="prozo_sync_end"
                    )

                if st.button("📦 Sync Custom Range", key="prozo_custom_sync", use_container_width=True):
                    st.session_state['run_prozo_custom_sync'] = True
                    st.session_state['prozo_custom_start'] = prozo_sync_start.strftime('%Y-%m-%d')
                    st.session_state['prozo_custom_end'] = prozo_sync_end.strftime('%Y-%m-%d')

            # Handle custom sync outside expander
            if st.session_state.get('run_prozo_custom_sync'):
                st.session_state['run_prozo_custom_sync'] = False
                custom_start = st.session_state.get('prozo_custom_start')
                custom_end = st.session_state.get('prozo_custom_end')

                with st.status(f"Syncing Prozo {custom_start} to {custom_end}...", expanded=True) as status:
                    try:
                        def progress_cb(msg, pct):
                            status.update(label=msg)

                        new_count, updated_count, failed_count = sync_prozo_orders(
                            custom_start, custom_end, progress_cb, headless=True
                        )
                        save_last_prozo_sync_timestamp()

                        # Auto-run matching
                        match_result = run_matching()

                        status.update(label=f"✅ Done: {new_count} new, {updated_count} updated, {match_result['matched']} matched", state="complete")

                    except ProzoLoginError as e:
                        status.update(label=f"❌ Login Failed", state="error")
                        st.error(f"**Login Error:** {str(e)}")
                        st.info("Check your PROZO_EMAIL and PROZO_PASSWORD in .env file")

                    except ProzoEmptyReportError as e:
                        status.update(label=f"❌ No Data", state="error")
                        st.warning(f"**No Data Found:** {str(e)}")
                        st.info("The report generated but contained no data for the selected date range")

                    except ProzoAutomationError as e:
                        status.update(label=f"❌ Sync Failed", state="error")
                        st.error(f"**Prozo Sync Error:** {get_error_message(e)}")
                        st.info("The Prozo dashboard may be down or the page structure may have changed. Try again later or use manual upload.")

                    except Exception as e:
                        status.update(label=f"❌ Unexpected Error", state="error")
                        st.error(f"**Unexpected Error:** {str(e)}")

    st.divider()

    # =========================================
    # MANUAL UPLOAD SECTION
    # =========================================
    st.subheader("📤 Manual Upload (Fallback)")

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        shopify_file = st.file_uploader(
            "Upload Shopify Orders CSV",
            type=['csv'],
            key='shopify_upload'
        )
        if shopify_file:
            with st.spinner("Processing Shopify data..."):
                result = parse_shopify_csv(shopify_file)
                if result['success']:
                    st.success(f"✅ Imported {result['records_total']} orders ({result['records_new']} new, {result['records_updated']} updated)")
                    # Auto-run matching
                    match_result = run_matching()
                    st.info(f"Matched {match_result['matched']} orders with Prozo data")
                else:
                    st.error(f"❌ Error: {result['error']}")

    with col2:
        prozo_file = st.file_uploader(
            "Upload Prozo MIS CSV",
            type=['csv'],
            key='prozo_upload'
        )
        if prozo_file:
            with st.spinner("Processing Prozo data..."):
                result = parse_prozo_csv(prozo_file)
                if result['success']:
                    st.success(f"✅ Imported {result['records_total']} shipments ({result['records_new']} new, {result['records_updated']} updated)")
                    # Auto-run matching (only if Shopify data exists)
                    match_result = run_matching()
                    if match_result.get('message'):
                        st.warning(f"⚠️ {match_result['message']}")
                    else:
                        st.info(f"Matched {match_result['matched']} orders with Shopify data")
                else:
                    st.error(f"❌ Error: {result['error']}")

    with col3:
        if st.button("🔄 Re-run Matching", use_container_width=True):
            with st.spinner("Matching orders..."):
                match_result = run_matching()
                st.success(f"✅ Matched {match_result['matched']} orders, {match_result['not_shipped']} not shipped")

    # Show current data stats
    counts = get_table_counts()
    st.markdown(f"<p style='color: #1A1A1A; font-size: 14px;'>📊 Data: {counts.get('raw_shopify_orders', 0)} Shopify orders | {counts.get('raw_prozo_orders', 0)} Prozo shipments | {counts.get('unified_orders', 0)} unified</p>", unsafe_allow_html=True)

    st.divider()

    # Date filter
    min_date, max_date = get_date_range()

    if not min_date:
        st.info("📭 No data yet. Please upload Shopify and Prozo CSV files above.")
        return

    # Quick date selection
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    # Calculate calendar-based Last Month (1st to last day of previous month)
    first_of_this_month = today.replace(day=1)
    last_day_of_last_month = first_of_this_month - timedelta(days=1)
    first_of_last_month = last_day_of_last_month.replace(day=1)

    # Date presets (calendar-based, not rolling)
    date_presets = {
        'Today': (today, today),
        'Yesterday': (yesterday, yesterday),
        'This Month': (first_of_this_month, today),
        'Last Month': (first_of_last_month, last_day_of_last_month),
        'Custom': None
    }

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        date_preset = st.selectbox(
            "📅 Quick Select",
            options=list(date_presets.keys()),
            index=0,  # Default to Yesterday
            key='date_preset'
        )

    # Determine dates based on preset
    if date_preset != 'Custom' and date_presets[date_preset]:
        preset_start, preset_end = date_presets[date_preset]
        start_date = preset_start
        end_date = preset_end
    else:
        # Custom: show date pickers
        preset_start = yesterday
        preset_end = yesterday

    with col2:
        start_date = st.date_input(
            "From Date",
            value=preset_start,
            key='dash_start_date',
            disabled=(date_preset != 'Custom')
        )

    with col3:
        end_date = st.date_input(
            "To Date",
            value=preset_end,
            key='dash_end_date',
            disabled=(date_preset != 'Custom')
        )

    # Use preset dates if not custom
    if date_preset != 'Custom' and date_presets[date_preset]:
        start_date, end_date = date_presets[date_preset]

    # Get metrics
    metrics = get_dashboard_metrics(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d")
    )

    # =========================================
    # SUMMARY CARDS
    # =========================================
    st.subheader("📈 Revenue Summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Orders",
            format_number(metrics['total_orders']),
        )

    with col2:
        st.metric(
            "Projected Revenue",
            format_currency(metrics['projected_revenue']),
            f"AOV: {format_currency(metrics['projected_aov'])}"
        )

    with col3:
        st.metric(
            "Actual Revenue",
            format_currency(metrics['actual_revenue']),
            f"AOV: {format_currency(metrics['actual_aov'])}"
        )

    with col4:
        st.metric(
            "Lost Revenue",
            format_currency(metrics['lost_revenue']),
            f"{metrics['lost_percentage']:.1f}% of projected",
            delta_color="inverse"
        )

    # Second row of metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Pending Revenue",
            format_currency(metrics['pending_revenue']),
            f"{metrics['in_transit_orders'] + metrics['not_shipped_orders']} orders"
        )

    with col2:
        st.metric(
            "Delivery Rate",
            f"{metrics['delivery_rate']:.1f}%",
            f"{metrics['delivered_orders']} delivered"
        )

    with col3:
        st.metric(
            "RTO Rate",
            f"{metrics['rto_rate']:.1f}%",
            f"{metrics['rto_orders']} orders",
            delta_color="inverse"
        )

    with col4:
        st.metric(
            "Avg Dispatch Time",
            f"{metrics['avg_dispatch_hours'] or 0}h",
        )

    st.divider()

    # =========================================
    # BREAKDOWNS
    # =========================================
    col1, col2 = st.columns(2)

    # Payment Method Breakdown
    with col1:
        st.subheader("💳 Payment Method Breakdown")

        payment_data = metrics.get('payment_breakdown', {})
        if payment_data:
            payment_df = pd.DataFrame([
                {
                    'Payment Mode': mode.replace('_', ' ').title() if mode else 'Unknown',
                    'Orders': data['count'],
                    'Percentage': f"{data['percentage']:.1f}%",
                    'Revenue': format_currency(data['total'])
                }
                for mode, data in payment_data.items()
            ])

            # Sort by count
            payment_df = payment_df.sort_values('Orders', ascending=False)

            # Table only
            st.dataframe(payment_df, use_container_width=True, hide_index=True)
        else:
            st.info("No payment data available")

    # Delivery Status Breakdown
    with col2:
        st.subheader("🚚 Delivery Status Breakdown")

        delivery_data = metrics.get('delivery_breakdown', {})
        if delivery_data:
            delivery_df = pd.DataFrame([
                {
                    'Status': f"{get_status_emoji(status)} {status.replace('_', ' ').title()}",
                    'Orders': data['count'],
                    'Percentage': f"{data['percentage']:.1f}%",
                    'Revenue': format_currency(data['total'])
                }
                for status, data in delivery_data.items()
            ])

            # Sort by count
            delivery_df = delivery_df.sort_values('Orders', ascending=False)

            # Table only
            st.dataframe(delivery_df, use_container_width=True, hide_index=True)
        else:
            st.info("No delivery data available")

    st.divider()

    # Dispatch Time Breakdown
    st.subheader("⏱️ Dispatch Time Breakdown")

    dispatch_data = metrics.get('dispatch_breakdown', {})
    if dispatch_data:
        col1, col2 = st.columns([2, 1])

        with col1:
            dispatch_df = pd.DataFrame([
                {
                    'Category': f"{get_dispatch_emoji(cat)} {cat.replace('_', ' ').title()}",
                    'Orders': data['count'],
                    'Percentage': f"{data['percentage']:.1f}%",
                    'Avg Hours': f"{data['avg_hours'] or '-'}h"
                }
                for cat, data in dispatch_data.items()
            ])

            # Custom order
            order = ['fast', 'normal', 'delayed', 'not_dispatched']
            dispatch_df['_sort'] = dispatch_df['Category'].apply(
                lambda x: order.index(x.split(' ')[-1].lower().replace(' ', '_')) if any(o in x.lower() for o in order) else 99
            )
            dispatch_df = dispatch_df.sort_values('_sort').drop('_sort', axis=1)

            st.dataframe(dispatch_df, use_container_width=True, hide_index=True)

        with col2:
            # Summary
            fast_pct = dispatch_data.get('fast', {}).get('percentage', 0)
            delayed_pct = dispatch_data.get('delayed', {}).get('percentage', 0)

            if fast_pct >= 70:
                st.success(f"✅ {fast_pct:.0f}% orders dispatched within 24h")
            elif fast_pct >= 50:
                st.warning(f"⚠️ {fast_pct:.0f}% orders dispatched within 24h")
            else:
                st.error(f"❌ Only {fast_pct:.0f}% dispatched within 24h")

            if delayed_pct > 10:
                st.error(f"❌ {delayed_pct:.0f}% orders delayed (>48h)")
    else:
        st.info("No dispatch data available")

    st.divider()

    # =========================================
    # SKU-LEVEL SALES
    # =========================================
    st.subheader("📦 SKU-Level Sales")

    sku_data, total_line_items = get_sku_level_sales(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d")
    )

    if sku_data:
        st.markdown(f"<p style='color: #374151; font-size: 14px;'>Total Line Items Sold: {total_line_items:,}</p>", unsafe_allow_html=True)

        sku_df = pd.DataFrame([
            {
                'SKU': item['sku'],
                'Item Name': item['item_name'][:50] + '...' if len(item['item_name']) > 50 else item['item_name'],
                'Qty Sold': item['total_qty'],
                'Orders': item['order_count'],
                'Revenue': format_currency(item['revenue']),
                'Share %': f"{item['percentage']:.1f}%"
            }
            for item in sku_data
        ])

        st.dataframe(sku_df, use_container_width=True, hide_index=True)
    else:
        st.info("No SKU data available")


# =============================================================================
# TAB 2: USER JOURNEY
# =============================================================================

def render_user_journey_tab():
    """Render the user journey tab."""

    st.subheader("👤 User Journey - Order List")

    # Search and filters
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

    with col1:
        search_query = st.text_input(
            "🔍 Search",
            placeholder="Search by Order ID, Phone, or Email",
            key='journey_search'
        )

    with col2:
        payment_options = ['all', 'prepaid', 'partial', 'cod', 'refunded']
        payment_filter = st.selectbox(
            "Payment Mode",
            options=payment_options,
            format_func=lambda x: x.replace('_', ' ').title() if x != 'all' else 'All',
            key='journey_payment'
        )

    with col3:
        status_options = ['all', 'delivered', 'in_transit', 'rto', 'cancelled', 'not_shipped']
        status_filter = st.selectbox(
            "Delivery Status",
            options=status_options,
            format_func=lambda x: f"{get_status_emoji(x)} {x.replace('_', ' ').title()}" if x != 'all' else 'All',
            key='journey_status'
        )

    with col4:
        # Date range
        min_date, max_date = get_date_range()
        if min_date:
            date_range = st.date_input(
                "Date Range",
                value=(
                    datetime.strptime(min_date, "%Y-%m-%d"),
                    datetime.strptime(max_date, "%Y-%m-%d")
                ),
                key='journey_date'
            )
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range
            else:
                start_date = end_date = date_range
        else:
            start_date = end_date = None

    # Get data
    orders, total_count = get_user_journey_data(
        search_query=search_query if search_query else None,
        payment_mode=payment_filter if payment_filter != 'all' else None,
        delivery_status=status_filter if status_filter != 'all' else None,
        start_date=start_date.strftime("%Y-%m-%d") if start_date else None,
        end_date=end_date.strftime("%Y-%m-%d") if end_date else None,
        limit=500
    )

    st.markdown(f"<p style='color: #374151; font-size: 14px;'>Showing {len(orders)} of {total_count} orders</p>", unsafe_allow_html=True)

    if orders:
        # Prepare dataframe
        df = pd.DataFrame(orders)

        # Format columns
        df['order_date'] = pd.to_datetime(df['order_date']).dt.strftime('%d %b %Y')
        df['total_amount'] = df['total_amount'].apply(lambda x: f"₹{x:,.0f}" if x else "-")
        df['payment_mode'] = df['payment_mode'].apply(lambda x: x.replace('_', ' ').title() if x else '-')
        df['delivery_status'] = df['delivery_status'].apply(
            lambda x: f"{get_status_emoji(x)} {x.replace('_', ' ').title()}" if x else '-'
        )
        df['dispatch'] = df.apply(
            lambda row: f"{get_dispatch_emoji(row['dispatch_category'])} {row['dispatch_hours']:.0f}h"
            if row['dispatch_hours'] else '-',
            axis=1
        )

        # Add refunded indicator
        df['payment_mode'] = df.apply(
            lambda row: f"{row['payment_mode']} 💸" if row.get('is_refunded') else row['payment_mode'],
            axis=1
        )

        # Select columns to display
        display_cols = [
            'order_id', 'order_date', 'customer_phone', 'customer_email',
            'customer_city', 'total_amount', 'payment_mode', 'delivery_status', 'dispatch'
        ]

        # Rename columns for display
        df_display = df[display_cols].rename(columns={
            'order_id': 'Order ID',
            'order_date': 'Date',
            'customer_phone': 'Phone',
            'customer_email': 'Email',
            'customer_city': 'City',
            'total_amount': 'Amount',
            'payment_mode': 'Payment',
            'delivery_status': 'Status',
            'dispatch': 'Dispatch'
        })

        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("No orders found matching your criteria")


# =============================================================================
# TAB 3: LINE ITEMS
# =============================================================================

def render_line_items_tab():
    """Render the line items tab."""

    st.subheader("📋 Line Items Breakdown")

    # Search
    search_query = st.text_input(
        "🔍 Search",
        placeholder="Search by Order ID or SKU",
        key='items_search'
    )

    # Get data
    items, total_count = get_line_items_data(
        search_query=search_query if search_query else None,
        limit=500
    )

    st.markdown(f"<p style='color: #374151; font-size: 14px;'>Showing {len(items)} of {total_count} line items</p>", unsafe_allow_html=True)

    if items:
        df = pd.DataFrame(items)

        # Format price
        df['lineitem_price'] = df['lineitem_price'].apply(lambda x: f"₹{x:,.0f}" if x else "-")

        # Rename columns
        df_display = df.rename(columns={
            'order_id': 'Order ID',
            'lineitem_name': 'Item Name',
            'lineitem_sku': 'SKU',
            'lineitem_quantity': 'Qty',
            'lineitem_price': 'Price',
            'lineitem_discount': 'Discount'
        })

        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("No line items found")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    st.set_page_config(
        page_title="Logistics Dashboard",
        page_icon="📦",
        layout="wide"
    )
    render_logistics_module()
