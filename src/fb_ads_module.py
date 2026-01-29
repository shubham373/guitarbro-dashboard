"""
Facebook Ads Analytics Module
Comprehensive analytics for Facebook/Meta advertising campaigns.
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import sqlite3
import os
import csv
from datetime import datetime, timedelta
from typing import Tuple, Optional, List, Dict
from ad_scaling_logic import get_ad_status

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================
FB_ADS_DB_PATH = "data/fb_ads.db"

# Column mapping for CSV to database
COLUMN_MAPPING = {
    "Reporting starts": "Reporting starts",
    "Reporting ends": "Reporting ends",
    "Ad name": "Ad name",
    "Ad delivery": "Ad delivery",
    "Amount spent (INR)": "Amount spent (INR)",
    "Purchase ROAS (return on ad spend)": "Purchase ROAS (return on ad spend)",
    "Purchases": "Purchases",
    "CTR (link click-through rate)": "CTR (link click-through rate)",
    "CPC (cost per link click) (INR)": "CPC (cost per link click) (INR)",
    "CPM (cost per 1,000 impressions) (INR)": "CPM (cost per 1,000 impressions) (INR)",
    "Hook rate": "Hook rate",
    "Hold Rate": "Hold Rate",
    "Impressions": "Impressions",
    "Reach": "Reach",
    "Frequency": "Frequency",
    "Adds to cart": "Adds to cart",
    "ATC Cost": "ATC Cost",
    "FTIR": "FTIR",
    "Link clicks": "Link clicks",
    "Landing page views": "Landing page views",
    "Click To LP Visit %": "Click To LP Visit %",
    "Checkouts initiated": "Checkouts initiated",
    "Cost per purchase (INR)": "Cost per purchase (INR)",
    "Purchases conversion value": "Purchases conversion value",
    "Engagement rate ranking": "Engagement rate ranking",
    "Engagement Ratio": "Engagement Ratio",
    "ATC to Purchase": "ATC to Purchase",
    "LP Conversion": "LP Conversion",
    "Campaign name": "Campaign name",
    "Ad set name": "Ad set name",
    "Video average play time": "Video average play time",
    "Percentage 25% Video": "Percentage 25% Video",
    "Percentage 50% Video": "Percentage 50% Video",
    "Percentage 75% Video": "Percentage 75% Video",
    "Percentage 95% Video": "Percentage 95% Video",
    "Percentage 100% Video": "Percentage 100% Video",
}


# =============================================================================
# SCALING LOGIC COLUMN MAPPER
# =============================================================================
_SCALING_COLUMN_MAP = {
    "Reporting starts": "Reporting_starts",
    "Amount spent (INR)": "Amount_spent_INR",
    "CPM (cost per 1,000 impressions) (INR)": "CPM_INR",
    "CPM (cost per 1,000 impressions)": "CPM_INR",          # handle variant without (INR)
    "Purchases conversion value": "Purchases_conversion_value",
    "Hook rate": "Hook_rate",
    "Hook Rate": "Hook_rate",                                # handle capital R variant
    "CTR (link click-through rate)": "CTR",
    "Purchases": "Purchases",
}


def map_columns_for_scaling(df: pd.DataFrame) -> pd.DataFrame:
    """Rename DB columns to the underscore format expected by ad_scaling_logic."""
    rename = {k: v for k, v in _SCALING_COLUMN_MAP.items() if k in df.columns}
    scaled = df.rename(columns=rename)
    for col in _SCALING_COLUMN_MAP.values():
        if col not in scaled.columns:
            scaled[col] = 0
    return scaled


# =============================================================================
# AD COMMENTS (CSV-based)
# =============================================================================
AD_COMMENTS_PATH = "data/ad_comments.csv"
_COMMENTS_COLUMNS = ["ad_name", "comment", "date", "time"]


def _ensure_comments_file() -> None:
    """Create the CSV with headers if it doesn't exist."""
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(AD_COMMENTS_PATH):
        with open(AD_COMMENTS_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_COMMENTS_COLUMNS)


def add_comment(ad_name: str, comment: str) -> None:
    """Append a comment row to the CSV."""
    _ensure_comments_file()
    now = datetime.now()
    with open(AD_COMMENTS_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([ad_name, comment, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")])


def get_comments_for_ad(ad_name: str) -> pd.DataFrame:
    """Return comments for a specific ad, most-recent first."""
    _ensure_comments_file()
    df = pd.read_csv(AD_COMMENTS_PATH, encoding="utf-8")
    df = df[df["ad_name"] == ad_name].sort_values(
        by=["date", "time"], ascending=False
    ).reset_index(drop=True)
    return df


def get_all_comments() -> pd.DataFrame:
    """Return every comment across all ads."""
    _ensure_comments_file()
    return pd.read_csv(AD_COMMENTS_PATH, encoding="utf-8")


def delete_comment(ad_name: str, date: str, time: str, comment: str) -> None:
    """Delete the first row that matches all four fields."""
    _ensure_comments_file()
    df = pd.read_csv(AD_COMMENTS_PATH, encoding="utf-8")
    mask = (
        (df["ad_name"] == ad_name)
        & (df["date"] == date)
        & (df["time"] == time)
        & (df["comment"] == comment)
    )
    idx = df[mask].index
    if len(idx) > 0:
        df = df.drop(idx[0])
    df.to_csv(AD_COMMENTS_PATH, index=False, encoding="utf-8")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def get_db_connection() -> sqlite3.Connection:
    """Get a connection to the FB Ads database."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(FB_ADS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_fb_ads_db() -> None:
    """Initialize the FB Ads database and create table if not exists."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fb_ads_data (
            [Reporting starts] TEXT,
            [Reporting ends] TEXT,
            [Ad name] TEXT,
            [Ad delivery] TEXT,
            [Amount spent (INR)] REAL,
            [Purchase ROAS (return on ad spend)] REAL,
            [Purchases] REAL,
            [CTR (link click-through rate)] REAL,
            [CPC (cost per link click) (INR)] REAL,
            [CPM (cost per 1,000 impressions) (INR)] REAL,
            [Hook rate] REAL,
            [Hold Rate] REAL,
            [Impressions] INTEGER,
            [Reach] INTEGER,
            [Frequency] REAL,
            [Adds to cart] REAL,
            [ATC Cost] REAL,
            [FTIR] REAL,
            [Link clicks] INTEGER,
            [Landing page views] INTEGER,
            [Click To LP Visit %] REAL,
            [Checkouts initiated] REAL,
            [Cost per purchase (INR)] REAL,
            [Purchases conversion value] REAL,
            [Engagement rate ranking] TEXT,
            [Engagement Ratio] REAL,
            [ATC to Purchase] REAL,
            [LP Conversion] REAL,
            [Campaign name] TEXT,
            [Ad set name] TEXT,
            [Video average play time] INTEGER,
            [Percentage 25% Video] REAL,
            [Percentage 50% Video] REAL,
            [Percentage 75% Video] REAL,
            [Percentage 95% Video] REAL,
            [Percentage 100% Video] REAL,
            [composite_key] TEXT UNIQUE
        )
    """)

    conn.commit()
    conn.close()


def calculate_ad_score(ctr: float, hook_rate: float, cpm: float) -> Tuple[int, str]:
    """
    Calculate Ad Score (max 12 points) based on CTR, Hook Rate, and CPM.

    Returns:
        Tuple of (score, recommendation)
    """
    # Handle None/NaN values
    if pd.isna(ctr) or ctr is None:
        ctr = 0
    if pd.isna(hook_rate) or hook_rate is None:
        hook_rate = 0
    if pd.isna(cpm) or cpm is None:
        cpm = 999  # High CPM = low score

    # CTR Scoring (CTR is already a percentage value, e.g., 0.93 means 0.93%)
    if ctr >= 1.00:
        ctr_score = 4
    elif ctr >= 0.85:
        ctr_score = 3
    elif ctr >= 0.70:
        ctr_score = 2
    else:
        ctr_score = 1

    # Hook Rate Scoring (Hook rate is decimal, e.g., 0.18 means 18%)
    if hook_rate >= 0.30:
        hook_score = 4
    elif hook_rate >= 0.20:
        hook_score = 3
    elif hook_rate >= 0.15:
        hook_score = 2
    else:
        hook_score = 1

    # CPM Scoring (CPM in INR)
    if cpm <= 100:
        cpm_score = 4
    elif cpm <= 150:
        cpm_score = 3
    elif cpm <= 200:
        cpm_score = 2
    else:
        cpm_score = 1

    # Total Ad Score
    ad_score = ctr_score + hook_score + cpm_score

    # Recommendation
    if ad_score >= 10:
        recommendation = "🟢 Scale"
    elif ad_score >= 8:
        recommendation = "🔵 Test"
    elif ad_score >= 6:
        recommendation = "🟡 Rework"
    else:
        recommendation = "🔴 Kill"

    return ad_score, recommendation


def get_trend_arrow(current: float, previous: float) -> str:
    """Get colored trend arrow based on percentage change."""
    if previous == 0 or pd.isna(previous):
        return "→"

    pct_change = ((current - previous) / abs(previous)) * 100

    if pct_change > 5:
        return "↑"
    elif pct_change < -5:
        return "↓"
    else:
        return "→"


def get_trend_with_color(current: float, previous: float, higher_is_better: bool = True) -> str:
    """Get trend arrow with appropriate color HTML."""
    if previous == 0 or pd.isna(previous):
        return '<span style="color: #6B7280;">→</span>'

    pct_change = ((current - previous) / abs(previous)) * 100

    if pct_change > 5:
        color = "#10B981" if higher_is_better else "#EF4444"
        return f'<span style="color: {color};">↑ {abs(pct_change):.1f}%</span>'
    elif pct_change < -5:
        color = "#EF4444" if higher_is_better else "#10B981"
        return f'<span style="color: {color};">↓ {abs(pct_change):.1f}%</span>'
    else:
        return '<span style="color: #6B7280;">→ 0%</span>'


def calculate_true_roas(df: pd.DataFrame) -> float:
    """
    Calculate ROAS correctly as Total Conversion Value / Total Spend.
    NOT as average or weighted average of daily ROAS values.
    """
    if df.empty:
        return 0.0
    total_conversion = pd.to_numeric(df["Purchases conversion value"], errors="coerce").fillna(0).sum()
    total_spend = pd.to_numeric(df["Amount spent (INR)"], errors="coerce").fillna(0).sum()
    if total_spend == 0:
        return 0.0
    return total_conversion / total_spend


def calculate_rolling_roas(df: pd.DataFrame, days: int) -> list:
    """
    Calculate X-day rolling ROAS.
    Formula: Sum(Conversion Value for last X days) / Sum(Spend for last X days)
    Returns None if insufficient data.
    """
    spend_col = pd.to_numeric(df["Amount spent (INR)"], errors="coerce").fillna(0).values
    conv_col = pd.to_numeric(df["Purchases conversion value"], errors="coerce").fillna(0).values

    rolling_roas = []
    for i in range(len(df)):
        if i < days - 1:
            rolling_roas.append(None)
        else:
            total_spend = spend_col[i - days + 1: i + 1].sum()
            total_conv = conv_col[i - days + 1: i + 1].sum()
            rolling_roas.append(total_conv / total_spend if total_spend > 0 else 0.0)
    return rolling_roas


def calculate_last_spend_roas(df: pd.DataFrame, threshold: float = 5000) -> list:
    """
    Calculate ROAS for the last X rupees of spend.
    Goes backward from each row until cumulative spend reaches threshold.
    Returns None if cumulative spend hasn't reached threshold yet.
    """
    spend_col = pd.to_numeric(df["Amount spent (INR)"], errors="coerce").fillna(0).values
    conv_col = pd.to_numeric(df["Purchases conversion value"], errors="coerce").fillna(0).values

    last_spend_roas = []
    for i in range(len(df)):
        cumulative_spend = spend_col[: i + 1].sum()
        if cumulative_spend < threshold:
            last_spend_roas.append(None)
        else:
            window_spend = 0.0
            window_conv = 0.0
            for j in range(i, -1, -1):
                window_spend += spend_col[j]
                window_conv += conv_col[j]
                if window_spend >= threshold:
                    break
            last_spend_roas.append(window_conv / window_spend if window_spend > 0 else 0.0)
    return last_spend_roas


def format_currency(value: float) -> str:
    """Format value as Indian Rupee currency."""
    if pd.isna(value) or value is None:
        return "₹0"
    return f"₹{value:,.2f}"


def get_weighted_average(df: pd.DataFrame, value_col: str, weight_col: str) -> float:
    """Calculate weighted average of a column."""
    if df.empty:
        return 0.0

    df_clean = df[[value_col, weight_col]].dropna()
    if df_clean.empty or df_clean[weight_col].sum() == 0:
        return 0.0

    return (df_clean[value_col] * df_clean[weight_col]).sum() / df_clean[weight_col].sum()


# =============================================================================
# DATA UPLOAD & MANAGEMENT
# =============================================================================
def upload_fb_ads_data(df: pd.DataFrame) -> Tuple[int, int, int]:
    """
    Upload FB Ads data to database with UPSERT logic.

    Returns:
        Tuple of (new_count, updated_count, unchanged_count)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    new_count = 0
    updated_count = 0
    unchanged_count = 0

    for _, row in df.iterrows():
        # Generate composite key
        ad_name = str(row.get("Ad name", ""))
        campaign_name = str(row.get("Campaign name", ""))
        ad_set_name = str(row.get("Ad set name", ""))
        reporting_starts = str(row.get("Reporting starts", ""))

        composite_key = f"{ad_name}||{campaign_name}||{ad_set_name}||{reporting_starts}"

        # Check if row already exists
        cursor.execute("SELECT 1 FROM fb_ads_data WHERE composite_key = ?", (composite_key,))
        exists = cursor.fetchone() is not None

        # Prepare values for insertion
        values = {
            "Reporting starts": row.get("Reporting starts"),
            "Reporting ends": row.get("Reporting ends"),
            "Ad name": row.get("Ad name"),
            "Ad delivery": row.get("Ad delivery"),
            "Amount spent (INR)": pd.to_numeric(row.get("Amount spent (INR)"), errors="coerce"),
            "Purchase ROAS (return on ad spend)": pd.to_numeric(row.get("Purchase ROAS (return on ad spend)"), errors="coerce"),
            "Purchases": pd.to_numeric(row.get("Purchases"), errors="coerce"),
            "CTR (link click-through rate)": pd.to_numeric(row.get("CTR (link click-through rate)"), errors="coerce"),
            "CPC (cost per link click) (INR)": pd.to_numeric(row.get("CPC (cost per link click) (INR)"), errors="coerce"),
            "CPM (cost per 1,000 impressions) (INR)": pd.to_numeric(row.get("CPM (cost per 1,000 impressions) (INR)"), errors="coerce"),
            "Hook rate": pd.to_numeric(row.get("Hook rate"), errors="coerce"),
            "Hold Rate": pd.to_numeric(row.get("Hold Rate"), errors="coerce"),
            "Impressions": pd.to_numeric(row.get("Impressions"), errors="coerce"),
            "Reach": pd.to_numeric(row.get("Reach"), errors="coerce"),
            "Frequency": pd.to_numeric(row.get("Frequency"), errors="coerce"),
            "Adds to cart": pd.to_numeric(row.get("Adds to cart"), errors="coerce"),
            "ATC Cost": pd.to_numeric(row.get("ATC Cost"), errors="coerce"),
            "FTIR": pd.to_numeric(row.get("FTIR"), errors="coerce"),
            "Link clicks": pd.to_numeric(row.get("Link clicks"), errors="coerce"),
            "Landing page views": pd.to_numeric(row.get("Landing page views"), errors="coerce"),
            "Click To LP Visit %": pd.to_numeric(row.get("Click To LP Visit %"), errors="coerce"),
            "Checkouts initiated": pd.to_numeric(row.get("Checkouts initiated"), errors="coerce"),
            "Cost per purchase (INR)": pd.to_numeric(row.get("Cost per purchase (INR)"), errors="coerce"),
            "Purchases conversion value": pd.to_numeric(row.get("Purchases conversion value"), errors="coerce"),
            "Engagement rate ranking": row.get("Engagement rate ranking"),
            "Engagement Ratio": pd.to_numeric(row.get("Engagement Ratio"), errors="coerce"),
            "ATC to Purchase": pd.to_numeric(row.get("ATC to Purchase"), errors="coerce"),
            "LP Conversion": pd.to_numeric(row.get("LP Conversion"), errors="coerce"),
            "Campaign name": row.get("Campaign name"),
            "Ad set name": row.get("Ad set name"),
            "Video average play time": pd.to_numeric(row.get("Video average play time"), errors="coerce"),
            "Percentage 25% Video": pd.to_numeric(row.get("Percentage 25% Video"), errors="coerce"),
            "Percentage 50% Video": pd.to_numeric(row.get("Percentage 50% Video"), errors="coerce"),
            "Percentage 75% Video": pd.to_numeric(row.get("Percentage 75% Video"), errors="coerce"),
            "Percentage 95% Video": pd.to_numeric(row.get("Percentage 95% Video"), errors="coerce"),
            "Percentage 100% Video": pd.to_numeric(row.get("Percentage 100% Video"), errors="coerce"),
            "composite_key": composite_key,
        }

        # Convert NaN to None for SQLite
        for key in values:
            if pd.isna(values[key]):
                values[key] = None

        try:
            cursor.execute("""
                INSERT INTO fb_ads_data (
                    [Reporting starts], [Reporting ends], [Ad name], [Ad delivery],
                    [Amount spent (INR)], [Purchase ROAS (return on ad spend)], [Purchases],
                    [CTR (link click-through rate)], [CPC (cost per link click) (INR)],
                    [CPM (cost per 1,000 impressions) (INR)], [Hook rate], [Hold Rate],
                    [Impressions], [Reach], [Frequency], [Adds to cart], [ATC Cost], [FTIR],
                    [Link clicks], [Landing page views], [Click To LP Visit %],
                    [Checkouts initiated], [Cost per purchase (INR)], [Purchases conversion value],
                    [Engagement rate ranking], [Engagement Ratio], [ATC to Purchase], [LP Conversion],
                    [Campaign name], [Ad set name], [Video average play time],
                    [Percentage 25% Video], [Percentage 50% Video], [Percentage 75% Video],
                    [Percentage 95% Video], [Percentage 100% Video], [composite_key]
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(composite_key) DO UPDATE SET
                    [Reporting ends] = excluded.[Reporting ends],
                    [Ad delivery] = excluded.[Ad delivery],
                    [Amount spent (INR)] = excluded.[Amount spent (INR)],
                    [Purchase ROAS (return on ad spend)] = excluded.[Purchase ROAS (return on ad spend)],
                    [Purchases] = excluded.[Purchases],
                    [CTR (link click-through rate)] = excluded.[CTR (link click-through rate)],
                    [CPC (cost per link click) (INR)] = excluded.[CPC (cost per link click) (INR)],
                    [CPM (cost per 1,000 impressions) (INR)] = excluded.[CPM (cost per 1,000 impressions) (INR)],
                    [Hook rate] = excluded.[Hook rate],
                    [Hold Rate] = excluded.[Hold Rate],
                    [Impressions] = excluded.[Impressions],
                    [Reach] = excluded.[Reach],
                    [Frequency] = excluded.[Frequency],
                    [Adds to cart] = excluded.[Adds to cart],
                    [ATC Cost] = excluded.[ATC Cost],
                    [FTIR] = excluded.[FTIR],
                    [Link clicks] = excluded.[Link clicks],
                    [Landing page views] = excluded.[Landing page views],
                    [Click To LP Visit %] = excluded.[Click To LP Visit %],
                    [Checkouts initiated] = excluded.[Checkouts initiated],
                    [Cost per purchase (INR)] = excluded.[Cost per purchase (INR)],
                    [Purchases conversion value] = excluded.[Purchases conversion value],
                    [Engagement rate ranking] = excluded.[Engagement rate ranking],
                    [Engagement Ratio] = excluded.[Engagement Ratio],
                    [ATC to Purchase] = excluded.[ATC to Purchase],
                    [LP Conversion] = excluded.[LP Conversion],
                    [Video average play time] = excluded.[Video average play time],
                    [Percentage 25% Video] = excluded.[Percentage 25% Video],
                    [Percentage 50% Video] = excluded.[Percentage 50% Video],
                    [Percentage 75% Video] = excluded.[Percentage 75% Video],
                    [Percentage 95% Video] = excluded.[Percentage 95% Video],
                    [Percentage 100% Video] = excluded.[Percentage 100% Video]
            """, (
                values["Reporting starts"], values["Reporting ends"], values["Ad name"], values["Ad delivery"],
                values["Amount spent (INR)"], values["Purchase ROAS (return on ad spend)"], values["Purchases"],
                values["CTR (link click-through rate)"], values["CPC (cost per link click) (INR)"],
                values["CPM (cost per 1,000 impressions) (INR)"], values["Hook rate"], values["Hold Rate"],
                values["Impressions"], values["Reach"], values["Frequency"], values["Adds to cart"],
                values["ATC Cost"], values["FTIR"], values["Link clicks"], values["Landing page views"],
                values["Click To LP Visit %"], values["Checkouts initiated"], values["Cost per purchase (INR)"],
                values["Purchases conversion value"], values["Engagement rate ranking"], values["Engagement Ratio"],
                values["ATC to Purchase"], values["LP Conversion"], values["Campaign name"], values["Ad set name"],
                values["Video average play time"], values["Percentage 25% Video"], values["Percentage 50% Video"],
                values["Percentage 75% Video"], values["Percentage 95% Video"], values["Percentage 100% Video"],
                values["composite_key"]
            ))

            if exists:
                if cursor.rowcount > 0:
                    updated_count += 1
                else:
                    unchanged_count += 1
            else:
                new_count += 1

        except sqlite3.IntegrityError:
            unchanged_count += 1

    conn.commit()
    conn.close()

    return new_count, updated_count, unchanged_count


def load_fb_ads_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    campaigns: Optional[list] = None,
    ad_sets: Optional[list] = None
) -> pd.DataFrame:
    """Load FB Ads data with optional filters."""
    conn = get_db_connection()

    query = "SELECT * FROM fb_ads_data WHERE 1=1"
    params = []

    if start_date:
        query += " AND [Reporting starts] >= ?"
        params.append(start_date)

    if end_date:
        query += " AND [Reporting starts] <= ?"
        params.append(end_date)

    if campaigns and len(campaigns) > 0:
        placeholders = ",".join(["?" for _ in campaigns])
        query += f" AND [Campaign name] IN ({placeholders})"
        params.extend(campaigns)

    if ad_sets and len(ad_sets) > 0:
        placeholders = ",".join(["?" for _ in ad_sets])
        query += f" AND [Ad set name] IN ({placeholders})"
        params.extend(ad_sets)

    query += " ORDER BY [Reporting starts] DESC"

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    return df


def get_unique_campaigns() -> list:
    """Get list of unique campaign names."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT [Campaign name] FROM fb_ads_data WHERE [Campaign name] IS NOT NULL ORDER BY [Campaign name]")
    campaigns = [row[0] for row in cursor.fetchall()]
    conn.close()
    return campaigns


def get_unique_ad_sets(campaigns: Optional[list] = None) -> list:
    """Get list of unique ad set names, optionally filtered by campaigns."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if campaigns and len(campaigns) > 0:
        placeholders = ",".join(["?" for _ in campaigns])
        query = f"SELECT DISTINCT [Ad set name] FROM fb_ads_data WHERE [Campaign name] IN ({placeholders}) AND [Ad set name] IS NOT NULL ORDER BY [Ad set name]"
        cursor.execute(query, campaigns)
    else:
        cursor.execute("SELECT DISTINCT [Ad set name] FROM fb_ads_data WHERE [Ad set name] IS NOT NULL ORDER BY [Ad set name]")

    ad_sets = [row[0] for row in cursor.fetchall()]
    conn.close()
    return ad_sets


def get_ad_history(ad_name: str) -> pd.DataFrame:
    """Get full history for a specific ad."""
    conn = get_db_connection()
    query = "SELECT * FROM fb_ads_data WHERE [Ad name] = ? ORDER BY [Reporting starts] ASC"
    df = pd.read_sql_query(query, conn, params=[ad_name])
    conn.close()
    return df


def get_date_range() -> Tuple[Optional[str], Optional[str]]:
    """Get min and max dates in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MIN([Reporting starts]), MAX([Reporting starts]) FROM fb_ads_data")
    result = cursor.fetchone()
    conn.close()

    if result and result[0] and result[1]:
        return result[0], result[1]
    return None, None


# =============================================================================
# UI COMPONENTS
# =============================================================================
def render_metric_card_with_trend(value: str, label: str, trend_html: str, is_blue: bool = False):
    """Render a metric card with trend indicator."""
    value_color = "#528FF0" if is_blue else "#1A1A1A"

    st.markdown(f"""
    <div style="background-color: #FFFFFF; border-radius: 12px; padding: 24px;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08); border: 1px solid #E5E7EB; margin-bottom: 16px;">
        <p style="font-size: 32px; font-weight: 700; color: {value_color}; margin: 0; line-height: 1.2;">{value}</p>
        <p style="font-size: 14px; color: #6B7280; margin-top: 8px; font-weight: 500;">{label}</p>
        <p style="font-size: 12px; margin-top: 4px;">{trend_html}</p>
    </div>
    """, unsafe_allow_html=True)


def render_section_header(title: str):
    """Render a section header."""
    st.markdown(f'<p style="font-size: 18px; font-weight: 600; color: #1A1A1A; margin: 24px 0 16px 0;">{title}</p>', unsafe_allow_html=True)


def get_score_color(score: int) -> str:
    """Get background color based on ad score."""
    if score >= 10:
        return "#D1FAE5"  # Light green
    elif score >= 8:
        return "#DBEAFE"  # Light blue
    elif score >= 6:
        return "#FEF3C7"  # Light yellow
    else:
        return "#FEE2E2"  # Light red


# =============================================================================
# SUMMARY VIEW
# =============================================================================
def render_summary_view(start_date: str, end_date: str, campaigns: list, ad_sets: list):
    """Render the summary view with filters and ad table."""

    # Load current period data
    df_current = load_fb_ads_data(start_date, end_date, campaigns if campaigns else None, ad_sets if ad_sets else None)

    # Calculate previous period
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    period_days = (end_dt - start_dt).days + 1

    prev_end_dt = start_dt - timedelta(days=1)
    prev_start_dt = prev_end_dt - timedelta(days=period_days - 1)

    prev_start_date = prev_start_dt.strftime("%Y-%m-%d")
    prev_end_date = prev_end_dt.strftime("%Y-%m-%d")

    # Load previous period data
    df_previous = load_fb_ads_data(prev_start_date, prev_end_date, campaigns if campaigns else None, ad_sets if ad_sets else None)

    # Filter for ads with spend > 0
    df_current_spend = df_current[df_current["Amount spent (INR)"].fillna(0) > 0]
    df_previous_spend = df_previous[df_previous["Amount spent (INR)"].fillna(0) > 0]

    # Calculate metrics for current period
    total_ads_current = df_current_spend["Ad name"].nunique() if not df_current_spend.empty else 0
    total_spend_current = df_current_spend["Amount spent (INR)"].sum() if not df_current_spend.empty else 0
    total_purchases_current = df_current_spend["Purchases"].sum() if not df_current_spend.empty else 0
    avg_roas_current = calculate_true_roas(df_current_spend)

    # Calculate metrics for previous period
    total_ads_previous = df_previous_spend["Ad name"].nunique() if not df_previous_spend.empty else 0
    total_spend_previous = df_previous_spend["Amount spent (INR)"].sum() if not df_previous_spend.empty else 0
    total_purchases_previous = df_previous_spend["Purchases"].sum() if not df_previous_spend.empty else 0
    avg_roas_previous = calculate_true_roas(df_previous_spend)

    # Render metric cards
    render_section_header("Performance Overview")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        trend_html = get_trend_with_color(total_ads_current, total_ads_previous, higher_is_better=True)
        render_metric_card_with_trend(f"{total_ads_current:,}", "Total Ads Live", f"vs prev period: {trend_html}", is_blue=True)

    with col2:
        trend_html = get_trend_with_color(total_spend_current, total_spend_previous, higher_is_better=True)
        render_metric_card_with_trend(f"₹{total_spend_current:,.0f}", "Total Spend", f"vs prev period: {trend_html}")

    with col3:
        trend_html = get_trend_with_color(total_purchases_current, total_purchases_previous, higher_is_better=True)
        render_metric_card_with_trend(f"{total_purchases_current:,.0f}", "Total Purchases", f"vs prev period: {trend_html}")

    with col4:
        trend_html = get_trend_with_color(avg_roas_current, avg_roas_previous, higher_is_better=True)
        render_metric_card_with_trend(f"{avg_roas_current:.2f}", "Avg ROAS", f"vs prev period: {trend_html}")

    # Build summary table
    if df_current_spend.empty:
        st.info("No ads with spend > 0 found for the selected period.")
        return

    render_section_header("Ad Performance")

    # Group by ad name and calculate aggregates
    ad_summary = []

    for ad_name in df_current_spend["Ad name"].unique():
        ad_data = df_current_spend[df_current_spend["Ad name"] == ad_name]

        # --- Date-range metrics ---
        period_spend = ad_data["Amount spent (INR)"].sum()
        period_purchases = ad_data["Purchases"].sum()
        period_roas = calculate_true_roas(ad_data)

        # --- Overall metrics (full history, all dates) ---
        ad_full = get_ad_history(ad_name)
        overall_spend = pd.to_numeric(ad_full["Amount spent (INR)"], errors="coerce").fillna(0).sum()
        overall_purchases = pd.to_numeric(ad_full["Purchases"], errors="coerce").fillna(0).sum()
        overall_conversion = pd.to_numeric(ad_full["Purchases conversion value"], errors="coerce").fillna(0).sum()
        overall_roas = overall_conversion / overall_spend if overall_spend > 0 else 0.0

        # Last ₹5000 ROAS (from full history, sorted by date asc)
        ad_full_sorted = ad_full.sort_values("Reporting starts").reset_index(drop=True)
        last5k_list = calculate_last_spend_roas(ad_full_sorted, 5000)
        last5k_roas = last5k_list[-1] if last5k_list and last5k_list[-1] is not None else None

        # Overall Stop Loss = (total purchases * 1200) - total spend
        overall_stop_loss = (overall_purchases * 1200) - overall_spend

        # Scaling status
        try:
            scaled_df = map_columns_for_scaling(ad_full_sorted)
            phase, status, reason = get_ad_status(scaled_df)
        except Exception:
            phase, status, reason = ("N/A", "N/A", "")

        ad_summary.append({
            "Ad Name": ad_name,
            "Overall Spend": overall_spend,
            "Overall Purchases": overall_purchases,
            "Overall ROAS": overall_roas,
            "Last 5K ROAS": last5k_roas,
            "Stop Loss": overall_stop_loss,
            "Phase": phase,
            "Status": status,
            "Reason": reason,
        })

    summary_df = pd.DataFrame(ad_summary)
    summary_df = summary_df.sort_values("Overall Spend", ascending=False).reset_index(drop=True)

    # Ad selector dropdown
    ad_names = summary_df["Ad Name"].tolist()
    selected_ad = st.selectbox(
        "Select an ad to view details",
        options=[""] + ad_names,
        format_func=lambda x: "-- Select an Ad --" if x == "" else x,
        key="ad_selector"
    )

    if selected_ad and selected_ad != "":
        st.session_state.selected_ad_name = selected_ad
        st.rerun()

    # Build HTML table via components.html (page scroll, no horizontal scroll)
    def fmt_spend(v):
        return f"₹{v / 1000:.1f}K" if v >= 1000 else f"₹{v:.0f}"

    summary_rows = ""
    for _, r in summary_df.iterrows():
        ad_display = str(r["Ad Name"]).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Last 5K ROAS
        l5k = r["Last 5K ROAS"]
        l5k_str = f'{l5k:.2f}' if l5k is not None else '<span style="color:#6B7280;font-style:italic;">N/A</span>'

        # Stop Loss color
        sl = r["Stop Loss"]
        if sl > 0:
            sl_str = f'+₹{sl:,.0f}'
            sl_color = "#10B981"
        elif sl >= -2000:
            sl_str = f'-₹{abs(sl):,.0f}' if sl < 0 else '₹0'
            sl_color = "#F59E0B"
        else:
            sl_str = f'-₹{abs(sl):,.0f}'
            sl_color = "#EF4444"

        # Phase & Status
        phase_display = str(r.get("Phase", "N/A")).replace("&", "&amp;")
        status_raw = str(r.get("Status", "N/A"))
        if "CONTINUE" in status_raw:
            status_color = "#10B981"
        elif "MONITOR" in status_raw:
            status_color = "#F59E0B"
        elif "LAST CHANCE" in status_raw:
            status_color = "#F97316"
        elif "KILL" in status_raw:
            status_color = "#EF4444"
        else:
            status_color = "#6B7280"
        status_display = status_raw.replace("&", "&amp;")

        # Reason
        reason_display = str(r.get("Reason", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        summary_rows += (
            f'<tr>'
            f'<td>{ad_display}</td>'
            f'<td>{fmt_spend(r["Overall Spend"])}</td>'
            f'<td>{r["Overall Purchases"]:.0f}</td>'
            f'<td>{r["Overall ROAS"]:.2f}</td>'
            f'<td>{l5k_str}</td>'
            f'<td style="color:{sl_color};font-weight:700;">{sl_str}</td>'
            f'<td>{phase_display}</td>'
            f'<td style="color:{status_color};font-weight:700;">{status_display}</td>'
            f'<td>{reason_display}</td>'
            f'</tr>'
        )

    summary_table_html = f"""
<style>
  /* Container */
  .table-container {{
      max-height:70vh; overflow-y:auto; overflow-x:auto;
      border-radius:8px; border:1px solid #374151;
  }}
  /* Dark-theme scrollbar */
  .table-container::-webkit-scrollbar {{ width:8px; height:8px; }}
  .table-container::-webkit-scrollbar-track {{ background:#111827; border-radius:4px; }}
  .table-container::-webkit-scrollbar-thumb {{ background:#4B5563; border-radius:4px; }}
  .table-container::-webkit-scrollbar-thumb:hover {{ background:#6B7280; }}
  .table-container {{ scrollbar-color:#4B5563 #111827; scrollbar-width:thin; }}

  /* Table */
  .ad-table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
  .ad-table thead {{ position:sticky; top:0; z-index:10; }}
  .ad-table thead th {{
      background:#1F2937; color:#FFFFFF; padding:12px 8px; text-align:left;
      font-size:11px; font-weight:600; white-space:nowrap;
      border-bottom:2px solid #528FF0;
      box-shadow:0 2px 4px rgba(0,0,0,0.3);
  }}
  .ad-table tbody td {{
      padding:12px 8px; border-bottom:1px solid #374151; color:#FFFFFF;
      font-size:12px; vertical-align:middle; line-height:1.4;
  }}
  .ad-table tbody tr {{ background:#111827; }}
  .ad-table tbody tr:nth-child(even) {{ background:#1F2937; }}
  /* Ad Name & Reason: allow text wrap */
  .ad-table td:nth-child(1), .ad-table td:nth-child(9) {{ white-space:normal; word-break:break-word; }}
  /* Other columns: single-line */
  .ad-table td:nth-child(2), .ad-table td:nth-child(3), .ad-table td:nth-child(4),
  .ad-table td:nth-child(5), .ad-table td:nth-child(6), .ad-table td:nth-child(7),
  .ad-table td:nth-child(8) {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  /* Column widths — 9 columns */
  .ad-table th:nth-child(1), .ad-table td:nth-child(1) {{ width:14%; }}
  .ad-table th:nth-child(2), .ad-table td:nth-child(2) {{ width:7%; }}
  .ad-table th:nth-child(3), .ad-table td:nth-child(3) {{ width:6%; }}
  .ad-table th:nth-child(4), .ad-table td:nth-child(4) {{ width:6%; }}
  .ad-table th:nth-child(5), .ad-table td:nth-child(5) {{ width:7%; }}
  .ad-table th:nth-child(6), .ad-table td:nth-child(6) {{ width:8%; }}
  .ad-table th:nth-child(7), .ad-table td:nth-child(7) {{ width:9%; }}
  .ad-table th:nth-child(8), .ad-table td:nth-child(8) {{ width:13%; }}
  .ad-table th:nth-child(9), .ad-table td:nth-child(9) {{ width:30%; }}
</style>
<div class="table-container">
<table class="ad-table">
<thead><tr>
  <th>Ad Name</th><th>Spend</th><th>Purch</th><th>ROAS</th>
  <th>L₹5K ROAS</th><th>Stop Loss</th><th>Phase</th><th>Status</th><th>Reason</th>
</tr></thead>
<tbody>{summary_rows}</tbody>
</table>
</div>"""

    st.markdown(summary_table_html, unsafe_allow_html=True)

    # Export all comments button
    all_comments = get_all_comments()
    if not all_comments.empty:
        csv_data = all_comments.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export All Comments",
            data=csv_data,
            file_name="ad_comments_export.csv",
            mime="text/csv",
            key="export_comments_btn",
        )


# =============================================================================
# DETAIL VIEW
# =============================================================================
def render_detail_view(ad_name: str):
    """Render detailed view for a specific ad."""

    # Back button
    if st.button("← Back to Summary", key="back_to_summary"):
        st.session_state.selected_ad_name = None
        st.rerun()

    # Get full ad history
    df = get_ad_history(ad_name)

    if df.empty:
        st.warning("No data found for this ad.")
        return

    # Ad summary card at top
    total_spend = pd.to_numeric(df["Amount spent (INR)"], errors="coerce").fillna(0).sum()
    total_purchases = pd.to_numeric(df["Purchases"], errors="coerce").fillna(0).sum()
    total_conversion = pd.to_numeric(df["Purchases conversion value"], errors="coerce").fillna(0).sum()
    true_roas = total_conversion / total_spend if total_spend > 0 else 0

    # Stop Loss = (Purchases x 1200) - Spend
    stop_loss = (total_purchases * 1200) - total_spend

    if stop_loss > 0:
        sl_color = "#10B981"
        sl_display = f"+₹{abs(stop_loss):,.0f}"
    elif stop_loss == 0:
        sl_color = "#F59E0B"
        sl_display = "₹0"
    elif stop_loss >= -2000:
        sl_color = "#F59E0B"
        sl_display = f"-₹{abs(stop_loss):,.0f}"
    else:
        sl_color = "#EF4444"
        sl_display = f"-₹{abs(stop_loss):,.0f}"

    st.markdown(f"""
    <div style="background: #FFFFFF; padding: 24px; border-radius: 12px; margin-bottom: 24px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #E5E7EB;">
        <p style="font-size: 20px; font-weight: 700; color: #1A1A1A; margin: 0 0 20px 0;">{ad_name}</p>
        <div style="display: flex; gap: 40px; flex-wrap: wrap;">
            <div>
                <div style="color: #6B7280; font-size: 12px; font-weight: 500;">Total Spend</div>
                <div style="font-size: 24px; font-weight: 700; color: #1A1A1A;">₹{total_spend:,.0f}</div>
            </div>
            <div>
                <div style="color: #6B7280; font-size: 12px; font-weight: 500;">Purchases</div>
                <div style="font-size: 24px; font-weight: 700; color: #1A1A1A;">{int(total_purchases)}</div>
            </div>
            <div>
                <div style="color: #6B7280; font-size: 12px; font-weight: 500;">Conversion Value</div>
                <div style="font-size: 24px; font-weight: 700; color: #1A1A1A;">₹{total_conversion:,.0f}</div>
            </div>
            <div>
                <div style="color: #6B7280; font-size: 12px; font-weight: 500;">Overall ROAS</div>
                <div style="font-size: 24px; font-weight: 700; color: #528FF0;">{true_roas:.2f}</div>
            </div>
            <div>
                <div style="color: #6B7280; font-size: 12px; font-weight: 500;">Stop Loss</div>
                <div style="font-size: 24px; font-weight: 700; color: {sl_color};">{sl_display}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Scaling Status Card
    try:
        df_sorted_for_scaling = df.sort_values("Reporting starts").reset_index(drop=True)
        scaled_df = map_columns_for_scaling(df_sorted_for_scaling)
        phase, status, reason = get_ad_status(scaled_df)
    except Exception:
        phase, status, reason = ("N/A", "N/A", "Could not compute scaling status")

    # Pick colors based on status
    if "CONTINUE" in status:
        _status_color = "#10B981"
        _bg_tint = "#ECFDF5"
    elif "MONITOR" in status:
        _status_color = "#F59E0B"
        _bg_tint = "#FFFBEB"
    elif "LAST CHANCE" in status:
        _status_color = "#F97316"
        _bg_tint = "#FFF7ED"
    elif "KILL" in status:
        _status_color = "#EF4444"
        _bg_tint = "#FEF2F2"
    else:
        _status_color = "#6B7280"
        _bg_tint = "#F9FAFB"

    st.markdown(f"""
    <div style="background: {_bg_tint}; padding: 20px 24px; border-radius: 12px; margin-bottom: 24px;
                border-left: 4px solid {_status_color}; border: 1px solid #E5E7EB; border-left: 4px solid {_status_color};">
        <div style="display: flex; gap: 32px; align-items: baseline; flex-wrap: wrap;">
            <div>
                <span style="font-size: 12px; color: #6B7280; font-weight: 500;">Phase</span><br/>
                <span style="font-size: 18px; font-weight: 700; color: #1A1A1A;">{phase}</span>
            </div>
            <div>
                <span style="font-size: 12px; color: #6B7280; font-weight: 500;">Status</span><br/>
                <span style="font-size: 18px; font-weight: 700; color: {_status_color};">{status}</span>
            </div>
        </div>
        <p style="margin: 12px 0 0 0; font-size: 13px; color: #374151;">{reason}</p>
    </div>
    """, unsafe_allow_html=True)

    # Settings Cards
    render_section_header("Settings")

    card_style = """
        background: #FFFFFF;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #E5E7EB;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        min-height: 120px;
    """
    card_heading_style = "font-size:14px; font-weight:600; color:#1A1A1A; margin:0 0 12px 0;"
    empty_label_style = "font-size:13px; color:#9CA3AF; margin:0;"

    s_col1, s_col2, s_col3, s_col4 = st.columns(4)

    with s_col1:
        st.markdown(f"""
        <div style="{card_style}">
            <p style="{card_heading_style}">Stop Loss</p>
            <p style="font-size:12px; color:#6B7280; margin:0 0 8px 0;">Last Spend ROAS Threshold</p>
        </div>
        """, unsafe_allow_html=True)
        spend_threshold = st.number_input(
            "Threshold (INR)",
            min_value=1000,
            max_value=50000,
            value=5000,
            step=1000,
            key="spend_threshold",
            label_visibility="collapsed",
        )

    with s_col2:
        st.markdown(f"""
        <div style="{card_style}">
            <p style="{card_heading_style}">—</p>
            <p style="{empty_label_style}">Coming soon</p>
        </div>
        """, unsafe_allow_html=True)

    with s_col3:
        st.markdown(f"""
        <div style="{card_style}">
            <p style="{card_heading_style}">—</p>
            <p style="{empty_label_style}">Coming soon</p>
        </div>
        """, unsafe_allow_html=True)

    with s_col4:
        st.markdown(f"""
        <div style="{card_style}">
            <p style="{card_heading_style}">—</p>
            <p style="{empty_label_style}">Coming soon</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div style="height: 1px; background-color: #E5E7EB; margin: 24px 0;"></div>', unsafe_allow_html=True)

    # Daily Performance table
    render_section_header("Daily Performance")

    def safe_float(val):
        try:
            result = pd.to_numeric(val, errors="coerce")
            if pd.isna(result):
                return 0.0
            return float(result)
        except Exception:
            return 0.0

    try:
        # Sort by date ascending
        df_sorted = df.sort_values("Reporting starts").reset_index(drop=True)

        # Pre-compute rolling columns on the sorted dataframe
        roas_3d = calculate_rolling_roas(df_sorted, 3)
        roas_5d = calculate_rolling_roas(df_sorted, 5)
        roas_7d = calculate_rolling_roas(df_sorted, 7)
        roas_last = calculate_last_spend_roas(df_sorted, spend_threshold)

        # Build HTML rows
        rows_html = ""
        cumulative_sl = 0.0
        row_count = 0

        for i, (_, row) in enumerate(df_sorted.iterrows()):
            spend = safe_float(row.get("Amount spent (INR)"))
            purchases = safe_float(row.get("Purchases"))
            roas_val = safe_float(row.get("Purchase ROAS (return on ad spend)"))
            ctr_val = safe_float(row.get("CTR (link click-through rate)"))
            cpc_val = safe_float(row.get("CPC (cost per link click) (INR)"))
            cpm_val = safe_float(row.get("CPM (cost per 1,000 impressions) (INR)"))
            hook_val = safe_float(row.get("Hook rate"))
            hold_val = safe_float(row.get("Hold Rate"))
            date_val = str(row.get("Reporting starts", ""))

            daily_pnl = (purchases * 1200) - spend
            cumulative_sl += daily_pnl

            ad_score, _ = calculate_ad_score(ctr_val, hook_val, cpm_val)

            # Rolling ROAS display
            r3 = roas_3d[i]
            r5 = roas_5d[i]
            r7 = roas_7d[i]
            rl = roas_last[i]
            r3_td = f'{r3:.2f}' if r3 is not None else '<span style="color:#6B7280;font-style:italic;">N/A</span>'
            r5_td = f'{r5:.2f}' if r5 is not None else '<span style="color:#6B7280;font-style:italic;">N/A</span>'
            r7_td = f'{r7:.2f}' if r7 is not None else '<span style="color:#6B7280;font-style:italic;">N/A</span>'
            rl_td = f'{rl:.2f}' if rl is not None else '<span style="color:#6B7280;font-style:italic;">N/A</span>'

            # Stop loss text and color
            if cumulative_sl > 0:
                sl_text = f"+₹{cumulative_sl:,.0f}"
                sl_color_row = "#10B981"
            elif cumulative_sl >= -2000:
                sl_text = f"-₹{abs(cumulative_sl):,.0f}" if cumulative_sl < 0 else "₹0"
                sl_color_row = "#F59E0B"
            else:
                sl_text = f"-₹{abs(cumulative_sl):,.0f}"
                sl_color_row = "#EF4444"

            # Shorten date to DD-MMM (e.g. 15-Jan)
            try:
                short_date = datetime.strptime(date_val, "%Y-%m-%d").strftime("%d-%b")
            except Exception:
                short_date = date_val

            # Compact spend: use K for thousands
            if spend >= 1000:
                spend_str = f"₹{spend / 1000:.1f}K"
            else:
                spend_str = f"₹{spend:.0f}"

            rows_html += (
                f'<tr>'
                f'<td>{short_date}</td>'
                f'<td>{spend_str}</td>'
                f'<td>{int(purchases)}</td>'
                f'<td>{roas_val:.2f}</td>'
                f'<td>{ctr_val:.2f}%</td>'
                f'<td>₹{cpc_val:.0f}</td>'
                f'<td>₹{cpm_val:.0f}</td>'
                f'<td>{hook_val * 100:.1f}%</td>'
                f'<td>{hold_val * 100:.1f}%</td>'
                f'<td>{ad_score}</td>'
                f'<td>{r3_td}</td>'
                f'<td>{r5_td}</td>'
                f'<td>{r7_td}</td>'
                f'<td>{rl_td}</td>'
                f'<td style="color:{sl_color_row};font-weight:700;">{sl_text}</td>'
                f'</tr>'
            )
            row_count += 1

        if row_count == 0:
            st.warning("No rows to display.")
        else:
            table_height = 34 + (row_count * 30)
            threshold_label = f"₹{spend_threshold:,}"

            html_page = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: transparent; }}
  table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
  th {{ background:#1F2937; color:#FFFFFF; padding:6px 4px; text-align:left; font-size:11px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  td {{ padding:6px 4px; border-bottom:1px solid #374151; color:#FFFFFF; font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  tr {{ background:#111827; }}
  tr:nth-child(even) {{ background:#1F2937; }}
  th:last-child, td:last-child {{ text-align:right; }}
  /* Column widths */
  th:nth-child(1), td:nth-child(1) {{ width:72px; }}   /* Date */
  th:nth-child(2), td:nth-child(2) {{ width:62px; }}   /* Spend */
  th:nth-child(3), td:nth-child(3) {{ width:36px; }}   /* Purch */
  th:nth-child(4), td:nth-child(4) {{ width:40px; }}   /* ROAS */
  th:nth-child(5), td:nth-child(5) {{ width:42px; }}   /* CTR */
  th:nth-child(6), td:nth-child(6) {{ width:50px; }}   /* CPC */
  th:nth-child(7), td:nth-child(7) {{ width:46px; }}   /* CPM */
  th:nth-child(8), td:nth-child(8) {{ width:42px; }}   /* Hook */
  th:nth-child(9), td:nth-child(9) {{ width:42px; }}   /* Hold */
  th:nth-child(10), td:nth-child(10) {{ width:30px; }} /* Score */
  th:nth-child(11), td:nth-child(11) {{ width:38px; }} /* 3D */
  th:nth-child(12), td:nth-child(12) {{ width:38px; }} /* 5D */
  th:nth-child(13), td:nth-child(13) {{ width:38px; }} /* 7D */
  th:nth-child(14), td:nth-child(14) {{ width:52px; }} /* Last */
  th:nth-child(15), td:nth-child(15) {{ width:72px; }} /* Stop Loss */
</style>
</head>
<body>
<table>
<thead><tr>
  <th>Date</th><th>Spend</th><th>Pr</th><th>ROAS</th><th>CTR</th>
  <th>CPC</th><th>CPM</th><th>Hook</th><th>Hold</th><th>Sc</th>
  <th>3D</th><th>5D</th><th>7D</th><th>L{threshold_label}</th><th>Stop Loss</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
<script>
  function resizeFrame() {{
    var h = document.body.scrollHeight;
    if (window.frameElement) {{
      window.frameElement.style.height = h + 'px';
    }}
  }}
  window.addEventListener('load', resizeFrame);
  setTimeout(resizeFrame, 150);
</script>
</body>
</html>"""

            components.html(html_page, height=table_height, scrolling=False)

    except Exception as e:
        st.error(f"Error building daily performance table: {e}")

    # -----------------------------------------------------------------
    # ADD NOTE + COMMENTS SECTION
    # -----------------------------------------------------------------
    st.markdown('<div style="height: 1px; background-color: #E5E7EB; margin: 24px 0;"></div>', unsafe_allow_html=True)

    with st.expander("💬 Add Note"):
        new_comment = st.text_area("Write a note for this ad", key="new_comment_input", height=100)
        if st.button("Save Note", key="save_comment_btn", type="primary"):
            if new_comment and new_comment.strip():
                add_comment(ad_name, new_comment.strip())
                st.success("Note saved!")
                st.rerun()
            else:
                st.warning("Please write something first.")

    render_section_header("📝 Ad Notes & Changes")

    comments_df = get_comments_for_ad(ad_name)

    if comments_df.empty:
        st.markdown(
            '<p style="color:#6B7280; font-size:13px;">No notes yet. Click <b>💬 Add Note</b> to add one.</p>',
            unsafe_allow_html=True,
        )
    else:
        for idx, crow in comments_df.iterrows():
            c_date = str(crow["date"])
            c_time = str(crow["time"])
            c_text = str(crow["comment"])

            c_col1, c_col2 = st.columns([5, 1])
            with c_col1:
                st.markdown(
                    f'<div style="background:#FFFFFF; border:1px solid #E5E7EB; border-radius:8px; '
                    f'padding:12px 16px; margin-bottom:8px;">'
                    f'<span style="color:#6B7280; font-size:11px; font-weight:500;">{c_date} &nbsp; {c_time}</span>'
                    f'<p style="color:#1A1A1A; font-size:13px; margin:6px 0 0 0;">{c_text}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with c_col2:
                if st.button("🗑️", key=f"del_comment_{idx}_{c_date}_{c_time}", help="Delete this note"):
                    delete_comment(ad_name, c_date, c_time, c_text)
                    st.rerun()


# =============================================================================
# MAIN MODULE ENTRY POINT
# =============================================================================
def render_fb_ads_module():
    """Main entry point for the FB Ads module."""

    # Initialize database
    init_fb_ads_db()

    # Page header
    st.markdown('<p style="font-size: 28px; font-weight: 700; color: #1A1A1A; margin-bottom: 8px;">FB Ads Analytics</p>', unsafe_allow_html=True)
    st.markdown('<p style="font-size: 14px; color: #6B7280; margin-bottom: 24px;">Facebook & Instagram advertising performance</p>', unsafe_allow_html=True)

    # Check if viewing ad detail
    if st.session_state.get("selected_ad_name"):
        render_detail_view(st.session_state.selected_ad_name)
        return

    # File uploader
    render_section_header("Upload Data")
    uploaded_file = st.file_uploader("Upload FB Ads CSV", type=["csv"], key="fb_ads_uploader")

    if uploaded_file is not None:
        uploaded_df = pd.read_csv(uploaded_file)
        total_rows = len(uploaded_df)

        # Debug: Show CSV columns and sample data
        st.markdown("**Debug: CSV Upload Info**")
        st.write(f"Columns in CSV: {list(uploaded_df.columns)}")
        st.write(f"Total rows: {total_rows}")
        if "Amount spent (INR)" in uploaded_df.columns:
            st.write(f"Sample spend values: {uploaded_df['Amount spent (INR)'].head(3).tolist()}")
        if "Purchases" in uploaded_df.columns:
            st.write(f"Sample purchases values: {uploaded_df['Purchases'].head(3).tolist()}")

        new_count, updated_count, unchanged_count = upload_fb_ads_data(uploaded_df)

        # Debug: Show database values after upload
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT [Ad name], [Reporting starts], [Amount spent (INR)], [Purchases] FROM fb_ads_data ORDER BY [Reporting starts] DESC LIMIT 3")
        db_sample = cursor.fetchall()
        conn.close()
        st.write("**After upload - DB sample (latest 3 rows):**")
        for r in db_sample:
            st.write(f"  {r[0][:40]}... | {r[1]} | Spend: {r[2]} | Purch: {r[3]}")

        if new_count > 0 or updated_count > 0:
            st.markdown(
                f'<div style="background:#ECFDF5; border:1px solid #10B981; border-radius:8px; padding:12px 16px; margin:8px 0;">'
                f'<span style="color:#065F46; font-size:14px;">✅ {new_count} new, {updated_count} updated, {unchanged_count} unchanged</span>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div style="background:#EFF6FF; border:1px solid #3B82F6; border-radius:8px; padding:12px 16px; margin:8px 0;">'
                f'<span style="color:#1E40AF; font-size:14px;">ℹ️ No changes — all {total_rows} rows already up to date</span>'
                f'</div>',
                unsafe_allow_html=True
            )


    # Check if we have data
    min_date, max_date = get_date_range()

    if not min_date or not max_date:
        st.info("No FB Ads data in database. Upload your FB Ads CSV to get started.")
        return

    # Filters section
    st.markdown('<div style="height: 1px; background-color: #E5E7EB; margin: 24px 0;"></div>', unsafe_allow_html=True)
    render_section_header("Filters")

    filter_col1, filter_col2, filter_col3 = st.columns(3)

    # Campaign filter
    all_campaigns = get_unique_campaigns()

    with filter_col1:
        selected_campaigns = st.multiselect(
            "Campaign",
            options=all_campaigns,
            default=[],
            placeholder="All Campaigns"
        )

    # Ad set filter (filtered by selected campaigns)
    all_ad_sets = get_unique_ad_sets(selected_campaigns if selected_campaigns else None)

    with filter_col2:
        selected_ad_sets = st.multiselect(
            "Ad Set",
            options=all_ad_sets,
            default=[],
            placeholder="All Ad Sets"
        )

    # Date range filter
    with filter_col3:
        # Default to last 7 days
        max_date_dt = datetime.strptime(max_date, "%Y-%m-%d")
        default_start = max_date_dt - timedelta(days=6)
        min_date_dt = datetime.strptime(min_date, "%Y-%m-%d")

        if default_start < min_date_dt:
            default_start = min_date_dt

        date_col1, date_col2 = st.columns(2)
        with date_col1:
            start_date = st.date_input(
                "Start Date",
                value=default_start,
                min_value=min_date_dt,
                max_value=max_date_dt,
                key="fb_start_date"
            )
        with date_col2:
            end_date = st.date_input(
                "End Date",
                value=max_date_dt,
                min_value=min_date_dt,
                max_value=max_date_dt,
                key="fb_end_date"
            )

    # Convert dates to strings
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    # Render summary view
    st.markdown('<div style="height: 1px; background-color: #E5E7EB; margin: 24px 0;"></div>', unsafe_allow_html=True)
    render_summary_view(start_date_str, end_date_str, selected_campaigns, selected_ad_sets)
