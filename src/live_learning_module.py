"""
Live Learning Module - Streamlit UI

Tracks user journey from Luma registrations -> Zoom attendance -> Shopify orders.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from io import StringIO
import json

from live_learning_db import (
    init_live_learning_tables,
    get_dashboard_metrics,
    get_user_journey_data,
    get_events_in_range,
    get_all_events,
    get_table_counts,
    run_order_matching
)
from live_learning_parsers import (
    parse_luma_csv,
    parse_zoom_csv,
    detect_csv_type,
    extract_event_date_from_zoom,
    extract_event_date_from_luma
)
from shared_styles import inject_custom_css, get_color_palette


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_duration(minutes):
    """Format duration in minutes to human readable format."""
    if minutes is None or minutes == 0:
        return "-"
    if minutes < 60:
        return f"{int(minutes)}m"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{int(hours)}h"
    return f"{int(hours)}h {int(mins)}m"


def format_percentage(value):
    """Format percentage with 1 decimal place."""
    if value is None:
        return "0%"
    return f"{value:.1f}%"


def get_filter_emoji(filter_type):
    """Get emoji for filter type."""
    emojis = {
        'all': '',
        'matched': '',
        'unmatched': '',
        'attended': '',
        'no_show': ''
    }
    return emojis.get(filter_type, '')


# =============================================================================
# MAIN MODULE FUNCTION
# =============================================================================

def render_live_learning_module():
    """Main function to render the Live Learning module."""

    # Initialize database
    init_live_learning_tables()

    # Inject shared CSS styles
    inject_custom_css()

    st.title("Live Learning Analytics")

    # Create tabs
    tab_dashboard, tab_upload, tab_events = st.tabs([
        "Dashboard",
        "Upload Data",
        "Events"
    ])

    # =========================================================================
    # TAB 1: DASHBOARD
    # =========================================================================
    with tab_dashboard:
        render_dashboard_tab()

    # =========================================================================
    # TAB 2: UPLOAD
    # =========================================================================
    with tab_upload:
        render_upload_tab()

    # =========================================================================
    # TAB 3: EVENTS
    # =========================================================================
    with tab_events:
        render_events_tab()


# =============================================================================
# TAB 1: DASHBOARD
# =============================================================================

def render_dashboard_tab():
    """Render the dashboard tab with metrics and user journey data."""

    st.subheader("Date Range Filter")

    # Date range selector
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        preset = st.selectbox(
            "Quick Select",
            ["Last 7 Days", "Last 14 Days", "Last 30 Days", "This Month", "Last Month", "Custom"],
            key="live_learning_preset"
        )

    # Calculate dates based on preset
    today = datetime.now().date()

    if preset == "Last 7 Days":
        start_date = today - timedelta(days=7)
        end_date = today
    elif preset == "Last 14 Days":
        start_date = today - timedelta(days=14)
        end_date = today
    elif preset == "Last 30 Days":
        start_date = today - timedelta(days=30)
        end_date = today
    elif preset == "This Month":
        start_date = today.replace(day=1)
        end_date = today
    elif preset == "Last Month":
        first_of_this_month = today.replace(day=1)
        end_date = first_of_this_month - timedelta(days=1)
        start_date = end_date.replace(day=1)
    else:
        start_date = today - timedelta(days=30)
        end_date = today

    with col2:
        start_date = st.date_input(
            "Start Date",
            value=start_date,
            key="live_learning_start"
        )

    with col3:
        end_date = st.date_input(
            "End Date",
            value=end_date,
            key="live_learning_end"
        )

    st.divider()

    # Get metrics for date range
    metrics = get_dashboard_metrics(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d')
    )

    # =========================================
    # OVERVIEW METRICS
    # =========================================
    st.subheader("Overview")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Events",
            metrics['total_events']
        )

    with col2:
        st.metric(
            "Unique Registrants",
            f"{metrics['total_registered']:,}"
        )

    with col3:
        st.metric(
            "Unique Attendees",
            f"{metrics['total_attended']:,}"
        )

    with col4:
        st.metric(
            "Attendance Rate",
            format_percentage(metrics['attendance_rate'])
        )

    # Second row of metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Order Matched",
            f"{metrics['total_matched']:,}"
        )

    with col2:
        st.metric(
            "Not Matched",
            f"{metrics['total_unmatched']:,}"
        )

    with col3:
        st.metric(
            "Match Rate",
            format_percentage(metrics['match_rate'])
        )

    with col4:
        st.metric(
            "Avg Duration",
            format_duration(metrics['avg_duration'])
        )

    # Third row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "First-time Registrants",
            f"{metrics['first_time_registrants']:,}"
        )

    with col2:
        st.metric(
            "Repeat Registrants",
            f"{metrics['repeat_registrants']:,}"
        )

    st.divider()

    # =========================================
    # ORDER MATCHING
    # =========================================
    st.subheader("Order Matching")

    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("Run Order Matching", type="primary"):
            with st.spinner("Matching users with Shopify orders..."):
                result = run_order_matching()

            if 'error' in result:
                st.error(f"Error: {result['error']}")
            else:
                st.success(
                    f"Processed {result['processed']} users. "
                    f"Matched: {result['matched']}, Unmatched: {result['unmatched']}"
                )
                st.rerun()

    with col2:
        st.caption(
            "Matches users with Shopify orders by email or phone. "
            "Searches from latest orders first for efficiency."
        )

    st.divider()

    # =========================================
    # USER JOURNEY TABLE
    # =========================================
    st.subheader("User Journey")

    # Filter options
    col1, col2 = st.columns([1, 3])

    with col1:
        filter_type = st.selectbox(
            "Filter Users",
            ["All Users", "Order Matched", "Not Matched", "Attended", "No-Show"],
            key="user_filter"
        )

    # Map filter selection to filter type
    filter_map = {
        "All Users": "all",
        "Order Matched": "matched",
        "Not Matched": "unmatched",
        "Attended": "attended",
        "No-Show": "no_show"
    }
    filter_key = filter_map.get(filter_type, "all")

    # Get user journey data
    users = get_user_journey_data(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d'),
        filter_key
    )

    if not users:
        st.info("No users found for the selected date range and filter.")
    else:
        # Prepare data for display
        display_data = []
        for user in users:
            # Parse all_emails and all_phones
            all_emails = json.loads(user.get('all_emails', '[]') or '[]')
            all_phones = json.loads(user.get('all_phones', '[]') or '[]')

            display_data.append({
                'Name': user.get('primary_name', '-'),
                'Email': user.get('primary_email', '-'),
                'Phone': user.get('primary_phone', '-'),
                'Events Registered': user.get('period_events_registered', 0) or 0,
                'Events Attended': user.get('period_events_attended', 0) or 0,
                'Total Duration': format_duration(user.get('period_duration', 0)),
                'Join Frequency': user.get('period_join_frequency', 0) or 0,
                'Order Matched': 'Yes' if user.get('order_matched') == 1 else 'No',
                'Match Method': user.get('match_method', '-') or '-',
                'Order Date': user.get('shopify_order_date', '-') or '-',
            })

        df = pd.DataFrame(display_data)

        # Display count
        st.caption(f"Showing {len(df)} users")

        # Display dataframe
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=400
        )

        # Download button
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"live_learning_users_{start_date}_{end_date}.csv",
            mime="text/csv"
        )


# =============================================================================
# TAB 2: UPLOAD
# =============================================================================

def render_upload_tab():
    """Render the upload tab for Luma and Zoom CSVs."""

    st.subheader("Upload Event Data")

    st.markdown("""
    Upload Luma registration reports and Zoom attendance reports to track user journeys.

    **Supported formats:**
    - **Luma**: Guest list export (CSV)
    - **Zoom**: Meeting attendance report (CSV)
    """)

    # Create sub-tabs for different upload types
    upload_luma, upload_zoom = st.tabs(["Luma Registration", "Zoom Attendance"])

    # =========================================
    # LUMA UPLOAD
    # =========================================
    with upload_luma:
        st.markdown("### Upload Luma Registration CSV")

        luma_file = st.file_uploader(
            "Choose Luma CSV file",
            type=['csv'],
            key="luma_uploader",
            help="Upload the guest list export from Luma"
        )

        if luma_file:
            # Try to detect event date
            luma_file.seek(0)
            suggested_date = extract_event_date_from_luma(luma_file)
            luma_file.seek(0)

            event_date = st.date_input(
                "Event Date",
                value=datetime.strptime(suggested_date, '%Y-%m-%d').date() if suggested_date else datetime.now().date(),
                key="luma_event_date",
                help="The date of the event these registrations are for"
            )

            # Preview
            with st.expander("Preview Data", expanded=False):
                luma_file.seek(0)
                preview_df = pd.read_csv(luma_file, nrows=10, encoding='utf-8-sig')
                st.dataframe(preview_df, use_container_width=True)
                st.caption(f"Columns: {', '.join(preview_df.columns.tolist())}")

            if st.button("Process Luma CSV", type="primary", key="process_luma"):
                with st.spinner("Processing Luma registrations..."):
                    luma_file.seek(0)
                    progress_bar = st.progress(0)

                    def update_progress(pct):
                        progress_bar.progress(pct)

                    result = parse_luma_csv(
                        luma_file,
                        event_date.strftime('%Y-%m-%d'),
                        luma_file.name,
                        update_progress
                    )

                progress_bar.empty()

                if 'error' in result:
                    st.error(f"Error: {result['error']}")
                else:
                    st.success(f"""
                    **Luma CSV processed successfully!**
                    - Total rows: {result['total_rows']}
                    - Processed: {result['processed']}
                    - New users: {result['new_users']}
                    - Existing users: {result['existing_users']}
                    - Registrations created: {result['registrations_created']}
                    - Skipped (declined): {result['skipped_declined']}
                    - Skipped (no contact): {result['skipped_no_contact']}
                    """)

    # =========================================
    # ZOOM UPLOAD
    # =========================================
    with upload_zoom:
        st.markdown("### Upload Zoom Attendance CSV")

        zoom_file = st.file_uploader(
            "Choose Zoom CSV file",
            type=['csv'],
            key="zoom_uploader",
            help="Upload the meeting attendance report from Zoom"
        )

        if zoom_file:
            # Try to detect event date
            zoom_file.seek(0)
            suggested_date = extract_event_date_from_zoom(zoom_file)
            zoom_file.seek(0)

            event_date = st.date_input(
                "Event Date",
                value=datetime.strptime(suggested_date, '%Y-%m-%d').date() if suggested_date else datetime.now().date(),
                key="zoom_event_date",
                help="The date of the Zoom meeting"
            )

            # Preview
            with st.expander("Preview Data", expanded=False):
                zoom_file.seek(0)
                preview_df = pd.read_csv(zoom_file, nrows=10, encoding='utf-8-sig')
                st.dataframe(preview_df, use_container_width=True)
                st.caption(f"Columns: {', '.join(preview_df.columns.tolist())}")

            if st.button("Process Zoom CSV", type="primary", key="process_zoom"):
                with st.spinner("Processing Zoom attendance..."):
                    zoom_file.seek(0)
                    progress_bar = st.progress(0)

                    def update_progress(pct):
                        progress_bar.progress(pct)

                    result = parse_zoom_csv(
                        zoom_file,
                        event_date.strftime('%Y-%m-%d'),
                        zoom_file.name,
                        update_progress
                    )

                progress_bar.empty()

                if 'error' in result:
                    st.error(f"Error: {result['error']}")
                else:
                    st.success(f"""
                    **Zoom CSV processed successfully!**
                    - Total rows: {result['total_rows']}
                    - Unique attendees: {result['unique_attendees']}
                    - New users: {result['new_users']}
                    - Existing users: {result['existing_users']}
                    - Total duration: {format_duration(result['total_duration_minutes'])}
                    - Skipped (host): {result['skipped_host']}
                    - Skipped (no email): {result['skipped_no_email']}
                    """)

    st.divider()

    # =========================================
    # DATABASE STATUS
    # =========================================
    st.subheader("Database Status")

    counts = get_table_counts()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Events", counts.get('live_events', 0))

    with col2:
        st.metric("Unified Users", counts.get('live_unified_users', 0))

    with col3:
        st.metric("Registrations", counts.get('live_event_registrations', 0))

    with col4:
        st.metric("Attendance Records", counts.get('live_event_attendance', 0))


# =============================================================================
# TAB 3: EVENTS
# =============================================================================

def render_events_tab():
    """Render the events list tab."""

    st.subheader("Event History")

    events = get_all_events()

    if not events:
        st.info("No events found. Upload Luma or Zoom data to create events.")
        return

    # Prepare data for display
    display_data = []
    for event in events:
        display_data.append({
            'Date': event.get('event_date', '-'),
            'Event Name': event.get('event_name', '-') or '-',
            'Source': event.get('source', '-').upper(),
            'Registrations': event.get('total_registrations', 0) or 0,
            'Attendees': event.get('total_attendees', 0) or 0,
            'File': event.get('file_name', '-') or '-',
            'Created': event.get('created_at', '-') or '-',
        })

    df = pd.DataFrame(display_data)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    st.caption(f"Total events: {len(events)}")
