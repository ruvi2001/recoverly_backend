"""Intervention Tools: Actual execution of actions"""

import random
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Load templates
TEMPLATES_DIR = Path(__file__).parent / "templates"

with open(TEMPLATES_DIR / "nudges.json", "r", encoding='utf-8') as f:
    NUDGE_TEMPLATES = json.load(f)

with open(TEMPLATES_DIR / "crisis_resources.json", "r", encoding='utf-8') as f:
    CRISIS_RESOURCES = json.load(f)

class InterventionTools:
    """ Tools for executing interventions
    
    Each tool:
    1. Performs the action
    2. Returns action details for logging
    3. Does not directly modify database (agent handles that)
    """
    def __init__(self, engine):
        """
        Args:
            engine: TemporalRiskEngine instance for database access
        """

        self.engine = engine

# NUDGE TOOLS

def send_buddy_connection_nudge(
    self,
    user_id: str,
    buddy_name: str = None,
    num_buddies: int = 1
) -> Dict:
    """ Send a nudge encouraging user to connect with buddies
    
        Returns:
           Action details for logging
    """
    # Select random template
    template = random.choice(NUDGE_TEMPLATES['buddy_connection'])

    # fill in placeholders
    message = template.format(
        buddy_name=buddy_name or "your buddy",
        num_buddies=num_buddies
    )

    #In production: Actually send to mobile app via push notification
    #For now: Log to database

    nudge_data = {
        'nudge_type': 'buddy_connection',
        'message': message,
        'buddy_suggested': buddy_name,
        'sent_at': datetime.now().isoformat()
    }

    # Store in social.nudges table
    with self.engine.get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO social.nudges (
                  user_id, nudge_type, nudge_message, risk_level, sent_at) VALUES (%s, %s, %s, %s, %s)
            """, (
                user_id,
                'buddy_connection',
                message,
                'MODERATE_RISK',       # Context-dependent
                datetime.now()
            ))

    return {
        'action_type': 'buddy_connection_nudge',
        'status': 'sent',
        'data': nudge_data
    }

def send_positive_reinforcement(self, user_id: str, days_sober: int = None) -> Dict:
    """Send encouraging message"""
    template = random.choice(NUDGE_TEMPLATES['positive_reinforcement'])
    message = template.format(days_sober=days_sober or "many")

    with self.engine.get_cursor() as cursor:
        cursor.execute("""
           INSERT INTO social.nudges (
            user_id, nudge_type, nudge_message, risk_level, sent_at
            ) VALUES (%s, %s, %s, %s, %s)
        """, (user_id, 'positive_reinforcement', message, 'LOW_RISK', datetime.now()))

    return {
        'action_type': 'positive_reinforcement',
        'status': 'sent',
        'data': {'message': message}
        }

# Escalation tools

def provide_crisis_resources(self, user_id: str) -> Dict:
    """
    Send crisis resources (hotlines, safety plan)

    """
    resources = {
        'hotlines': CRISIS_RESOURCES['crisis_hotlines'],
        'safety_plan': CRISIS_RESOURCES['safety_plan_steps'],
        'grounding': CRISIS_RESOURCES['grounding_exercises'][0]    # Send first exercise
    }

    # Format message
    message = f"""
        Crisis Resources Available 24/7:

        **National Suicide Prevention Lifeline**
        Call: 988
        Text: HOME to 741741

        **SAMHSA National Helpline**
        Call: 1-800-662-4357

        **Immediate Help**:
        If you're in immediate danger, please call 911 or go to your nearest emergency room.

        **Quick Grounding Exercise**:
        {resources['grounding']['name']}
        {chr(10).join('• ' + step for step in resources['grounding']['steps'])}

        You are not alone. Help is available.
    """
    with self.engine.get_cursor() as cursor:
        cursor.execute("""
          INSERT INTO social.nudges (
             user_id, nudge_type, nudge_message, risk_level, sent_at
             ) VALUES (%s, %s, %s, %s, %s)
        """, (user_id, 'crisis_resources', message, 'HIGH_RISK', datetime.now()))
    
    return {
        'action_type': 'crisis_resources',
        'status': 'sent',
        'data': resources
    }

def notify_counselor(
    self,
    user_id: str,
    risk_score: float,
    trigger_reason: str
) -> Dict:
    """
    Send alert to counselor
    """
    with self.engine.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO social.escalations (
                user_id, escalation_type, urgency, risk_score,
                trigger_reason, escalated_to, notification_method, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING escalation_id
        """, (
            user_id,
            'counselor_alert',
            'high',
            risk_score,
            trigger_reason,
            'counselor_on_duty',
            'in_app',
            'pending'
        ))

        escalation_id = cursor.fetchone()['escalation_id']

    return {
        'action_type': 'counselor_alert',
        'status': 'sent',
        'data': {
            'escalation_id': escalation_id,
            'urgency': 'high'
        }
    }

def schedule_urgent_meeting(self, user_id: str) -> Dict:
        """
        Auto-schedule urgent counselor meeting
        """
        # Find next available slot (simplified - in production, check actual calendar)
        scheduled_time = datetime.now() + timedelta(hours=2)
        
        with self.engine.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO social.meetings (
                    user_id, meeting_type, scheduled_time, duration_minutes,
                    counselor_id, user_consent, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING meeting_id
            """, (
                user_id,
                'emergency',
                scheduled_time,
                60,
                'counselor_emergency',
                False,  # Consent requested, not yet given
                'scheduled'
            ))
            
            meeting_id = cursor.fetchone()['meeting_id']
        
        return {
            'action_type': 'urgent_meeting_scheduled',
            'status': 'scheduled',
            'data': {
                'meeting_id': meeting_id,
                'scheduled_time': scheduled_time.isoformat()
            }
        }
    
  
# HELPER METHODS
   
    
def get_intervention_history(self, user_id: str, hours_back: int = 24) -> List[Dict]:
        """Get recent interventions for a user"""
        with self.engine.get_cursor() as cursor:
            cursor.execute("""
                SELECT action_type, timestamp 
                FROM social.actions
                WHERE user_id = %s
                  AND timestamp >= (CURRENT_TIMESTAMP - INTERVAL '%s hours')
                ORDER BY timestamp DESC
            """, (user_id, hours_back))
            
            return cursor.fetchall()
        