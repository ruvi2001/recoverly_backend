"""
Temporal Risk Aggregation Engine - Social Service
Uses existing tables in 'social' schema of 'recoverly_platform' database
Aligned with actual database initialization script
"""

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import numpy as np
import json
from contextlib import contextmanager


class TemporalRiskEngine:
    """
    Aggregates message-level risk predictions into user-level risk profiles
    
    IMPORTANT: This version uses the ACTUAL tables created in social schema
    - Does NOT create its own tables
    - Uses social.message_predictions (with message_id FK to core.messages)
    - Uses social.user_risk_profiles
    - Uses social.actions for interventions
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "recoverly_platform",
        user: str = "postgres",
        password: str = "1234",
        min_conn: int = 1,
        max_conn: int = 10,
        schema: str = "social"
    ):
        """
        Initialize with PostgreSQL connection parameters
        
        Args:
            host: PostgreSQL host
            port: PostgreSQL port  
            database: Database name (recoverly_platform)
            user: Database user
            password: Database password
            min_conn: Minimum connections in pool
            max_conn: Maximum connections in pool
            schema: Schema to use (default: social)
        """
        self.schema = schema
        
        try:
            # Create connection pool for concurrent access
            self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
                min_conn,
                max_conn,
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                options=f'-c search_path={schema},core'  # Access social + core schemas
            )
            
            # Verify tables exist (don't create them - they should already exist)
            self._verify_tables()
            
        except psycopg2.Error as e:
            raise Exception(f"Failed to connect to PostgreSQL: {e}")
    
    @contextmanager
    def get_cursor(self, cursor_factory=RealDictCursor):
        """
        Context manager for database connections from pool
        Ensures connections are properly returned to pool
        """
        conn = self.connection_pool.getconn()
        try:
            cursor = conn.cursor(cursor_factory=cursor_factory)
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
    
    def _verify_tables(self):
        """
        Verify that required tables exist in social schema
        Does NOT create tables - they should be created by database init script
        """
        required_tables = [
            'message_predictions',
            'user_risk_profiles',
            'actions',
            'nudges',
            'escalations',
            'meetings'
        ]
        
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = %s
            """, (self.schema,))
            
            existing_tables = [row['table_name'] for row in cursor.fetchall()]
            
            missing = set(required_tables) - set(existing_tables)
            if missing:
                raise Exception(
                    f"Missing tables in {self.schema} schema: {missing}. "
                    "Please run the database initialization script first."
                )
    
    def ensure_user_exists(
        self, 
        user_id: str, 
        username: str = None, 
        email: str = None,
        full_name: str = None
    ):
        """
        Ensure user exists in core.users table
        
        Creates user if doesn't exist (for testing/development)
        In production, assume mobile app creates users
        
        Args:
            user_id: Unique user identifier
            username: Username (defaults to user_id)
            email: Email (defaults to user_id@recoverly.app)
            full_name: Full name (optional)
        """
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO core.users (user_id, username, email, full_name, status)
                VALUES (%s, %s, %s, %s, 'active')
                ON CONFLICT (user_id) DO NOTHING
            """, (
                user_id, 
                username or user_id, 
                email or f"{user_id}@recoverly.app",
                full_name
            ))

    def store_message_prediction(
        self,
        user_id: str,
        message_id: int,  # ← FK to core.messages
        predictions: Dict[str, float],
        conversation_type: str = 'buddy',
        timestamp: Optional[datetime] = None
    ) -> int:
        """
        Store predictions for a message
        
        IMPORTANT: Message text should already be in core.messages
        This only stores the ML predictions
        
        Args:
            user_id: User identifier
            message_id: ID from core.messages table
            predictions: Dict with p_craving, p_relapse, p_negative_mood, 
                        p_neutral, p_toxic, p_isolation, risk_score
            conversation_type: 'buddy' or 'counselor'
            timestamp: Prediction timestamp
        
        Returns:
            prediction_id: ID of inserted prediction record
        """
        with self.get_cursor() as cursor:
            ts = timestamp or datetime.now()
            
            cursor.execute(f"""
                INSERT INTO {self.schema}.message_predictions (
                    message_id, user_id, timestamp,
                    p_craving, p_relapse, p_negative_mood, p_neutral, p_toxic,
                    p_isolation, risk_score, conversation_type
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                message_id, user_id, ts,
                predictions.get('p_craving', 0.0),
                predictions.get('p_relapse', 0.0),
                predictions.get('p_negative_mood', 0.0),
                predictions.get('p_neutral', 0.0),
                predictions.get('p_toxic', 0.0),
                predictions.get('p_isolation', 0.0),
                predictions.get('risk_score', 0.0),
                conversation_type
            ))
            
            result = cursor.fetchone()
            return result['id']
    
    def store_message_with_prediction(
        self,
        user_id: str,
        message_text: str,
        predictions: Dict[str, float],
        conversation_type: str = 'buddy',
        recipient_id: Optional[str] = None,
        conversation_id: Optional[int] = None,
        timestamp: Optional[datetime] = None
    ) -> Tuple[int, int]:
        """
        Store message in core.messages AND predictions in social.message_predictions
        
        Use this when you receive a message from the mobile app
        
        Returns:
            (message_id, prediction_id)
        """
        with self.get_cursor() as cursor:
            ts = timestamp or datetime.now()
            
            # 1. Store message in core.messages
            cursor.execute("""
                INSERT INTO core.messages (
                    user_id, message_text, timestamp, conversation_type, recipient_id, conversation_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING message_id
            """, (user_id, message_text, ts, conversation_type, recipient_id, conversation_id))
            
            message_id = cursor.fetchone()['message_id']
            
            # 2. Store predictions in social.message_predictions
            cursor.execute(f"""
                INSERT INTO {self.schema}.message_predictions (
                    message_id, user_id, timestamp,
                    p_craving, p_relapse, p_negative_mood, p_neutral, p_toxic,
                    p_isolation, risk_score, conversation_type
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                message_id, user_id, ts,
                predictions.get('p_craving', 0.0),
                predictions.get('p_relapse', 0.0),
                predictions.get('p_negative_mood', 0.0),
                predictions.get('p_neutral', 0.0),
                predictions.get('p_toxic', 0.0),
                predictions.get('p_isolation', 0.0),
                predictions.get('risk_score', 0.0),
                conversation_type
            ))
            
            prediction_id = cursor.fetchone()['id']
            
            return message_id, prediction_id
    
    def get_user_messages(
        self, 
        user_id: str, 
        days_back: int = 30
    ) -> List[Dict]:
        """
        Get user's messages with predictions by joining core.messages and social.message_predictions
        """
        with self.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT 
                    m.message_id,
                    m.message_text,
                    m.timestamp,
                    p.p_craving,
                    p.p_relapse,
                    p.p_negative_mood,
                    p.p_neutral,
                    p.p_toxic,
                    p.p_isolation,
                    p.risk_score,
                    p.conversation_type
                FROM core.messages m
                JOIN {self.schema}.message_predictions p ON m.message_id = p.message_id
                WHERE m.user_id = %s
                  AND m.timestamp >= (CURRENT_TIMESTAMP - INTERVAL '%s days')
                ORDER BY m.timestamp ASC
            """, (user_id, days_back))
            
            return cursor.fetchall()
    
    def compute_window_metrics(
        self, 
        messages: List[Dict],
        window_days: int,
        thresholds: Dict
    ) -> Dict:
        """
        Compute aggregated metrics over a time window
        """
        if not messages:
            return {
                'avg_risk_score': 0.0,
                'max_risk_score': 0.0,
                'avg_isolation': 0.0,
                'high_risk_count': 0,
                'toxic_incidents': 0,
                'message_count': 0
            }
        
        # Filter to window
        cutoff = datetime.now() - timedelta(days=window_days)
        windowed = [m for m in messages if m['timestamp'] >= cutoff]
        
        if not windowed:
            return {
                'avg_risk_score': 0.0,
                'max_risk_score': 0.0,
                'avg_isolation': 0.0,
                'high_risk_count': 0,
                'toxic_incidents': 0,
                'message_count': 0
            }
        
        risk_scores = [m['risk_score'] for m in windowed]
        isolation_probs = [m['p_isolation'] for m in windowed]
        
        # Count high-risk messages using thresholds
        high_risk_count = sum(
            1 for m in windowed 
            if m['risk_score'] >= thresholds.get('T_high', 0.7) or 
               m['p_relapse'] >= thresholds.get('T_relapse', 0.5) or 
               m['p_craving'] >= thresholds.get('T_craving', 0.5)
        )
        
        toxic_incidents = sum(
            1 for m in windowed 
            if m['p_toxic'] >= thresholds.get('T_toxic', 0.7)
        )
        
        return {
            'avg_risk_score': float(np.mean(risk_scores)),
            'max_risk_score': float(np.max(risk_scores)),
            'avg_isolation': float(np.mean(isolation_probs)),
            'high_risk_count': high_risk_count,
            'toxic_incidents': toxic_incidents,
            'message_count': len(windowed)
        }
    
    def detect_trend(
        self,
        messages: List[Dict],
        metric: str = 'risk_score'
    ) -> str:
        """
        Detect if user's risk is improving, stable, or declining
        
        Returns:
            'improving', 'stable', 'declining', or 'rapid_decline'
        """
        if len(messages) < 5:
            return 'stable'
        
        now = datetime.now()
        recent_7d = [m for m in messages if (now - m['timestamp']).days <= 7]
        previous_7d = [m for m in messages if 7 < (now - m['timestamp']).days <= 14]
        
        if not recent_7d or not previous_7d:
            return 'stable'
        
        recent_avg = np.mean([m[metric] for m in recent_7d])
        previous_avg = np.mean([m[metric] for m in previous_7d])
        
        delta = recent_avg - previous_avg
        
        # Check for rapid decline (spike in last 2 days)
        last_2d = [m for m in messages if (now - m['timestamp']).days <= 2]
        if last_2d:
            last_2d_max = max(m[metric] for m in last_2d)
            if last_2d_max >= 0.8:
                return 'rapid_decline'
        
        if delta < -0.15:
            return 'improving'
        elif delta > 0.15:
            return 'declining'
        else:
            return 'stable'
    
    def compute_engagement_metrics(
        self,
        user_id: str,
        messages: List[Dict]
    ) -> Dict:
        """
        Compute engagement metrics
        """
        now = datetime.now()
        
        messages_7d = [m for m in messages if (now - m['timestamp']).days <= 7]
        
        buddy_msgs = [m for m in messages_7d if m.get('conversation_type') == 'buddy']
        counselor_msgs = [m for m in messages_7d if m.get('conversation_type') == 'counselor']
        
        if buddy_msgs:
            last_buddy = max(m['timestamp'] for m in buddy_msgs)
            days_since_buddy = (now - last_buddy).days
        else:
            days_since_buddy = 999
        
        if messages:
            last_msg_time = max(m['timestamp'] for m in messages)
        else:
            last_msg_time = None
        
        return {
            'total_messages_7d': len(messages_7d),
            'buddy_messages_7d': len(buddy_msgs),
            'counselor_messages_7d': len(counselor_msgs),
            'last_message_time': last_msg_time,
            'days_since_last_buddy_msg': days_since_buddy
        }
    
    def apply_final_risk_decision(
        self,
        short_metrics: Dict,
        medium_metrics: Dict,
        engagement: Dict,
        risk_trend: str,
        isolation_trend: str,
        thresholds: Dict
    ) -> Tuple[str, List[str]]:
        """
        Apply fusion_v2 logic to determine final risk label
        """
        reasons = []
        
        short_max_risk = short_metrics['max_risk_score']
        short_avg_risk = short_metrics['avg_risk_score']
        short_high_count = short_metrics['high_risk_count']
        short_avg_iso = short_metrics['avg_isolation']
        
        # HIGH RISK
        if short_max_risk >= thresholds.get('T_high', 0.7):
            reasons.append(f"Max risk score in last 7 days: {short_max_risk:.3f}")
            return 'HIGH_RISK', reasons
        
        if short_high_count >= 3:
            reasons.append(f"Multiple high-risk messages: {short_high_count}")
            return 'HIGH_RISK', reasons
        
        if risk_trend == 'rapid_decline':
            reasons.append("Rapid decline detected")
            return 'HIGH_RISK', reasons
        
        if short_avg_risk >= thresholds.get('T_iso_escalate', 0.7) and \
           short_avg_iso >= thresholds.get('T_iso', 0.9):
            reasons.append("Isolation escalating moderate risk")
            return 'HIGH_RISK', reasons
        
        # MODERATE RISK
        if short_avg_risk >= thresholds.get('T_mid', 0.3):
            reasons.append(f"Elevated average risk: {short_avg_risk:.3f}")
            return 'MODERATE_RISK', reasons
        
        if risk_trend == 'declining':
            reasons.append("Risk trend declining (worsening)")
            return 'MODERATE_RISK', reasons
        
        if engagement['days_since_last_buddy_msg'] > 5 and short_avg_risk > 0.2:
            reasons.append("Social withdrawal + mild risk")
            return 'MODERATE_RISK', reasons
        
        # ISOLATION ONLY
        if short_avg_iso >= thresholds.get('T_iso', 0.9) and short_avg_risk < 0.3:
            reasons.append("High isolation without addiction risk")
            return 'ISOLATION_ONLY', reasons
        
        # LOW RISK
        reasons.append("No significant risk indicators")
        return 'LOW_RISK', reasons
    
    def update_user_risk_profile(
        self, 
        user_id: str,
        thresholds: Dict
    ) -> Dict:
        """
        Compute and store complete risk profile for a user
        
        Updates social.user_risk_profiles table
        """
        # Get messages with predictions
        messages = self.get_user_messages(user_id, days_back=30)
        
        if not messages:
            return {
                'user_id': user_id,
                'current_risk_label': 'LOW_RISK',
                'message_count': 0,
                'reasons': ['No message history']
            }
        
        # Compute metrics
        short_metrics = self.compute_window_metrics(messages, 7, thresholds)
        medium_metrics = self.compute_window_metrics(messages, 30, thresholds)
        
        # Detect trends
        risk_trend = self.detect_trend(messages, 'risk_score')
        isolation_trend = self.detect_trend(messages, 'p_isolation')
        
        # Engagement
        engagement = self.compute_engagement_metrics(user_id, messages)
        
        # Final decision
        risk_label, reasons = self.apply_final_risk_decision(
            short_metrics, medium_metrics, engagement,
            risk_trend, isolation_trend, thresholds
        )
        
        # Store in database
        with self.get_cursor() as cursor:
            now = datetime.now()
            
            # Check if label changed
            cursor.execute(f"""
                SELECT current_risk_label, risk_label_since 
                FROM {self.schema}.user_risk_profiles 
                WHERE user_id = %s
            """, (user_id,))
            
            existing = cursor.fetchone()
            
            if existing and existing['current_risk_label'] == risk_label:
                risk_label_since = existing['risk_label_since']
            else:
                risk_label_since = now
            
            # Update user_risk_profiles
            cursor.execute(f"""
                INSERT INTO {self.schema}.user_risk_profiles (
                    user_id, last_updated,
                    short_avg_risk_score, short_max_risk_score, short_avg_isolation,
                    short_high_risk_count, short_toxic_incidents,
                    medium_avg_risk_score, medium_max_risk_score, medium_avg_isolation,
                    risk_trend, isolation_trend,
                    current_risk_label, risk_label_since,
                    total_messages_7d, buddy_messages_7d, counselor_messages_7d,
                    last_message_time, days_since_last_buddy_msg,
                    reasons
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (user_id) DO UPDATE SET
                    last_updated = EXCLUDED.last_updated,
                    short_avg_risk_score = EXCLUDED.short_avg_risk_score,
                    short_max_risk_score = EXCLUDED.short_max_risk_score,
                    short_avg_isolation = EXCLUDED.short_avg_isolation,
                    short_high_risk_count = EXCLUDED.short_high_risk_count,
                    short_toxic_incidents = EXCLUDED.short_toxic_incidents,
                    medium_avg_risk_score = EXCLUDED.medium_avg_risk_score,
                    medium_max_risk_score = EXCLUDED.medium_max_risk_score,
                    medium_avg_isolation = EXCLUDED.medium_avg_isolation,
                    risk_trend = EXCLUDED.risk_trend,
                    isolation_trend = EXCLUDED.isolation_trend,
                    current_risk_label = EXCLUDED.current_risk_label,
                    risk_label_since = EXCLUDED.risk_label_since,
                    total_messages_7d = EXCLUDED.total_messages_7d,
                    buddy_messages_7d = EXCLUDED.buddy_messages_7d,
                    counselor_messages_7d = EXCLUDED.counselor_messages_7d,
                    last_message_time = EXCLUDED.last_message_time,
                    days_since_last_buddy_msg = EXCLUDED.days_since_last_buddy_msg,
                    reasons = EXCLUDED.reasons
            """, (
                user_id, now,
                short_metrics['avg_risk_score'], short_metrics['max_risk_score'],
                short_metrics['avg_isolation'], short_metrics['high_risk_count'],
                short_metrics['toxic_incidents'],
                medium_metrics['avg_risk_score'], medium_metrics['max_risk_score'],
                medium_metrics['avg_isolation'],
                risk_trend, isolation_trend,
                risk_label, risk_label_since,
                engagement['total_messages_7d'], engagement['buddy_messages_7d'],
                engagement['counselor_messages_7d'], engagement['last_message_time'],
                engagement['days_since_last_buddy_msg'],
                Json(reasons)
            ))
        
        return {
            'user_id': user_id,
            'current_risk_label': risk_label,
            'risk_label_since': risk_label_since,
            'reasons': reasons,
            'short_window': short_metrics,
            'medium_window': medium_metrics,
            'engagement': engagement,
            'trends': {
                'risk': risk_trend,
                'isolation': isolation_trend
            },
            'last_updated': now
        }
    
    def get_users_needing_check_in(self, days_silent: int = 3) -> List[str]:
        """Get users who need check-ins"""
        with self.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT user_id 
                FROM {self.schema}.user_risk_profiles
                WHERE days_since_last_buddy_msg >= %s
                  AND current_risk_label != 'HIGH_RISK'
                ORDER BY days_since_last_buddy_msg DESC
            """, (days_silent,))
            
            return [row['user_id'] for row in cursor.fetchall()]
    
    def get_all_user_profiles(self) -> List[Dict]:
        """Get all user risk profiles"""
        with self.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT 
                    user_id, current_risk_label, risk_trend, isolation_trend,
                    short_avg_risk_score, short_avg_isolation,
                    days_since_last_buddy_msg, last_updated
                FROM {self.schema}.user_risk_profiles
                ORDER BY 
                    CASE current_risk_label
                        WHEN 'HIGH_RISK' THEN 1
                        WHEN 'MODERATE_RISK' THEN 2
                        WHEN 'ISOLATION_ONLY' THEN 3
                        ELSE 4
                    END,
                    short_avg_risk_score DESC
            """)
            
            return cursor.fetchall()
    
    def log_action(
        self,
        user_id: str,
        action_type: str,
        risk_level: str,
        action_data: Dict,
        ai_reasoning: Optional[str] = None,
        confidence_score: Optional[float] = None
    ) -> int:
        """
        Log an action in social.actions table
        
        This replaces the old "interventions" table
        """
        with self.get_cursor() as cursor:
            cursor.execute(f"""
                INSERT INTO {self.schema}.actions (
                    user_id, action_type, risk_level, action_data,
                    ai_reasoning, confidence_score
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING action_id
            """, (
                user_id, action_type, risk_level, 
                Json(action_data), ai_reasoning, confidence_score
            ))
            
            return cursor.fetchone()['action_id']

    def get_or_create_one_to_one_conversation(self, user_id: str, other_user_id: str, conversation_type: str) -> int:
        if conversation_type not in ("buddy", "counselor"):
            raise ValueError("conversation_type must be 'buddy' or 'counselor'")

        u1, u2 = sorted([user_id, other_user_id])

        with self.get_cursor() as cursor:
            # Find existing 1-1 conversation between these exact 2 users
            cursor.execute("""
               SELECT c.conversation_id
               FROM core.conversations c
               JOIN core.conversation_participants p1 ON p1.conversation_id = c.conversation_id
               JOIN core.conversation_participants p2 ON p2.conversation_id = c.conversation_id
               WHERE c.conversation_type = %s
                  AND p1.user_id = %s
                  AND p2.user_id = %s
                  AND p1.user_id < p2.user_id  -- Ensure p1 and p2 are different rows
                  -- Ensure conversation has EXACTLY 2 participants (no more, no less)
                  AND (SELECT COUNT(*) FROM core.conversation_participants 
                       WHERE conversation_id = c.conversation_id) = 2
               LIMIT 1
            """, (conversation_type, u1, u2))

            row = cursor.fetchone()
            if row:
                return int(row["conversation_id"])

            # create new conversation and get id
            cursor.execute("""
                INSERT INTO core.conversations (conversation_type)
                VALUES (%s)
                RETURNING conversation_id
            """, (conversation_type,))
            conversation_id = int(cursor.fetchone()["conversation_id"])
            
            # Insert participants using the conversation id
            cursor.execute("""
                INSERT INTO core.conversation_participants (conversation_id, user_id) VALUES (%s, %s), (%s, %s)
            """, (conversation_id, u1, conversation_id, u2))

            return conversation_id

    def assert_user_in_conversation(self, conversation_id: int, user_id: str) -> None:
        with self.get_cursor() as cursor:
            cursor.execute("""
               SELECT 1
               FROM core.conversation_participants
               WHERE conversation_id = %s AND user_id = %s
               LIMIT 1
            """, (conversation_id, user_id))
            
            if not cursor.fetchone():
                raise ValueError("User not in conversation")

    def get_other_participant(self, conversation_id: int, my_user_id: str) -> str:
        with self.get_cursor() as cursor:
            cursor.execute("""
               SELECT user_id
               FROM core.conversation_participants
               WHERE conversation_id = %s AND user_id <> %s
               LIMIT 1
            """, (conversation_id, my_user_id))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Conversation not found or not 1:1")
            return row["user_id"]
    
    def close(self):
        """Close all connections"""
        if self.connection_pool:
            self.connection_pool.closeall()
    

    def list_conversations_for_user(self, user_id: str):
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    c.conversation_id,
                    c.conversation_type,
                    (
                        SELECT cp.user_id
                        FROM core.conversation_participants cp
                        WHERE cp.conversation_id = c.conversation_id AND cp.user_id <> %s
                        LIMIT 1
                    ) AS other_user_id,
                    m.message_text AS last_message_text,
                    m.timestamp AS last_message_time
                FROM core.conversations c
                JOIN core.conversation_participants p ON p.conversation_id = c.conversation_id
                LEFT JOIN LATERAL (
                    SELECT message_text, timestamp
                    FROM core.messages
                    WHERE conversation_id = c.conversation_id
                    ORDER BY timestamp DESC
                    LIMIT 1
            ) m ON TRUE
            WHERE p.user_id = %s
            ORDER BY COALESCE(m.timestamp, c.created_at) DESC
        """, (user_id, user_id))
            
            rows = cursor.fetchall()
            return rows

    def get_messages(self, conversation_id: int, limit: int = 50):
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT message_id, user_id, recipient_id, message_text, timestamp, conversation_type, metadata
                FROM core.messages
                WHERE conversation_id = %s
                ORDER BY timestamp ASC
                LIMIT %s
            """, (conversation_id, limit))

            rows = cursor.fetchall()
            return rows

# Singleton instance
_engine_instance = None

def get_engine() -> TemporalRiskEngine:
    """Get or create engine instance"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = TemporalRiskEngine()
    return _engine_instance


# Test
if __name__ == "__main__":
    print("=" * 80)
    print("Temporal Risk Engine - Testing with Actual Schema")
    print("=" * 80)
    
    try:
        engine = TemporalRiskEngine(
            host="localhost",
            database="recoverly_platform",
            user="postgres",
            password="1234"
        )
        print("✓ Connected successfully")
        print("✓ Verified tables exist in social schema")
        
        # Load fusion config
        with open("../ml/fusion_v2.json", "r") as f:
            config = json.load(f)
        thresholds = config['thresholds']
        
        # Test storing a message with prediction
        print("\nTesting message storage...")
        test_user = "test_user_001"
        test_msg = "I'm feeling really down today"
        test_predictions = {
            'p_craving': 0.15,
            'p_relapse': 0.10,
            'p_negative_mood': 0.65,
            'p_neutral': 0.05,
            'p_toxic': 0.05,
            'p_isolation': 0.75,
            'risk_score': 0.455
        }
        
        msg_id, pred_id = engine.store_message_with_prediction(
            user_id=test_user,
            message_text=test_msg,
            predictions=test_predictions,
            conversation_type='buddy'
        )
        
        print(f"✓ Stored message {msg_id} with prediction {pred_id}")
        
        # Test risk profile update
        print("\nUpdating risk profile...")
        profile = engine.update_user_risk_profile(test_user, thresholds)
        
        print(f"\n✓ User: {profile['user_id']}")
        print(f"  Risk Label: {profile['current_risk_label']}")
        print(f"  Reasons: {profile['reasons']}")
        
        engine.close()
        print("\n✓ Test complete!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
