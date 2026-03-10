"""
Test the complete intervention workflow
"""

from db.temporal_engine import get_engine
from ml.risk_analyzer import get_analyzer
from agent.intervention_agent import get_agent
import json
from datetime import datetime, timedelta

# Setup
engine = get_engine()

with open("ml/fusion_v2.json", "r") as f:
    config = json.load(f)
thresholds = config['thresholds']

# Create test user
user_id = "test_intervention_user"
engine.ensure_user_exists(user_id)

# Simulate messages showing decline
test_messages = [
    ("I'm doing okay today", {'p_craving': 0.1, 'p_relapse': 0.05, 'p_negative_mood': 0.2,
                              'p_neutral': 0.6, 'p_toxic': 0.05, 'p_isolation': 0.3, 'risk_score': 0.14}),
    
    ("Feeling a bit down", {'p_craving': 0.15, 'p_relapse': 0.1, 'p_negative_mood': 0.5,
                           'p_neutral': 0.2, 'p_toxic': 0.05, 'p_isolation': 0.4, 'risk_score': 0.35}),
    
    ("I don't want to talk to anyone", {'p_craving': 0.2, 'p_relapse': 0.15, 'p_negative_mood': 0.6,
                                        'p_neutral': 0.05, 'p_toxic': 0.0, 'p_isolation': 0.85, 'risk_score': 0.42}),
    
    ("I'm craving really bad", {'p_craving': 0.85, 'p_relapse': 0.3, 'p_negative_mood': 0.5,
                               'p_neutral': 0.05, 'p_toxic': 0.0, 'p_isolation': 0.6, 'risk_score': 0.85})
]

print("=" * 80)
print("INTERVENTION AGENT TEST")
print("=" * 80)

# Store messages over time
for i, (text, predictions) in enumerate(test_messages):
    ts = datetime.now() - timedelta(days=len(test_messages)-i-1)
    
    msg_id, pred_id = engine.store_message_with_prediction(
        user_id=user_id,
        message_text=text,
        predictions=predictions,
        conversation_type='buddy',
        timestamp=ts
    )
    
    print(f"\nDay {i+1}: '{text}'")
    print(f"  Risk Score: {predictions['risk_score']:.3f}")

# Update risk profile
print("\n" + "=" * 80)
print("COMPUTING RISK PROFILE")
print("=" * 80)

profile = engine.update_user_risk_profile(user_id, thresholds)

print(f"\nUser: {profile['user_id']}")
print(f"Risk Label: {profile['current_risk_label']}")
print(f"Risk Trend: {profile['trends']['risk']}")
print(f"\nReasons:")
for reason in profile['reasons']:
    print(f"  • {reason}")

# Trigger intervention agent
print("\n" + "=" * 80)
print("TRIGGERING INTERVENTION AGENT")
print("=" * 80)

agent = get_agent(engine)
actions = agent.process_user(profile)

print(f"\nActions taken: {len(actions)}")
for action in actions:
    print(f" {action['action_type']}: {action['status']}")

# Verify in database
print("\n" + "=" * 80)
print("VERIFYING IN DATABASE")
print("=" * 80)

import psycopg2
conn = psycopg2.connect(
    host="localhost",
    database="recoverly_platform",
    user="postgres",
    password="1234"
)
cursor = conn.cursor()

# Check social.actions
cursor.execute("SELECT COUNT(*) FROM social.actions WHERE user_id = %s", (user_id,))
action_count = cursor.fetchone()[0]
print(f"Actions logged in social.actions: {action_count}")

# Check social.nudges
cursor.execute("SELECT COUNT(*) FROM social.nudges WHERE user_id = %s", (user_id,))
nudge_count = cursor.fetchone()[0]
print(f"Nudges sent in social.nudges: {nudge_count}")

# Check social.escalations
cursor.execute("SELECT COUNT(*) FROM social.escalations WHERE user_id = %s", (user_id,))
escalation_count = cursor.fetchone()[0]
print(f"Escalations in social.escalations: {escalation_count}")

cursor.close()
conn.close()

print("\nTest complete!")