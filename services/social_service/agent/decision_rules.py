"""
Decision Rules: Maps risk labels to intervention actions
"""

from typing import List, Dict

#Action definitions for each risk level
INTERVENTION_RULES = {
    'HIGH_RISK' : {
        'urgency': 'critical',
        'max_delay_hours': 2,
        'required_actions': [
            'provide_crisis_resources',
            'notify_counselor',
            'schedule_urgent_meeting'
        ],
        'optional_actions': [
            'request_family_notification'
        ],
        'constraints': {
            'max_per_day': 5,      #can send multiple in crisis
            'min_hours_between': 1
        }
    },
    'MODERATE_RISK': {
        'urgency': 'high',
        'max_delay_hours': 24,
        'required_actions': [
            'send_buddy_connection_nudge'
        ],
        'optional_actions': [
            'send_counselor_encouragement',
            'recommend_coping_exercises'
        ],
        'constraints': {
            'max_per_day': 2,
            'min_hours_between': 12
        }
    },
    'ISOLATION_ONLY': {
        'urgency': 'medium',
        'max_delay_hours': 48,
        'required_actions': [
            'send_buddy_suggestion'
        ],
        'optional_actions': [
            'recommend_group_activity',
            'schedule_wellness_check'
        ],
        'constraints': {
            'max_per_day': 2,
            'min_hours_between': 24
        }
    },
    'LOW_RISK': {
        'urgency': 'low',
        'max_delay_hours': 168,         # 1 week
        'required_actions': [
            'send_positive_reinforcement'
        ],
        'optional_actions': [],
        'constraints': {
          'max_per_day': 1,
          'min_hours_between': 72
        }
    }
}

def get_actions_for_risk_level(risk_label: str) -> Dict:
    """"Get intervention actions for a risk level"""
    return INTERVENTION_RULES.get(risk_label, INTERVENTION_RULES['LOW_RISK'])

def should_send_intervention(
    risk_label: str,
    last_intervention_hours_ago: float,
    interventions_today: int
) -> bool:
    """ 
    Check if we should send an intervention
    Prevents spam by checking:
    - Time since last intervention
    - Number of interventions today
    """
    rules = get_actions_for_risk_level(risk_label)
    constraints = rules['constraints']
    
    # Check daily limits
    if interventions_today >= constraints['max_per_day']:
        return False

    # Check time between interventions
    if last_intervention_hours_ago < constraints['min_hours_between']:
       return False

    return True