from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, conint

Feature = conint(ge=1, le=7)

class PatientCreate(BaseModel):
    patient_id: str
    age: int = Field(..., gt=0, lt=130)
    days_since_last_use: int = Field(..., ge=0)

class PatientResponse(BaseModel):
    patient_id: str
    age: int
    days_since_last_use: int
    created_at: datetime
    model_config = {"from_attributes": True}

class AssessmentInput(BaseModel):
    patient_id: str
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
        return {f: getattr(self, f) for f in [
            "self_efficacy_doubt", "emotional_distress", "anger_irritability",
            "unclear_thinking", "poor_concentration", "feeling_trapped",
            "sleep_disturbance", "craving_thoughts", "relapse_ideation",
            "recovery_actions",
        ]}

class XaiItem(BaseModel):
    feature_name: str
    feature_value: int
    contribution: float
    rank: int

class AssessmentResult(BaseModel):
    assessment_id: int
    patient_id: str
    assessment_date: date
    prediction_id: int
    predicted_label: int
    predicted_risk_percent: float
    category: str
    emoji: str
    total_score: int
    model_version: str
    xai: List[XaiItem]
    model_config = {"protected_namespaces": ()}

class FollowupCreate(BaseModel):
    assessment_id: int
    actual_relapse: conint(ge=0, le=1)  # type: ignore

class FollowupResponse(BaseModel):
    followup_id: int
    assessment_id: int
    actual_relapse: int
    reported_at: datetime
    model_config = {"from_attributes": True}

class HistoryEntry(BaseModel):
    assessment_id: int
    assessment_date: date
    predicted_label: Optional[int] = None
    predicted_risk_percent: Optional[float] = None
    category: Optional[str] = None
    actual_relapse: Optional[int] = None
    xai: List[XaiItem] = []

class MonitoringSummary(BaseModel):
    trend: str
    emoji: str
    recent_change: Optional[float] = None
    alert: Optional[str] = None
    weeks_tracked: int
    total_relapses: int

class HistoryResponse(BaseModel):
    summary: MonitoringSummary
    history: List[HistoryEntry]

class WeeklyCheckinCreate(BaseModel):
    patient_id: str
    actual_relapse: conint(ge=0, le=1)  # type: ignore

class WeeklyCheckinResponse(BaseModel):
    checkin_id: int
    patient_id: str
    actual_relapse: int
    reported_at: datetime
    model_config = {"from_attributes": True

}

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
    patient_id: str
    days: List[DailyTrendPoint]
    weeks: List[WeeklyTrendPoint]