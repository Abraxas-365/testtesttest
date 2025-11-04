-- Sessions and conversation history tables

-- Sessions table for tracking conversations
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    app_name VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) REFERENCES agents(agent_id) ON DELETE SET NULL,
    -- Session metadata
    title VARCHAR(500),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'closed', 'archived')),
    metadata JSONB DEFAULT '{}'::jsonb,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE,
    closed_at TIMESTAMP WITH TIME ZONE
);

-- Messages table for conversation history
CREATE TABLE IF NOT EXISTS messages (
    message_id VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    -- Message details
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'agent', 'system', 'tool')),
    content TEXT NOT NULL,
    -- Tool information (for tool calls/results)
    tool_name VARCHAR(255),
    tool_call_id VARCHAR(255),
    -- Message metadata
    tokens_used INTEGER,
    model_used VARCHAR(100),
    metadata JSONB DEFAULT '{}'::jsonb,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for sessions
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_agent_id ON sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_app_name_user ON sessions(app_name, user_id);

-- Indexes for messages
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at);

-- Function to update session's last_message_at timestamp
CREATE OR REPLACE FUNCTION update_session_last_message()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE sessions
    SET last_message_at = NEW.created_at,
        updated_at = NOW()
    WHERE session_id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update session timestamp on new message
DROP TRIGGER IF EXISTS trigger_update_session_last_message ON messages;
CREATE TRIGGER trigger_update_session_last_message
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_session_last_message();
