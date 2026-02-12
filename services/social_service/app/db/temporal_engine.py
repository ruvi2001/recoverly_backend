"""
Temporal Risk Aggregation Engine - PostgreSQL Version
Computes user-level risk profiles from message-level predictions over time windows
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
    with temporal windows and trend detection
    
    PostgreSQL version with connection pooling for production use
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "recoverly_platform",
        user: str = "postgres",
        password: str = "1234",
        min_conn: int = 1,
        max_conn: int = 10
    ):
        """
        Initialize with PostgreSQL connection parameters
        
        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Database name
            user: Database user
            password: Database password
            min_conn: Minimum connections in pool
            max_conn: Maximum connections in pool
        """
        try:
            # Create connection pool for concurrent access
            self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
                min_conn,
                max_conn,
                host=host,
                port=port,
                database=database,
                user=user,
                password=password
            )
            
            # Initialize database schema
            self._init_database()
            
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
    
    def _init_database(self):
        """Initialize database tables if they don't exist"""
        with self.get_cursor() as cursor:
            
            # Message predictions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_predictions (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    message_text TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    -- Model outputs
                    p_craving REAL,
                    p_relapse REAL,
                    p_negative_mood REAL,
                    p_neutral REAL,
                    p_toxic REAL,
                    p_isolation REAL,
                    risk_score REAL,
                    
                    -- Metadata
                    conversation_type VARCHAR(50),
                    msg_risk_label VARCHAR(50),
                    
                    -- Indexing for fast queries
                    CONSTRAINT user_timestamp_idx UNIQUE (user_id, timestamp)
                )
            """)
            
            # Indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_time 
                ON message_predictions(user_id, timestamp DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON message_predictions(timestamp DESC)
            """)
            
            # User risk profiles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_risk_profiles (
                    user_id VARCHAR(255) PRIMARY KEY,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    -- Short-term window metrics
                    short_avg_risk_score REAL,
                    short_max_risk_score REAL,
                    short_avg_isolation REAL,
                    short_high_risk_count INTEGER,
                    short_toxic_incidents INTEGER,
                    
                    -- Medium-term window metrics
                    medium_avg_risk_score REAL,
                    medium_max_risk_score REAL,
                    medium_avg_isolation REAL,
                    
                    -- Trends
                    risk_trend VARCHAR(50),
                    isolation_trend VARCHAR(50),
                    
                    -- Final decision
                    current_risk_label VARCHAR(50),
                    risk_label_since TIMESTAMP,
                    
                    -- Engagement metrics
                    total_messages_7d INTEGER,
                    buddy_messages_7d INTEGER,
                    counselor_messages_7d INTEGER,
                    last_message_time TIMESTAMP,
                    last_login_time TIMESTAMP,
                    days_since_last_buddy_msg INTEGER,
                    days_since_last_login INTEGER
                )
            """)
            
            # Index on risk label for quick filtering
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_risk_label 
                ON user_risk_profiles(current_risk_label)
            """)
            
            # Interventions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interventions (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    intervention_type VARCHAR(100),
                    risk_label_at_time VARCHAR(50),
                    context JSONB,
                    outcome VARCHAR(50) DEFAULT 'pending',
                    
                    FOREIGN KEY (user_id) REFERENCES user_risk_profiles(user_id)
                        ON DELETE CASCADE
                )
            """)
            
            # Index on user_id and timestamp for intervention history queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_interventions_user_time 
                ON interventions(user_id, timestamp DESC)
            """)
    
    def store_message_prediction(
        self,
        user_id: str,
        message_text: str,
        predictions: Dict[str, float],
        conversation_type: str = 'buddy',
        timestamp: Optional[datetime] = None
    ) -> int:
        """
        Store a single message's predictions
        
        Args:
            user_id: Unique user identifier
            message_text: The actual message content
            predictions: Dict with keys: p_craving, p_relapse, p_negative_mood, 
                         p_neutral, p_toxic, p_isolation, risk_score
            conversation_type: 'buddy' or 'counselor'
            timestamp: Message timestamp (defaults to now)
        
        Returns:
            message_id: The database ID of the inserted record
        """
        with self.get_cursor() as cursor:
            ts = timestamp or datetime.now()
            
            cursor.execute("""
                INSERT INTO message_predictions (
                    user_id, message_text, timestamp,
                    p_craving, p_relapse, p_negative_mood, p_neutral, p_toxic,
                    p_isolation, risk_score, conversation_type
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, timestamp) DO UPDATE SET
                    message_text = EXCLUDED.message_text,
                    p_craving = EXCLUDED.p_craving,
                    p_relapse = EXCLUDED.p_relapse,
                    p_negative_mood = EXCLUDED.p_negative_mood,
                    p_neutral = EXCLUDED.p_neutral,
                    p_toxic = EXCLUDED.p_toxic,
                    p_isolation = EXCLUDED.p_isolation,
                    risk_score = EXCLUDED.risk_score
                RETURNING id
            """, (
                user_id, message_text, ts,
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
    
    def get_user_messages(
        self, 
        user_id: str, 
        days_back: int = 30
    ) -> List[Dict]:
        """
        Retrieve all messages for a user within the time window
        Uses PostgreSQL's powerful date arithmetic
        """
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id, message_text, timestamp,
                    p_craving, p_relapse, p_negative_mood, p_neutral, p_toxic,
                    p_isolation, risk_score, conversation_type
                FROM message_predictions
                WHERE user_id = %s 
                  AND timestamp >= (CURRENT_TIMESTAMP - INTERVAL '%s days')
                ORDER BY timestamp ASC
            """, (user_id, days_back))
            
            return cursor.fetchall()
    
    def compute_window_metrics(
        self, 
        messages: List[Dict],
        window_days: int
    ) -> Dict:
        """
        Compute aggregated metrics over a time window
        
        Returns:
            Dict with avg/max/count statistics
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
        
        # Count high-risk messages (using your thresholds from fusion_v2.json)
        high_risk_count = sum(
            1 for m in windowed 
            if m['risk_score'] >= 0.7 or m['p_relapse'] >= 0.5 or m['p_craving'] >= 0.5
        )
        
        toxic_incidents = sum(1 for m in windowed if m['p_toxic'] >= 0.7)
        
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
        
        Strategy:
        - Compare recent 7 days to previous 7 days
        - Use slope of linear regression as secondary indicator
        
        Returns:
            'improving', 'stable', 'declining', or 'rapid_decline'
        """
        if len(messages) < 5:
            return 'stable'  # Not enough data
        
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
            if last_2d_max >= 0.8:  # Very high risk spike
                return 'rapid_decline'
        
        # Thresholds for trend classification
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
        Compute engagement-related metrics
        """
        now = datetime.now()
        
        # Messages in last 7 days
        messages_7d = [m for m in messages if (now - m['timestamp']).days <= 7]
        
        buddy_msgs = [m for m in messages_7d if m['conversation_type'] == 'buddy']
        counselor_msgs = [m for m in messages_7d if m['conversation_type'] == 'counselor']
        
        # Days since last buddy message
        if buddy_msgs:
            last_buddy = max(m['timestamp'] for m in buddy_msgs)
            days_since_buddy = (now - last_buddy).days
        else:
            days_since_buddy = 999  # Large number if never messaged
        
        # Last message time (any type)
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
        Apply your fusion_v2 logic at the user level (not message level)
        
        This is similar to your apply_fusion_v2() but operates on aggregated data
        """
        reasons = []
        
        # Extract key values
        short_max_risk = short_metrics['max_risk_score']
        short_avg_risk = short_metrics['avg_risk_score']
        short_high_count = short_metrics['high_risk_count']
        short_avg_iso = short_metrics['avg_isolation']
        
        # HIGH RISK conditions
        if short_max_risk >= thresholds.get('T_high', 0.7):
            reasons.append(f"Max risk score in last 7 days: {short_max_risk:.3f}")
            return 'HIGH_RISK', reasons
        
        if short_high_count >= 3:
            reasons.append(f"Multiple high-risk messages in short window: {short_high_count}")
            return 'HIGH_RISK', reasons
        
        if risk_trend == 'rapid_decline':
            reasons.append("Detected rapid decline in user state")
            return 'HIGH_RISK', reasons
        
        # Isolation escalates risk if base risk is already elevated
        if short_avg_risk >= thresholds.get('T_iso_escalate', 0.7) and \
           short_avg_iso >= thresholds.get('T_iso', 0.9):
            reasons.append("Isolation escalating moderate base risk")
            return 'HIGH_RISK', reasons
        
        # MODERATE RISK conditions
        if short_avg_risk >= thresholds.get('T_mid', 0.3):
            reasons.append(f"Average risk score elevated: {short_avg_risk:.3f}")
            return 'MODERATE_RISK', reasons
        
        if risk_trend == 'declining':
            reasons.append("Risk trend is declining (worsening)")
            return 'MODERATE_RISK', reasons
        
        # Low engagement + some risk = moderate
        if engagement['days_since_last_buddy_msg'] > 5 and short_avg_risk > 0.2:
            reasons.append("Social withdrawal + mild risk")
            return 'MODERATE_RISK', reasons
        
        # ISOLATION ONLY
        if short_avg_iso >= thresholds.get('T_iso', 0.9) and short_avg_risk < 0.3:
            reasons.append("High isolation without addiction risk")
            return 'ISOLATION_ONLY', reasons
        
        # LOW RISK (default)
        reasons.append("No significant risk indicators")
        return 'LOW_RISK', reasons
    
    def update_user_risk_profile(
        self, 
        user_id: str,
        thresholds: Dict,
        login_timestamp: Optional[datetime] = None
    ) -> Dict:
        """
        Main function: compute complete risk profile for a user
        
        This is what you'll call periodically (e.g., after new messages arrive)
        
        Returns:
            Complete user risk profile
        """
        # Get all recent messages
        messages = self.get_user_messages(user_id, days_back=30)
        
        if not messages:
            # New user or no activity - return default safe profile
            return {
                'user_id': user_id,
                'current_risk_label': 'LOW_RISK',
                'message_count': 0,
                'reasons': ['No message history']
            }
        
        # Compute window metrics
        short_metrics = self.compute_window_metrics(messages, window_days=7)
        medium_metrics = self.compute_window_metrics(messages, window_days=30)
        
        # Detect trends
        risk_trend = self.detect_trend(messages, metric='risk_score')
        isolation_trend = self.detect_trend(messages, metric='p_isolation')
        
        # Engagement metrics
        engagement = self.compute_engagement_metrics(user_id, messages)
        
        # Final risk decision
        risk_label, reasons = self.apply_final_risk_decision(
            short_metrics=short_metrics,
            medium_metrics=medium_metrics,
            engagement=engagement,
            risk_trend=risk_trend,
            isolation_trend=isolation_trend,
            thresholds=thresholds
        )
        
        # Store in database
        with self.get_cursor() as cursor:
            now = datetime.now()
            
            # Check if risk label changed
            cursor.execute(
                "SELECT current_risk_label, risk_label_since FROM user_risk_profiles WHERE user_id = %s", 
                (user_id,)
            )
            existing = cursor.fetchone()
            
            if existing and existing['current_risk_label'] == risk_label:
                # Same label - keep original timestamp
                risk_label_since = existing['risk_label_since']
            else:
                # Label changed - update timestamp
                risk_label_since = now
            
            cursor.execute("""
                INSERT INTO user_risk_profiles (
                    user_id, last_updated,
                    short_avg_risk_score, short_max_risk_score, short_avg_isolation,
                    short_high_risk_count, short_toxic_incidents,
                    medium_avg_risk_score, medium_max_risk_score, medium_avg_isolation,
                    risk_trend, isolation_trend,
                    current_risk_label, risk_label_since,
                    total_messages_7d, buddy_messages_7d, counselor_messages_7d,
                    last_message_time, days_since_last_buddy_msg,
                    last_login_time, days_since_last_login
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
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
                    last_login_time = EXCLUDED.last_login_time,
                    days_since_last_login = EXCLUDED.days_since_last_login
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
                login_timestamp or now,
                (now - login_timestamp).days if login_timestamp else 0
            ))
        
        # Return complete profile
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
        """
        Find users who haven't messaged buddies in N days
        Used to trigger random check-ins
        """
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT user_id, days_since_last_buddy_msg, current_risk_label
                FROM user_risk_profiles
                WHERE days_since_last_buddy_msg >= %s
                AND current_risk_label != 'HIGH_RISK'
                ORDER BY days_since_last_buddy_msg DESC
            """, (days_silent,))
            
            return [row['user_id'] for row in cursor.fetchall()]
    
    def get_all_user_profiles(self) -> List[Dict]:
        """
        Get current risk profiles for all users
        Useful for agent to scan for intervention needs
        """
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT 
                    user_id, current_risk_label, risk_trend, isolation_trend,
                    short_avg_risk_score, short_avg_isolation,
                    days_since_last_buddy_msg, last_updated
                FROM user_risk_profiles
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
    
    def log_intervention(
        self,
        user_id: str,
        intervention_type: str,
        risk_label: str,
        context: Dict,
        outcome: str = 'pending'
    ) -> int:
        """
        Log an intervention action
        
        Args:
            user_id: Target user
            intervention_type: Type of intervention (e.g., 'buddy_nudge')
            risk_label: User's risk label at time of intervention
            context: Additional context (dict will be stored as JSON)
            outcome: 'pending', 'engaged', 'ignored', 'escalated'
        
        Returns:
            intervention_id
        """
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO interventions (
                    user_id, intervention_type, risk_label_at_time, context, outcome
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (user_id, intervention_type, risk_label, Json(context), outcome))
            
            result = cursor.fetchone()
            return result['id']
    
    def get_intervention_history(
        self,
        user_id: str,
        days_back: int = 30
    ) -> List[Dict]:
        """
        Get all interventions for a user
        """
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id, timestamp, intervention_type, 
                    risk_label_at_time, context, outcome
                FROM interventions
                WHERE user_id = %s
                  AND timestamp >= (CURRENT_TIMESTAMP - INTERVAL '%s days')
                ORDER BY timestamp DESC
            """, (user_id, days_back))
            
            return cursor.fetchall()
    
    def close(self):
        """Close all database connections"""
        if self.connection_pool:
            self.connection_pool.closeall()


# Example usage
if __name__ == "__main__":
    print("=" * 80)
    print("PostgreSQL Temporal Risk Engine - Test")
    print("=" * 80)
    
    # NOTE: Update these connection parameters for your setup
    print("\nAttempting to connect to PostgreSQL...")
    print("Update connection parameters in the code if needed.")
    print()
    
    try:
        # Initialize engine
        engine = TemporalRiskEngine(
            host="localhost",
            port=5432,
            database="risk_monitoring",
            user="postgres",
            password="your_password_here"  # UPDATE THIS
        )
        print("✓ Connected to PostgreSQL successfully")
        
        # Load fusion thresholds
        import json
        with open("fusion_v2.json", "r") as f:
            config = json.load(f)
        thresholds = config['thresholds']
        
        # Test with sample data
        print("\n" + "=" * 80)
        print("Testing with sample user data...")
        print("=" * 80)
        
        user_id = "test_user_001"
        
        # Simulate a week of messages with increasing risk
        from datetime import datetime, timedelta
        
        test_messages = [
            {"text": "Hey everyone", "predictions": {
                'p_craving': 0.1, 'p_relapse': 0.05, 'p_negative_mood': 0.2,
                'p_neutral': 0.6, 'p_toxic': 0.05, 'p_isolation': 0.3, 'risk_score': 0.14
            }, "days_ago": 7},
            
            {"text": "Feeling a bit down today", "predictions": {
                'p_craving': 0.15, 'p_relapse': 0.1, 'p_negative_mood': 0.5,
                'p_neutral': 0.2, 'p_toxic': 0.05, 'p_isolation': 0.4, 'risk_score': 0.35
            }, "days_ago": 5},
            
            {"text": "I don't want to talk to anyone", "predictions": {
                'p_craving': 0.2, 'p_relapse': 0.15, 'p_negative_mood': 0.6,
                'p_neutral': 0.05, 'p_toxic': 0.0, 'p_isolation': 0.85, 'risk_score': 0.42
            }, "days_ago": 2},
            
            {"text": "I'm craving really bad right now", "predictions": {
                'p_craving': 0.85, 'p_relapse': 0.3, 'p_negative_mood': 0.5,
                'p_neutral': 0.05, 'p_toxic': 0.0, 'p_isolation': 0.6, 'risk_score': 0.85
            }, "days_ago": 0},
        ]
        
        # Store messages
        print("\nStoring messages...")
        for msg in test_messages:
            ts = datetime.now() - timedelta(days=msg['days_ago'])
            msg_id = engine.store_message_prediction(
                user_id=user_id,
                message_text=msg['text'],
                predictions=msg['predictions'],
                conversation_type='buddy',
                timestamp=ts
            )
            print(f"  Stored message {msg_id}: '{msg['text'][:50]}...'")
        
        # Compute risk profile
        print("\nComputing risk profile...")
        profile = engine.update_user_risk_profile(user_id, thresholds)
        
        print("\n" + "=" * 80)
        print("USER RISK PROFILE")
        print("=" * 80)
        print(f"User: {profile['user_id']}")
        print(f"Risk Label: {profile['current_risk_label']}")
        print(f"Risk Trend: {profile['trends']['risk']}")
        print(f"Isolation Trend: {profile['trends']['isolation']}")
        print(f"\nReasons:")
        for reason in profile['reasons']:
            print(f"  - {reason}")
        
        print(f"\nShort-term metrics:")
        for key, val in profile['short_window'].items():
            print(f"  {key}: {val}")
        
        print(f"\nEngagement:")
        for key, val in profile['engagement'].items():
            print(f"  {key}: {val}")
        
        # Test intervention logging
        print("\n" + "=" * 80)
        print("Logging sample intervention...")
        intervention_id = engine.log_intervention(
            user_id=user_id,
            intervention_type='counselor_alert',
            risk_label=profile['current_risk_label'],
            context={'reason': 'High risk detected', 'auto_generated': True}
        )
        print(f"✓ Logged intervention {intervention_id}")
        
        # Close connections
        engine.close()
        print("\n✓ Test completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nMake sure:")
        print("  1. PostgreSQL is installed and running")
        print("  2. Database 'risk_monitoring' exists")
        print("  3. Connection parameters are correct")
        print("  4. User has necessary permissions")
