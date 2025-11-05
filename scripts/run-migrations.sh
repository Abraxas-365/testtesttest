#!/bin/bash
set -e

# Load configuration
if [ -f "deploy-config.sh" ]; then
  source deploy-config.sh
else
  echo "❌ deploy-config.sh not found!"
  echo "Please create it first or run deployment script"
  exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "======================================"
echo "🗄️  Database Migration Runner"
echo "======================================"
echo "Project: $PROJECT_ID"
echo "DB Instance: $DB_INSTANCE_NAME"
echo "Database: $DB_NAME"
echo "======================================"

# Get connection name
export CONNECTION_NAME=$(gcloud sql instances describe $DB_INSTANCE_NAME \
  --format='value(connectionName)' 2>/dev/null)

if [ -z "$CONNECTION_NAME" ]; then
  echo "❌ Could not find Cloud SQL instance: $DB_INSTANCE_NAME"
  exit 1
fi

echo "Connection: $CONNECTION_NAME"
echo ""

# ==========================================
# Start Cloud SQL Proxy
# ==========================================
echo "🔌 Starting Cloud SQL Proxy..."

# Download proxy if not exists
if [ ! -f "./cloud-sql-proxy" ]; then
  echo "Downloading Cloud SQL Proxy..."
  curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.linux.amd64
  chmod +x cloud-sql-proxy
fi

# Kill existing proxy if running
pkill -f cloud-sql-proxy 2>/dev/null || true
sleep 2

# Start proxy
./cloud-sql-proxy $CONNECTION_NAME &
PROXY_PID=$!
echo "Proxy PID: $PROXY_PID"
sleep 5

# Cleanup function
cleanup() {
  echo ""
  echo "🧹 Cleaning up..."
  kill $PROXY_PID 2>/dev/null || true
  exit ${1:-0}
}

trap cleanup EXIT INT TERM

# ==========================================
# Test Database Connection
# ==========================================
echo ""
echo "🔍 Testing database connection..."

if PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME -c "SELECT 1;" > /dev/null 2>&1; then
  echo -e "${GREEN}✅ Database connection successful${NC}"
else
  echo -e "${RED}❌ Database connection failed${NC}"
  cleanup 1
fi

# ==========================================
# Create Migration Tracking Table
# ==========================================
echo ""
echo "📋 Setting up migration tracking..."

PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME <<'EOSQL'
-- Create migrations tracking table
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id SERIAL PRIMARY KEY,
    version VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(500) NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    applied_by VARCHAR(255) DEFAULT CURRENT_USER,
    execution_time_ms INTEGER,
    checksum VARCHAR(64),
    status VARCHAR(50) DEFAULT 'success'
);

CREATE INDEX IF NOT EXISTS idx_migrations_version ON schema_migrations(version);
CREATE INDEX IF NOT EXISTS idx_migrations_applied_at ON schema_migrations(applied_at);
EOSQL

echo -e "${GREEN}✅ Migration tracking table ready${NC}"

# ==========================================
# Function to Check if Migration Applied
# ==========================================
is_migration_applied() {
  local version=$1
  PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME -tAc \
    "SELECT COUNT(*) FROM schema_migrations WHERE version = '$version' AND status = 'success';"
}

# ==========================================
# Function to Run Migration
# ==========================================
run_migration() {
  local version=$1
  local name=$2
  local file=$3
  
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo -e "${BLUE}📦 Migration: $version${NC}"
  echo "   Name: $name"
  echo "   File: $file"
  
  # Check if already applied
  local applied=$(is_migration_applied $version)
  if [ "$applied" -gt 0 ]; then
    echo -e "${YELLOW}⏭️  Already applied, skipping${NC}"
    return 0
  fi
  
  # Check if file exists
  if [ ! -f "$file" ]; then
    echo -e "${RED}❌ Migration file not found: $file${NC}"
    return 1
  fi
  
  # Calculate checksum
  local checksum=$(md5sum "$file" | cut -d' ' -f1)
  
  # Run migration
  echo "   Running migration..."
  local start_time=$(date +%s%3N)
  
  if PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME -f "$file" > /dev/null 2>&1; then
    local end_time=$(date +%s%3N)
    local duration=$((end_time - start_time))
    
    # Record success
    PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME <<EOSQL
INSERT INTO schema_migrations (version, name, execution_time_ms, checksum, status)
VALUES ('$version', '$name', $duration, '$checksum', 'success');
EOSQL
    
    echo -e "${GREEN}✅ SUCCESS${NC} (${duration}ms)"
    return 0
  else
    # Record failure
    PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME <<EOSQL
INSERT INTO schema_migrations (version, name, checksum, status)
VALUES ('$version', '$name', '$checksum', 'failed');
EOSQL
    
    echo -e "${RED}❌ FAILED${NC}"
    return 1
  fi
}

# ==========================================
# Run Migrations in Order
# ==========================================
echo ""
echo "======================================"
echo "🚀 Running Migrations"
echo "======================================"

FAILED=0

# Migration 001: Initial Schema
if [ -f "src/infrastructure/adapters/postgres/schema.sql" ]; then
  run_migration "001" "Initial Schema - Agents, Tools, Corpuses" \
    "src/infrastructure/adapters/postgres/schema.sql" || FAILED=1
fi

# Migration 002: Remove area_type constraint
if [ -f "migrations/002_remove_area_type_constraint.sql" ]; then
  run_migration "002" "Remove area_type CHECK constraint for Azure AD groups" \
    "migrations/002_remove_area_type_constraint.sql" || FAILED=1
fi

# Migration 003: Azure AD Group Mappings
if [ -f "migrations/003_azure_ad_group_mappings.sql" ]; then
  run_migration "003" "Create Azure AD Group Mappings table" \
    "migrations/003_azure_ad_group_mappings.sql" || FAILED=1
fi

# Migration 004: Sessions Schema (if exists)
if [ -f "src/infrastructure/adapters/postgres/sessions_schema.sql" ]; then
  run_migration "004" "Create Sessions and Messages tables" \
    "src/infrastructure/adapters/postgres/sessions_schema.sql" || FAILED=1
fi

# ==========================================
# Show Migration Status
# ==========================================
echo ""
echo "======================================"
echo "📊 Migration Status"
echo "======================================"

PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME <<'EOSQL'
SELECT 
  version,
  name,
  status,
  applied_at,
  execution_time_ms || 'ms' as duration
FROM schema_migrations
ORDER BY version;
EOSQL

echo ""
echo "======================================"

if [ $FAILED -eq 0 ]; then
  echo -e "${GREEN}🎉 All migrations completed successfully!${NC}"
  cleanup 0
else
  echo -e "${RED}❌ Some migrations failed${NC}"
  cleanup 1
fi
