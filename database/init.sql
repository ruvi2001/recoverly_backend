-- ============================================================================
-- PostgreSQL Database Initialization Script
-- Project: Recoverly Platform
-- Description: Creates main database with schemas for all components
-- ============================================================================

-- ============================================================================
-- STEP 1: Create Main Database
-- ============================================================================
-- Run this separately first:
-- CREATE DATABASE recoverly_platform;
-- \c recoverly_platform

-- ============================================================================
-- STEP 2: Create Schemas
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS core;      -- Shared tables (users, messages)
CREATE SCHEMA IF NOT EXISTS social;    -- Component 3: Social support & peer network
CREATE SCHEMA IF NOT EXISTS risk;      -- Component 1: Risk detection & XAI
CREATE SCHEMA IF NOT EXISTS reco;      -- Component 2: Recommendations
CREATE SCHEMA IF NOT EXISTS causal;    -- Component 4: Causal analysis

 -- ============================================================================
-- OPTIONAL CLEANUP FOR OLD RECO PLACEHOLDER / OLD TABLE NAMES
-- Uncomment only if you want to rebuild reco from scratch
-- ============================================================================
DROP TABLE IF EXISTS reco.recommendation_templates CASCADE;
DROP TABLE IF EXISTS reco.recommendations CASCADE;
DROP TABLE IF EXISTS reco.questionnaire_submissions CASCADE;
DROP TABLE IF EXISTS reco.feedback CASCADE;
DROP TABLE IF EXISTS reco.assessments CASCADE;
DROP TABLE IF EXISTS reco.placeholder CASCADE;

DROP TABLE IF EXISTS risk.placeholder CASCADE;
DROP TABLE IF EXISTS causal.placeholder CASCADE;


-- ============================================================================
-- STEP 3: Core Schema - Shared Tables
-- ============================================================================

-- Users table
CREATE TABLE IF NOT EXISTS core.users (
    user_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(100) UNIQUE,
    email VARCHAR(255) UNIQUE,
    full_name VARCHAR(255),
    phone VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP,
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB
);

-- Messages table (all user messages)
CREATE TABLE IF NOT EXISTS core.messages (
    message_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES core.users(user_id) ON DELETE CASCADE,
    message_text TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    conversation_type VARCHAR(50),  -- 'buddy', 'counselor', 'group'
    recipient_id VARCHAR(255),      -- Who received the message
    metadata JSONB
);

-- Indexes for core tables
CREATE INDEX idx_users_status ON core.users(status);
CREATE INDEX idx_users_last_active ON core.users(last_active DESC);
CREATE INDEX idx_messages_user_time ON core.messages(user_id, timestamp DESC);
CREATE INDEX idx_messages_timestamp ON core.messages(timestamp DESC);
CREATE INDEX idx_messages_conversation ON core.messages(conversation_type);

-- ============================================================================
-- STEP 4: Social Schema - Component 3 
-- ============================================================================

-- Message-level predictions from ML models
CREATE TABLE social.message_predictions (
    id SERIAL PRIMARY KEY,
    message_id INTEGER REFERENCES core.messages(message_id) ON DELETE CASCADE,
    user_id VARCHAR(255) REFERENCES core.users(user_id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Risk model outputs
    p_craving REAL,
    p_relapse REAL,
    p_negative_mood REAL,
    p_neutral REAL,
    p_toxic REAL,
    p_isolation REAL,
    risk_score REAL,
    
    -- Metadata
    conversation_type VARCHAR(50),
    model_version VARCHAR(50)
);

-- User-level risk profiles (aggregated over time)
CREATE TABLE social.user_risk_profiles (
    user_id VARCHAR(255) PRIMARY KEY REFERENCES core.users(user_id) ON DELETE CASCADE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Short-term window metrics (7 days)
    short_avg_risk_score REAL,
    short_max_risk_score REAL,
    short_avg_isolation REAL,
    short_high_risk_count INTEGER,
    short_toxic_incidents INTEGER,
    
    -- Medium-term window metrics (30 days)
    medium_avg_risk_score REAL,
    medium_max_risk_score REAL,
    medium_avg_isolation REAL,
    
    -- Trends
    risk_trend VARCHAR(50),           -- 'improving', 'stable', 'declining', 'rapid_decline'
    isolation_trend VARCHAR(50),
    
    -- Current risk state
    current_risk_label VARCHAR(50),   -- 'HIGH_RISK', 'MODERATE_RISK', 'LOW_RISK', 'ISOLATION_ONLY'
    risk_label_since TIMESTAMP,
    
    -- Engagement metrics
    total_messages_7d INTEGER,
    buddy_messages_7d INTEGER,
    counselor_messages_7d INTEGER,
    last_message_time TIMESTAMP,
    days_since_last_buddy_msg INTEGER,
    
    -- Additional context
    reasons JSONB                     -- Array of reasons for current risk label
);

-- Actions triggered by the system
CREATE TABLE social.actions (
    action_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES core.users(user_id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Action details
    action_type VARCHAR(100),         -- 'nudge', 'escalation', 'meeting_scheduled', 'family_notified'
    risk_level VARCHAR(50),           -- Risk level at time of action
    
    -- Action content (flexible JSON storage)
    action_data JSONB,
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'in_progress', 'completed', 'failed'
    outcome VARCHAR(50),              -- 'engaged', 'ignored', 'escalated'
    
    -- AI decision context
    ai_reasoning TEXT,                -- Why the AI chose this action
    confidence_score REAL             -- AI's confidence in this decision
);

-- Nudges sent to users
CREATE TABLE social.nudges (
    nudge_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES core.users(user_id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Nudge details
    nudge_type VARCHAR(100),          -- 'peer_interaction', 'outdoor_activity', 'encouraging', 'meeting_reminder'
    nudge_message TEXT NOT NULL,
    risk_level VARCHAR(50),
    
    -- Delivery tracking
    sent_at TIMESTAMP,
    viewed_at TIMESTAMP,
    acted_on_at TIMESTAMP,
    
    -- User response
    user_response VARCHAR(50),        -- 'positive', 'negative', 'ignored'
    response_data JSONB               -- Additional response details
);

-- Escalations to counselors/family
CREATE TABLE social.escalations (
    escalation_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES core.users(user_id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Escalation details
    escalation_type VARCHAR(100),     -- 'counselor_alert', 'family_notification', 'urgent_meeting', 'emergency'
    urgency VARCHAR(50),              -- 'low', 'medium', 'high', 'critical'
    
    -- Context
    risk_score REAL,
    risk_level VARCHAR(50),
    trigger_reason TEXT,
    trigger_data JSONB,               -- Additional context
    
    -- Recipients
    escalated_to VARCHAR(255),        -- counselor_id or family_member_id
    notification_method VARCHAR(50),  -- 'email', 'sms', 'in_app', 'phone_call'
    
    -- Status
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'acknowledged', 'in_progress', 'resolved'
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_notes TEXT
);

-- Meetings scheduled
CREATE TABLE social.meetings (
    meeting_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES core.users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Meeting details
    meeting_type VARCHAR(100),        -- 'counselor', 'peer_group', 'family', 'emergency'
    scheduled_time TIMESTAMP,
    duration_minutes INTEGER,
    
    -- Participants
    counselor_id VARCHAR(255),
    participants JSONB,               -- Array of participant IDs
    
    -- Consent
    user_consent BOOLEAN DEFAULT FALSE,
    consent_given_at TIMESTAMP,
    
    -- Status
    status VARCHAR(50) DEFAULT 'scheduled',  -- 'scheduled', 'confirmed', 'completed', 'cancelled', 'no_show'
    completed_at TIMESTAMP,
    notes TEXT
);

-- Indexes for social schema
CREATE INDEX idx_predictions_user_time ON social.message_predictions(user_id, timestamp DESC);
CREATE INDEX idx_predictions_message ON social.message_predictions(message_id);
CREATE INDEX idx_risk_profiles_label ON social.user_risk_profiles(current_risk_label);
CREATE INDEX idx_risk_profiles_updated ON social.user_risk_profiles(last_updated DESC);
CREATE INDEX idx_actions_user_time ON social.actions(user_id, timestamp DESC);
CREATE INDEX idx_actions_type ON social.actions(action_type);
CREATE INDEX idx_actions_status ON social.actions(status);
CREATE INDEX idx_nudges_user ON social.nudges(user_id, timestamp DESC);
CREATE INDEX idx_nudges_type ON social.nudges(nudge_type);
CREATE INDEX idx_escalations_user ON social.escalations(user_id, timestamp DESC);
CREATE INDEX idx_escalations_status ON social.escalations(status);
CREATE INDEX idx_escalations_urgency ON social.escalations(urgency);
CREATE INDEX idx_meetings_user ON social.meetings(user_id, scheduled_time);
CREATE INDEX idx_meetings_status ON social.meetings(status);

-- ============================================================================
-- STEP 5: Placeholder Schemas for Other Components
-- ============================================================================
-- ============================================================
-- RISK SCHEMA
-- ============================================================

CREATE TABLE IF NOT EXISTS risk.assessments (
    assessment_id SERIAL PRIMARY KEY,

    user_id VARCHAR(255) NOT NULL,
    assessment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    assessed_at TIMESTAMP NOT NULL DEFAULT NOW(),

    self_efficacy_doubt INTEGER NOT NULL,
    emotional_distress INTEGER NOT NULL,
    anger_irritability INTEGER NOT NULL,
    unclear_thinking INTEGER NOT NULL,
    poor_concentration INTEGER NOT NULL,
    feeling_trapped INTEGER NOT NULL,
    sleep_disturbance INTEGER NOT NULL,
    craving_thoughts INTEGER NOT NULL,
    relapse_ideation INTEGER NOT NULL,
    recovery_actions INTEGER NOT NULL,

    CONSTRAINT fk_assessments_user
        FOREIGN KEY (user_id)
        REFERENCES core.users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_self_efficacy_doubt CHECK (self_efficacy_doubt BETWEEN 1 AND 7),
    CONSTRAINT ck_emotional_distress CHECK (emotional_distress BETWEEN 1 AND 7),
    CONSTRAINT ck_anger_irritability CHECK (anger_irritability BETWEEN 1 AND 7),
    CONSTRAINT ck_unclear_thinking CHECK (unclear_thinking BETWEEN 1 AND 7),
    CONSTRAINT ck_poor_concentration CHECK (poor_concentration BETWEEN 1 AND 7),
    CONSTRAINT ck_feeling_trapped CHECK (feeling_trapped BETWEEN 1 AND 7),
    CONSTRAINT ck_sleep_disturbance CHECK (sleep_disturbance BETWEEN 1 AND 7),
    CONSTRAINT ck_craving_thoughts CHECK (craving_thoughts BETWEEN 1 AND 7),
    CONSTRAINT ck_relapse_ideation CHECK (relapse_ideation BETWEEN 1 AND 7),
    CONSTRAINT ck_recovery_actions CHECK (recovery_actions BETWEEN 1 AND 7)
);

CREATE INDEX IF NOT EXISTS ix_risk_assessments_user_id
    ON risk.assessments(user_id);

CREATE TABLE IF NOT EXISTS risk.risk_predictions (
    prediction_id SERIAL PRIMARY KEY,

    assessment_id INTEGER NOT NULL UNIQUE,
    predicted_label SMALLINT NOT NULL,
    predicted_risk_percent NUMERIC(5,2) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    predicted_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_risk_predictions_assessment
        FOREIGN KEY (assessment_id)
        REFERENCES risk.assessments(assessment_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_predicted_label CHECK (predicted_label IN (0, 1)),
    CONSTRAINT ck_risk_percent CHECK (predicted_risk_percent BETWEEN 0.00 AND 100.00),
    CONSTRAINT ck_risk_level CHECK (
        risk_level IN ('LOW', 'MODERATE', 'HIGH', 'VERY_HIGH')
    )
);

CREATE INDEX IF NOT EXISTS ix_risk_predictions_assessment_id
    ON risk.risk_predictions(assessment_id);

CREATE TABLE IF NOT EXISTS risk.xai_explanations (
    xai_id SERIAL PRIMARY KEY,

    prediction_id INTEGER NOT NULL,
    feature_name VARCHAR(100) NOT NULL,
    feature_value INTEGER NOT NULL,
    contribution NUMERIC(10,6) NOT NULL,
    rank INTEGER NOT NULL,

    CONSTRAINT fk_xai_prediction
        FOREIGN KEY (prediction_id)
        REFERENCES risk.risk_predictions(prediction_id)
        ON DELETE CASCADE,

    CONSTRAINT uq_xai_prediction_feature UNIQUE (prediction_id, feature_name),
    CONSTRAINT uq_xai_prediction_rank UNIQUE (prediction_id, rank),

    CONSTRAINT ck_xai_feature_value CHECK (feature_value BETWEEN 1 AND 7),
    CONSTRAINT ck_xai_rank CHECK (rank BETWEEN 1 AND 10)
);

CREATE INDEX IF NOT EXISTS ix_xai_explanations_prediction_id
    ON risk.xai_explanations(prediction_id);

CREATE TABLE IF NOT EXISTS risk.weekly_relapse_checkins (
    checkin_id SERIAL PRIMARY KEY,

    user_id VARCHAR(255) NOT NULL,
    actual_relapse SMALLINT NOT NULL,
    reported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    week_start DATE,

    CONSTRAINT fk_weekly_checkins_user
        FOREIGN KEY (user_id)
        REFERENCES core.users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_weekly_actual_relapse CHECK (actual_relapse IN (0, 1))
);

CREATE INDEX IF NOT EXISTS ix_weekly_relapse_checkins_user_id
    ON risk.weekly_relapse_checkins(user_id);

CREATE INDEX IF NOT EXISTS ix_weekly_relapse_checkins_reported_at
    ON risk.weekly_relapse_checkins(reported_at);

CREATE INDEX IF NOT EXISTS ix_weekly_relapse_checkins_week_start
    ON risk.weekly_relapse_checkins(week_start);

CREATE TABLE IF NOT EXISTS risk.placeholder (
    id SERIAL PRIMARY KEY,
    note TEXT
);

-- ============================================================================
-- STEP 5A: Reco Schema (Component 2) - Recommendation System
-- ============================================================================

-- Stores each completed recommendation questionnaire submission
-- Risk level is received from Component 1 and stored here for traceability.
CREATE TABLE IF NOT EXISTS reco.assessments (
    assessment_id SERIAL PRIMARY KEY,

    user_id VARCHAR(255) NOT NULL
        REFERENCES core.users(user_id) ON DELETE CASCADE,

    risk_level VARCHAR(50) NOT NULL,

    raw_payload JSONB NOT NULL,
    encoded_vector JSONB,
    request_meta JSONB,

    assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reco_assessments_user
ON reco.assessments(user_id, assessed_at DESC);

CREATE INDEX IF NOT EXISTS idx_reco_assessments_risk
ON reco.assessments(risk_level);

-- Stores the recommendation decision produced by classifier + bandit
CREATE TABLE IF NOT EXISTS reco.recommendations (
    recommendation_id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL UNIQUE
        REFERENCES reco.assessments(assessment_id)
        ON DELETE CASCADE,    user_id VARCHAR(255) NOT NULL REFERENCES core.users(user_id) ON DELETE CASCADE,

    recommendation_family VARCHAR(100) NOT NULL,
    selected_action VARCHAR(150) NOT NULL,

    classifier_family VARCHAR(100) NOT NULL,
    classifier_confidence NUMERIC(8,6),

    bandit_action VARCHAR(150),
    policy_mode VARCHAR(50) NOT NULL,
    policy_version VARCHAR(100),

    confidence NUMERIC(8,6) NOT NULL,

    reward NUMERIC(8,6),

    decision_meta JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_reco_confidence
        CHECK (confidence BETWEEN 0.00 AND 1.00),

    CONSTRAINT ck_reco_classifier_confidence
        CHECK (classifier_confidence IS NULL OR classifier_confidence BETWEEN 0.00 AND 1.00),

    CONSTRAINT ck_reco_reward
        CHECK (reward IS NULL OR reward BETWEEN 0.00 AND 1.00)
);

CREATE TABLE reco.arrs_sessions (
    session_id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    submitted_at VARCHAR(100),
    risk_level VARCHAR(50),
    predicted_category VARCHAR(255) NOT NULL,
    confidence FLOAT,
    answers_json JSONB NOT NULL,
    recommendation_json JSONB,
    feedback_rating INT NOT NULL,
    feedback_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reco_recommendations_assessment
ON reco.recommendations(assessment_id);

CREATE INDEX idx_reco_recommendations_created
ON reco.recommendations(created_at DESC);

CREATE INDEX idx_reco_recommendations_action
ON reco.recommendations(selected_action);

CREATE INDEX IF NOT EXISTS idx_reco_recommendations_family
ON reco.recommendations(recommendation_family);

CREATE INDEX IF NOT EXISTS idx_reco_recommendations_policy_mode
ON reco.recommendations(policy_mode);


-- Stores user feedback on a previously served recommendation
CREATE TABLE IF NOT EXISTS reco.feedback (

    feedback_id SERIAL PRIMARY KEY,

    recommendation_id INTEGER NOT NULL UNIQUE
        REFERENCES reco.recommendations(recommendation_id)
        ON DELETE CASCADE,

    helpful SMALLINT NOT NULL,
    rating SMALLINT NOT NULL,
    feedback_action VARCHAR(150),

    feedback_meta JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_reco_feedback_helpful
        CHECK (helpful IN (0,1)),

    CONSTRAINT ck_reco_feedback_rating
        CHECK (rating BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS idx_reco_feedback_recommendation
ON reco.feedback(recommendation_id);

CREATE INDEX IF NOT EXISTS idx_reco_feedback_created
ON reco.feedback(created_at DESC);

 -- Optional DB-driven recommendation content store
-- Your current engine can use JSON file content, but this table is useful later.
CREATE TABLE IF NOT EXISTS reco.recommendation_templates (
    template_id SERIAL PRIMARY KEY,

    action_family VARCHAR(150) NOT NULL,
    template_title VARCHAR(255),
    template_text TEXT NOT NULL,
    language_code VARCHAR(20) DEFAULT 'en',
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reco_templates_family
ON reco.recommendation_templates(action_family);

CREATE INDEX IF NOT EXISTS idx_reco_templates_active
ON reco.recommendation_templates(is_active);

-- Causal Schema (Component 4) - Placeholder
CREATE TABLE causal.placeholder (
    id SERIAL PRIMARY KEY,
    note TEXT DEFAULT 'Component 4 tables will be added here'
);

-- ============================================================================
-- STEP 6: Grant Permissions (Optional - for multi-user setup)
-- ============================================================================

-- Grant usage on schemas to your application user
-- GRANT USAGE ON SCHEMA core, social, risk, reco, causal TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA core, social TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA core, social TO your_app_user;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- List all schemas
SELECT schema_name 
FROM information_schema.schemata 
WHERE schema_name IN ('core', 'social', 'risk', 'reco', 'causal')
ORDER BY schema_name;

-- List all tables in social schema
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'social'
ORDER BY table_name;

-- Count tables in each schema
SELECT 
    table_schema,
    COUNT(*) as table_count
FROM information_schema.tables
WHERE table_schema IN ('core', 'social', 'risk', 'reco', 'causal')
GROUP BY table_schema
ORDER BY table_schema;

SELECT schema_name FROM information_schema.schemata
WHERE schema_name IN ('core', 'social');

SELECT table_name FROM information_schema.tables
WHERE table_schema = 'social'
ORDER BY table_name;

SELECT * FROM core.messages WHERE user_id = 'test_user_001';
SELECT * FROM social.message_predictions WHERE user_id = 'test_user_001';
SELECT * FROM social.user_risk_profiles WHERE user_id = 'test_user_002';

SELECT * FROM core.messages ORDER BY timestamp DESC LIMIT 5;
SELECT * FROM social.message_predictions ORDER BY timestamp DESC LIMIT 5;
SELECT user_id, current_risk_label, reasons 
FROM social.user_risk_profiles;

-- 1. Check mes
SELECT * FROM core.messages WHERE user_id = 'alice_001';


-- 2. Check predictions
SELECT * FROM social.message_predictions WHERE user_id = 'alice_001';

-- 3. Check risk profile
SELECT user_id, current_risk_label, reasons 
FROM social.user_risk_profiles 
WHERE user_id = 'alice_001';

-- 4. Check interventions logged
SELECT * FROM social.actions WHERE user_id = 'alice_001';

-- 5. Check nudges sent
SELECT * FROM social.nudges WHERE user_id = 'alice_001';

-- 6. Check escalations
SELECT * FROM social.escalations WHERE user_id = 'alice_001';

SELECT to_regclass('core.conversations') AS conversations,
       to_regclass('core.conversation_participants') AS participants;

SELECT column_name
FROM information_schema.columns
WHERE table_schema='core' AND table_name='messages'
ORDER BY ordinal_position;

SELECT * FROM core.messages WHERE conversation_id = 1;
SELECT * FROM social.message_predictions WHERE message_id = 5;

-- core.user_credentials: stores local password auth only
CREATE TABLE IF NOT EXISTS core.user_credentials (
  user_id VARCHAR(255) PRIMARY KEY REFERENCES core.users(user_id) ON DELETE CASCADE,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_login TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_credentials_last_login
ON core.user_credentials(last_login DESC);

SELECT user_id, email, username, full_name, status, created_at
FROM core.users
ORDER BY created_at DESC
LIMIT 20;

SELECT u.user_id, u.email, u.created_at,
       (c.user_id IS NOT NULL) AS has_credentials,
	   c.last_login
FROM core.users u
LEFT JOIN core.user_credentials c ON c.user_id = u.user_id
ORDER BY u.created_at DESC
LIMIT 50;

SELECT user_id, email, full_name, status, created_at
FROM core.users
WHERE email = 'test_001@example.com';

SELECT c.user_id, c.created_at, c.last_login
FROM core.user_credentials c
WHERE c.user_id = (
  SELECT user_id FROM core.users WHERE email='test_001@example.com'
  );

DROP TABLE IF EXISTS reco.placeholder;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('core', 'social', 'risk', 'reco', 'causal')
ORDER BY table_schema, table_name;