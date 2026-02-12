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
-- STEP 3: Core Schema - Shared Tables
-- ============================================================================

-- Users table
CREATE TABLE core.users (
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
CREATE TABLE core.messages (
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
-- STEP 4: Social Schema - Component 3 (Your Component)
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

-- Risk Schema (Component 1) - Placeholder
-- Other team members will add their tables here
CREATE TABLE risk.placeholder (
    id SERIAL PRIMARY KEY,
    note TEXT DEFAULT 'Component 1 tables will be added here'
);

-- Reco Schema (Component 2) - Placeholder
CREATE TABLE reco.placeholder (
    id SERIAL PRIMARY KEY,
    note TEXT DEFAULT 'Component 2 tables will be added here'
);

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
