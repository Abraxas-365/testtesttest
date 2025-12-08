-- ============================================
-- INIT SCHEMAS - Consolidated Migration
-- Version: 1.0.0
-- Date: 2025-01-11
-- Description: Single migration file with all tables
-- ============================================

BEGIN;

-- ============================================
-- SECTION 1: CORE AGENT TABLES
-- ============================================

-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    agent_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    instruction TEXT NOT NULL,
    description TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Agent classification
    agent_type VARCHAR(50) DEFAULT 'assistant' CHECK (agent_type IN ('assistant', 'coordinator', 'specialist', 'rag', 'tool')),
    area_type VARCHAR(50) DEFAULT 'general',  -- NO CONSTRAINT - allows dynamic Azure AD group mapping
    
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
    tool_type VARCHAR(50) NOT NULL CHECK (tool_type IN ('function', 'builtin', 'third_party', 'rag', 'agent')),
    function_name VARCHAR(255),
    parameters JSONB DEFAULT '{}'::jsonb,
    description TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- RAG Corpuses table
CREATE TABLE IF NOT EXISTS corpuses (
    corpus_id VARCHAR(255) PRIMARY KEY,
    corpus_name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Vertex AI RAG corpus resource name
    vertex_corpus_name VARCHAR(500),
    
    -- Embedding model configuration
    embedding_model VARCHAR(100) DEFAULT 'text-embedding-005',
    
    -- Vector database settings
    vector_db_type VARCHAR(50) DEFAULT 'vertex_rag' CHECK (vector_db_type IN ('vertex_rag', 'qdrant', 'pinecone', 'weaviate')),
    vector_db_config JSONB DEFAULT '{}'::jsonb,
    
    -- Corpus metadata
    document_count INTEGER DEFAULT 0,
    chunk_size INTEGER DEFAULT 1000,
    chunk_overlap INTEGER DEFAULT 200,
    metadata JSONB DEFAULT '{}'::jsonb,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Agent-Corpus association table (many-to-many)
CREATE TABLE IF NOT EXISTS agent_corpuses (
    agent_id VARCHAR(255) REFERENCES agents(agent_id) ON DELETE CASCADE,
    corpus_id VARCHAR(255) REFERENCES corpuses(corpus_id) ON DELETE CASCADE,
    priority INTEGER DEFAULT 1,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (agent_id, corpus_id)
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

-- ============================================
-- SECTION 2: AZURE AD GROUP MAPPINGS
-- ============================================

CREATE TABLE IF NOT EXISTS azure_ad_group_mappings (
    mapping_id SERIAL PRIMARY KEY,
    group_name VARCHAR(255) NOT NULL UNIQUE,
    area_type VARCHAR(50) NOT NULL,
    weight INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- SECTION 3: ADK SESSION TABLES
-- ============================================

-- Sessions table (ADK-compatible)
CREATE TABLE IF NOT EXISTS sessions (
    app_name VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    id VARCHAR(255) NOT NULL,
    
    state JSONB DEFAULT '{}'::jsonb NOT NULL,
    
    -- ADK requires BOTH create_time AND update_time
    create_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    update_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    
    PRIMARY KEY (app_name, user_id, id),
    UNIQUE (id)
);

-- App states table
CREATE TABLE IF NOT EXISTS app_states (
    app_name VARCHAR(255) PRIMARY KEY,
    state JSONB DEFAULT '{}'::jsonb NOT NULL,
    create_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    update_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- User states table
CREATE TABLE IF NOT EXISTS user_states (
    app_name VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    state JSONB DEFAULT '{}'::jsonb NOT NULL,
    create_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    update_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    PRIMARY KEY (app_name, user_id)
);

-- Events table (ADK-compatible)
CREATE TABLE IF NOT EXISTS events (
    -- CRITICAL: id must be VARCHAR, not SERIAL
    id VARCHAR(255) PRIMARY KEY,
    
    -- Session identification
    app_name VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    
    -- Event metadata
    invocation_id VARCHAR(255),
    author VARCHAR(255),
    branch VARCHAR(255),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Event data (ADK stores these as JSONB/BYTEA)
    content JSONB,
    actions BYTEA,
    long_running_tool_ids_json TEXT,
    grounding_metadata JSONB,
    
    -- Event flags
    partial BOOLEAN,
    turn_complete BOOLEAN,
    error_code VARCHAR(255),
    error_message TEXT,
    interrupted BOOLEAN,
    
    FOREIGN KEY (app_name, user_id, session_id) 
        REFERENCES sessions(app_name, user_id, id) 
        ON DELETE CASCADE
);

-- ============================================
-- SECTION 4: INDEXES
-- ============================================

-- Agents indexes
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
CREATE INDEX IF NOT EXISTS idx_agents_enabled ON agents(enabled);
CREATE INDEX IF NOT EXISTS idx_agents_type ON agents(agent_type);
CREATE INDEX IF NOT EXISTS idx_agents_area ON agents(area_type);
CREATE INDEX IF NOT EXISTS idx_agents_type_area ON agents(agent_type, area_type);

-- Tools indexes
CREATE INDEX IF NOT EXISTS idx_tools_name ON tools(tool_name);
CREATE INDEX IF NOT EXISTS idx_tools_type ON tools(tool_type);

-- Agent associations indexes
CREATE INDEX IF NOT EXISTS idx_agent_tools_agent_id ON agent_tools(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_tools_tool_id ON agent_tools(tool_id);
CREATE INDEX IF NOT EXISTS idx_sub_agents_parent ON agent_sub_agents(parent_agent_id);
CREATE INDEX IF NOT EXISTS idx_sub_agents_child ON agent_sub_agents(sub_agent_id);

-- Corpuses indexes
CREATE INDEX IF NOT EXISTS idx_corpuses_name ON corpuses(corpus_name);
CREATE INDEX IF NOT EXISTS idx_corpuses_enabled ON corpuses(enabled);
CREATE INDEX IF NOT EXISTS idx_agent_corpuses_agent_id ON agent_corpuses(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_corpuses_corpus_id ON agent_corpuses(corpus_id);

-- Azure AD group mappings indexes
CREATE INDEX IF NOT EXISTS idx_group_mappings_group_name ON azure_ad_group_mappings(group_name);
CREATE INDEX IF NOT EXISTS idx_group_mappings_area_type ON azure_ad_group_mappings(area_type);
CREATE INDEX IF NOT EXISTS idx_group_mappings_enabled ON azure_ad_group_mappings(enabled);
CREATE INDEX IF NOT EXISTS idx_group_mappings_weight ON azure_ad_group_mappings(weight DESC);

-- Sessions indexes
CREATE INDEX IF NOT EXISTS idx_sessions_app_name ON sessions(app_name);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_app_user ON sessions(app_name, user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_update_time ON sessions(update_time);

-- User states indexes
CREATE INDEX IF NOT EXISTS idx_user_states_user_id ON user_states(user_id);

-- Events indexes
CREATE INDEX IF NOT EXISTS idx_events_session ON events(app_name, user_id, session_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_author ON events(author);
CREATE INDEX IF NOT EXISTS idx_events_invocation_id ON events(invocation_id);
CREATE INDEX IF NOT EXISTS idx_events_turn_complete ON events(turn_complete);

-- ============================================
-- SECTION 5: TRIGGERS
-- ============================================

-- Trigger to update Azure AD group mappings timestamp
CREATE OR REPLACE FUNCTION update_azure_ad_group_mappings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER azure_ad_group_mappings_updated_at
    BEFORE UPDATE ON azure_ad_group_mappings
    FOR EACH ROW
    EXECUTE FUNCTION update_azure_ad_group_mappings_updated_at();

-- ============================================
-- SECTION 6: SAMPLE DATA
-- ============================================

-- Insert sample agents
INSERT INTO agents (agent_id, name, instruction, description, model_name, temperature, agent_type, area_type)
VALUES
    ('agent-001', 'search_assistant', 'You are a helpful assistant with access to the company SharePoint documents. Use the rag_search tool to retrieve relevant information from company documents, policies, and internal information. You can ONLY search the knowledge base - you cannot search the web or access other external tools.', 'Assistant with access ONLY to GrupoDC SharePoint knowledge base via RAG search.', 'gemini-2.5-flash', 0.7, 'assistant', 'general'),
    ('agent-002', 'data_analyst', 'You are a data analyst that can process and analyze data.', 'A data analysis expert.', 'gemini-2.5-pro', 0.5, 'specialist', 'data_analysis'),
    ('agent-003', 'marketing_specialist', 'You are a marketing expert with access to company marketing materials, campaigns, and best practices. Use the RAG tool to retrieve relevant information from the marketing corpus.', 'Marketing specialist with RAG capabilities.', 'gemini-2.5-pro', 0.7, 'rag', 'marketing'),
    ('agent-004', 'legal_advisor', 'You are a legal advisor with access to company legal documents, contracts, and compliance information. Use the RAG tool to retrieve relevant legal information.', 'Legal advisor with document access.', 'gemini-2.5-pro', 0.5, 'rag', 'legal'),
    ('agent-005', 'developer_assistant', 'You are a developer assistant with access to code documentation, API references, and technical guides. Help developers with code-related questions.', 'Developer assistant with technical documentation access.', 'gemini-2.5-flash', 0.6, 'rag', 'developer')
ON CONFLICT (agent_id) DO NOTHING;

-- Insert sample tools
INSERT INTO tools (tool_id, tool_name, tool_type, function_name, description)
VALUES
    ('tool-001', 'web_search', 'function', 'search_web', 'Search the web for information'),
    ('tool-002', 'calculate', 'function', 'calculate', 'Perform mathematical calculations'),
    ('tool-003', 'get_weather', 'function', 'get_weather', 'Get current weather information'),
    ('tool-004', 'rag_search', 'rag', 'vertex_rag_retrieval', 'Retrieve information from RAG corpus using Vertex AI RAG Engine'),
    ('tool-005', 'data_analyst_tool', 'agent', 'agent-002', 'Delegate data analysis tasks to the data analyst agent')
ON CONFLICT (tool_id) DO NOTHING;

-- Insert sample corpuses
INSERT INTO corpuses (corpus_id, corpus_name, display_name, description, vertex_corpus_name, embedding_model, vector_db_type, enabled)
VALUES
    ('corpus-sharepoint', 'grupodc_sharepoint_rag', 'GrupoDC SharePoint RAG Corpus', 'Corpus principal donde se indexan los documentos de SharePoint', 'projects/delfosti-grupodc-polidc-dev/locations/us-east4/ragCorpora/4611686018427387904', 'text-multilingual-embedding-002', 'vertex_rag', TRUE)
ON CONFLICT (corpus_id) DO NOTHING;

-- Assign RAG tool ONLY to agent-001
INSERT INTO agent_tools (agent_id, tool_id)
VALUES
    ('agent-001', 'tool-004')
ON CONFLICT (agent_id, tool_id) DO NOTHING;

-- Assign corpus to agent-001
INSERT INTO agent_corpuses (agent_id, corpus_id, priority)
VALUES
    ('agent-001', 'corpus-sharepoint', 1)
ON CONFLICT (agent_id, corpus_id) DO NOTHING;

-- Insert Azure AD group mappings with weights
INSERT INTO azure_ad_group_mappings (group_name, area_type, weight, description) VALUES
    -- Admin has highest priority
    ('Admin-Users', 'admin', 1000, 'Administrators with full access'),

    -- Specialized departments with high priority
    ('Legal-Users', 'legal', 900, 'Legal department users'),
    ('Finance-Users', 'finance', 900, 'Finance department users'),
    ('HR-Users', 'hr', 850, 'Human Resources department users'),

    -- Technical teams
    ('Developer-Users', 'developer', 800, 'Software developers and engineers'),
    ('Operations-Users', 'operations', 800, 'Operations and DevOps teams'),
    ('Data-Analysis-Users', 'data_analysis', 750, 'Data analysts and scientists'),

    -- Business teams
    ('Sales-Users', 'sales', 700, 'Sales team members'),
    ('Marketing-Users', 'marketing', 700, 'Marketing department users'),
    ('Customer-Support-Users', 'customer_support', 650, 'Customer support agents'),

    -- General/fallback with lowest priority
    ('All-Employees', 'general', 100, 'All company employees - fallback agent')
ON CONFLICT (group_name) DO NOTHING;

COMMIT;

-- ============================================
-- MIGRATION COMPLETED
-- ============================================

-- Verification query
DO $$
DECLARE
    agents_count INTEGER;
    tools_count INTEGER;
    corpuses_count INTEGER;
    mappings_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO agents_count FROM agents;
    SELECT COUNT(*) INTO tools_count FROM tools;
    SELECT COUNT(*) INTO corpuses_count FROM corpuses;
    SELECT COUNT(*) INTO mappings_count FROM azure_ad_group_mappings;
    
    RAISE NOTICE '========================================';
    RAISE NOTICE 'INIT SCHEMAS COMPLETED';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Agents: %', agents_count;
    RAISE NOTICE 'Tools: %', tools_count;
    RAISE NOTICE 'Corpuses: %', corpuses_count;
    RAISE NOTICE 'Group mappings: %', mappings_count;
    RAISE NOTICE '========================================';
END $$;





-- Migration: Remove area_type CHECK constraint to allow dynamic Azure AD group mapping
-- Date: 2025-01-04
-- Description: Allows area_type to match any Azure AD group name, not restricted to predefined values

-- Step 1: Drop the existing CHECK constraint
-- Note: In PostgreSQL, we need to find and drop the constraint by name
-- The constraint name is usually auto-generated, so we'll recreate the table definition

-- First, let's drop the constraint if it exists
DO $$
BEGIN
    -- Try to drop the constraint if it exists
    ALTER TABLE agents DROP CONSTRAINT IF EXISTS agents_area_type_check;
EXCEPTION
    WHEN undefined_object THEN
        NULL;
END $$;

-- Step 2: Verify the change
-- You can now insert agents with any area_type value that matches your Azure AD groups
-- Example: area_type = 'Legal-Users', 'HR-Users', 'Engineering-Team', etc.

-- Step 3: Update index (optional but recommended)
-- Add index for better query performance when filtering by area_type
CREATE INDEX IF NOT EXISTS idx_agents_area_type ON agents(area_type);

-- Migration completed successfully
-- area_type can now be any string value matching your Azure AD group structure




-- Migration: Create Azure AD Group Mappings Table
-- Date: 2025-01-04
-- Description: Store Azure AD group to agent area_type mappings with weights for priority routing

-- Create table for Azure AD group mappings
CREATE TABLE IF NOT EXISTS azure_ad_group_mappings (
    mapping_id SERIAL PRIMARY KEY,
    group_name VARCHAR(255) NOT NULL UNIQUE,  -- Azure AD group display name
    area_type VARCHAR(50) NOT NULL,           -- Maps to agents.area_type
    weight INTEGER NOT NULL DEFAULT 0,        -- Higher weight = higher priority
    description TEXT,                         -- Optional description
    enabled BOOLEAN DEFAULT TRUE,             -- Enable/disable mapping without deleting
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for fast lookups
CREATE INDEX IF NOT EXISTS idx_group_mappings_group_name ON azure_ad_group_mappings(group_name);
CREATE INDEX IF NOT EXISTS idx_group_mappings_area_type ON azure_ad_group_mappings(area_type);
CREATE INDEX IF NOT EXISTS idx_group_mappings_enabled ON azure_ad_group_mappings(enabled);
CREATE INDEX IF NOT EXISTS idx_group_mappings_weight ON azure_ad_group_mappings(weight DESC);

-- Insert default group mappings with weights
-- Higher weight = higher priority when user is in multiple groups
INSERT INTO azure_ad_group_mappings (group_name, area_type, weight, description) VALUES
    -- Admin has highest priority
    ('Admin-Users', 'admin', 1000, 'Administrators with full access'),

    -- Specialized departments with high priority
    ('Legal-Users', 'legal', 900, 'Legal department users'),
    ('Finance-Users', 'finance', 900, 'Finance department users'),
    ('HR-Users', 'hr', 850, 'Human Resources department users'),

    -- Technical teams
    ('Developer-Users', 'developer', 800, 'Software developers and engineers'),
    ('Operations-Users', 'operations', 800, 'Operations and DevOps teams'),
    ('Data-Analysis-Users', 'data_analysis', 750, 'Data analysts and scientists'),

    -- Business teams
    ('Sales-Users', 'sales', 700, 'Sales team members'),
    ('Marketing-Users', 'marketing', 700, 'Marketing department users'),
    ('Customer-Support-Users', 'customer_support', 650, 'Customer support agents'),

    -- General/fallback with lowest priority
    ('All-Employees', 'general', 100, 'All company employees - fallback agent')
ON CONFLICT (group_name) DO NOTHING;

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_azure_ad_group_mappings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER azure_ad_group_mappings_updated_at
    BEFORE UPDATE ON azure_ad_group_mappings
    FOR EACH ROW
    EXECUTE FUNCTION update_azure_ad_group_mappings_updated_at();

-- Grant permissions (adjust as needed for your database user)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON azure_ad_group_mappings TO your_app_user;
-- GRANT USAGE, SELECT ON SEQUENCE azure_ad_group_mappings_mapping_id_seq TO your_app_user;

COMMENT ON TABLE azure_ad_group_mappings IS 'Maps Azure AD security groups to agent area types with priority weights';
COMMENT ON COLUMN azure_ad_group_mappings.group_name IS 'Azure AD group display name (must match exactly)';
COMMENT ON COLUMN azure_ad_group_mappings.area_type IS 'Agent area_type to route to (matches agents.area_type)';
COMMENT ON COLUMN azure_ad_group_mappings.weight IS 'Priority weight - higher values take precedence for multi-group users';
COMMENT ON COLUMN azure_ad_group_mappings.enabled IS 'Whether this mapping is active';



BEGIN;

-- Drop dependent objects
DROP TRIGGER IF EXISTS trigger_update_session_last_message ON messages CASCADE;
DROP FUNCTION IF EXISTS update_session_last_message() CASCADE;

-- Drop all tables
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS user_states CASCADE;
DROP TABLE IF EXISTS app_states CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;

-- ============================================
-- Create ADK-compatible sessions table
-- ============================================
CREATE TABLE sessions (
    app_name VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    id VARCHAR(255) NOT NULL,
    
    state JSONB DEFAULT '{}'::jsonb NOT NULL,
    
    -- ADK requires BOTH create_time AND update_time
    create_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    update_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    
    PRIMARY KEY (app_name, user_id, id),
    UNIQUE (id)
);

CREATE INDEX idx_sessions_app_name ON sessions(app_name);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_app_user ON sessions(app_name, user_id);
CREATE INDEX idx_sessions_update_time ON sessions(update_time);

-- ============================================
-- Create app_states table
-- ============================================
CREATE TABLE app_states (
    app_name VARCHAR(255) PRIMARY KEY,
    state JSONB DEFAULT '{}'::jsonb NOT NULL,
    create_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    update_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- ============================================
-- Create user_states table
-- ============================================
CREATE TABLE user_states (
    app_name VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    state JSONB DEFAULT '{}'::jsonb NOT NULL,
    create_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    update_time TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    PRIMARY KEY (app_name, user_id)
);

CREATE INDEX idx_user_states_user_id ON user_states(user_id);

-- ============================================
-- Create events table (ADK-compatible)
-- ============================================
CREATE TABLE events (
    -- ⚠️ CRITICAL: id must be VARCHAR, not SERIAL
    id VARCHAR(255) PRIMARY KEY,
    
    -- Session identification
    app_name VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    
    -- Event metadata
    invocation_id VARCHAR(255),
    author VARCHAR(255),
    branch VARCHAR(255),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Event data (ADK stores these as JSONB/BYTEA)
    content JSONB,
    actions BYTEA,
    long_running_tool_ids_json TEXT,
    grounding_metadata JSONB,
    
    -- Event flags
    partial BOOLEAN,
    turn_complete BOOLEAN,
    error_code VARCHAR(255),
    error_message TEXT,
    interrupted BOOLEAN,
    
    FOREIGN KEY (app_name, user_id, session_id) 
        REFERENCES sessions(app_name, user_id, id) 
        ON DELETE CASCADE
);

CREATE INDEX idx_events_session ON events(app_name, user_id, session_id);
CREATE INDEX idx_events_timestamp ON events(timestamp);
CREATE INDEX idx_events_author ON events(author);
CREATE INDEX idx_events_invocation_id ON events(invocation_id);
CREATE INDEX idx_events_turn_complete ON events(turn_complete);

COMMIT;



-- Fix events table schema for ADK compatibility
BEGIN;

-- Step 1: Drop dependent foreign key constraint (if exists)
ALTER TABLE messages DROP CONSTRAINT IF EXISTS fk_messages_session CASCADE;

-- Step 2: Drop the existing events table and recreate with correct schema
DROP TABLE IF EXISTS events CASCADE;

-- Step 3: Create events table matching ADK's expectations
CREATE TABLE events (
    -- ✅ CRITICAL: id must be VARCHAR, not SERIAL
    id VARCHAR(255) PRIMARY KEY,  -- ADK generates string IDs like "hQ2N32eV"
    
    -- Session identification (composite foreign key)
    app_name VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    
    -- Event metadata
    invocation_id VARCHAR(255),
    author VARCHAR(255),
    branch VARCHAR(255),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Event data (ADK uses JSONB for these)
    content JSONB,
    actions BYTEA,  -- ADK stores EventActions as pickled binary
    long_running_tool_ids_json TEXT,
    grounding_metadata JSONB,
    
    -- Event flags
    partial BOOLEAN,
    turn_complete BOOLEAN,
    error_code VARCHAR(255),
    error_message TEXT,
    interrupted BOOLEAN,
    
    -- Foreign key to sessions table
    FOREIGN KEY (app_name, user_id, session_id) 
        REFERENCES sessions(app_name, user_id, id) 
        ON DELETE CASCADE
);

-- Step 4: Create indexes for performance
CREATE INDEX idx_events_session ON events(app_name, user_id, session_id);
CREATE INDEX idx_events_timestamp ON events(timestamp);
CREATE INDEX idx_events_author ON events(author);
CREATE INDEX idx_events_invocation_id ON events(invocation_id);
CREATE INDEX idx_events_turn_complete ON events(turn_complete);

COMMIT;




BEGIN;

-- Step 1: Ensure RAG tool exists
INSERT INTO tools (tool_id, tool_name, tool_type, function_name, description, enabled)
VALUES (
    'tool-004',
    'rag_search',
    'rag',
    'vertex_rag_retrieval',
    'Retrieve information from RAG corpus using Vertex AI RAG Engine',
    TRUE
)
ON CONFLICT (tool_id) DO UPDATE SET
    tool_name = EXCLUDED.tool_name,
    description = EXCLUDED.description,
    enabled = TRUE;

-- Step 2: REMOVE ALL existing tools from agent-001
DELETE FROM agent_tools WHERE agent_id = 'agent-001';

-- Step 3: Assign ONLY the RAG tool to agent-001
INSERT INTO agent_tools (agent_id, tool_id)
VALUES ('agent-001', 'tool-004');

-- Step 4: Create/update corpus entry with your actual Vertex AI RAG corpus
INSERT INTO corpuses (
    corpus_id,
    corpus_name,
    display_name,
    description,
    vertex_corpus_name,
    embedding_model,
    vector_db_type,
    enabled
)
VALUES (
    'corpus-sharepoint',
    'grupodc_sharepoint_rag',
    'GrupoDC SharePoint RAG Corpus',
    'Corpus principal donde se indexan los documentos de SharePoint',
    'projects/delfosti-grupodc-polidc-dev/locations/us-east4/ragCorpora/4611686018427387904',
    'text-multilingual-embedding-002',
    'vertex_rag',
    TRUE
)
ON CONFLICT (corpus_id) DO UPDATE SET
    vertex_corpus_name = 'projects/delfosti-grupodc-polidc-dev/locations/us-east4/ragCorpora/4611686018427387904',
    embedding_model = 'text-multilingual-embedding-002',
    enabled = TRUE,
    updated_at = NOW();

-- Step 5: Assign corpus to agent-001 with priority 1
INSERT INTO agent_corpuses (agent_id, corpus_id, priority)
VALUES ('agent-001', 'corpus-sharepoint', 1)
ON CONFLICT (agent_id, corpus_id) DO UPDATE SET
    priority = 1;

-- Step 6: Update agent description and instruction
UPDATE agents
SET 
    description = 'Assistant with access ONLY to GrupoDC SharePoint knowledge base via RAG search.',
    instruction = 'You are a helpful assistant with access to the company SharePoint documents. Use the rag_search tool to retrieve relevant information from company documents, policies, and internal information. You can ONLY search the knowledge base - you cannot search the web or access other external tools.',
    updated_at = NOW()
WHERE agent_id = 'agent-001';

COMMIT;

-- Verify the changes
DO $$
DECLARE
    tool_count INTEGER;
    corpus_count INTEGER;
    tool_name TEXT;
BEGIN
    -- Count tools
    SELECT COUNT(*) INTO tool_count FROM agent_tools WHERE agent_id = 'agent-001';
    
    -- Get tool name
    SELECT t.tool_name INTO tool_name 
    FROM agent_tools at 
    JOIN tools t ON at.tool_id = t.tool_id 
    WHERE at.agent_id = 'agent-001';
    
    -- Count corpuses
    SELECT COUNT(*) INTO corpus_count FROM agent_corpuses WHERE agent_id = 'agent-001';
    
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Migration 006 Complete!';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Agent: search_assistant (agent-001)';
    RAISE NOTICE 'Total tools assigned: %', tool_count;
    RAISE NOTICE 'Tool name: %', tool_name;
    RAISE NOTICE 'Corpuses assigned: %', corpus_count;
    RAISE NOTICE '----------------------------------------';
    RAISE NOTICE 'RAG Configuration:';
    RAISE NOTICE '  - Corpus: grupodc-sharepoint-rag-corpus-dev';
    RAISE NOTICE '  - Embedding: text-multilingual-embedding-002';
    RAISE NOTICE '  - Region: us-east4';
    RAISE NOTICE '  - Vector DB: RagManaged';
    RAISE NOTICE '========================================';
    
    -- Warn if unexpected configuration
    IF tool_count != 1 THEN
        RAISE WARNING 'Expected 1 tool, found %', tool_count;
    END IF;
    
    IF tool_name != 'rag_search' THEN
        RAISE WARNING 'Expected rag_search tool, found %', tool_name;
    END IF;
END $$;
