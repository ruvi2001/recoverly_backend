-- ============================================================================
-- Recoverly Platform - Cloud/Shared Initialization Script
-- One DB: recoverly_platform
-- Schemas: core, social, risk, reco, causal
-- Social tables are intentionally omitted.
-- Adds roles + permissions so each member owns only their schema.
-- ============================================================================

-- ============================================================================
-- STEP 1: Create Schemas
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS social;  -- tables omitted
CREATE SCHEMA IF NOT EXISTS risk;
CREATE SCHEMA IF NOT EXISTS reco;
CREATE SCHEMA IF NOT EXISTS causal;

-- ============================================================================
-- STEP 2: Core Schema - Shared Tables (admin-owned)
-- ============================================================================

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

CREATE TABLE IF NOT EXISTS core.messages (
    message_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES core.users(user_id) ON DELETE CASCADE,
    message_text TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    conversation_type VARCHAR(50),
    recipient_id VARCHAR(255),
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_users_status ON core.users(status);
CREATE INDEX IF NOT EXISTS idx_users_last_active ON core.users(last_active DESC);
CREATE INDEX IF NOT EXISTS idx_messages_user_time ON core.messages(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON core.messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON core.messages(conversation_type);

-- ============================================================================
-- STEP 3: Placeholders for other schemas (so they can connect immediately)
-- ============================================================================

CREATE TABLE IF NOT EXISTS risk.placeholder (
    id SERIAL PRIMARY KEY,
    note TEXT DEFAULT 'Component 1 tables will be added here'
);

CREATE TABLE IF NOT EXISTS reco.placeholder (
    id SERIAL PRIMARY KEY,
    note TEXT DEFAULT 'Component 2 tables will be added here'
);

CREATE TABLE IF NOT EXISTS causal.placeholder (
    id SERIAL PRIMARY KEY,
    note TEXT DEFAULT 'Component 4 tables will be added here'
);

-- ============================================================================
-- STEP 4: Create Component Users (LOGIN roles)
-- NOTE: Change passwords before running.
-- ============================================================================

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'social_user') THEN
    CREATE ROLE social_user LOGIN PASSWORD 'CHANGE_ME_social';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'risk_user') THEN
    CREATE ROLE risk_user   LOGIN PASSWORD 'CHANGE_ME_risk';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reco_user') THEN
    CREATE ROLE reco_user   LOGIN PASSWORD 'CHANGE_ME_reco';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'causal_user') THEN
    CREATE ROLE causal_user LOGIN PASSWORD 'CHANGE_ME_causal';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'core_owner') THEN
    CREATE ROLE core_owner  LOGIN PASSWORD 'CHANGE_ME_core';
  END IF;
END $$;

-- ============================================================================
-- STEP 5: Lock down PUBLIC defaults (important in cloud)
-- ============================================================================

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- ============================================================================
-- STEP 6: Ownership (optional but clean)
-- ============================================================================
-- We keep core owned by core_owner, others by their service users.
-- If you prefer admin (postgres) to own everything, skip this block.

ALTER SCHEMA social OWNER TO social_user;
ALTER SCHEMA risk   OWNER TO risk_user;
ALTER SCHEMA reco   OWNER TO reco_user;
ALTER SCHEMA causal OWNER TO causal_user;
ALTER SCHEMA core   OWNER TO core_owner;

-- If the core tables were created before changing owner, ensure ownership:
ALTER TABLE core.users OWNER TO core_owner;
ALTER TABLE core.messages OWNER TO core_owner;

-- ============================================================================
-- STEP 7: Database access
-- ============================================================================

GRANT CONNECT ON DATABASE recoverly_platform TO
  social_user, risk_user, reco_user, causal_user, core_owner;

-- ============================================================================
-- STEP 8: Schema-level privileges
-- Each user can USE + CREATE only in their own schema.
-- Everyone can USE core (read-only tables granted below).
-- ============================================================================

GRANT USAGE, CREATE ON SCHEMA social TO social_user;
GRANT USAGE, CREATE ON SCHEMA risk   TO risk_user;
GRANT USAGE, CREATE ON SCHEMA reco   TO reco_user;
GRANT USAGE, CREATE ON SCHEMA causal TO causal_user;

GRANT USAGE ON SCHEMA core TO social_user, risk_user, reco_user, causal_user;

-- Prevent other users from creating tables in someone else's schema
REVOKE CREATE ON SCHEMA core   FROM social_user, risk_user, reco_user, causal_user;
REVOKE CREATE ON SCHEMA risk   FROM social_user, reco_user, causal_user, core_owner;
REVOKE CREATE ON SCHEMA reco   FROM social_user, risk_user, causal_user, core_owner;
REVOKE CREATE ON SCHEMA causal FROM social_user, risk_user, reco_user, core_owner;
REVOKE CREATE ON SCHEMA social FROM risk_user, reco_user, causal_user, core_owner;

-- ============================================================================
-- STEP 9: Table privileges
-- Core is shared READ for all component users (no writes)
-- ============================================================================
REVOKE ALL ON ALL TABLES IN SCHEMA core FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA core FROM PUBLIC;

GRANT SELECT ON ALL TABLES IN SCHEMA core TO social_user, risk_user, reco_user, causal_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO social_user, risk_user, reco_user, causal_user;

-- Ensure future core tables stay readable automatically
ALTER DEFAULT PRIVILEGES FOR ROLE core_owner IN SCHEMA core
GRANT SELECT ON TABLES TO social_user, risk_user, reco_user, causal_user;

ALTER DEFAULT PRIVILEGES FOR ROLE core_owner IN SCHEMA core
GRANT USAGE, SELECT ON SEQUENCES TO social_user, risk_user, reco_user, causal_user;

-- ============================================================================
-- STEP 10: Own schema full access (each user to their schema)
-- ============================================================================
-- These grants ensure their services can run migrations and CRUD freely.

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA social TO social_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA social TO social_user;
ALTER DEFAULT PRIVILEGES FOR ROLE social_user IN SCHEMA social
GRANT ALL ON TABLES TO social_user;
ALTER DEFAULT PRIVILEGES FOR ROLE social_user IN SCHEMA social
GRANT ALL ON SEQUENCES TO social_user;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA risk TO risk_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA risk TO risk_user;
ALTER DEFAULT PRIVILEGES FOR ROLE risk_user IN SCHEMA risk
GRANT ALL ON TABLES TO risk_user;
ALTER DEFAULT PRIVILEGES FOR ROLE risk_user IN SCHEMA risk
GRANT ALL ON SEQUENCES TO risk_user;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA reco TO reco_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA reco TO reco_user;
ALTER DEFAULT PRIVILEGES FOR ROLE reco_user IN SCHEMA reco
GRANT ALL ON TABLES TO reco_user;
ALTER DEFAULT PRIVILEGES FOR ROLE reco_user IN SCHEMA reco
GRANT ALL ON SEQUENCES TO reco_user;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA causal TO causal_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA causal TO causal_user;
ALTER DEFAULT PRIVILEGES FOR ROLE causal_user IN SCHEMA causal
GRANT ALL ON TABLES TO causal_user;
ALTER DEFAULT PRIVILEGES FOR ROLE causal_user IN SCHEMA causal
GRANT ALL ON SEQUENCES TO causal_user;

-- ============================================================================
-- STEP 11: Set search_path so they can write SQL without prefixing schema
-- ============================================================================
ALTER ROLE social_user SET search_path = social, core;
ALTER ROLE risk_user   SET search_path = risk, core;
ALTER ROLE reco_user   SET search_path = reco, core;
ALTER ROLE causal_user SET search_path = causal, core;
ALTER ROLE core_owner  SET search_path = core;

-- ============================================================================
-- STEP 12: Verify
-- ============================================================================
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name IN ('core', 'social', 'risk', 'reco', 'causal')
ORDER BY schema_name;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('core', 'social', 'risk', 'reco', 'causal')
ORDER BY table_schema, table_name;
