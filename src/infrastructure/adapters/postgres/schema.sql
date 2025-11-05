-- Database schema for agent configuration

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
    area_type VARCHAR(50) DEFAULT 'general',  -- Removed constraint to match Azure AD groups dynamically
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

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
CREATE INDEX IF NOT EXISTS idx_agents_enabled ON agents(enabled);
CREATE INDEX IF NOT EXISTS idx_agents_type ON agents(agent_type);
CREATE INDEX IF NOT EXISTS idx_agents_area ON agents(area_type);
CREATE INDEX IF NOT EXISTS idx_agents_type_area ON agents(agent_type, area_type);
CREATE INDEX IF NOT EXISTS idx_tools_name ON tools(tool_name);
CREATE INDEX IF NOT EXISTS idx_tools_type ON tools(tool_type);
CREATE INDEX IF NOT EXISTS idx_agent_tools_agent_id ON agent_tools(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_tools_tool_id ON agent_tools(tool_id);
CREATE INDEX IF NOT EXISTS idx_sub_agents_parent ON agent_sub_agents(parent_agent_id);
CREATE INDEX IF NOT EXISTS idx_sub_agents_child ON agent_sub_agents(sub_agent_id);
CREATE INDEX IF NOT EXISTS idx_corpuses_name ON corpuses(corpus_name);
CREATE INDEX IF NOT EXISTS idx_corpuses_enabled ON corpuses(enabled);
CREATE INDEX IF NOT EXISTS idx_agent_corpuses_agent_id ON agent_corpuses(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_corpuses_corpus_id ON agent_corpuses(corpus_id);

-- Sample data for testing
INSERT INTO agents (agent_id, name, instruction, description, model_name, temperature, agent_type, area_type)
VALUES
    ('agent-001', 'search_assistant', 'You are a helpful assistant that can search the web and answer questions.', 'An assistant that can search the web.', 'gemini-2.5-flash', 0.7, 'assistant', 'general'),
    ('agent-002', 'data_analyst', 'You are a data analyst that can process and analyze data.', 'A data analysis expert.', 'gemini-2.5-pro', 0.5, 'specialist', 'data_analysis'),
    ('agent-003', 'marketing_rag_agent', 'You are a marketing expert with access to company marketing materials, campaigns, and best practices. Use the RAG tool to retrieve relevant information from the marketing corpus.', 'Marketing specialist with RAG capabilities.', 'gemini-2.5-pro', 0.7, 'rag', 'marketing'),
    ('agent-004', 'legal_advisor', 'You are a legal advisor with access to company legal documents, contracts, and compliance information. Use the RAG tool to retrieve relevant legal information.', 'Legal advisor with document access.', 'gemini-2.5-pro', 0.5, 'rag', 'legal'),
    ('agent-005', 'dev_assistant', 'You are a developer assistant with access to code documentation, API references, and technical guides. Help developers with code-related questions.', 'Developer assistant with technical documentation access.', 'gemini-2.5-flash', 0.6, 'rag', 'developer')
ON CONFLICT (agent_id) DO NOTHING;

INSERT INTO tools (tool_id, tool_name, tool_type, function_name, description)
VALUES
    ('tool-001', 'web_search', 'function', 'search_web', 'Search the web for information'),
    ('tool-002', 'calculate', 'function', 'calculate', 'Perform mathematical calculations'),
    ('tool-003', 'get_weather', 'function', 'get_weather', 'Get current weather information'),
    ('tool-004', 'rag_search', 'rag', 'vertex_rag_retrieval', 'Retrieve information from RAG corpus using Vertex AI RAG Engine'),
    ('tool-005', 'data_analyst_tool', 'agent', 'agent-002', 'Delegate data analysis tasks to the data analyst agent')
ON CONFLICT (tool_id) DO NOTHING;

INSERT INTO agent_tools (agent_id, tool_id)
VALUES
    ('agent-001', 'tool-001'),
    ('agent-001', 'tool-003'),
    ('agent-002', 'tool-002'),
    ('agent-003', 'tool-004'),
    ('agent-004', 'tool-004'),
    ('agent-005', 'tool-004')
ON CONFLICT (agent_id, tool_id) DO NOTHING;

-- Sample corpuses
INSERT INTO corpuses (corpus_id, corpus_name, display_name, description, embedding_model, document_count)
VALUES
    ('corpus-001', 'marketing_knowledge', 'Marketing Knowledge Base', 'Marketing campaigns, strategies, and best practices', 'text-embedding-005', 0),
    ('corpus-002', 'legal_documents', 'Legal Documents Repository', 'Contracts, compliance docs, and legal guidelines', 'text-embedding-005', 0),
    ('corpus-003', 'technical_docs', 'Technical Documentation', 'API docs, code samples, and technical guides', 'text-embedding-005', 0),
    ('corpus-004', 'sales_playbook', 'Sales Playbook', 'Sales strategies, scripts, and customer insights', 'text-embedding-005', 0),
    ('corpus-005', 'operations_manual', 'Operations Manual', 'Standard operating procedures and workflows', 'text-embedding-005', 0)
ON CONFLICT (corpus_id) DO NOTHING;

-- Assign corpuses to agents
INSERT INTO agent_corpuses (agent_id, corpus_id, priority)
VALUES
    -- Marketing agent gets marketing, sales, and operations knowledge
    ('agent-003', 'corpus-001', 1),
    ('agent-003', 'corpus-004', 2),
    ('agent-003', 'corpus-005', 3),
    -- Legal advisor gets legal and operations knowledge
    ('agent-004', 'corpus-002', 1),
    ('agent-004', 'corpus-005', 2),
    -- Developer assistant gets technical docs
    ('agent-005', 'corpus-003', 1)
ON CONFLICT (agent_id, corpus_id) DO NOTHING;
