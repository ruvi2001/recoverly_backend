from db.temporal_engine import TemporalRiskEngine
import json

# Initialize 
engine = TemporalRiskEngine(
    host = "localhost",
    database = "recoverly_platform",
    user = "postgres",
    password = "1234"
)

print(" Connected and verified tables")

# Load fusion config
with open("ml/fusion_v2.json", "r") as f:
    config = json.load(f)
thresholds = config["thresholds"]

# create a test user in core.users first
import psycopg2
conn = psycopg2.connect(
    host="localhost",
    database="recoverly_platform",
    user="postgres",
    password="1234"
)
cursor = conn.cursor()
cursor.execute("""
      INSERT INTO core.users (user_id, username, email)
      VALUES ('test_user_001', 'testuser', 'test@example.com')
      ON CONFLICT (user_id) DO NOTHING
      """)
conn.commit()
cursor.close()
conn.close()

print("Test user created")

# test storing message with predictions
user_id = "test_user_001"
message_text = "I'm feeling really down and isolated today"
predictions = {
    'p_craving': 0.15,
    'p_relapse': 0.10,
    'p_negative_mood': 0.70,
    'p_neutral': 0.05,
    'p_toxic': 0.0,
    'p_isolation': 0.85,
    'risk_score': 0.49
}

# store in BOTH core.messages AND social.message_predictions
msg_id, pred_id = engine.store_message_with_prediction(
    user_id=user_id,
    message_text=message_text,
    predictions=predictions,
    conversation_type='buddy'
)

print(f"stored message {msg_id} with prediction {pred_id}")

# update risk profile
profile = engine.update_user_risk_profile(user_id, thresholds)

print(f"\n Risk Profile:")
print(f"user: {profile['user_id']}")
print(f" Risk Label: {profile['current_risk_label']}")
print(f" Reasons: {', '.join(profile['reasons'])}")

engine.close()
print("\n all tests passed.")


