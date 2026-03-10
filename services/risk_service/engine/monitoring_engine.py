from typing import List, Optional, Literal, Tuple
from api.schemas import HistoryEntry, MonitoringSummary

Trend = Literal["FIRST_ASSESSMENT", "WORSENING", "IMPROVING", "STABLE"]

LOW_MAX  = 15
MOD_MAX  = 50
HIGH_MAX = 85

def risk_level(pct: Optional[float]) -> str:
    if pct is None:
        return "No Data"
    if pct < LOW_MAX:
        return "Low"
    if pct < MOD_MAX:
        return "Moderate"
    if pct < HIGH_MAX:
        return "High"
    return "Very High"

def _latest_two_with_risk(entries_sorted: List[HistoryEntry]) -> Tuple[Optional[HistoryEntry], Optional[HistoryEntry]]:
    with_risk = [e for e in entries_sorted if e.predicted_risk_percent is not None]
    if len(with_risk) >= 2:
        return with_risk[-2], with_risk[-1]
    if len(with_risk) == 1:
        return None, with_risk[-1]
    return None, None

def analyze_history(
    entries: List[HistoryEntry],
    *,
    window_size: int = 6,
    relapse_window_size: Optional[int] = None,
    change_warn: float = 10.0,
    change_alert: float = 15.0,
) -> Optional[MonitoringSummary]:
    if not entries:
        return None

    entries_sorted = sorted(entries, key=lambda x: x.assessment_date)
    w = max(1, int(window_size))
    window_entries = entries_sorted[-w:]

    r_w = max(1, int(relapse_window_size if relapse_window_size is not None else w))
    relapse_window_entries = entries_sorted[-r_w:]

    total_relapses_all = sum(1 for e in entries_sorted if getattr(e, "actual_relapse", None) is True)
    total_relapses_recent = sum(1 for e in relapse_window_entries if getattr(e, "actual_relapse", None) is True)

    prev_e, latest_e = _latest_two_with_risk(entries_sorted)

    trend: Trend = "FIRST_ASSESSMENT"
    emoji = "🆕"
    recent_change: Optional[float] = None
    alert: Optional[str] = None

    if latest_e is not None and prev_e is not None:
        latest_r = float(latest_e.predicted_risk_percent)  # type: ignore
        prev_r = float(prev_e.predicted_risk_percent)      # type: ignore
        recent_change = latest_r - prev_r

        if recent_change > change_warn:
            trend, emoji = "WORSENING", "⬆️"
        elif recent_change < -change_warn:
            trend, emoji = "IMPROVING", "⬇️"
        else:
            trend, emoji = "STABLE", "➡️"

        if recent_change > change_alert:
            alert = f"⚠️ Risk jumped from {prev_r:.1f}% ({risk_level(prev_r)}) to {latest_r:.1f}% ({risk_level(latest_r)})."

    if total_relapses_recent > 0 and alert is None:
        alert = "⚠️ A relapse was reported recently. Consider extra support and coping actions."

    return MonitoringSummary(
        trend=trend,
        emoji=emoji,
        recent_change=recent_change,
        alert=alert,
        weeks_tracked=len(window_entries),
        total_relapses=total_relapses_all,
    )