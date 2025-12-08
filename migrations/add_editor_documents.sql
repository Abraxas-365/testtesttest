-- ============================================
-- Migration: Add AI Text Editor Support
-- Version: 1.0.0
-- Date: 2024-12-07
-- Description: Creates editor_documents table and text_editor_agent
-- ============================================

BEGIN;

-- ============================================
-- SECTION 1: EDITOR DOCUMENTS TABLE
-- ============================================

-- Editor documents table for persisting user documents
CREATE TABLE IF NOT EXISTS editor_documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    title VARCHAR(500) NOT NULL DEFAULT 'Untitled Document',
    content TEXT NOT NULL DEFAULT '',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- SECTION 2: INDEXES
-- ============================================

-- Index for efficient user document queries
CREATE INDEX IF NOT EXISTS idx_editor_documents_user_id ON editor_documents(user_id);

-- Index for sorting by last updated
CREATE INDEX IF NOT EXISTS idx_editor_documents_updated_at ON editor_documents(updated_at DESC);

-- Composite index for user + updated_at (common query pattern)
CREATE INDEX IF NOT EXISTS idx_editor_documents_user_updated ON editor_documents(user_id, updated_at DESC);

-- ============================================
-- SECTION 3: TRIGGERS
-- ============================================

-- Auto-update timestamp trigger function
CREATE OR REPLACE FUNCTION update_editor_document_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop trigger if exists (for idempotent migrations)
DROP TRIGGER IF EXISTS trigger_editor_document_update ON editor_documents;

-- Create trigger for auto-updating updated_at
CREATE TRIGGER trigger_editor_document_update
    BEFORE UPDATE ON editor_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_editor_document_timestamp();

-- ============================================
-- SECTION 4: TEXT EDITOR AGENT
-- ============================================

-- Insert the dedicated text_editor_agent (idempotent - uses ON CONFLICT)
INSERT INTO agents (
    agent_id,
    name,
    instruction,
    description,
    enabled,
    metadata,
    agent_type,
    area_type,
    model_name,
    temperature
)
VALUES (
    'agent-text-editor',
    'text_editor_agent',
    'You are an AI text editor assistant. When the user provides document content and asks for modifications:

1. Analyze the current document content carefully
2. When suggesting changes, format them as JSON diff blocks using this exact format:

```diff
{"type": "modification", "original": "original text", "new": "replacement text"}
```

3. For additions, use:
```diff
{"type": "addition", "position": "after: [context text]", "new": "text to add"}
```

4. For deletions, use:
```diff
{"type": "deletion", "original": "text to remove"}
```

5. Always explain your changes in natural language before or after the diff blocks
6. Be precise with the original text - it must match exactly for the diff to apply
7. Respond in the same language as the user message
8. When the user asks you to write or rewrite content, provide the full text without diff blocks
9. Only use diff blocks when making targeted modifications to existing text',
    'AI Text Editor Assistant for document editing with diff suggestions. Helps users edit and improve their documents with precise text modifications.',
    TRUE,
    '{"capabilities": ["text_editing", "diff_suggestions", "content_rewriting", "grammar_correction", "style_improvement"]}'::jsonb,
    'specialist',
    'general',
    'gemini-2.5-flash',
    0.7
)
ON CONFLICT (agent_id) DO UPDATE SET
    instruction = EXCLUDED.instruction,
    description = EXCLUDED.description,
    model_name = EXCLUDED.model_name,
    temperature = EXCLUDED.temperature,
    metadata = EXCLUDED.metadata,
    updated_at = NOW();

-- Also handle conflict on name (UNIQUE constraint)
INSERT INTO agents (
    agent_id,
    name,
    instruction,
    description,
    enabled,
    metadata,
    agent_type,
    area_type,
    model_name,
    temperature
)
VALUES (
    'agent-text-editor',
    'text_editor_agent',
    'You are an AI text editor assistant.',
    'AI Text Editor Assistant',
    TRUE,
    '{}'::jsonb,
    'specialist',
    'general',
    'gemini-2.5-flash',
    0.7
)
ON CONFLICT (name) DO NOTHING;

COMMIT;

-- ============================================
-- VERIFICATION
-- ============================================

DO $$
DECLARE
    doc_count INTEGER;
    agent_exists BOOLEAN;
BEGIN
    SELECT COUNT(*) INTO doc_count FROM editor_documents;
    SELECT EXISTS(SELECT 1 FROM agents WHERE name = 'text_editor_agent') INTO agent_exists;

    RAISE NOTICE '========================================';
    RAISE NOTICE 'AI Text Editor Migration Complete!';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Editor documents table: created';
    RAISE NOTICE 'Current document count: %', doc_count;
    RAISE NOTICE 'Text editor agent exists: %', agent_exists;
    RAISE NOTICE '========================================';
END $$;
