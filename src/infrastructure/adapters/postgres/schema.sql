-- Database schema for agent configuration

-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    agent_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    instruction TEXT NOT NULL,
    description TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    -- Model configuration
    model_name VARCHAR(100) NOT NULL,
    temperature DECIMAL(3, 2) DEFAULT 0.7,
    max_tokens INTEGER,
    top_p DECIMAL(3, 2),
    top_k INTEGER,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tools table
CREATE TABLE IF NOT EXISTS tools (
    tool_id VARCHAR(255) PRIMARY KEY,
    tool_name VARCHAR(255) NOT NULL UNIQUE,
    tool_type VARCHAR(50) NOT NULL CHECK (tool_type IN ('function', 'builtin', 'third_party')),
    function_name VARCHAR(255),
    parameters JSONB DEFAULT '{}'::jsonb,
    description TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Agent-Tool association table (many-to-many)
CREATE TABLE IF NOT EXISTS agent_tools (
    agent_id VARCHAR(255) REFERENCES agents(agent_id) ON DELETE CASCADE,
    tool_id VARCHAR(255) REFERENCES tools(tool_id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, tool_id)
);

-- Agent hierarchy table (for sub-agents)
CREATE TABLE IF NOT EXISTS agent_sub_agents (
    parent_agent_id VARCHAR(255) REFERENCES agents(agent_id) ON DELETE CASCADE,
    sub_agent_id VARCHAR(255) REFERENCES agents(agent_id) ON DELETE CASCADE,
    PRIMARY KEY (parent_agent_id, sub_agent_id),
    CHECK (parent_agent_id != sub_agent_id)
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
CREATE INDEX IF NOT EXISTS idx_agents_enabled ON agents(enabled);
CREATE INDEX IF NOT EXISTS idx_tools_name ON tools(tool_name);
CREATE INDEX IF NOT EXISTS idx_tools_type ON tools(tool_type);
CREATE INDEX IF NOT EXISTS idx_agent_tools_agent_id ON agent_tools(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_tools_tool_id ON agent_tools(tool_id);
CREATE INDEX IF NOT EXISTS idx_sub_agents_parent ON agent_sub_agents(parent_agent_id);
CREATE INDEX IF NOT EXISTS idx_sub_agents_child ON agent_sub_agents(sub_agent_id);

-- Sample data for testing
INSERT INTO agents (agent_id, name, instruction, description, model_name, temperature)
VALUES
    ('agent-001', 'search_assistant', 'You are a helpful assistant that can search the web and answer questions.', 'An assistant that can search the web.', 'gemini-2.5-flash', 0.7),
    ('agent-002', 'data_analyst', 'You are a data analyst that can process and analyze data.', 'A data analysis expert.', 'gemini-2.5-pro', 0.5)
ON CONFLICT (agent_id) DO NOTHING;

INSERT INTO tools (tool_id, tool_name, tool_type, function_name, description)
VALUES
    ('tool-001', 'web_search', 'function', 'search_web', 'Search the web for information'),
    ('tool-002', 'calculate', 'function', 'calculate', 'Perform mathematical calculations'),
    ('tool-003', 'get_weather', 'function', 'get_weather', 'Get current weather information')
ON CONFLICT (tool_id) DO NOTHING;

INSERT INTO agent_tools (agent_id, tool_id)
VALUES
    ('agent-001', 'tool-001'),
    ('agent-001', 'tool-003'),
    ('agent-002', 'tool-002')
ON CONFLICT (agent_id, tool_id) DO NOTHING;
