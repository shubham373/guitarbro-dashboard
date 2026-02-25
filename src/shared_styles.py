"""
Shared Styles - GuitarBro Dashboard

This module contains the shared CSS styles that MUST be applied to ALL modules.
Import and call inject_custom_css() at the start of every module's render function.

STYLING RULES (from STYLING_GUIDE.md):
- Normal text (no pill/background): BLACK (#000000)
- Blue pill background: BLACK text (#000000)
- Dark/Gray pill background: WHITE text (#FFFFFF)
- NEVER use low-contrast combinations
"""

import streamlit as st


def inject_custom_css():
    """
    Inject the standard CSS styles for the dashboard.
    Call this at the start of every module's render function.
    """
    st.markdown("""
    <style>
    /* ============================================ */
    /* GUITARBRO DASHBOARD - SHARED STYLES         */
    /* ============================================ */
    /* STYLING GUIDE:                               */
    /* - Normal text (no pill): BLACK              */
    /* - Blue pill background: BLACK text          */
    /* - Dark/Gray pill background: WHITE text     */
    /* ============================================ */

    /* ============================================ */
    /* BASE: WHITE BACKGROUND, BLACK TEXT           */
    /* ============================================ */

    body, html, .stApp, .main, .block-container {
        background-color: #FFFFFF !important;
    }

    /* All normal text is BLACK */
    p, span, div, label, h1, h2, h3, h4, h5, h6,
    caption, small, strong, em, b, i, a, li {
        color: #000000 !important;
    }

    /* ============================================ */
    /* BLUE PILLS: BLACK TEXT                       */
    /* ============================================ */

    /* Primary buttons - Blue pill, black text */
    .stButton > button {
        background-color: #DBEAFE !important;
        color: #000000 !important;
        border: 1px solid #93C5FD !important;
        border-radius: 20px !important;
        font-weight: 500 !important;
    }

    .stButton > button:hover {
        background-color: #BFDBFE !important;
        color: #000000 !important;
    }

    /* ============================================ */
    /* DARK/GRAY PILLS: WHITE TEXT                  */
    /* ============================================ */

    /* File uploader inner drop zone (dark gray) */
    [data-testid="stFileUploader"] section {
        background-color: #374151 !important;
        border-radius: 8px !important;
    }

    [data-testid="stFileUploader"] section * {
        color: #FFFFFF !important;
    }

    [data-testid="stFileUploader"] section p {
        color: #FFFFFF !important;
    }

    [data-testid="stFileUploader"] section small {
        color: #E5E7EB !important;
    }

    [data-testid="stFileUploader"] section span {
        color: #FFFFFF !important;
    }

    /* File uploader outer border - Blue */
    [data-testid="stFileUploader"] {
        background-color: #EFF6FF !important;
        border: 2px dashed #3B82F6 !important;
        border-radius: 12px !important;
        padding: 8px !important;
    }

    /* File uploader label - BLACK (outside pill) */
    [data-testid="stFileUploader"] label {
        color: #000000 !important;
        font-weight: 500 !important;
    }

    /* Uploaded file name badge (dark) - WHITE text */
    [data-testid="stFileUploader"] [data-testid="stMarkdownContainer"] {
        background-color: #1F2937 !important;
        border-radius: 6px !important;
        padding: 4px 8px !important;
    }

    [data-testid="stFileUploader"] [data-testid="stMarkdownContainer"] * {
        color: #FFFFFF !important;
    }

    /* ============================================ */
    /* METRIC CARDS: BLUE PILL, BLACK TEXT          */
    /* ============================================ */

    [data-testid="stMetric"] {
        background-color: #DBEAFE !important;
        border: 1px solid #93C5FD !important;
        border-radius: 12px !important;
        padding: 16px !important;
    }

    [data-testid="stMetricLabel"] {
        color: #000000 !important;
        font-weight: 600 !important;
    }

    [data-testid="stMetricValue"] {
        color: #000000 !important;
        font-weight: 700 !important;
    }

    [data-testid="stMetricDelta"] {
        color: #000000 !important;
    }

    [data-testid="stMetricDelta"] svg {
        fill: #000000 !important;
    }

    /* ============================================ */
    /* TABS: BLUE SELECTED, BLACK TEXT              */
    /* ============================================ */

    .stTabs [data-baseweb="tab-list"] {
        background-color: #EFF6FF !important;
        border-radius: 8px !important;
        padding: 4px !important;
    }

    .stTabs [data-baseweb="tab"] {
        color: #000000 !important;
        background-color: transparent !important;
    }

    .stTabs [aria-selected="true"] {
        background-color: #DBEAFE !important;
        color: #000000 !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
    }

    /* ============================================ */
    /* ALERTS: BLUE PILL, BLACK TEXT                */
    /* ============================================ */

    .stAlert, [data-testid="stAlert"] {
        background-color: #DBEAFE !important;
        border: 1px solid #93C5FD !important;
        border-radius: 8px !important;
    }

    .stAlert *, [data-testid="stAlert"] * {
        color: #000000 !important;
    }

    /* Success alert - green tint but still black text */
    .stSuccess, [data-testid="stAlertSuccess"] {
        background-color: #D1FAE5 !important;
        border: 1px solid #6EE7B7 !important;
    }

    .stSuccess *, [data-testid="stAlertSuccess"] * {
        color: #000000 !important;
    }

    /* Error alert */
    .stError, [data-testid="stAlertError"] {
        background-color: #FEE2E2 !important;
        border: 1px solid #FCA5A5 !important;
    }

    .stError *, [data-testid="stAlertError"] * {
        color: #000000 !important;
    }

    /* Warning alert */
    .stWarning, [data-testid="stAlertWarning"] {
        background-color: #FEF3C7 !important;
        border: 1px solid #FCD34D !important;
    }

    .stWarning *, [data-testid="stAlertWarning"] * {
        color: #000000 !important;
    }

    /* ============================================ */
    /* INPUTS: WHITE BG, BLACK TEXT                 */
    /* ============================================ */

    .stSelectbox label, .stTextInput label, .stDateInput label,
    .stNumberInput label, .stTextArea label {
        color: #000000 !important;
        font-weight: 500 !important;
    }

    .stSelectbox > div > div,
    .stTextInput > div > div,
    .stDateInput > div > div,
    .stNumberInput > div > div,
    .stTextArea > div > div {
        background-color: #FFFFFF !important;
        border: 1px solid #93C5FD !important;
        color: #000000 !important;
    }

    .stSelectbox span, .stTextInput input, .stDateInput input,
    .stNumberInput input, .stTextArea textarea {
        color: #000000 !important;
    }

    /* ============================================ */
    /* DATAFRAME: BLUE HEADER, BLACK TEXT           */
    /* ============================================ */

    [data-testid="stDataFrame"] {
        border: 1px solid #93C5FD !important;
        border-radius: 8px !important;
        overflow: hidden !important;
    }

    [data-testid="stDataFrame"] th {
        background-color: #DBEAFE !important;
        color: #000000 !important;
        font-weight: 600 !important;
    }

    [data-testid="stDataFrame"] td {
        color: #000000 !important;
        background-color: #FFFFFF !important;
    }

    [data-testid="stDataFrame"] * {
        color: #000000 !important;
    }

    /* ============================================ */
    /* TITLES: BLACK TEXT                           */
    /* ============================================ */

    h1, h2, h3, h4, h5, h6,
    .stTitle, .stHeader, .stSubheader,
    [data-testid="stHeader"] {
        color: #000000 !important;
    }

    /* ============================================ */
    /* SIDEBAR: LIGHT BG, BLACK TEXT                */
    /* ============================================ */

    [data-testid="stSidebar"] {
        background-color: #F8FAFC !important;
    }

    [data-testid="stSidebar"] * {
        color: #000000 !important;
    }

    [data-testid="stSidebar"] .stButton > button {
        background-color: #DBEAFE !important;
        color: #000000 !important;
    }

    /* ============================================ */
    /* CHARTS: BLACK TEXT                           */
    /* ============================================ */

    [data-testid="stVegaLiteChart"] text {
        fill: #000000 !important;
    }

    /* ============================================ */
    /* DIVIDER                                      */
    /* ============================================ */

    hr, [data-testid="stHorizontalBlock"] {
        border-color: #93C5FD !important;
    }

    /* ============================================ */
    /* DATE PICKER: ALL WHITE BG, ALL BLACK TEXT    */
    /* ============================================ */

    /* Date input field */
    [data-testid="stDateInput"] input {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border: 2px solid #3B82F6 !important;
        border-radius: 8px !important;
    }

    [data-testid="stDateInput"] > div > div {
        background-color: #FFFFFF !important;
        border: 2px solid #3B82F6 !important;
        border-radius: 8px !important;
    }

    [data-testid="stDateInput"] svg {
        fill: #000000 !important;
    }

    /* Calendar popup - WHITE background, BLACK text */
    [data-baseweb="calendar"] {
        background-color: #FFFFFF !important;
        border-radius: 8px !important;
    }

    [data-baseweb="calendar"] * {
        color: #000000 !important;
        background-color: transparent !important;
    }

    /* Month/Year header */
    [data-baseweb="calendar"] [data-baseweb="typo-labellarge"],
    [data-baseweb="calendar"] [data-baseweb="typo-labelmedium"],
    [data-baseweb="calendar"] button {
        color: #000000 !important;
        background-color: #FFFFFF !important;
    }

    /* Day names (Sun, Mon, Tue...) */
    [data-baseweb="calendar"] th {
        color: #000000 !important;
        background-color: #FFFFFF !important;
    }

    /* Calendar days */
    [data-baseweb="calendar"] td {
        color: #000000 !important;
        background-color: #FFFFFF !important;
    }

    [data-baseweb="calendar"] td div {
        color: #000000 !important;
    }

    /* Selected day - Blue background, WHITE text */
    [data-baseweb="calendar"] [aria-selected="true"] {
        background-color: #3B82F6 !important;
        color: #FFFFFF !important;
    }

    [data-baseweb="calendar"] [aria-selected="true"] div {
        color: #FFFFFF !important;
    }

    [data-baseweb="calendar"] [aria-selected="true"] * {
        color: #FFFFFF !important;
    }

    /* Hover state */
    [data-baseweb="calendar"] td:hover {
        background-color: #DBEAFE !important;
    }

    /* Navigation arrows */
    [data-baseweb="calendar"] svg {
        fill: #000000 !important;
        color: #000000 !important;
    }

    /* Popover containing calendar */
    [data-baseweb="popover"]:has([data-baseweb="calendar"]) {
        background-color: #FFFFFF !important;
        border: 2px solid #3B82F6 !important;
    }

    [data-baseweb="popover"]:has([data-baseweb="calendar"]) > div {
        background-color: #FFFFFF !important;
    }

    /* Month/Year dropdown in calendar */
    [data-baseweb="calendar"] [data-baseweb="select"] {
        background-color: #FFFFFF !important;
    }

    [data-baseweb="calendar"] [data-baseweb="select"] * {
        color: #000000 !important;
    }

    /* ============================================ */
    /* EXPANDER: BLUE HEADER, BLACK TEXT            */
    /* ============================================ */

    .streamlit-expanderHeader {
        background-color: #DBEAFE !important;
        color: #000000 !important;
        border-radius: 8px !important;
    }

    .streamlit-expanderContent {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border: 1px solid #93C5FD !important;
    }

    /* ============================================ */
    /* SELECTBOX / MULTISELECT DROPDOWNS            */
    /* WHITE BG, BLACK TEXT, BOLD BORDERS           */
    /* ============================================ */

    /* Main select container */
    [data-baseweb="select"] {
        background-color: #FFFFFF !important;
        border: 2px solid #3B82F6 !important;
        border-radius: 8px !important;
    }

    /* Selected value text */
    [data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #000000 !important;
    }

    [data-baseweb="select"] span {
        color: #000000 !important;
    }

    [data-baseweb="select"] input {
        color: #000000 !important;
        background-color: #FFFFFF !important;
    }

    /* Placeholder text */
    [data-baseweb="select"] [data-baseweb="tag"] {
        background-color: #DBEAFE !important;
        color: #000000 !important;
    }

    /* Dropdown arrow icon */
    [data-baseweb="select"] svg {
        fill: #000000 !important;
        color: #000000 !important;
    }

    /* Dropdown menu container */
    [data-baseweb="menu"] {
        background-color: #FFFFFF !important;
        border: 2px solid #3B82F6 !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
    }

    /* Dropdown menu list */
    [data-baseweb="menu"] ul {
        background-color: #FFFFFF !important;
    }

    /* Dropdown menu items */
    [data-baseweb="menu"] li {
        background-color: #FFFFFF !important;
        color: #000000 !important;
    }

    [data-baseweb="menu"] li span {
        color: #000000 !important;
    }

    [data-baseweb="menu"] li:hover {
        background-color: #DBEAFE !important;
        color: #000000 !important;
    }

    /* Selected/highlighted option */
    [data-baseweb="menu"] li[aria-selected="true"],
    [data-baseweb="menu"] li[data-highlighted="true"] {
        background-color: #DBEAFE !important;
        color: #000000 !important;
    }

    /* Listbox (another menu variant) */
    [role="listbox"] {
        background-color: #FFFFFF !important;
        border: 2px solid #3B82F6 !important;
    }

    [role="listbox"] [role="option"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
    }

    [role="listbox"] [role="option"]:hover {
        background-color: #DBEAFE !important;
    }

    [role="listbox"] [role="option"][aria-selected="true"] {
        background-color: #DBEAFE !important;
        color: #000000 !important;
        font-weight: 600 !important;
    }

    /* Popover that contains dropdowns */
    [data-baseweb="popover"] {
        background-color: #FFFFFF !important;
        border: 2px solid #3B82F6 !important;
        border-radius: 8px !important;
    }

    [data-baseweb="popover"] > div {
        background-color: #FFFFFF !important;
    }

    /* Ensure all text in popovers is black (except calendar which uses dark bg) */
    [data-baseweb="popover"]:not(:has([data-baseweb="calendar"])) * {
        color: #000000 !important;
    }

    /* Multiselect tags (selected items) */
    [data-baseweb="tag"] {
        background-color: #DBEAFE !important;
        color: #000000 !important;
        border: 1px solid #93C5FD !important;
    }

    [data-baseweb="tag"] span {
        color: #000000 !important;
    }

    /* Clear/remove button in tags */
    [data-baseweb="tag"] svg {
        fill: #000000 !important;
    }

    /* Streamlit specific selectbox overrides */
    .stSelectbox > div > div {
        background-color: #FFFFFF !important;
        border: 2px solid #3B82F6 !important;
        border-radius: 8px !important;
    }

    .stSelectbox > div > div > div {
        color: #000000 !important;
    }

    .stSelectbox [data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
    }

    /* Multiselect specific */
    .stMultiSelect > div > div {
        background-color: #FFFFFF !important;
        border: 2px solid #3B82F6 !important;
        border-radius: 8px !important;
    }

    .stMultiSelect [data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
    }

    /* Input text in select (for searchable dropdowns) */
    [data-baseweb="input"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
    }

    [data-baseweb="input"] input {
        background-color: #FFFFFF !important;
        color: #000000 !important;
    }

    [data-baseweb="base-input"] {
        background-color: #FFFFFF !important;
    }

    /* ============================================ */
    /* CHECKBOX / RADIO: BLACK TEXT                 */
    /* ============================================ */

    .stCheckbox label, .stRadio label {
        color: #000000 !important;
    }

    /* ============================================ */
    /* SPINNER: BLUE                                */
    /* ============================================ */

    .stSpinner > div {
        border-color: #3B82F6 !important;
    }

    </style>
    """, unsafe_allow_html=True)


def get_color_palette():
    """
    Return the standard color palette for programmatic use.
    """
    return {
        # Text colors
        'text_primary': '#000000',      # Black - for all normal text
        'text_on_dark': '#FFFFFF',      # White - for text on dark backgrounds

        # Blue palette (pills, borders, highlights)
        'blue_light': '#DBEAFE',        # Pill backgrounds, metric cards, tabs
        'blue_medium': '#93C5FD',       # Borders, dividers
        'blue_dark': '#3B82F6',         # Accents, links
        'blue_very_light': '#EFF6FF',   # Subtle backgrounds

        # Gray palette (dark pills)
        'gray_dark': '#374151',         # Dark pill backgrounds (WHITE text)
        'gray_darker': '#1F2937',       # File badges, dark elements (WHITE text)

        # Status colors (all use BLACK text)
        'status_success_bg': '#D1FAE5',
        'status_success_border': '#6EE7B7',
        'status_error_bg': '#FEE2E2',
        'status_error_border': '#FCA5A5',
        'status_warning_bg': '#FEF3C7',
        'status_warning_border': '#FCD34D',
        'status_info_bg': '#DBEAFE',
        'status_info_border': '#93C5FD',

        # Background
        'bg_white': '#FFFFFF',
        'bg_light': '#F8FAFC',
    }
