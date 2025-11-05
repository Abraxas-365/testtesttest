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
