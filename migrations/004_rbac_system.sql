-- ============================================
-- RBAC System Migration
-- Role-Based Access Control with Superadmin Whitelist
-- and Entra ID Group to Role Mapping
-- ============================================

BEGIN;

-- ============================================
-- 1. SUPERADMIN WHITELIST TABLE
-- ============================================
-- Stores email addresses of users with superadmin privileges
CREATE TABLE IF NOT EXISTS superadmin_whitelist (
    whitelist_id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    added_by_email VARCHAR(255) NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    notes TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    CONSTRAINT superadmin_whitelist_email_unique UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_superadmin_whitelist_email ON superadmin_whitelist(LOWER(email));
CREATE INDEX IF NOT EXISTS idx_superadmin_whitelist_enabled ON superadmin_whitelist(enabled);

-- ============================================
-- 2. RBAC ROLES TABLE
-- ============================================
-- Defines available roles with their permissions
CREATE TABLE IF NOT EXISTS rbac_roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    weight INTEGER NOT NULL DEFAULT 0,  -- Higher weight = more privileged
    permissions JSONB NOT NULL DEFAULT '[]'::jsonb,  -- Array of permission strings
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT rbac_roles_name_unique UNIQUE (role_name)
);

CREATE INDEX IF NOT EXISTS idx_rbac_roles_name ON rbac_roles(role_name);
CREATE INDEX IF NOT EXISTS idx_rbac_roles_weight ON rbac_roles(weight DESC);
CREATE INDEX IF NOT EXISTS idx_rbac_roles_enabled ON rbac_roles(enabled);

-- Trigger for auto-updating updated_at
CREATE OR REPLACE FUNCTION update_rbac_roles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS rbac_roles_updated_at ON rbac_roles;
CREATE TRIGGER rbac_roles_updated_at
    BEFORE UPDATE ON rbac_roles
    FOR EACH ROW
    EXECUTE FUNCTION update_rbac_roles_updated_at();

-- Insert predefined roles with their permissions
INSERT INTO rbac_roles (role_name, display_name, description, weight, permissions) VALUES
(
    'superadmin',
    'Super Administrator',
    'Full system access including superadmin management',
    1000,
    '["*"]'::jsonb
),
(
    'admin',
    'Administrator',
    'Full access to all resources except superadmin whitelist management',
    900,
    '[
        "agents:list", "agents:view", "agents:create", "agents:edit", "agents:delete", "agents:invoke",
        "policies:list", "policies:view", "policies:create", "policies:edit", "policies:delete", "policies:publish", "policies:share",
        "documents:upload", "documents:list", "documents:view", "documents:delete",
        "sessions:list", "sessions:view", "sessions:delete_own", "sessions:delete_all",
        "group_mappings:list", "group_mappings:view", "group_mappings:create", "group_mappings:edit", "group_mappings:delete"
    ]'::jsonb
),
(
    'editor',
    'Editor',
    'Can create and edit resources but limited delete and admin capabilities',
    500,
    '[
        "agents:list", "agents:view", "agents:invoke",
        "policies:list", "policies:view", "policies:create", "policies:edit",
        "documents:upload", "documents:list", "documents:view",
        "sessions:list_own", "sessions:view_own", "sessions:delete_own"
    ]'::jsonb
),
(
    'viewer',
    'Viewer',
    'Read-only access to resources',
    100,
    '[
        "agents:list", "agents:view", "agents:invoke",
        "policies:list", "policies:view",
        "documents:list", "documents:view",
        "sessions:list_own", "sessions:view_own"
    ]'::jsonb
)
ON CONFLICT (role_name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    weight = EXCLUDED.weight,
    permissions = EXCLUDED.permissions,
    updated_at = NOW();

-- ============================================
-- 3. ENTRA ID GROUP TO ROLE MAPPINGS
-- ============================================
-- Maps Azure AD / Entra ID groups to RBAC roles
CREATE TABLE IF NOT EXISTS entra_group_role_mappings (
    mapping_id SERIAL PRIMARY KEY,
    group_id VARCHAR(255),  -- Azure AD Group Object ID (optional, for validation)
    group_name VARCHAR(255) NOT NULL,  -- Azure AD group display name
    role_name VARCHAR(50) NOT NULL,
    description TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    created_by_email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT entra_group_role_mappings_group_unique UNIQUE (group_name),
    CONSTRAINT entra_group_role_mappings_role_fk FOREIGN KEY (role_name)
        REFERENCES rbac_roles(role_name) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_entra_group_role_mappings_group ON entra_group_role_mappings(group_name);
CREATE INDEX IF NOT EXISTS idx_entra_group_role_mappings_role ON entra_group_role_mappings(role_name);
CREATE INDEX IF NOT EXISTS idx_entra_group_role_mappings_enabled ON entra_group_role_mappings(enabled);

-- Trigger for auto-updating updated_at
CREATE OR REPLACE FUNCTION update_entra_group_role_mappings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS entra_group_role_mappings_updated_at ON entra_group_role_mappings;
CREATE TRIGGER entra_group_role_mappings_updated_at
    BEFORE UPDATE ON entra_group_role_mappings
    FOR EACH ROW
    EXECUTE FUNCTION update_entra_group_role_mappings_updated_at();

-- ============================================
-- 4. RBAC AUDIT LOG
-- ============================================
-- Tracks all RBAC-related changes for security auditing
CREATE TABLE IF NOT EXISTS rbac_audit_log (
    log_id SERIAL PRIMARY KEY,
    action VARCHAR(50) NOT NULL,  -- e.g., 'superadmin_added', 'mapping_created'
    performed_by_email VARCHAR(255) NOT NULL,
    target_resource VARCHAR(100) NOT NULL,  -- e.g., 'superadmin_whitelist', 'entra_group_role_mappings'
    target_id VARCHAR(255),  -- ID or email of the affected resource
    old_value JSONB,
    new_value JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rbac_audit_log_action ON rbac_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_rbac_audit_log_performed_by ON rbac_audit_log(performed_by_email);
CREATE INDEX IF NOT EXISTS idx_rbac_audit_log_target ON rbac_audit_log(target_resource, target_id);
CREATE INDEX IF NOT EXISTS idx_rbac_audit_log_created_at ON rbac_audit_log(created_at DESC);

-- ============================================
-- 5. HELPER FUNCTIONS
-- ============================================

-- Function to check if a user is a superadmin
CREATE OR REPLACE FUNCTION is_superadmin(user_email VARCHAR)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS(
        SELECT 1 FROM superadmin_whitelist
        WHERE LOWER(email) = LOWER(user_email) AND enabled = TRUE
    );
END;
$$ LANGUAGE plpgsql;

-- Function to get role for user based on their groups
CREATE OR REPLACE FUNCTION get_role_for_groups(group_names TEXT[])
RETURNS TABLE(
    role_name VARCHAR,
    display_name VARCHAR,
    weight INTEGER,
    permissions JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT r.role_name, r.display_name, r.weight, r.permissions
    FROM entra_group_role_mappings m
    JOIN rbac_roles r ON m.role_name = r.role_name
    WHERE m.group_name = ANY(group_names)
      AND m.enabled = TRUE
      AND r.enabled = TRUE
    ORDER BY r.weight DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

COMMIT;
