from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, conint
from typing import Optional
from datetime import datetime

Feature = conint(ge=1, le=7)


class AssessmentInput(BaseModel):
    user_id: str
    assessment_date: date = Field(default_factory=date.today)

    self_efficacy_doubt: Feature  # type: ignore
    emotional_distress: Feature  # type: ignore
    anger_irritability: Feature  # type: ignore
    unclear_thinking: Feature  # type: ignore
    poor_concentration: Feature  # type: ignore
    feeling_trapped: Feature  # type: ignore
    sleep_disturbance: Feature  # type: ignore
    craving_thoughts: Feature  # type: ignore
    relapse_ideation: Feature  # type: ignore
    recovery_actions: Feature  # type: ignore

    def features_dict(self):
        return {
            f: getattr(self, f)
            for f in [
                "self_efficacy_doubt",
                "emotional_distress",
                "anger_irritability",
                "unclear_thinking",
                "poor_concentration",
                "feeling_trapped",
                "sleep_disturbance",
                "craving_thoughts",
                "relapse_ideation",
                "recovery_actions",
            ]
        }


class XaiItem(BaseModel):
    feature_name: str
    feature_value: int
    contribution: float
    rank: int


class AssessmentResult(BaseModel):
    assessment_id: int
    user_id: str
    assessment_date: date
    prediction_id: int
    predicted_label: int
    predicted_risk_percent: float
    risk_level: str
    category: str
    emoji: str
    total_score: int
    model_version: str
    xai: List[XaiItem]

    model_config = {"protected_namespaces": ()}


class WeeklyCheckinCreate(BaseModel):
    user_id: str
    actual_relapse: conint(ge=0, le=1)  # type: ignore


class WeeklyCheckinResponse(BaseModel):
    checkin_id: int
    user_id: str
    actual_relapse: int
    reported_at: datetime

    model_config = {"from_attributes": True}


class DailyTrendPoint(BaseModel):
    day: date
    risk_percent: Optional[float] = None
    category: Optional[str] = None
    relapse_this_week: bool = False


class WeeklyTrendPoint(BaseModel):
    week_start: date
    week_label: str
    avg_risk_percent: Optional[float] = None
    relapse_reported: bool = False
    trend: Optional[str] = None
    emoji: Optional[str] = None
    recent_change: Optional[float] = None
    alert: Optional[str] = None


class TrendResponse(BaseModel):
    user_id: str
    days: List[DailyTrendPoint]
    weeks: List[WeeklyTrendPoint]


class HistoryEntry(BaseModel):
    assessment_date: datetime
    predicted_risk_percent: Optional[float] = None
    actual_relapse: Optional[int] = None


class MonitoringSummary(BaseModel):
    trend: str
    emoji: str
    recent_change: Optional[float] = None
    alert: Optional[str] = None
    weeks_tracked: int
    total_relapses: int