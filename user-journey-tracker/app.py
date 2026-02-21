"""
User Journey Tracker - Streamlit Application

Main application for tracking customer journeys from order to upsell purchase.
Phase 1: Shopify Orders + Zoom Attendance matching
"""

import streamlit as st
import pandas as pd
from schema import init_database, reset_database, get_table_counts
from data_loader import (
    load_shopify_csv, load_zoom_csv,
    get_shopify_stats, get_zoom_stats,
    get_shopify_orders_df, get_zoom_participants_df
)
from matching_engine import (
    run_matching_for_meeting, import_orders_as_unified_users,
    get_unified_users_df, get_matching_stats
)

# Page config
st.set_page_config(
    page_title="User Journey Tracker",
    page_icon="🎯",
    layout="wide"
)

# Custom CSS for light theme (matching existing dashboard)
st.markdown("""
<style>
    /* Main background */
    .stApp {
        background-color: #F7F8FA;
    }

    /* Text colors - ensure visibility */
    .stMarkdown, .stText, p, span, label {
        color: #1A1A1A !important;
    }

    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        color: #1A1A1A !important;
    }

    /* Metric cards */
    [data-testid="stMetricValue"] {
        color: #1A1A1A !important;
    }
    [data-testid="stMetricLabel"] {
        color: #666666 !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #FFFFFF;
        padding: 8px;
        border-radius: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        color: #1A1A1A !important;
        background-color: #F0F2F5;
        border-radius: 6px;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #528FF0 !important;
        color: #FFFFFF !important;
    }

    /* Dataframes */
    .stDataFrame {
        background-color: #FFFFFF;
        border-radius: 8px;
    }

    /* Cards/containers */
    .metric-card {
        background-color: #FFFFFF;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #E5E7EB;
        margin-bottom: 16px;
    }

    /* Success/warning/error messages */
    .stSuccess, .stWarning, .stError, .stInfo {
        color: #1A1A1A !important;
    }

    /* Buttons */
    .stButton > button {
        background-color: #528FF0;
        color: #FFFFFF;
        border: none;
        border-radius: 6px;
    }
    .stButton > button:hover {
        background-color: #4178D4;
    }

    /* File uploader */
    [data-testid="stFileUploader"] {
        background-color: #FFFFFF;
        border-radius: 8px;
        padding: 16px;
    }

    /* Expander */
    .streamlit-expanderHeader {
        color: #1A1A1A !important;
        background-color: #FFFFFF;
    }

    /* Select boxes and inputs */
    .stSelectbox label, .stTextInput label, .stNumberInput label {
        color: #1A1A1A !important;
    }
</style>
""", unsafe_allow_html=True)

# Initialize database on first run
init_database()


def render_upload_tab():
    """Tab 1: Upload & Preview data"""
    st.header("Upload & Preview Data")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Shopify Orders CSV")
        shopify_file = st.file_uploader(
            "Upload Shopify Orders Export",
            type=['csv'],
            key="shopify_upload",
            help="Export from Shopify Admin > Orders > Export"
        )

        if shopify_file:
            with st.spinner("Processing Shopify orders..."):
                try:
                    total, unique, dupes = load_shopify_csv(shopify_file)
                    st.success(f"Loaded {unique} unique orders ({dupes} duplicates removed from {total} rows)")
                except Exception as e:
                    st.error(f"Error loading Shopify CSV: {str(e)}")

        # Show current Shopify stats
        stats = get_shopify_stats()
        if stats['total_orders'] > 0:
            st.markdown("**Current Data:**")
            cols = st.columns(3)
            cols[0].metric("Total Orders", stats['total_orders'])
            cols[1].metric("COD Orders", stats['cod_orders'])
            cols[2].metric("Prepaid Orders", stats['prepaid_orders'])

            with st.expander("Preview Shopify Data"):
                df = get_shopify_orders_df()
                st.dataframe(
                    df[['order_number', 'email', 'phone', 'billing_name',
                        'total', 'payment_method', 'created_at']].head(20),
                    use_container_width=True
                )

    with col2:
        st.subheader("Zoom Attendance CSV")
        zoom_file = st.file_uploader(
            "Upload Zoom Attendance Report",
            type=['csv'],
            key="zoom_upload",
            help="Export from Zoom > Reports > Meeting > Attendance"
        )

        if zoom_file:
            with st.spinner("Processing Zoom attendance..."):
                try:
                    total, external, internal, topic, date = load_zoom_csv(zoom_file)
                    st.success(f"Loaded meeting: {topic} ({date})")
                    st.info(f"{external} external participants, {internal} internal excluded")
                except Exception as e:
                    st.error(f"Error loading Zoom CSV: {str(e)}")

        # Show current Zoom stats
        stats = get_zoom_stats()
        if stats['total_raw_records'] > 0:
            st.markdown("**Current Data:**")
            cols = st.columns(3)
            cols[0].metric("Raw Records", stats['total_raw_records'])
            cols[1].metric("External Participants", stats['external_participants'])
            cols[2].metric("Unique Meetings", stats['unique_meetings'])

            with st.expander("Preview Zoom Data"):
                df = get_zoom_participants_df(external_only=True)
                st.dataframe(
                    df[['meeting_topic', 'meeting_date', 'participant_name',
                        'email', 'total_duration_minutes']].head(20),
                    use_container_width=True
                )

    # Database management
    st.divider()
    st.subheader("Database Management")

    col1, col2, col3 = st.columns(3)

    with col1:
        counts = get_table_counts()
        st.markdown("**Table Row Counts:**")
        for table, count in counts.items():
            st.text(f"{table}: {count}")

    with col2:
        if st.button("Reset All Data", type="secondary"):
            if st.session_state.get('confirm_reset'):
                reset_database()
                st.success("Database reset successfully")
                st.session_state['confirm_reset'] = False
                st.rerun()
            else:
                st.session_state['confirm_reset'] = True
                st.warning("Click again to confirm reset")


def render_matching_tab():
    """Tab 2: Run Matching"""
    st.header("Run Matching Algorithm")

    # Get available meetings
    from schema import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT meeting_id, meeting_topic, meeting_date, COUNT(*) as participant_count
        FROM zoom_participants_deduped
        WHERE is_internal = 0
        GROUP BY meeting_id
        ORDER BY meeting_date DESC
    """)
    meetings = cursor.fetchall()
    conn.close()

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Match Zoom Participants to Orders")

        if not meetings:
            st.info("No Zoom meetings loaded yet. Upload Zoom CSV in the Upload tab first.")
        else:
            # Meeting selector
            meeting_options = {
                f"{m['meeting_topic']} ({m['meeting_date']}) - {m['participant_count']} participants": m['meeting_id']
                for m in meetings
            }

            selected_meeting = st.selectbox(
                "Select Meeting to Match",
                options=list(meeting_options.keys())
            )

            if selected_meeting:
                meeting_id = meeting_options[selected_meeting]

                if st.button("Run Matching", type="primary"):
                    with st.spinner("Running matching algorithm..."):
                        stats = run_matching_for_meeting(meeting_id)

                    st.success(f"Matching complete!")

                    # Display results
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Total Participants", stats['total_participants'])
                    col_b.metric("Matched", stats['matched'])
                    col_c.metric("Unmatched", stats['unmatched'])

                    # Match method breakdown
                    st.markdown("**Match Methods Used:**")
                    for method, count in stats['match_methods'].items():
                        if count > 0:
                            st.text(f"  {method.replace('_', ' ').title()}: {count}")

                    # Results table
                    if stats['results']:
                        st.markdown("**Match Results:**")
                        results_df = pd.DataFrame(stats['results'])

                        # Color code matched/unmatched
                        st.dataframe(
                            results_df,
                            column_config={
                                "matched": st.column_config.CheckboxColumn("Matched"),
                                "confidence": st.column_config.ProgressColumn(
                                    "Confidence",
                                    min_value=0,
                                    max_value=1,
                                    format="%.2f"
                                )
                            },
                            use_container_width=True
                        )

    with col2:
        st.subheader("Import Orders")
        st.markdown("""
        Import Shopify orders as unified users
        (for customers who haven't attended any events).
        """)

        shopify_stats = get_shopify_stats()
        if shopify_stats['total_orders'] == 0:
            st.info("No Shopify orders loaded yet.")
        else:
            if st.button("Import Unmatched Orders"):
                with st.spinner("Importing orders..."):
                    count = import_orders_as_unified_users()
                st.success(f"Imported {count} orders as unified users")


def render_unified_users_tab():
    """Tab 3: View Unified Users"""
    st.header("Unified Users")

    # Get stats
    stats = get_matching_stats()

    # Top metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Users", stats['total_unified_users'])
    col2.metric("Attended Events", stats['attended_events'])
    col3.metric("Needs Review", stats['needs_review'])
    col4.metric("Avg Confidence", f"{stats['avg_confidence']:.1%}")
    col5.metric("Journey Stages", len(stats.get('by_journey_stage', {})))

    # Journey stage breakdown
    if stats.get('by_journey_stage'):
        st.subheader("Journey Stage Distribution")
        stage_df = pd.DataFrame([
            {"Stage": k, "Count": v}
            for k, v in stats['by_journey_stage'].items()
        ])
        st.bar_chart(stage_df.set_index('Stage'))

    # User table
    st.subheader("User List")

    df = get_unified_users_df()

    if df.empty:
        st.info("No unified users yet. Run matching or import orders first.")
    else:
        # Filters
        col1, col2, col3 = st.columns(3)

        with col1:
            stage_filter = st.multiselect(
                "Journey Stage",
                options=df['journey_stage'].dropna().unique().tolist(),
                default=[]
            )

        with col2:
            attended_filter = st.selectbox(
                "Event Attendance",
                options=["All", "Attended", "Not Attended"]
            )

        with col3:
            review_filter = st.checkbox("Needs Review Only", value=False)

        # Apply filters
        filtered_df = df.copy()

        if stage_filter:
            filtered_df = filtered_df[filtered_df['journey_stage'].isin(stage_filter)]

        if attended_filter == "Attended":
            filtered_df = filtered_df[filtered_df['has_attended_any'] == 1]
        elif attended_filter == "Not Attended":
            filtered_df = filtered_df[filtered_df['has_attended_any'] == 0]

        if review_filter:
            filtered_df = filtered_df[filtered_df['needs_review'] == 1]

        # Display columns
        display_cols = [
            'primary_name', 'primary_email', 'primary_phone',
            'journey_stage', 'order_count', 'total_order_value',
            'has_attended_any', 'total_events_attended',
            'match_confidence', 'match_method', 'needs_review'
        ]

        available_cols = [c for c in display_cols if c in filtered_df.columns]

        st.dataframe(
            filtered_df[available_cols],
            column_config={
                "has_attended_any": st.column_config.CheckboxColumn("Attended"),
                "needs_review": st.column_config.CheckboxColumn("Review"),
                "match_confidence": st.column_config.ProgressColumn(
                    "Confidence",
                    min_value=0,
                    max_value=1
                ),
                "total_order_value": st.column_config.NumberColumn(
                    "Order Value",
                    format="₹%.2f"
                )
            },
            use_container_width=True
        )

        st.caption(f"Showing {len(filtered_df)} of {len(df)} users")


def render_audit_tab():
    """Tab 4: Audit Log"""
    st.header("Match Audit Log")

    from schema import get_db_connection
    conn = get_db_connection()

    # Get audit log
    df = pd.read_sql_query("""
        SELECT
            mal.id,
            mal.unified_user_id,
            uu.primary_name,
            uu.primary_email,
            mal.source_table,
            mal.match_field,
            mal.value_from_user,
            mal.value_from_source,
            mal.confidence,
            mal.match_result,
            mal.created_at
        FROM match_audit_log mal
        LEFT JOIN unified_users uu ON mal.unified_user_id = uu.id
        ORDER BY mal.created_at DESC
        LIMIT 500
    """, conn)
    conn.close()

    if df.empty:
        st.info("No audit records yet. Run matching to generate audit trail.")
    else:
        # Summary stats
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Records", len(df))
        col2.metric("Avg Confidence", f"{df['confidence'].mean():.1%}")
        col3.metric("Unique Users", df['unified_user_id'].nunique())

        # Match field breakdown
        if 'match_field' in df.columns:
            st.subheader("Match Field Distribution")
            field_counts = df['match_field'].value_counts()
            st.bar_chart(field_counts)

        # Full log table
        st.subheader("Audit Trail")
        st.dataframe(
            df,
            column_config={
                "confidence": st.column_config.ProgressColumn(
                    "Confidence",
                    min_value=0,
                    max_value=1
                )
            },
            use_container_width=True
        )


def main():
    """Main application entry point."""
    st.title("User Journey Tracker")
    st.caption("Track customer journeys from order to upsell purchase")

    # Create tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "Upload & Preview",
        "Run Matching",
        "Unified Users",
        "Audit Log"
    ])

    with tab1:
        render_upload_tab()

    with tab2:
        render_matching_tab()

    with tab3:
        render_unified_users_tab()

    with tab4:
        render_audit_tab()


if __name__ == "__main__":
    main()
