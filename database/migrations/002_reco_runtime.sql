-- Runtime recommendation service schema.
-- Safe to run more than once and aligned with services/reco_service/db/models.py.

CREATE SCHEMA IF NOT EXISTS reco;

CREATE TABLE IF NOT EXISTS reco.assessments (
    assessment_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES core.users(user_id) ON DELETE CASCADE,
    relapse_risk_level VARCHAR(50) NOT NULL,
    raw_payload JSONB NOT NULL,
    encoded_vector JSONB,
    request_meta JSONB,
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_reco_assessments_user_id
    ON reco.assessments(user_id);

CREATE INDEX IF NOT EXISTS ix_reco_assessments_assessed_at
    ON reco.assessments(assessed_at DESC);

CREATE TABLE IF NOT EXISTS reco.recommendations (
    recommendation_id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL UNIQUE
        REFERENCES reco.assessments(assessment_id) ON DELETE CASCADE,
    recommendation_family VARCHAR(100) NOT NULL,
    selected_action VARCHAR(150) NOT NULL,
    classifier_family VARCHAR(100) NOT NULL,
    classifier_confidence NUMERIC(8, 6),
    bandit_action VARCHAR(150),
    policy_mode VARCHAR(50) NOT NULL,
    policy_version VARCHAR(100),
    confidence NUMERIC(8, 6) NOT NULL,
    reward NUMERIC(8, 6),
    decision_meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_reco_confidence CHECK (confidence BETWEEN 0.00 AND 1.00),
    CONSTRAINT ck_reco_classifier_confidence
        CHECK (classifier_confidence IS NULL OR classifier_confidence BETWEEN 0.00 AND 1.00),
    CONSTRAINT ck_reco_reward
        CHECK (reward IS NULL OR reward BETWEEN 0.00 AND 1.00)
);

CREATE INDEX IF NOT EXISTS ix_reco_recommendations_assessment_id
    ON reco.recommendations(assessment_id);

CREATE INDEX IF NOT EXISTS ix_reco_recommendations_created_at
    ON reco.recommendations(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reco_recommendations_action
    ON reco.recommendations(selected_action);

CREATE INDEX IF NOT EXISTS idx_reco_recommendations_family
    ON reco.recommendations(recommendation_family);

CREATE INDEX IF NOT EXISTS idx_reco_recommendations_policy_mode
    ON reco.recommendations(policy_mode);

CREATE TABLE IF NOT EXISTS reco.feedback (
    feedback_id SERIAL PRIMARY KEY,
    recommendation_id INTEGER NOT NULL UNIQUE
        REFERENCES reco.recommendations(recommendation_id) ON DELETE CASCADE,
    helpful SMALLINT NOT NULL,
    rating SMALLINT NOT NULL,
    feedback_action VARCHAR(150),
    feedback_meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_reco_feedback_recommendation UNIQUE (recommendation_id),
    CONSTRAINT ck_reco_feedback_helpful CHECK (helpful IN (0, 1)),
    CONSTRAINT ck_reco_feedback_rating CHECK (rating BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS ix_reco_feedback_recommendation_id
    ON reco.feedback(recommendation_id);

CREATE INDEX IF NOT EXISTS ix_reco_feedback_created_at
    ON reco.feedback(created_at DESC);

CREATE TABLE IF NOT EXISTS reco.arrs_sessions (
    session_id SERIAL PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    submitted_at VARCHAR,
    risk_level VARCHAR,
    predicted_category VARCHAR NOT NULL,
    confidence FLOAT,
    answers_json JSONB NOT NULL,
    recommendation_json JSONB,
    feedback_rating INTEGER,
    feedback_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_reco_arrs_sessions_user_id
    ON reco.arrs_sessions(user_id);

ALTER TABLE reco.arrs_sessions
    ALTER COLUMN feedback_rating DROP NOT NULL;

CREATE TABLE IF NOT EXISTS reco.recommendation_templates (
    template_id SERIAL PRIMARY KEY,
    action_family VARCHAR(150) NOT NULL,
    template_title VARCHAR(255),
    template_text TEXT NOT NULL,
    language_code VARCHAR(20) DEFAULT 'en',
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reco_templates_family
    ON reco.recommendation_templates(action_family);

CREATE INDEX IF NOT EXISTS idx_reco_templates_active
    ON reco.recommendation_templates(is_active);
