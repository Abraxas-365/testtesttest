#!/bin/bash
set -e

source deploy-config.sh

echo "======================================"
echo "🔍 Database Connection Diagnostics"
echo "======================================"
echo ""

# Get connection info
export CONNECTION_NAME=$(gcloud sql instances describe $DB_INSTANCE_NAME \
  --format='value(connectionName)')

echo "📋 Connection Details:"
echo "   Instance: $DB_INSTANCE_NAME"
echo "   Connection: $CONNECTION_NAME"
echo "   Database: $DB_NAME"
echo "   User: $DB_USER"
echo ""

# Start proxy
echo "🔌 Starting Cloud SQL Proxy..."
pkill -f cloud-sql-proxy 2>/dev/null || true
sleep 2

./cloud-sql-proxy $CONNECTION_NAME --port 5432 > /tmp/proxy.log 2>&1 &
PROXY_PID=$!
sleep 5

cleanup() {
  echo ""
  echo "🧹 Stopping proxy..."
  kill $PROXY_PID 2>/dev/null || true
}
trap cleanup EXIT

echo "✅ Proxy started (PID: $PROXY_PID)"
echo ""

# Test 1: Check if proxy is listening
echo "Test 1: Checking if proxy is listening on port 5432..."
if nc -zv 127.0.0.1 5432 2>&1 | grep -q succeeded; then
  echo "✅ Proxy is listening"
else
  echo "❌ Proxy is not listening"
  cat /tmp/proxy.log
  exit 1
fi
echo ""

# Test 2: List all databases (using postgres superuser)
echo "Test 2: Listing databases (as postgres user)..."
echo "Attempting to connect with root password..."

# First, let's check if we can list databases
if PGPASSWORD="$DB_ROOT_PASSWORD" psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "\l" 2>&1; then
  echo "✅ Connected as postgres user"
else
  echo "❌ Cannot connect as postgres user"
  echo ""
  echo "Let's try to reset the postgres password..."
  
  # Reset postgres password
  NEW_ROOT_PASSWORD=$(openssl rand -base64 24)
  gcloud sql users set-password postgres \
    --instance=$DB_INSTANCE_NAME \
    --password="$NEW_ROOT_PASSWORD"
  
  # Update config
  sed -i "s/^export DB_ROOT_PASSWORD=.*/export DB_ROOT_PASSWORD=\"$NEW_ROOT_PASSWORD\"/" deploy-config.sh
  export DB_ROOT_PASSWORD="$NEW_ROOT_PASSWORD"
  
  echo "✅ Password reset. New password saved to deploy-config.sh"
  
  # Save to secrets file
  cat > ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt <<EOL
Project: $PROJECT_ID
DB Instance: $DB_INSTANCE_NAME
Database: $DB_NAME
Root User: postgres
Root Password: $DB_ROOT_PASSWORD
App User: $DB_USER
App Password: $DB_APP_PASSWORD
Updated: $(date)
EOL
  
  echo "✅ Saved to ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt"
  sleep 2
  
  # Try again
  if PGPASSWORD="$DB_ROOT_PASSWORD" psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "\l" > /dev/null 2>&1; then
    echo "✅ Now connected successfully"
  else
    echo "❌ Still cannot connect"
    exit 1
  fi
fi
echo ""

# Test 3: Check if app user exists and works
echo "Test 3: Checking app user ($DB_USER)..."

# List users
echo "Current database users:"
PGPASSWORD="$DB_ROOT_PASSWORD" psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "\du"
echo ""

# Check if app user exists
USER_EXISTS=$(PGPASSWORD="$DB_ROOT_PASSWORD" psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -tAc \
  "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER';")

if [ "$USER_EXISTS" = "1" ]; then
  echo "✅ User $DB_USER exists"
  
  # Reset app user password
  echo "Resetting app user password..."
  NEW_APP_PASSWORD=$(openssl rand -base64 24)
  PGPASSWORD="$DB_ROOT_PASSWORD" psql -h 127.0.0.1 -p 5432 -U postgres -d postgres <<EOSQL
ALTER USER $DB_USER WITH PASSWORD '$NEW_APP_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOSQL
  
  # Update config
  sed -i "s/^export DB_APP_PASSWORD=.*/export DB_APP_PASSWORD=\"$NEW_APP_PASSWORD\"/" deploy-config.sh
  export DB_APP_PASSWORD="$NEW_APP_PASSWORD"
  
  echo "✅ App user password reset"
  
  # Update secrets file
  cat > ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt <<EOL
Project: $PROJECT_ID
DB Instance: $DB_INSTANCE_NAME
Database: $DB_NAME
Root User: postgres
Root Password: $DB_ROOT_PASSWORD
App User: $DB_USER
App Password: $DB_APP_PASSWORD
Updated: $(date)
EOL

else
  echo "⚠️  User $DB_USER does not exist, creating..."
  
  NEW_APP_PASSWORD=$(openssl rand -base64 24)
  PGPASSWORD="$DB_ROOT_PASSWORD" psql -h 127.0.0.1 -p 5432 -U postgres -d postgres <<EOSQL
CREATE USER $DB_USER WITH PASSWORD '$NEW_APP_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOSQL
  
  # Update config
  sed -i "s/^export DB_APP_PASSWORD=.*/export DB_APP_PASSWORD=\"$NEW_APP_PASSWORD\"/" deploy-config.sh
  export DB_APP_PASSWORD="$NEW_APP_PASSWORD"
  
  echo "✅ User created"
  
  # Update secrets file
  cat > ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt <<EOL
Project: $PROJECT_ID
DB Instance: $DB_INSTANCE_NAME
Database: $DB_NAME
Root User: postgres
Root Password: $DB_ROOT_PASSWORD
App User: $DB_USER
App Password: $DB_APP_PASSWORD
Updated: $(date)
EOL
fi
echo ""

# Test 4: Test connection with app user
echo "Test 4: Testing connection as app user..."
if PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -p 5432 -U $DB_USER -d $DB_NAME -c "SELECT 1;" > /dev/null 2>&1; then
  echo "✅ App user can connect to database!"
else
  echo "❌ App user cannot connect"
  
  # Grant more permissions
  echo "Granting additional permissions..."
  PGPASSWORD="$DB_ROOT_PASSWORD" psql -h 127.0.0.1 -p 5432 -U postgres -d $DB_NAME <<EOSQL
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;
EOSQL
  
  echo "✅ Permissions granted"
  
  # Try again
  if PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -p 5432 -U $DB_USER -d $DB_NAME -c "SELECT 1;" > /dev/null 2>&1; then
    echo "✅ Now connected successfully!"
  else
    echo "❌ Still cannot connect"
    exit 1
  fi
fi
echo ""

# Test 5: Update secret manager
echo "Test 5: Updating Secret Manager..."
echo -n "$DB_APP_PASSWORD" | gcloud secrets versions add db-password --data-file=-
echo "✅ Secret Manager updated"
echo ""

echo "======================================"
echo "🎉 All diagnostics passed!"
echo "======================================"
echo ""
echo "Updated credentials:"
echo "   App User: $DB_USER"
echo "   App Password: (saved to deploy-config.sh and Secret Manager)"
echo ""
echo "You can now run migrations with:"
echo "   ./run-migrations.sh"
echo ""

