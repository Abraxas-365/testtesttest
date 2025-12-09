-- ============================================
-- POLICY SYSTEM - Migration 003
-- Version: 3.0.0
-- Date: 2025-12-09
-- Description: Add policy creation and management system
-- ============================================

BEGIN;

-- ============================================
-- SECTION 1: POLICY CORE TABLES
-- ============================================

-- Policy Status Enum Type
CREATE TYPE policy_status AS ENUM (
    'draft',           -- Initial creation, documents uploaded
    'generating',      -- AI is generating policy content
    'in_review',       -- User is editing conversationally
    'approved',        -- User approved, ready for artifact generation
    'published',       -- PDF/JPEG generated and saved to GCS
    'archived'         -- Retired/outdated policy
);

-- Policy Access Level Enum Type
CREATE TYPE access_level AS ENUM (
    'private',         -- Only owner can access
    'group',           -- Specific Entra ID groups
    'organization'     -- All authenticated users
);

-- Policies table
CREATE TABLE policies (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ownership and identification
    owner_user_id VARCHAR(255) NOT NULL,  -- Azure AD Object ID
    title VARCHAR(500) NOT NULL,
    description TEXT,

    -- Policy content (markdown or HTML)
    content TEXT,
    content_format VARCHAR(20) DEFAULT 'markdown' CHECK (content_format IN ('markdown', 'html', 'plain')),

    -- Workflow state
    status policy_status NOT NULL DEFAULT 'draft',

    -- Access control
    access_level access_level NOT NULL DEFAULT 'private',

    -- Generated artifacts (GCS paths)
    pdf_blob_path VARCHAR(1000),    -- gs://bucket/policies/{policy_id}/policy.pdf
    jpeg_blob_path VARCHAR(1000),   -- gs://bucket/policies/{policy_id}/policy.jpg

    -- ADK Session linking (for conversational editing)
    editing_session_id VARCHAR(255),  -- Links to sessions.id

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Version tracking
    version INTEGER DEFAULT 1,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    approved_at TIMESTAMP WITH TIME ZONE,
    published_at TIMESTAMP WITH TIME ZONE,
    archived_at TIMESTAMP WITH TIME ZONE,

    -- Constraints
    CONSTRAINT valid_pdf_path CHECK (pdf_blob_path IS NULL OR pdf_blob_path ~ '^gs://.*\.pdf$'),
    CONSTRAINT valid_jpeg_path CHECK (jpeg_blob_path IS NULL OR jpeg_blob_path ~ '^gs://.*\.(jpg|jpeg)$'),
    CONSTRAINT published_requires_artifacts CHECK (
        status != 'published' OR (pdf_blob_path IS NOT NULL AND jpeg_blob_path IS NOT NULL)
    )
);

-- Policy source documents (uploaded by user)
CREATE TABLE policy_documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id UUID NOT NULL REFERENCES policies(policy_id) ON DELETE CASCADE,

    -- Document metadata
    filename VARCHAR(500) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT,

    -- GCS storage
    blob_path VARCHAR(1000) NOT NULL UNIQUE,  -- uploads/{user_id}/{document_id}/{filename}
    gcs_uri VARCHAR(1000) NOT NULL,

    -- Document order (for multi-document policies)
    display_order INTEGER DEFAULT 0,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- Constraints
    CONSTRAINT valid_gcs_uri CHECK (gcs_uri ~ '^gs://.*')
);

-- Policy version history (audit trail)
CREATE TABLE policy_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id UUID NOT NULL REFERENCES policies(policy_id) ON DELETE CASCADE,

    -- Version snapshot
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_format VARCHAR(20) NOT NULL,
    status policy_status NOT NULL,

    -- Change tracking
    changed_by_user_id VARCHAR(255) NOT NULL,
    change_summary TEXT,

    -- Snapshot metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- Constraints
    CONSTRAINT unique_policy_version UNIQUE (policy_id, version_number)
);

-- Policy access control (Entra ID group permissions)
CREATE TABLE policy_access (
    access_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id UUID NOT NULL REFERENCES policies(policy_id) ON DELETE CASCADE,

    -- Azure AD group
    group_name VARCHAR(255) NOT NULL,  -- Must match azure_ad_group_mappings.group_name

    -- Permission level
    can_view BOOLEAN DEFAULT TRUE,
    can_edit BOOLEAN DEFAULT FALSE,
    can_approve BOOLEAN DEFAULT FALSE,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    granted_by_user_id VARCHAR(255) NOT NULL,

    -- Constraints
    CONSTRAINT unique_policy_group UNIQUE (policy_id, group_name)
);

-- ============================================
-- SECTION 2: QUESTIONNAIRE TABLES
-- ============================================

-- Question Type Enum
CREATE TYPE question_type AS ENUM (
    'multiple_choice',
    'true_false',
    'multiple_select',
    'short_answer'
);

-- Questionnaires table
CREATE TABLE questionnaires (
    questionnaire_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id UUID NOT NULL REFERENCES policies(policy_id) ON DELETE CASCADE,

    -- Questionnaire metadata
    title VARCHAR(500) NOT NULL,
    description TEXT,

    -- Configuration
    pass_threshold_percentage INTEGER DEFAULT 70 CHECK (pass_threshold_percentage BETWEEN 0 AND 100),
    randomize_questions BOOLEAN DEFAULT FALSE,
    randomize_options BOOLEAN DEFAULT FALSE,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- Constraints
    CONSTRAINT one_questionnaire_per_policy UNIQUE (policy_id)
);

-- Questions table
CREATE TABLE questions (
    question_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    questionnaire_id UUID NOT NULL REFERENCES questionnaires(questionnaire_id) ON DELETE CASCADE,

    -- Question content
    question_text TEXT NOT NULL,
    question_type question_type NOT NULL,

    -- Options (JSONB array for multiple choice/select)
    -- Format: [{"id": "a", "text": "Option A"}, {"id": "b", "text": "Option B"}]
    options JSONB,

    -- Correct answer(s)
    -- For multiple_choice/true_false: single value like "a" or "true"
    -- For multiple_select: array like ["a", "c"]
    -- For short_answer: array of acceptable answers
    correct_answer JSONB NOT NULL,

    -- Explanation (shown after answering)
    explanation TEXT,

    -- Question metadata
    difficulty VARCHAR(20) CHECK (difficulty IN ('easy', 'medium', 'hard')),
    points INTEGER DEFAULT 1,
    display_order INTEGER DEFAULT 0,

    -- AI generation metadata
    generated_from_content TEXT,  -- Reference to policy section

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- Constraints
    CONSTRAINT valid_options CHECK (
        (question_type IN ('multiple_choice', 'multiple_select') AND options IS NOT NULL) OR
        (question_type NOT IN ('multiple_choice', 'multiple_select'))
    ),
    CONSTRAINT valid_correct_answer CHECK (correct_answer IS NOT NULL)
);

-- Question attempts (for analytics)
CREATE TABLE question_attempts (
    attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,

    -- User info
    user_id VARCHAR(255) NOT NULL,

    -- Answer data
    user_answer JSONB NOT NULL,
    is_correct BOOLEAN NOT NULL,
    time_spent_seconds INTEGER,

    -- Timestamp
    attempted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- ============================================
-- SECTION 3: INDEXES FOR PERFORMANCE
-- ============================================

-- Policies indexes
CREATE INDEX idx_policies_owner ON policies(owner_user_id);
CREATE INDEX idx_policies_status ON policies(status);
CREATE INDEX idx_policies_created ON policies(created_at DESC);
CREATE INDEX idx_policies_updated ON policies(updated_at DESC);
CREATE INDEX idx_policies_owner_status ON policies(owner_user_id, status);
CREATE INDEX idx_policies_session ON policies(editing_session_id) WHERE editing_session_id IS NOT NULL;

-- Policy documents indexes
CREATE INDEX idx_policy_docs_policy ON policy_documents(policy_id);
CREATE INDEX idx_policy_docs_order ON policy_documents(policy_id, display_order);

-- Policy versions indexes
CREATE INDEX idx_policy_versions_policy ON policy_versions(policy_id, version_number DESC);
CREATE INDEX idx_policy_versions_created ON policy_versions(created_at DESC);

-- Policy access indexes
CREATE INDEX idx_policy_access_policy ON policy_access(policy_id);
CREATE INDEX idx_policy_access_group ON policy_access(group_name);
CREATE INDEX idx_policy_access_policy_group ON policy_access(policy_id, group_name);

-- Questionnaires indexes
CREATE INDEX idx_questionnaires_policy ON questionnaires(policy_id);
CREATE INDEX idx_questionnaires_active ON questionnaires(is_active) WHERE is_active = TRUE;

-- Questions indexes
CREATE INDEX idx_questions_questionnaire ON questions(questionnaire_id);
CREATE INDEX idx_questions_order ON questions(questionnaire_id, display_order);
CREATE INDEX idx_questions_type ON questions(question_type);

-- Question attempts indexes
CREATE INDEX idx_attempts_question ON question_attempts(question_id);
CREATE INDEX idx_attempts_user ON question_attempts(user_id);
CREATE INDEX idx_attempts_user_date ON question_attempts(user_id, attempted_at DESC);

-- ============================================
-- SECTION 4: TRIGGERS
-- ============================================

-- Update policies.updated_at on modification
CREATE OR REPLACE FUNCTION update_policy_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER policies_updated_at
    BEFORE UPDATE ON policies
    FOR EACH ROW
    EXECUTE FUNCTION update_policy_updated_at();

-- Create version snapshot on significant changes
CREATE OR REPLACE FUNCTION create_policy_version_snapshot()
RETURNS TRIGGER AS $$
BEGIN
    -- Only create snapshot if content or status changed
    IF (NEW.content IS DISTINCT FROM OLD.content) OR (NEW.status IS DISTINCT FROM OLD.status) THEN
        INSERT INTO policy_versions (
            policy_id,
            version_number,
            content,
            content_format,
            status,
            changed_by_user_id,
            metadata
        ) VALUES (
            NEW.policy_id,
            NEW.version,
            NEW.content,
            NEW.content_format,
            NEW.status,
            NEW.owner_user_id,  -- Should be passed via application context
            jsonb_build_object(
                'previous_status', OLD.status,
                'new_status', NEW.status,
                'change_trigger', 'auto_snapshot'
            )
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER policy_version_snapshot
    AFTER UPDATE ON policies
    FOR EACH ROW
    WHEN (OLD.version IS DISTINCT FROM NEW.version)
    EXECUTE FUNCTION create_policy_version_snapshot();

-- Update questionnaires.updated_at on modification
CREATE OR REPLACE FUNCTION update_questionnaire_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER questionnaires_updated_at
    BEFORE UPDATE ON questionnaires
    FOR EACH ROW
    EXECUTE FUNCTION update_questionnaire_updated_at();

-- Update questions.updated_at on modification
CREATE OR REPLACE FUNCTION update_question_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER questions_updated_at
    BEFORE UPDATE ON questions
    FOR EACH ROW
    EXECUTE FUNCTION update_question_updated_at();

-- Link session metadata to policy (when session is created for policy editing)
CREATE OR REPLACE FUNCTION sync_session_to_policy()
RETURNS TRIGGER AS $$
BEGIN
    -- Check if session has policy_id metadata
    IF NEW.state ? 'policy_id' THEN
        UPDATE policies
        SET editing_session_id = NEW.id
        WHERE policy_id = (NEW.state->>'policy_id')::UUID
          AND editing_session_id IS DISTINCT FROM NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER session_policy_link
    AFTER INSERT OR UPDATE ON sessions
    FOR EACH ROW
    WHEN (NEW.state ? 'policy_id')
    EXECUTE FUNCTION sync_session_to_policy();

-- ============================================
-- SECTION 5: HELPER FUNCTIONS
-- ============================================

-- Check if user can access policy (via group membership)
CREATE OR REPLACE FUNCTION user_can_access_policy(
    p_policy_id UUID,
    p_user_id VARCHAR(255),
    p_user_groups VARCHAR(255)[]
)
RETURNS BOOLEAN AS $$
DECLARE
    v_policy RECORD;
    v_has_access BOOLEAN;
BEGIN
    -- Get policy
    SELECT * INTO v_policy FROM policies WHERE policy_id = p_policy_id;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Owner always has access
    IF v_policy.owner_user_id = p_user_id THEN
        RETURN TRUE;
    END IF;

    -- Check access level
    IF v_policy.access_level = 'private' THEN
        RETURN FALSE;
    END IF;

    IF v_policy.access_level = 'organization' THEN
        RETURN TRUE;
    END IF;

    -- Check group-based access
    IF v_policy.access_level = 'group' THEN
        SELECT EXISTS (
            SELECT 1 FROM policy_access
            WHERE policy_id = p_policy_id
              AND group_name = ANY(p_user_groups)
              AND can_view = TRUE
        ) INTO v_has_access;

        RETURN v_has_access;
    END IF;

    RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Get accessible policies for user
CREATE OR REPLACE FUNCTION get_accessible_policies(
    p_user_id VARCHAR(255),
    p_user_groups VARCHAR(255)[]
)
RETURNS TABLE (
    policy_id UUID,
    title VARCHAR(500),
    status policy_status,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT p.policy_id, p.title, p.status, p.created_at
    FROM policies p
    WHERE
        -- Owner can always access
        p.owner_user_id = p_user_id
        OR
        -- Organization-wide access
        p.access_level = 'organization'
        OR
        -- Group-based access
        (p.access_level = 'group' AND EXISTS (
            SELECT 1 FROM policy_access pa
            WHERE pa.policy_id = p.policy_id
              AND pa.group_name = ANY(p_user_groups)
              AND pa.can_view = TRUE
        ))
    ORDER BY p.updated_at DESC;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- SECTION 6: COMMENTS
-- ============================================

COMMENT ON TABLE policies IS 'Core policy documents with content and workflow state';
COMMENT ON TABLE policy_documents IS 'Source documents uploaded by users to generate policies';
COMMENT ON TABLE policy_versions IS 'Audit trail of policy content changes';
COMMENT ON TABLE policy_access IS 'Entra ID group-based access control for policies';
COMMENT ON TABLE questionnaires IS 'Auto-generated questionnaires for policy validation';
COMMENT ON TABLE questions IS 'Individual questions with correct answers';
COMMENT ON TABLE question_attempts IS 'User answers for analytics and progress tracking';

COMMENT ON COLUMN policies.editing_session_id IS 'Links to ADK chat session for conversational editing';
COMMENT ON COLUMN policies.content IS 'Policy content in markdown, HTML, or plain text';
COMMENT ON COLUMN policies.status IS 'Workflow state: draft -> generating -> in_review -> approved -> published';
COMMENT ON COLUMN policy_access.group_name IS 'Must match Azure AD group from azure_ad_group_mappings';

COMMIT;

-- ============================================
-- MIGRATION COMPLETED
-- ============================================

DO $$
DECLARE
    policies_count INTEGER;
    access_count INTEGER;
    questionnaires_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO policies_count FROM policies;
    SELECT COUNT(*) INTO access_count FROM policy_access;
    SELECT COUNT(*) INTO questionnaires_count FROM questionnaires;

    RAISE NOTICE '========================================';
    RAISE NOTICE 'POLICY SYSTEM MIGRATION COMPLETED';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Policies: %', policies_count;
    RAISE NOTICE 'Access rules: %', access_count;
    RAISE NOTICE 'Questionnaires: %', questionnaires_count;
    RAISE NOTICE '========================================';
END $$;
