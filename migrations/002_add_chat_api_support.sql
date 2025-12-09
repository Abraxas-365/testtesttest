-- ============================================
-- CHAT API SUPPORT - Migration 002
-- Version: 2.0.0
-- Date: 2025-12-08
-- Description: Add support for chat session API
-- ============================================

BEGIN;

-- Add agent_id column to sessions table (if not exists)
ALTER TABLE sessions
ADD COLUMN IF NOT EXISTS agent_id VARCHAR(255);

-- Backfill agent_id from app_name for existing sessions
UPDATE sessions
SET agent_id = REPLACE(app_name, 'agent_', '')
WHERE agent_id IS NULL AND app_name LIKE 'agent_%';

-- Add title column (first message preview)
ALTER TABLE sessions
ADD COLUMN IF NOT EXISTS title TEXT;

-- Add status column (if not exists)
ALTER TABLE sessions
ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'active';

-- Add closed_at column
ALTER TABLE sessions
ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP WITH TIME ZONE;

-- Create indexes for chat queries
CREATE INDEX IF NOT EXISTS idx_sessions_user_status_time
    ON sessions(user_id, status, update_time DESC);

CREATE INDEX IF NOT EXISTS idx_sessions_agent_id
    ON sessions(agent_id);

CREATE INDEX IF NOT EXISTS idx_events_session_timestamp
    ON events(session_id, timestamp DESC);

-- Partial index for active sessions only (optimized for common queries)
CREATE INDEX IF NOT EXISTS idx_sessions_active
    ON sessions(user_id, update_time DESC)
    WHERE status = 'active';

-- Add composite index for user + agent filtering
CREATE INDEX IF NOT EXISTS idx_sessions_user_agent
    ON sessions(user_id, agent_id);

COMMIT;
