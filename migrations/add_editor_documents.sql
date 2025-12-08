-- Migration: Add editor_documents table for AI Text Editor
-- Created: 2024-12-07

-- Editor documents table for persisting user documents
CREATE TABLE IF NOT EXISTS editor_documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for efficient user document queries
CREATE INDEX IF NOT EXISTS idx_editor_documents_user_id ON editor_documents(user_id);

-- Index for sorting by last updated
CREATE INDEX IF NOT EXISTS idx_editor_documents_updated_at ON editor_documents(updated_at DESC);

-- Composite index for user + updated_at (common query pattern)
CREATE INDEX IF NOT EXISTS idx_editor_documents_user_updated ON editor_documents(user_id, updated_at DESC);

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

-- Insert the dedicated text_editor_agent (idempotent - skip if exists)
INSERT INTO agents (agent_id, name, description, model_config, enabled, instruction)
SELECT
    gen_random_uuid(),
    'text_editor_agent',
    'AI Text Editor Assistant for document editing with diff suggestions',
    '{"model": "gemini-2.5-flash", "temperature": 0.7}'::jsonb,
    true,
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
9. Only use diff blocks when making targeted modifications to existing text'
WHERE NOT EXISTS (
    SELECT 1 FROM agents WHERE name = 'text_editor_agent'
);
