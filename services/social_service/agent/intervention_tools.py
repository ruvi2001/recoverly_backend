"""Intervention Tools: Actual execution of actions"""

import random
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Load templates
TEMPLATES_DIR = Path(__file__).parent / "templates"

with open(TEMPLATES_DIR / "nudges.json", "r", encoding="utf-8") as f:
    NUDGE_TEMPLATES = json.load(f)

with open(TEMPLATES_DIR / "crisis_resources.json", "r", encoding="utf-8") as f:
    CRISIS_RESOURCES = json.load(f)


class InterventionTools:
    """
    Tools for executing interventions.

    NOTE:
    - In your current implementation, tools DO write to DB (social.nudges, social.escalations, social.meetings).
    - The agent additionally logs a summary in social.actions.
    """

    def __init__(self, engine):
        self.engine = engine

    # -----------------------
    # NUDGE TOOLS
    # -----------------------
    def send_buddy_connection_nudge(
        self,
        user_id: str,
        buddy_name: Optional[str] = None,
        num_buddies: int = 1,
        risk_level: str = "MODERATE_RISK",
    ) -> Dict:
        """Send a nudge encouraging user to connect with buddies"""
        template = random.choice(NUDGE_TEMPLATES["buddy_connection"])
        message = template.format(
            buddy_name=buddy_name or "your buddy",
            num_buddies=num_buddies,
        )

        with self.engine.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO social.nudges (
                    user_id, nudge_type, nudge_message, risk_level, sent_at
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING nudge_id
                """,
                (user_id, "buddy_connection", message, risk_level, datetime.now()),
            )
            row = cursor.fetchone()
            nudge_id = row["nudge_id"] if row else None

        return {
            "action_type": "buddy_connection_nudge",
            "status": "sent",
            "data": {
                "nudge_id": nudge_id,
                "nudge_type": "buddy_connection",
                "message": message,
                "buddy_suggested": buddy_name,
                "sent_at": datetime.now().isoformat(),
            },
        }

    def send_positive_reinforcement(
        self,
        user_id: str,
        days_sober: Optional[int] = None,
        risk_level: str = "LOW_RISK",
    ) -> Dict:
        """Send encouraging message"""
        template = random.choice(NUDGE_TEMPLATES["positive_reinforcement"])
        message = template.format(days_sober=days_sober or "many")

        with self.engine.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO social.nudges (
                    user_id, nudge_type, nudge_message, risk_level, sent_at
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING nudge_id
                """,
                (user_id, "positive_reinforcement", message, risk_level, datetime.now()),
            )
            row = cursor.fetchone()
            nudge_id = row["nudge_id"] if row else None

        return {
            "action_type": "positive_reinforcement",
            "status": "sent",
            "data": {
                "nudge_id": nudge_id,
                "message": message,
            },
        }

    # -----------------------
    # ESCALATION TOOLS
    # -----------------------
    def provide_crisis_resources(self, user_id: str) -> Dict:
        """
        Send crisis resources (hotlines, safety plan)
        NOTE: Your resources file is US-based. Replace with Sri Lanka resources when ready.
        """
        resources = {
            "hotlines": CRISIS_RESOURCES.get("crisis_hotlines", []),
            "safety_plan": CRISIS_RESOURCES.get("safety_plan_steps", []),
            "grounding": (CRISIS_RESOURCES.get("grounding_exercises") or [{}])[0],
        }

        # Keep message short in-app
        grounding = resources.get("grounding") or {}
        grounding_steps = grounding.get("steps") or []
        grounding_block = "\n".join([f"• {s}" for s in grounding_steps[:5]])

        message = (
            "Support resources:\n\n"
            "If you feel unsafe or overwhelmed, please reach out to a trusted person or a counselor.\n\n"
            f"Quick grounding: {grounding.get('name','Grounding')}\n"
            f"{grounding_block}\n"
        )

        with self.engine.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO social.nudges (
                    user_id, nudge_type, nudge_message, risk_level, sent_at
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING nudge_id
                """,
                (user_id, "crisis_resources", message, "HIGH_RISK", datetime.now()),
            )
            row = cursor.fetchone()
            nudge_id = row["nudge_id"] if row else None

        return {
            "action_type": "crisis_resources",
            "status": "sent",
            "data": {
                "nudge_id": nudge_id,
                "resources": resources,
            },
        }

    def notify_counselor(self, user_id: str, risk_score: float, trigger_reason: str) -> Dict:
        """Create counselor escalation record"""
        with self.engine.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO social.escalations (
                    user_id, escalation_type, urgency, risk_score,
                    trigger_reason, escalated_to, notification_method, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING escalation_id
                """,
                (
                    user_id,
                    "counselor_alert",
                    "high",
                    risk_score,
                    trigger_reason,
                    "counselor_on_duty",
                    "in_app",
                    "pending",
                ),
            )
            row = cursor.fetchone()
            escalation_id = row["escalation_id"] if row else None

        return {
            "action_type": "counselor_alert",
            "status": "sent",
            "data": {"escalation_id": escalation_id, "urgency": "high"},
        }

    def schedule_urgent_meeting(self, user_id: str) -> Dict:
        """Auto-schedule urgent counselor meeting (demo scheduling)"""
        scheduled_time = datetime.now() + timedelta(hours=2)

        with self.engine.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO social.meetings (
                    user_id, meeting_type, scheduled_time, duration_minutes,
                    counselor_id, user_consent, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING meeting_id
                """,
                (
                    user_id,
                    "emergency",
                    scheduled_time,
                    60,
                    "counselor_emergency",
                    False,
                    "scheduled",
                ),
            )
            row = cursor.fetchone()
            meeting_id = row["meeting_id"] if row else None

        return {
            "action_type": "urgent_meeting_scheduled",
            "status": "scheduled",
            "data": {"meeting_id": meeting_id, "scheduled_time": scheduled_time.isoformat()},
        }

    # -----------------------
    # HELPERS
    # -----------------------
    def get_intervention_history(self, user_id: str, hours_back: int = 24) -> List[Dict]:
        """Get recent interventions for a user"""
        with self.engine.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT action_type, timestamp
                FROM social.actions
                WHERE user_id = %s
                  AND timestamp >= (CURRENT_TIMESTAMP - INTERVAL '%s hours')
                ORDER BY timestamp DESC
                """,
                (user_id, hours_back),
            )
            return cursor.fetchall()