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
