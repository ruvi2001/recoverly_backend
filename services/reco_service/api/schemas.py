from datetime import datetime
from typing import Any, Optional, Dict, List 

from pydantic import BaseModel, ConfigDict, Field


class RecommendationQuestionnaire(BaseModel):
    support_contact_frequency_during_stress: str = Field(
        ..., alias="Support_Contact_Frequency_During_Stress"
    )
    coping_self_efficacy_level: str = Field(
        ..., alias="Coping_Self_Efficacy_Level"
    )
    spiritual_activities_helpfulness_level: str = Field(
        ..., alias="Spiritual_Activities_Helpfulness_Level"
    )
    spiritual_activity_frequency: str = Field(
        ..., alias="Spiritual_Activity_Frequency"
    )
    peak_temptation_time_of_day: str = Field(
        ..., alias="Peak_Temptation_Time_of_Day"
    )
    current_exposure_to_active_users: str = Field(
        ..., alias="Current_Exposure_to_Active_Users"
    )
    response_to_substance_use_invitation: str = Field(
        ..., alias="Response_to_Substance_Use_Invitation"
    )
    readiness_for_continued_abstinence: str = Field(
        ..., alias="Readiness_for_Continued_Abstinence"
    )
    first_contact_during_craving: str = Field(
        ..., alias="First_Contact_During_Craving"
    )
    most_effective_coping_strategy: str = Field(
        ..., alias="Most_Effective_Coping_Strategy"
    )
    likely_companions_during_relapse: str = Field(
        ..., alias="Likely_Companions_During_Relapse"
    )
    most_needed_current_support_type: str = Field(
        ..., alias="Most_Needed_Current_Support_Type"
    )

    support_person_type: list[str] | str = Field(
        default_factory=list, alias="Support_Person_Type"
    )
    coping_strategies_used: list[str] | str = Field(
        default_factory=list, alias="Coping_Strategies_Used"
    )
    primary_motivation_for_abstinence: list[str] | str = Field(
        default_factory=list, alias="Primary_Motivation_for_Abstinence"
    )
    primary_trigger_factors: list[str] | str = Field(
        default_factory=list, alias="Primary_Trigger_Factors"
    )
    high_risk_locations: list[str] | str = Field(
        default_factory=list, alias="High_Risk_Locations"
    )
    recent_positive_recovery_actions: list[str] | str = Field(
        default_factory=list, alias="Recent_Positive_Recovery_Actions"
    )

    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    def payload_dict(self) -> dict[str, Any]:
        return {
            "support_contact_freq": self.support_contact_frequency_during_stress,
            "coping_efficacy": self.coping_self_efficacy_level,
            "sp_helpfulness": self.spiritual_activities_helpfulness_level,
            "sp_frequency": self.spiritual_activity_frequency,
            "peak_urge_time": self.peak_temptation_time_of_day,
            "exposure": self.current_exposure_to_active_users,
            "invite_response": self.response_to_substance_use_invitation,
            "readiness": self.readiness_for_continued_abstinence,
            "first_contact": self.first_contact_during_craving,
            "best_coping": self.most_effective_coping_strategy,
            "companion": self.likely_companions_during_relapse,
            "support_needed": self.most_needed_current_support_type,
            "support_people": self._ensure_list(self.support_person_type),
            "coping_choices": self._ensure_list(self.coping_strategies_used),
            "motivations": self._ensure_list(self.primary_motivation_for_abstinence),
            "triggers": self._ensure_list(self.primary_trigger_factors),
            "locations": self._ensure_list(self.high_risk_locations),
            "positive_steps": self._ensure_list(self.recent_positive_recovery_actions),
        }

    @staticmethod
    def _ensure_list(value: list[str] | str) -> list[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            value = value.strip()
            return [value] if value else []
        return []


class RecommendRequest(BaseModel):
    questionnaire: RecommendationQuestionnaire


class RecommendResponse(BaseModel):
    assessment_id: int
    recommendation_id: int
    user_id: str

    recommendation_family: str
    selected_action: str

    classifier_family: str
    classifier_confidence: float

    bandit_action: Optional[str]
    policy_mode: str
    policy_version: Optional[str]
    confidence: float

    recommendation_title: Optional[str] = None
    recommendation_message: Optional[str] = None
    
    created_at: datetime
    explanation: Optional[str] = None

    model_config = ConfigDict(protected_namespaces=())


class FeedbackRequest(BaseModel):
    recommendation_id: int
    helpful: int = Field(..., ge=0, le=1)
    rating: int = Field(..., ge=1, le=5)
    feedback_action: str | None = None


class FeedbackResponse(BaseModel):
    ok: bool
    recommendation_id: int
    helpful: int
    rating: int
    bandit_updated: bool


class RecommendationHistoryItem(BaseModel):
    recommendation_id: int
    recommendation_family: str
    selected_action: str
    classifier_family: str
    policy_mode: str
    confidence: float
    helpful: int | None = None
    rating: int | None = None
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    classifier_loaded: bool
    bandit_loaded: bool
    encoder_loaded: bool
    policy_loaded: bool
    actions: list[str]


class ActionFamiliesResponse(BaseModel):
    actions: list[str]
    action_descriptions: dict[str, str]


class ErrorResponse(BaseModel):
    detail: str
    extra: dict[str, Any] | None = None

class ARRSAnalyzeRequest(BaseModel):
    submitted_at: Optional[str] = None
    risk_level: Optional[str] = "Moderate"
    answers: dict[str, list[str]]

class ARRSAnalyzeResponse(BaseModel):
    predicted_family: str
    selected_action: str | dict | list
    recommendation: str | dict | list
    confidence: float | None = None


class ARRSSaveSessionRequest(BaseModel):
    submitted_at: Optional[str] = None
    risk_level: Optional[str] = "Moderate"
    predicted_category: str
    confidence: Optional[float] = None
    answers: dict[str, list[str]]
    recommendation: Any = None
    feedback_rating: int
    feedback_text: Optional[str] = ""


class ARRSSaveSessionResponse(BaseModel):
    ok: bool
    session_id: int
    message: str