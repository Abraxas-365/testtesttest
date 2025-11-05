#!/bin/bash
set -e

echo "======================================"
echo "🔐 Fixing Authentication & Running Migrations"
echo "======================================"

# Load configuration
source deploy-config.sh

echo ""
echo "Step 1: Re-authenticating with Google Cloud..."
echo "This will open a browser window for authentication."
echo ""

# Clear existing credentials
gcloud auth application-default revoke 2>/dev/null || true

# Re-authenticate with application default credentials
echo "Please authenticate in your browser..."
gcloud auth application-default login

echo ""
echo "✅ Authentication refreshed"
echo ""

# Verify authentication works
echo "Step 2: Verifying Cloud SQL access..."
export CONNECTION_NAME=$(gcloud sql instances describe $DB_INSTANCE_NAME \
  --format='value(connectionName)')

if [ -z "$CONNECTION_NAME" ]; then
  echo "❌ Could not access Cloud SQL instance"
  exit 1
fi

echo "✅ Cloud SQL instance accessible: $CONNECTION_NAME"
echo ""

# Download fresh proxy
echo "Step 3: Downloading fresh Cloud SQL Proxy..."
rm -f cloud-sql-proxy
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.linux.amd64
chmod +x cloud-sql-proxy

echo "✅ Cloud SQL Proxy downloaded"
echo ""

# Kill any existing proxy
pkill -f cloud-sql-proxy 2>/dev/null || true
sleep 2

# Start proxy with verbose output
echo "Step 4: Starting Cloud SQL Proxy..."
./cloud-sql-proxy $CONNECTION_NAME --port 5432 &
PROXY_PID=$!

echo "Proxy PID: $PROXY_PID"
echo "Waiting for proxy to be ready..."
sleep 10

# Test connection
echo ""
echo "Step 5: Testing database connection..."

if PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -p 5432 -U $DB_USER -d $DB_NAME -c "SELECT 1;" > /dev/null 2>&1; then
  echo "✅ Database connection successful!"
else
  echo "❌ Database connection failed"
  echo ""
  echo "Debug info:"
  ps aux | grep cloud-sql-proxy
  echo ""
  echo "Trying to kill proxy and show errors..."
  kill $PROXY_PID 2>/dev/null || true
  exit 1
fi

echo ""
echo "Step 6: Running schema migrations..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Migration 1: Main schema
echo ""
echo "📦 Migration 1: Initial Schema"
if [ -f "src/infrastructure/adapters/postgres/schema.sql" ]; then
  PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -p 5432 -U $DB_USER -d $DB_NAME \
    -f src/infrastructure/adapters/postgres/schema.sql
  echo "✅ Schema applied"
else
  echo "⚠️  schema.sql not found, skipping"
fi

# Migration 2: Remove area_type constraint
echo ""
echo "📦 Migration 2: Remove area_type constraint"
if [ -f "migrations/002_remove_area_type_constraint.sql" ]; then
  PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -p 5432 -U $DB_USER -d $DB_NAME \
    -f migrations/002_remove_area_type_constraint.sql
  echo "✅ Constraint removed"
else
  echo "⚠️  Migration file not found, skipping"
fi

# Migration 3: Azure AD mappings
echo ""
echo "📦 Migration 3: Azure AD Group Mappings"
if [ -f "migrations/003_azure_ad_group_mappings.sql" ]; then
  PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -p 5432 -U $DB_USER -d $DB_NAME \
    -f migrations/003_azure_ad_group_mappings.sql
  echo "✅ Group mappings created"
else
  echo "⚠️  Migration file not found, skipping"
fi

# Migration 4: Sessions (if exists)
echo ""
echo "📦 Migration 4: Sessions Schema (optional)"
if [ -f "src/infrastructure/adapters/postgres/sessions_schema.sql" ]; then
  PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -p 5432 -U $DB_USER -d $DB_NAME \
    -f src/infrastructure/adapters/postgres/sessions_schema.sql
  echo "✅ Sessions schema applied"
else
  echo "⚠️  Sessions schema not found, skipping"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verify tables were created
echo "Step 7: Verifying database tables..."
PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -p 5432 -U $DB_USER -d $DB_NAME <<'EOSQL'
\dt
EOSQL

echo ""
echo "Checking table counts..."
PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -p 5432 -U $DB_USER -d $DB_NAME <<'EOSQL'
SELECT 'agents' as table_name, COUNT(*) as count FROM agents
UNION ALL
SELECT 'tools', COUNT(*) FROM tools
UNION ALL
SELECT 'corpuses', COUNT(*) FROM corpuses
UNION ALL
SELECT 'azure_ad_group_mappings', COUNT(*) FROM azure_ad_group_mappings;
EOSQL

# Stop proxy
echo ""
echo "🧹 Cleaning up..."
kill $PROXY_PID 2>/dev/null || true

echo ""
echo "======================================"
echo "🎉 Migrations completed successfully!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Build and deploy the service:"
echo "   gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME"
echo "   gcloud run deploy $SERVICE_NAME --image gcr.io/$PROJECT_ID/$SERVICE_NAME --region $REGION"
echo ""

