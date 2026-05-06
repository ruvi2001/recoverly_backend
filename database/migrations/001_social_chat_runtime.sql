-- Runtime chat support used by services/social_service.
-- Safe to run more than once.

ALTER TABLE core.messages
    ADD COLUMN IF NOT EXISTS deleted_for_everyone BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(255) REFERENCES core.users(user_id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS core.conversation_deletions (
    conversation_id INTEGER NOT NULL REFERENCES core.conversations(conversation_id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL REFERENCES core.users(user_id) ON DELETE CASCADE,
    deleted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conversation_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_deletions_user
    ON core.conversation_deletions(user_id, deleted_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_time
    ON core.messages(conversation_id, timestamp DESC);
