"""
Intervention Agent: Autonomous decision-making and action execution
"""

from datetime import datetime, timedelta
from typing import Dict, List
import logging

from .decision_rules import get_actions_for_risk_level, should_send_intervention
from .intervention_tools import InterventionTools

logger = logging.getLogger(__name__)

class InterventionAgent:
    """
    Autonomous agent that:
    1. Analyzes user risk profile
    2. Decides what actions to take
    3. Executes interventions
    4. Logs everything
    """
    
    def __init__(self, engine):
        """
        Args:
            engine: TemporalRiskEngine instance
        """
        self.engine = engine
        self.tools = InterventionTools(engine)
    
    def process_user(self, risk_profile: Dict) -> List[Dict]:
        """
        Main entry point: Process a user and trigger interventions
        
        Args:
            risk_profile: Output from engine.update_user_risk_profile()
        
        Returns:
            List of actions taken
        """
        user_id = risk_profile['user_id']
        risk_label = risk_profile['current_risk_label']
        
        logger.info(f"Processing user {user_id} with risk label: {risk_label}")
        
        # Get intervention rules for this risk level
        rules = get_actions_for_risk_level(risk_label)
        
        # Check if we should send intervention (prevent spam)
        if not self._should_intervene(user_id, risk_label):
            logger.info(f"Skipping intervention for {user_id} (frequency limit)")
            return []
        
        # Execute interventions
        actions_taken = []
        
        # Execute required actions
        for action_name in rules['required_actions']:
            try:
                action_result = self._execute_action(
                    action_name, 
                    user_id, 
                    risk_profile
                )
                actions_taken.append(action_result)
                
                # Log to social.actions
                self._log_action(user_id, action_result, risk_label)
                
            except Exception as e:
                logger.error(f"Failed to execute {action_name}: {e}")
        
        logger.info(f"Completed {len(actions_taken)} interventions for {user_id}")
        
        return actions_taken
    
    def _should_intervene(self, user_id: str, risk_label: str) -> bool:
        """
        Check if we should send intervention based on frequency limits
        """
        # Get recent interventions
        with self.engine.get_cursor() as cursor:
            # Count interventions today
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM social.actions
                WHERE user_id = %s
                  AND timestamp >= (CURRENT_TIMESTAMP - INTERVAL '24 hours')
            """, (user_id,))
            interventions_today = cursor.fetchone()['count']
            
            # Get last intervention time
            cursor.execute("""
                SELECT timestamp
                FROM social.actions
                WHERE user_id = %s
                ORDER BY timestamp DESC
                LIMIT 1
            """, (user_id,))
            last_intervention = cursor.fetchone()
        
        if last_intervention:
            hours_ago = (datetime.now() - last_intervention['timestamp']).total_seconds() / 3600
        else:
            hours_ago = 999  # No previous intervention
        
        # Check against rules
        return should_send_intervention(risk_label, hours_ago, interventions_today)
    
    def _execute_action(
        self, 
        action_name: str, 
        user_id: str, 
        risk_profile: Dict
    ) -> Dict:
        """
        Execute a specific intervention action
        """
        logger.info(f"Executing {action_name} for {user_id}")
        
        # Map action names to tool methods
        action_map = {
            'provide_crisis_resources': lambda: self.tools.provide_crisis_resources(user_id),
            
            'notify_counselor': lambda: self.tools.notify_counselor(
                user_id,
                risk_profile['short_window']['max_risk_score'],
                ', '.join(risk_profile['reasons'])
            ),
            
            'schedule_urgent_meeting': lambda: self.tools.schedule_urgent_meeting(user_id),
            
            'send_buddy_connection_nudge': lambda: self.tools.send_buddy_connection_nudge(
                user_id,
                buddy_name="your buddy",  # In production: get actual buddy
                num_buddies=risk_profile['engagement'].get('buddy_count', 1)
            ),
            
            'send_positive_reinforcement': lambda: self.tools.send_positive_reinforcement(
                user_id,
                days_sober=None  # In production: calculate from user data
            ),
            
            'send_buddy_suggestion': lambda: self.tools.send_buddy_connection_nudge(
                user_id,
                buddy_name="a friend"
            ),
            
            'send_counselor_encouragement': lambda: self.tools.notify_counselor(
                user_id,
                risk_profile['short_window']['avg_risk_score'],
                "Moderate risk - encouragement needed"
            ),
            
            'recommend_coping_exercises': lambda: {
                'action_type': 'coping_exercise',
                'status': 'sent',
                'data': {'message': 'Try the 5-4-3-2-1 grounding technique'}
            },
            
            'recommend_group_activity': lambda: {
                'action_type': 'group_activity',
                'status': 'sent',
                'data': {'message': 'Weekly group session available'}
            },
            
            'schedule_wellness_check': lambda: {
                'action_type': 'wellness_check',
                'status': 'scheduled',
                'data': {'scheduled_time': (datetime.now() + timedelta(days=1)).isoformat()}
            }
        }
        
        # Execute the action
        if action_name in action_map:
            return action_map[action_name]()
        else:
            logger.warning(f"Unknown action: {action_name}")
            return {
                'action_type': action_name,
                'status': 'not_implemented',
                'data': {}
            }
    
    def _log_action(self, user_id: str, action_result: Dict, risk_label: str):
        """
        Log action to social.actions table
        """
        action_id = self.engine.log_action(
            user_id=user_id,
            action_type=action_result['action_type'],
            risk_level=risk_label,
            action_data=action_result.get('data', {}),
            ai_reasoning=f"Triggered by risk label: {risk_label}",
            confidence_score=0.85  # Placeholder
        )
        
        logger.info(f"Logged action {action_id} for {user_id}")



# HELPER: Get or create agent instance


_agent_instance = None

def get_agent(engine):
    """Get or create intervention agent"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = InterventionAgent(engine)
    return _agent_instance