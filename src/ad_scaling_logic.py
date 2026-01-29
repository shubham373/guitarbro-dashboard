"""
Ad Scaling Logic Module
========================
Complete implementation of 3-phase ad scaling decision system for GuitarBro.

Phases:
- Launch (₹0 - ₹5,000): Test creative potential
- Validation (₹5,000 - ₹15,000): Prove profitability
- Longevity (₹15,000+): Protect accumulated profit

Statuses:
- 🟢 CONTINUE: Ad performing well, keep running
- 🟡 MONITOR: Ad needs watching, check daily
- 🟠 LAST CHANCE: Give 1 more day, then decide
- 🔴 KILL: Stop immediately
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict, List

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════════════

# Phase boundaries (cumulative spend)
LAUNCH_MAX_SPEND = 5000
VALIDATION_MAX_SPEND = 15000

# Stop Loss thresholds
LAUNCH_STOP_LOSS_WARNING = -1000
LAUNCH_STOP_LOSS_CRITICAL = -2000
LAUNCH_STOP_LOSS_HARD_STOP = -3000
VALIDATION_STOP_LOSS_HARD_STOP = -2000

# ROAS thresholds (breakeven = 2.0)
ROAS_GOOD = 2.2
ROAS_ACCEPTABLE = 2.0
ROAS_WARNING = 1.8
ROAS_SAFE_ZONE = 2.7  # Longevity: don't worry above this

# Ad Score thresholds
AD_SCORE_STRONG = 9
AD_SCORE_DECENT = 7
AD_SCORE_WEAK = 5

# Decay thresholds (Longevity)
DECAY_IGNORE = 20  # Below this, normal fluctuation
DECAY_WARNING = 30  # Above this, likely kill
DECAY_VELOCITY_RECOVERING = -10
DECAY_VELOCITY_STABLE = 5
DECAY_VELOCITY_ACCELERATING = 15

# Profit Buffer thresholds (Longevity)
PROFIT_BUFFER_SAFE = 5000

# Profit per purchase (for Stop Loss calculation)
PROFIT_PER_PURCHASE = 1000

# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_stop_loss(total_purchases: int, total_spend: float) -> float:
    """Calculate Stop Loss: (Purchases × ₹1,000) - Spend"""
    return (total_purchases * PROFIT_PER_PURCHASE) - total_spend


def calculate_scaling_roas(total_conversion_value: float, total_spend: float) -> float:
    """Calculate true ROAS: Total Conversion Value / Total Spend"""
    if total_spend <= 0:
        return 0.0
    return total_conversion_value / total_spend


def calculate_scaling_ad_score(ctr: float, hook_rate: float, cpm: float) -> int:
    """
    Calculate Ad Score (3-12 points) based on CTR, Hook Rate, CPM.

    CTR Scoring (already in % form, e.g., 0.85 = 0.85%):
        4pts: ≥ 1.00%
        3pts: 0.85% - 0.999%
        2pts: 0.70% - 0.849%
        1pt:  < 0.70%

    Hook Rate Scoring (decimal form, e.g., 0.25 = 25%):
        4pts: ≥ 30%
        3pts: 20% - 29.9%
        2pts: 15% - 19.9%
        1pt:  < 15%

    CPM Scoring (₹):
        4pts: ≤ ₹100
        3pts: ₹101 - ₹150
        2pts: ₹151 - ₹200
        1pt:  > ₹200
    """
    # CTR Score
    if ctr >= 1.00:
        ctr_score = 4
    elif ctr >= 0.85:
        ctr_score = 3
    elif ctr >= 0.70:
        ctr_score = 2
    else:
        ctr_score = 1

    # Hook Rate Score (convert to percentage)
    hook_pct = hook_rate * 100 if hook_rate < 1 else hook_rate
    if hook_pct >= 30:
        hook_score = 4
    elif hook_pct >= 20:
        hook_score = 3
    elif hook_pct >= 15:
        hook_score = 2
    else:
        hook_score = 1

    # CPM Score
    if cpm <= 100:
        cpm_score = 4
    elif cpm <= 150:
        cpm_score = 3
    elif cpm <= 200:
        cpm_score = 2
    else:
        cpm_score = 1

    return ctr_score + hook_score + cpm_score


# ═══════════════════════════════════════════════════════════════════════════════
# TREND CALCULATION (Time-based for Launch & Validation)
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_trend(df: pd.DataFrame) -> str:
    """
    Calculate trend by comparing Day 1 metrics vs Last 3-Day average.
    Used for Launch and Validation phases.

    Returns: "IMPROVING", "STABLE", or "DECLINING"
    """
    if len(df) < 3:
        return "N/A"

    df = df.sort_values('Reporting_starts').reset_index(drop=True)

    # Day 1 values
    day1_score = df.iloc[0].get('Ad_Score', 0) or 0
    day1_ctr = df.iloc[0].get('CTR', 0) or 0
    day1_hook = df.iloc[0].get('Hook_rate', 0) or 0
    day1_cpm = df.iloc[0].get('CPM_INR', 0) or 0

    # Last 3 days average
    last_3 = df.tail(3)
    avg_score = last_3['Ad_Score'].mean() if 'Ad_Score' in last_3.columns else 0
    avg_ctr = last_3['CTR'].mean() if 'CTR' in last_3.columns else 0
    avg_hook = last_3['Hook_rate'].mean() if 'Hook_rate' in last_3.columns else 0
    avg_cpm = last_3['CPM_INR'].mean() if 'CPM_INR' in last_3.columns else 0

    # Calculate trend points
    trend_points = 0

    # Ad Score trend (higher = better)
    if day1_score > 0:
        score_change = (avg_score - day1_score) / day1_score * 100
        if score_change > 10:
            trend_points += 1
        elif score_change < -10:
            trend_points -= 1

    # CTR trend (higher = better)
    if day1_ctr > 0:
        ctr_change = (avg_ctr - day1_ctr) / day1_ctr * 100
        if ctr_change > 10:
            trend_points += 1
        elif ctr_change < -10:
            trend_points -= 1

    # Hook trend (higher = better)
    if day1_hook > 0:
        hook_change = (avg_hook - day1_hook) / day1_hook * 100
        if hook_change > 10:
            trend_points += 1
        elif hook_change < -10:
            trend_points -= 1

    # CPM trend (lower = better, so reverse logic)
    if day1_cpm > 0:
        cpm_change = (avg_cpm - day1_cpm) / day1_cpm * 100
        if cpm_change < -10:  # CPM decreased = good
            trend_points += 1
        elif cpm_change > 10:  # CPM increased = bad
            trend_points -= 1

    # Classify trend
    if trend_points >= 2:
        return "IMPROVING"
    elif trend_points <= -2:
        return "DECLINING"
    else:
        return "STABLE"


def calculate_trajectory(current_stop_loss: float, stop_loss_at_5k: float) -> str:
    """
    Calculate Stop Loss trajectory for Validation phase.
    Compares current Stop Loss to Stop Loss at ₹5,000 spend.

    Returns: "IMPROVING", "STABLE", or "WORSENING"
    """
    if stop_loss_at_5k is None:
        return "N/A"

    diff = current_stop_loss - stop_loss_at_5k

    if diff > 300:  # Moving toward positive
        return "IMPROVING"
    elif diff < -300:  # Moving more negative
        return "WORSENING"
    else:
        return "STABLE"


# ═══════════════════════════════════════════════════════════════════════════════
# SPEND-BASED ROAS CALCULATION (For Longevity Phase)
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_last_x_spend_roas(df: pd.DataFrame, threshold: float) -> Optional[float]:
    """
    Calculate ROAS for last X amount of spend.
    Goes backward from most recent until cumulative spend >= threshold.

    Args:
        df: DataFrame with daily ad data (must have Reporting_starts, Amount_spent_INR, Purchases_conversion_value)
        threshold: Spend threshold (e.g., 3000, 5000, 7000, 10000)

    Returns:
        ROAS for the spend window, or None if insufficient spend
    """
    if df.empty:
        return None

    df = df.sort_values('Reporting_starts', ascending=False).reset_index(drop=True)  # Most recent first

    cumulative_spend = 0.0
    cumulative_conv_value = 0.0

    for _, row in df.iterrows():
        spend = row.get('Amount_spent_INR', 0)
        if pd.isna(spend):
            spend = 0
        conv_value = row.get('Purchases_conversion_value', 0)
        if pd.isna(conv_value):
            conv_value = 0

        cumulative_spend += spend
        cumulative_conv_value += conv_value

        if cumulative_spend >= threshold:
            break

    if cumulative_spend < threshold:
        return None  # Not enough spend yet

    return cumulative_conv_value / cumulative_spend if cumulative_spend > 0 else 0.0


def calculate_all_spend_windows(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """
    Calculate ROAS for all spend windows used in Longevity phase.

    Returns dict with L3K, L5K, L7K, L10K ROAS values.
    """
    return {
        'L3K': calculate_last_x_spend_roas(df, 3000),
        'L5K': calculate_last_x_spend_roas(df, 5000),
        'L7K': calculate_last_x_spend_roas(df, 7000),
        'L10K': calculate_last_x_spend_roas(df, 10000),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DECAY CALCULATION (For Longevity Phase)
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_decay(baseline_roas: float, current_roas: float) -> float:
    """
    Calculate decay percentage from baseline.

    Decay = (Baseline - Current) / Baseline × 100
    """
    if baseline_roas <= 0:
        return 0.0
    return (baseline_roas - current_roas) / baseline_roas * 100


def classify_decay_pattern(
    baseline_roas: float,
    l3k_roas: Optional[float],
    l5k_roas: Optional[float],
    l7k_roas: Optional[float],
    l10k_roas: Optional[float]
) -> Dict:
    """
    Classify decay pattern based on multi-window analysis.

    Patterns:
    - RECOVERING: Each newer window is BETTER (L3K < L5K < L7K decay)
    - ACCELERATING: Each newer window is WORSE (L3K > L5K > L7K > L10K decay)
    - STABLE: L3K ≈ L7K decay (±5%)
    - SUDDEN DROP: L3K >> L7K decay (>15% difference)
    - MIXED: None of the above

    Returns dict with pattern, decay values, and velocity.
    """
    result = {
        'pattern': 'N/A',
        'l3k_decay': None,
        'l5k_decay': None,
        'l7k_decay': None,
        'l10k_decay': None,
        'decay_velocity': None
    }

    if baseline_roas <= 0:
        return result

    # Calculate decay for each window (only if ROAS available)
    if l3k_roas is not None:
        result['l3k_decay'] = calculate_decay(baseline_roas, l3k_roas)
    if l5k_roas is not None:
        result['l5k_decay'] = calculate_decay(baseline_roas, l5k_roas)
    if l7k_roas is not None:
        result['l7k_decay'] = calculate_decay(baseline_roas, l7k_roas)
    if l10k_roas is not None:
        result['l10k_decay'] = calculate_decay(baseline_roas, l10k_roas)

    # Need at least L3K and L7K for pattern detection
    if result['l3k_decay'] is None or result['l7k_decay'] is None:
        result['pattern'] = 'INSUFFICIENT_DATA'
        return result

    l3k_decay = result['l3k_decay']
    l5k_decay = result['l5k_decay'] if result['l5k_decay'] is not None else l3k_decay
    l7k_decay = result['l7k_decay']
    l10k_decay = result['l10k_decay'] if result['l10k_decay'] is not None else l7k_decay

    # Decay Velocity (recent vs older)
    result['decay_velocity'] = l3k_decay - l7k_decay

    # Pattern Detection
    if l3k_decay < l5k_decay < l7k_decay:
        # Each newer window is BETTER (less decay)
        result['pattern'] = 'RECOVERING'

    elif l3k_decay > l5k_decay > l7k_decay > l10k_decay:
        # Each newer window is WORSE (more decay)
        result['pattern'] = 'ACCELERATING'

    elif abs(l3k_decay - l7k_decay) < 5:
        # Recent and older decay are similar
        result['pattern'] = 'STABLE'

    elif l3k_decay > l7k_decay + 15:
        # Sudden recent drop
        result['pattern'] = 'SUDDEN_DROP'

    else:
        result['pattern'] = 'MIXED'

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_phase(total_spend: float) -> str:
    """
    Detect which phase the ad is in based on cumulative spend.

    Returns: "LAUNCH", "VALIDATION", or "LONGEVITY"
    """
    if total_spend < LAUNCH_MAX_SPEND:
        return "LAUNCH"
    elif total_spend < VALIDATION_MAX_SPEND:
        return "VALIDATION"
    else:
        return "LONGEVITY"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: LAUNCH PHASE LOGIC (₹0 - ₹5,000)
# ═══════════════════════════════════════════════════════════════════════════════

def get_launch_phase_status(
    stop_loss: float,
    ad_score: int,
    trend: str,
    total_spend: float
) -> Tuple[str, str]:
    """
    Get status and reason for Launch phase ad.

    Priority:
    1. Stop Loss (capital protection)
    2. Ad Score (creative quality)
    3. Trend (performance direction)

    Returns: (status, reason)
    """
    # Not enough spend to judge
    if total_spend < 2500:
        return ("🟡 MONITOR", f"Learning phase — ₹{total_spend:.0f} spent, need ₹2,500 minimum")

    # ═══════════════════════════════════════════════════════════════════════════
    # STOP LOSS CHECKS
    # ═══════════════════════════════════════════════════════════════════════════

    # Hard Stop: Stop Loss < -₹3,000
    if stop_loss < LAUNCH_STOP_LOSS_HARD_STOP:
        return ("🔴 KILL", f"Stop Loss ₹{stop_loss:,.0f} exceeded -₹3,000 hard limit")

    # Critical: Stop Loss -₹2,000 to -₹3,000
    if stop_loss < LAUNCH_STOP_LOSS_CRITICAL:
        if ad_score >= AD_SCORE_STRONG and trend == "IMPROVING":
            return ("🟠 LAST CHANCE", f"Stop Loss ₹{stop_loss:,.0f} critical, but Ad Score {ad_score} strong & improving")
        else:
            return ("🔴 KILL", f"Stop Loss ₹{stop_loss:,.0f} critical, Ad Score {ad_score} not strong enough")

    # Warning: Stop Loss -₹1,000 to -₹2,000
    if stop_loss < LAUNCH_STOP_LOSS_WARNING:
        if ad_score >= AD_SCORE_STRONG:
            if trend == "IMPROVING":
                return ("🟢 CONTINUE", f"Stop Loss ₹{stop_loss:,.0f} warning zone, but Ad Score {ad_score} strong & improving")
            else:
                return ("🟡 MONITOR", f"Stop Loss ₹{stop_loss:,.0f} warning zone, Ad Score {ad_score} strong but {trend.lower()}")
        elif ad_score >= AD_SCORE_DECENT:
            if trend == "IMPROVING":
                return ("🟡 MONITOR", f"Stop Loss ₹{stop_loss:,.0f} warning, Ad Score {ad_score} decent & improving")
            else:
                return ("🟠 LAST CHANCE", f"Stop Loss ₹{stop_loss:,.0f} warning, Ad Score {ad_score} decent but {trend.lower()}")
        elif ad_score >= AD_SCORE_WEAK:
            return ("🟠 LAST CHANCE", f"Stop Loss ₹{stop_loss:,.0f} warning, Ad Score {ad_score} weak")
        else:
            return ("🔴 KILL", f"Stop Loss ₹{stop_loss:,.0f} warning, Ad Score {ad_score} poor")

    # ═══════════════════════════════════════════════════════════════════════════
    # SAFE STOP LOSS (> -₹1,000) - Focus on Ad Score & Trend
    # ═══════════════════════════════════════════════════════════════════════════

    if ad_score >= AD_SCORE_STRONG:
        return ("🟢 CONTINUE", f"Ad Score {ad_score} strong, Stop Loss ₹{stop_loss:,.0f} safe")

    elif ad_score >= AD_SCORE_DECENT:
        if trend == "DECLINING":
            return ("🟡 MONITOR", f"Ad Score {ad_score} decent but declining trend")
        else:
            return ("🟢 CONTINUE", f"Ad Score {ad_score} decent, trend {trend.lower()}")

    elif ad_score >= AD_SCORE_WEAK:
        if trend == "IMPROVING":
            return ("🟡 MONITOR", f"Ad Score {ad_score} weak but improving")
        elif trend == "STABLE":
            return ("🟡 MONITOR", f"Ad Score {ad_score} weak, trend stable")
        else:
            return ("🟠 LAST CHANCE", f"Ad Score {ad_score} weak & declining")

    else:  # ad_score < 5
        if trend == "IMPROVING":
            return ("🟡 MONITOR", f"Ad Score {ad_score} poor but improving — give chance")
        elif trend == "STABLE":
            return ("🟠 LAST CHANCE", f"Ad Score {ad_score} poor, not improving")
        else:
            return ("🔴 KILL", f"Ad Score {ad_score} poor & declining")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: VALIDATION PHASE LOGIC (₹5,000 - ₹15,000)
# ═══════════════════════════════════════════════════════════════════════════════

def get_validation_phase_status(
    stop_loss: float,
    trajectory: str,
    trend: str,
    roas: float,
    total_spend: float
) -> Tuple[str, str]:
    """
    Get status and reason for Validation phase ad.

    Priority:
    1. Stop Loss (must stay > -₹2,000)
    2. ROAS (must reach ≥ 2.0)
    3. Trajectory (Stop Loss moving toward ₹0?)
    4. Trend (performance direction)

    Returns: (status, reason)
    """
    # ═══════════════════════════════════════════════════════════════════════════
    # HARD STOP: Stop Loss < -₹2,000
    # ═══════════════════════════════════════════════════════════════════════════

    if stop_loss < VALIDATION_STOP_LOSS_HARD_STOP:
        return ("🔴 KILL", f"Stop Loss ₹{stop_loss:,.0f} exceeded -₹2,000 limit at ₹{total_spend:,.0f} spend")

    # ═══════════════════════════════════════════════════════════════════════════
    # PROFITABLE: Stop Loss > ₹0
    # ═══════════════════════════════════════════════════════════════════════════

    if stop_loss > 0:
        if roas >= ROAS_ACCEPTABLE:
            return ("🟢 CONTINUE", f"Profitable: Stop Loss +₹{stop_loss:,.0f}, ROAS {roas:.2f}")
        elif roas >= ROAS_WARNING:
            if trend == "DECLINING" and trajectory == "WORSENING":
                return ("🟠 LAST CHANCE", f"ROAS {roas:.2f} below 2.0, declining trend, trajectory worsening")
            else:
                return ("🟡 MONITOR", f"ROAS {roas:.2f} below 2.0 but profitable, trend {trend.lower()}")
        else:
            return ("🟠 LAST CHANCE", f"ROAS {roas:.2f} critical despite positive Stop Loss")

    # ═══════════════════════════════════════════════════════════════════════════
    # WARNING ZONE: Stop Loss -₹1,000 to -₹2,000
    # ═══════════════════════════════════════════════════════════════════════════

    if stop_loss < -1000:
        if trajectory == "IMPROVING" and trend == "IMPROVING":
            if roas >= ROAS_ACCEPTABLE:
                return ("🟡 MONITOR", f"Stop Loss ₹{stop_loss:,.0f} but improving, ROAS {roas:.2f}")
            elif roas >= ROAS_WARNING:
                return ("🟠 LAST CHANCE", f"Stop Loss ₹{stop_loss:,.0f}, ROAS {roas:.2f} warning, but both improving")
            else:
                return ("🔴 KILL", f"Stop Loss ₹{stop_loss:,.0f}, ROAS {roas:.2f} critical")
        elif trajectory == "IMPROVING" and trend == "STABLE":
            return ("🟠 LAST CHANCE", f"Stop Loss ₹{stop_loss:,.0f}, trajectory improving but trend stable")
        else:
            return ("🔴 KILL", f"Stop Loss ₹{stop_loss:,.0f}, trajectory {trajectory.lower()}, trend {trend.lower()}")

    # ═══════════════════════════════════════════════════════════════════════════
    # NEAR BREAK-EVEN: Stop Loss ₹0 to -₹1,000
    # ═══════════════════════════════════════════════════════════════════════════

    if trajectory == "IMPROVING":
        if trend == "IMPROVING" and roas >= ROAS_ACCEPTABLE:
            return ("🟢 CONTINUE", f"Trajectory improving, ROAS {roas:.2f}, trend improving")
        elif trend in ["IMPROVING", "STABLE"] and roas >= ROAS_WARNING:
            return ("🟢 CONTINUE", f"Trajectory improving, ROAS {roas:.2f}, trend {trend.lower()}")
        elif roas < ROAS_WARNING:
            return ("🟡 MONITOR", f"Trajectory improving but ROAS {roas:.2f} below 1.8")
        else:
            return ("🟡 MONITOR", f"Trajectory improving, ROAS {roas:.2f}, trend {trend.lower()}")

    elif trajectory == "STABLE":
        if roas >= ROAS_ACCEPTABLE and trend == "STABLE":
            return ("🟡 MONITOR", f"ROAS {roas:.2f} acceptable, trajectory & trend stable")
        elif roas >= ROAS_WARNING and trend == "STABLE":
            return ("🟠 LAST CHANCE", f"ROAS {roas:.2f} warning zone, trajectory & trend stable")
        elif trend == "DECLINING":
            return ("🟠 LAST CHANCE", f"Trend declining despite stable trajectory")
        else:
            return ("🔴 KILL", f"ROAS {roas:.2f}, trajectory stable, not improving")

    else:  # trajectory == "WORSENING"
        return ("🔴 KILL", f"Trajectory worsening — Stop Loss moving negative at ₹{total_spend:,.0f} spend")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: LONGEVITY PHASE LOGIC (₹15,000+)
# ═══════════════════════════════════════════════════════════════════════════════

def get_longevity_phase_status(
    overall_roas: float,
    baseline_roas: float,
    decay_info: Dict,
    stop_loss: float,
    ad_score_trend: str,
    total_spend: float
) -> Tuple[str, str]:
    """
    Get status and reason for Longevity phase ad.

    Priority:
    1. ROAS Zone (Safe ≥2.7, Watch 2.2-2.7, Concern 2.0-2.2, Danger <2.0)
    2. Decay Pattern (Recovering/Stable/Accelerating/Sudden Drop)
    3. Decay Velocity (Is decay accelerating?)
    4. Profit Buffer (Stop Loss)
    5. Ad Score Trend (Rebound potential)

    Returns: (status, reason)
    """
    pattern = decay_info.get('pattern', 'N/A')
    l3k_decay = decay_info.get('l3k_decay')
    decay_velocity = decay_info.get('decay_velocity')

    # Format decay for display
    decay_str = f"{l3k_decay:.1f}%" if l3k_decay is not None else "N/A"
    velocity_str = f"{decay_velocity:+.1f}%" if decay_velocity is not None else "N/A"

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 1: SAFE ZONE (ROAS ≥ 2.7)
    # ═══════════════════════════════════════════════════════════════════════════

    if overall_roas >= ROAS_SAFE_ZONE:
        if pattern == "ACCELERATING" and l3k_decay is not None and l3k_decay > 30:
            return ("🟡 MONITOR", f"ROAS {overall_roas:.2f} safe but rapid decay {decay_str}, velocity {velocity_str}")
        else:
            return ("🟢 CONTINUE", f"ROAS {overall_roas:.2f} in safe zone — no intervention needed")

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 4: DANGER ZONE (ROAS < 2.0)
    # ═══════════════════════════════════════════════════════════════════════════

    if overall_roas < ROAS_ACCEPTABLE:
        return ("🔴 KILL", f"ROAS {overall_roas:.2f} below breakeven at ₹{total_spend:,.0f} spend")

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 3: CONCERN ZONE (ROAS 2.0 - 2.2)
    # ═══════════════════════════════════════════════════════════════════════════

    if overall_roas < ROAS_GOOD:
        if pattern == "RECOVERING":
            return ("🟡 MONITOR", f"ROAS {overall_roas:.2f} concern zone but recovering, decay {decay_str}")

        if l3k_decay is not None and l3k_decay > 20:
            return ("🔴 KILL", f"ROAS {overall_roas:.2f} concern zone, decay {decay_str} > 20%")

        if l3k_decay is not None and l3k_decay > 10:
            if ad_score_trend == "IMPROVING" and stop_loss > PROFIT_BUFFER_SAFE:
                return ("🟠 LAST CHANCE", f"ROAS {overall_roas:.2f}, decay {decay_str}, but Ad Score improving")
            else:
                return ("🔴 KILL", f"ROAS {overall_roas:.2f}, decay {decay_str}, Ad Score {ad_score_trend.lower()}")

        # l3k_decay <= 10
        if ad_score_trend in ["IMPROVING", "STABLE"] and stop_loss > PROFIT_BUFFER_SAFE:
            return ("🟡 MONITOR", f"ROAS {overall_roas:.2f}, minor decay {decay_str}, buffer +₹{stop_loss:,.0f}")
        else:
            return ("🟠 LAST CHANCE", f"ROAS {overall_roas:.2f}, decay {decay_str}, low buffer ₹{stop_loss:,.0f}")

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 2: WATCH ZONE (ROAS 2.2 - 2.7)
    # ═══════════════════════════════════════════════════════════════════════════

    # Recovering pattern — always good
    if pattern == "RECOVERING":
        return ("🟢 CONTINUE", f"ROAS {overall_roas:.2f}, pattern recovering, decay {decay_str}")

    # Check decay level
    if l3k_decay is None or l3k_decay < DECAY_IGNORE:
        return ("🟢 CONTINUE", f"ROAS {overall_roas:.2f}, decay {decay_str} within normal range")

    # Decay 20-30%
    if l3k_decay < DECAY_WARNING:
        if decay_velocity is not None and decay_velocity > DECAY_VELOCITY_ACCELERATING:
            return ("🔴 KILL", f"ROAS {overall_roas:.2f}, decay accelerating rapidly {velocity_str}")

        if pattern == "ACCELERATING":
            if stop_loss > PROFIT_BUFFER_SAFE:
                return ("🟡 MONITOR", f"ROAS {overall_roas:.2f}, accelerating decay but buffer +₹{stop_loss:,.0f}")
            else:
                return ("🟠 LAST CHANCE", f"ROAS {overall_roas:.2f}, accelerating decay, low buffer ₹{stop_loss:,.0f}")

        if pattern == "SUDDEN_DROP":
            return ("🟡 MONITOR", f"ROAS {overall_roas:.2f}, sudden drop detected — investigate cause")

        if ad_score_trend == "IMPROVING":
            return ("🟡 MONITOR", f"ROAS {overall_roas:.2f}, decay {decay_str} but Ad Score improving")
        elif ad_score_trend == "STABLE":
            if stop_loss > PROFIT_BUFFER_SAFE:
                return ("🟡 MONITOR", f"ROAS {overall_roas:.2f}, decay {decay_str}, stable Ad Score, buffer safe")
            else:
                return ("🟠 LAST CHANCE", f"ROAS {overall_roas:.2f}, decay {decay_str}, low buffer")
        else:  # DECLINING
            return ("🟠 LAST CHANCE", f"ROAS {overall_roas:.2f}, decay {decay_str}, Ad Score declining")

    # Decay > 30%
    if ad_score_trend == "IMPROVING" and stop_loss > PROFIT_BUFFER_SAFE:
        return ("🟠 LAST CHANCE", f"ROAS {overall_roas:.2f}, high decay {decay_str} but Ad Score improving")
    else:
        return ("🔴 KILL", f"ROAS {overall_roas:.2f}, decay {decay_str} exceeds 30% limit")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION: GET AD STATUS
# ═══════════════════════════════════════════════════════════════════════════════

def get_ad_status(df: pd.DataFrame) -> Tuple[str, str, str]:
    """
    Main function to get ad status based on current phase.

    Args:
        df: DataFrame with complete ad history (daily data)

    Returns: (phase, status, reason)
    """
    if df.empty:
        return ("N/A", "🟡 MONITOR", "No data available")

    # Auto-rename columns to expected format
    column_mapping = {
        'Amount spent (INR)': 'Amount_spent_INR',
        'Purchases conversion value': 'Purchases_conversion_value',
        'Reporting starts': 'Reporting_starts',
        'CTR (link click-through rate)': 'CTR',
        'Hook Rate': 'Hook_rate',
        'Hook rate': 'Hook_rate',
        'CPM (cost per 1,000 impressions)': 'CPM_INR',
        'CPM (cost per 1,000 impressions) (INR)': 'CPM_INR',
    }
    df = df.rename(columns=column_mapping)

    # Sort by date ascending
    df = df.sort_values('Reporting_starts').reset_index(drop=True)

    # Calculate totals
    total_spend = df['Amount_spent_INR'].sum()
    total_purchases = df['Purchases'].fillna(0).sum() if 'Purchases' in df.columns else 0
    total_conv_value = df['Purchases_conversion_value'].sum() if 'Purchases_conversion_value' in df.columns else 0

    # Calculate key metrics
    stop_loss = calculate_stop_loss(int(total_purchases), total_spend)
    overall_roas = calculate_scaling_roas(total_conv_value, total_spend)

    # Calculate Ad Score for latest day
    latest = df.iloc[-1]
    ctr = latest.get('CTR', 0) or 0
    hook_rate = latest.get('Hook_rate', 0) or 0
    cpm = latest.get('CPM_INR', 0) or 0
    ad_score = calculate_scaling_ad_score(ctr, hook_rate, cpm)

    # Add Ad Score to DataFrame for trend calculation
    df['Ad_Score'] = df.apply(
        lambda row: calculate_scaling_ad_score(
            row.get('CTR', 0) or 0,
            row.get('Hook_rate', 0) or 0,
            row.get('CPM_INR', 0) or 0
        ),
        axis=1
    )

    # Detect phase
    phase = detect_phase(total_spend)

    # ═══════════════════════════════════════════════════════════════════════════
    # LAUNCH PHASE
    # ═══════════════════════════════════════════════════════════════════════════

    if phase == "LAUNCH":
        trend = calculate_trend(df)
        status, reason = get_launch_phase_status(stop_loss, ad_score, trend, total_spend)
        return (phase, status, reason)

    # ═══════════════════════════════════════════════════════════════════════════
    # VALIDATION PHASE
    # ═══════════════════════════════════════════════════════════════════════════

    elif phase == "VALIDATION":
        trend = calculate_trend(df)

        # Calculate Stop Loss at ₹5,000 for trajectory
        spend_at_5k = 0
        purchases_at_5k = 0
        for _, row in df.iterrows():
            spend_val = row.get('Amount_spent_INR', 0)
            spend_at_5k += 0 if pd.isna(spend_val) else spend_val
            purch_val = row.get('Purchases', 0)
            purchases_at_5k += 0 if pd.isna(purch_val) else purch_val
            if spend_at_5k >= LAUNCH_MAX_SPEND:
                break
        stop_loss_at_5k = calculate_stop_loss(int(purchases_at_5k), spend_at_5k)

        trajectory = calculate_trajectory(stop_loss, stop_loss_at_5k)

        status, reason = get_validation_phase_status(stop_loss, trajectory, trend, overall_roas, total_spend)
        return (phase, status, reason)

    # ═══════════════════════════════════════════════════════════════════════════
    # LONGEVITY PHASE
    # ═══════════════════════════════════════════════════════════════════════════

    else:  # LONGEVITY
        # Calculate baseline ROAS (overall ROAS at entry to Longevity)
        # For simplicity, use overall ROAS as baseline
        baseline_roas = overall_roas

        # Calculate spend-based windows
        spend_windows = calculate_all_spend_windows(df)

        # Get L5K ROAS for decay calculation (primary window)
        l5k_roas = spend_windows.get('L5K') or overall_roas

        # Classify decay pattern
        decay_info = classify_decay_pattern(
            baseline_roas,
            spend_windows.get('L3K'),
            spend_windows.get('L5K'),
            spend_windows.get('L7K'),
            spend_windows.get('L10K')
        )

        # Calculate Ad Score trend
        ad_score_trend = calculate_trend(df)

        status, reason = get_longevity_phase_status(
            overall_roas,
            baseline_roas,
            decay_info,
            stop_loss,
            ad_score_trend,
            total_spend
        )
        return (phase, status, reason)


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH PROCESSING: GET STATUS FOR ALL ADS
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_ads_status(get_ad_history_func, ad_names: List[str]) -> pd.DataFrame:
    """
    Get status for all ads.

    Args:
        get_ad_history_func: Function that takes ad_name and returns DataFrame with full history
        ad_names: List of ad names to process

    Returns:
        DataFrame with columns: Ad_Name, Phase, Status, Reason
    """
    results = []

    for ad_name in ad_names:
        try:
            df = get_ad_history_func(ad_name)
            phase, status, reason = get_ad_status(df)
            results.append({
                'Ad_Name': ad_name,
                'Phase': phase,
                'Status': status,
                'Reason': reason
            })
        except Exception as e:
            results.append({
                'Ad_Name': ad_name,
                'Phase': 'ERROR',
                'Status': '⚠️ ERROR',
                'Reason': str(e)
            })

    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════════════════════
# TESTING / EXAMPLE USAGE
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Example test data
    print("=" * 60)
    print("AD SCALING LOGIC MODULE - TEST")
    print("=" * 60)

    # Test Ad Score calculation
    print("\n--- Ad Score Tests ---")
    print(f"CTR 1.2%, Hook 25%, CPM ₹90 → Score: {calculate_scaling_ad_score(1.2, 0.25, 90)}")  # Should be 12
    print(f"CTR 0.8%, Hook 22%, CPM ₹130 → Score: {calculate_scaling_ad_score(0.8, 0.22, 130)}")  # Should be 9
    print(f"CTR 0.5%, Hook 12%, CPM ₹220 → Score: {calculate_scaling_ad_score(0.5, 0.12, 220)}")  # Should be 3

    # Test Stop Loss calculation
    print("\n--- Stop Loss Tests ---")
    print(f"5 purchases, ₹3000 spend → Stop Loss: ₹{calculate_stop_loss(5, 3000):,}")  # +2000
    print(f"2 purchases, ₹4000 spend → Stop Loss: ₹{calculate_stop_loss(2, 4000):,}")  # -2000

    # Test Phase detection
    print("\n--- Phase Detection Tests ---")
    print(f"₹3,000 spend → Phase: {detect_phase(3000)}")  # LAUNCH
    print(f"₹8,000 spend → Phase: {detect_phase(8000)}")  # VALIDATION
    print(f"₹20,000 spend → Phase: {detect_phase(20000)}")  # LONGEVITY

    # Test Decay calculation
    print("\n--- Decay Tests ---")
    decay_info = classify_decay_pattern(3.0, 2.1, 2.3, 2.5, 2.7)
    print(f"Baseline 3.0, L3K 2.1, L5K 2.3, L7K 2.5, L10K 2.7")
    print(f"Pattern: {decay_info['pattern']}")
    print(f"L3K Decay: {decay_info['l3k_decay']:.1f}%")
    print(f"Decay Velocity: {decay_info['decay_velocity']:+.1f}%")

    print("\n" + "=" * 60)
    print("MODULE READY FOR INTEGRATION")
    print("=" * 60)
