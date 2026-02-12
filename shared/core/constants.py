"""
Shared constants used across all services
"""

from enum import Enum


class RiskLevel(str, Enum):
    """Risk level classifications"""
    HIGH_RISK = "HIGH_RISK"
    MODERATE_RISK = "MODERATE_RISK"
    LOW_RISK = "LOW_RISK"
    ISOLATION_ONLY = "ISOLATION_ONLY"
    UNKNOWN = "UNKNOWN"


class RiskTrend(str, Enum):
    """Risk trend over time"""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    RAPID_DECLINE = "rapid_decline"


class ActionType(str, Enum):
    """Types of actions that can be triggered"""
    NUDGE = "nudge"
    ESCALATION = "escalation"
    MEETING_SCHEDULED = "meeting_scheduled"
    FAMILY_NOTIFIED = "family_notified"
    COUNSELOR_ALERT = "counselor_alert"


class NudgeType(str, Enum):
    """Types of nudges"""
    PEER_INTERACTION = "peer_interaction"
    OUTDOOR_ACTIVITY = "outdoor_activity"
    ENCOURAGING = "encouraging"
    MEETING_REMINDER = "meeting_reminder"
    SELF_CARE = "self_care"


class EscalationUrgency(str, Enum):
    """Escalation urgency levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConversationType(str, Enum):
    """Types of conversations"""
    BUDDY = "buddy"
    COUNSELOR = "counselor"
    GROUP = "group"
    FAMILY = "family"


# Risk thresholds
RISK_THRESHOLDS = {
    "high_risk": 0.7,
    "moderate_risk": 0.4,
    "low_risk": 0.2,
}

# Time windows (in days)
TIME_WINDOWS = {
    "short_term": 7,
    "medium_term": 30,
    "long_term": 90,
}

# Isolation thresholds
ISOLATION_THRESHOLDS = {
    "days_without_buddy_msg": 3,
    "isolation_probability": 0.6,
}
