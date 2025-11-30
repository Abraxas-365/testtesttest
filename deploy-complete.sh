#!/bin/bash
set -e  # Exit on error

# Load configuration
source deploy-config.sh

echo "======================================"
echo "🚀 ADK Agent Service Deployment"
echo "======================================"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo "DB Instance: $DB_INSTANCE_NAME"
echo "Authentication: Multi-mode (Bot + Teams SSO + Web OAuth2)"
echo "======================================"

# ==========================================
# STEP 1: Enable Required APIs
# ==========================================
echo ""
echo "📦 Step 1: Enabling required APIs..."
gcloud services enable \
  sqladmin.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  containerregistry.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com

echo "✅ APIs enabled"

# ==========================================
# STEP 2: Set IAM Permissions
# ==========================================
echo ""
echo "🔑 Step 2: Setting up IAM permissions..."

export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
export COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Grant Cloud Build permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CLOUDBUILD_SA" \
  --role="roles/storage.admin" \
  --no-user-output-enabled

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CLOUDBUILD_SA" \
  --role="roles/editor" \
  --no-user-output-enabled

# Grant Compute Engine (Cloud Run) permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$COMPUTE_SA" \
  --role="roles/cloudsql.client" \
  --no-user-output-enabled

echo "✅ IAM permissions set"

# ==========================================
# STEP 3: Create Cloud SQL Instance
# ==========================================
echo ""
echo "🗄️  Step 3: Creating Cloud SQL instance..."

# Check if instance already exists
if gcloud sql instances describe $DB_INSTANCE_NAME &>/dev/null; then
  echo "⚠️  Cloud SQL instance already exists, skipping creation"
else
  gcloud sql instances create $DB_INSTANCE_NAME \
    --database-version=POSTGRES_16 \
    --tier=db-custom-1-3840 \
    --region=$REGION \
    --root-password="$DB_ROOT_PASSWORD" \
    --storage-auto-increase \
    --storage-size=10GB \
    --backup-start-time=03:00 \
    --no-assign-ip

  echo "⏳ Waiting for Cloud SQL instance to be ready..."
  while [ "$(gcloud sql instances describe $DB_INSTANCE_NAME --format='value(state)')" != "RUNNABLE" ]; do
    echo "   Still creating..."
    sleep 10
  done

  echo "✅ Cloud SQL instance created"
fi

# ==========================================
# STEP 4: Configure Database
# ==========================================
echo ""
echo "🔧 Step 4: Configuring database..."

# Set root password (in case instance already existed)
gcloud sql users set-password postgres \
  --instance=$DB_INSTANCE_NAME \
  --password="$DB_ROOT_PASSWORD"

# Create database
gcloud sql databases create $DB_NAME --instance=$DB_INSTANCE_NAME 2>/dev/null || echo "Database already exists"

# Create application user
gcloud sql users create $DB_USER \
  --instance=$DB_INSTANCE_NAME \
  --password="$DB_APP_PASSWORD" 2>/dev/null || \
gcloud sql users set-password $DB_USER \
  --instance=$DB_INSTANCE_NAME \
  --password="$DB_APP_PASSWORD"

echo "✅ Database configured"

# Save passwords securely
mkdir -p ~/.gcp-secrets
cat > ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt <<EOL
===========================================
GrupoDC Agent Service - Credentials
===========================================
Project: $PROJECT_ID
Region: $REGION
Created: $(date)

DATABASE CONFIGURATION:
-----------------------
DB Instance: $DB_INSTANCE_NAME
Database: $DB_NAME
Root User: postgres
Root Password: $DB_ROOT_PASSWORD
App User: $DB_USER
App Password: $DB_APP_PASSWORD

AZURE AD / MICROSOFT ENTRA ID:
-------------------------------
Tenant ID: $AZURE_TENANT_ID
Client ID: $AZURE_CLIENT_ID
Client Secret: $AZURE_CLIENT_SECRET
Redirect URI: $AZURE_REDIRECT_URI
Frontend URL: $FRONTEND_URL

MICROSOFT GRAPH API:
--------------------
Tenant ID: $GRAPH_TENANT_ID
Client ID: $GRAPH_CLIENT_ID
Client Secret: $GRAPH_CLIENT_SECRET

IMPORTANT NOTES:
----------------
1. These credentials are SENSITIVE - keep them secure!
2. Add redirect URI to Azure AD App Registration:
   - Go to: https://portal.azure.com
   - Azure AD → App Registrations → Your App
   - Authentication → Add Web redirect URI:
     $AZURE_REDIRECT_URI
3. Grant API permissions:
   - openid, profile, email, User.Read
4. Grant admin consent for the organization
5. Client Secret expires - renew before expiration!

===========================================
EOL
chmod 600 ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt
echo "🔐 Passwords saved to ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt"

# ==========================================
# STEP 5: Initialize Database Schema
# ==========================================
echo ""
echo "📋 Step 5: Initializing database schema..."

export CONNECTION_NAME=$(gcloud sql instances describe $DB_INSTANCE_NAME \
  --format='value(connectionName)')

# Download Cloud SQL Proxy if not exists
if [ ! -f "./cloud-sql-proxy" ]; then
  echo "Downloading Cloud SQL Proxy..."
  curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.linux.amd64
  chmod +x cloud-sql-proxy
fi

# Start proxy in background
echo "Starting Cloud SQL Proxy..."
./cloud-sql-proxy $CONNECTION_NAME &
PROXY_PID=$!
sleep 5

# Run schema migrations
echo "Running schema migrations..."
if [ -f "src/infrastructure/adapters/postgres/schema.sql" ]; then
  PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME \
    -f src/infrastructure/adapters/postgres/schema.sql
else
  echo "⚠️  schema.sql not found, skipping initial schema setup"
fi

# Run additional migrations if they exist
if [ -f "migrations/002_remove_area_type_constraint.sql" ]; then
  echo "Running migration 002..."
  PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME \
    -f migrations/002_remove_area_type_constraint.sql
fi

if [ -f "migrations/003_azure_ad_group_mappings.sql" ]; then
  echo "Running migration 003..."
  PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME \
    -f migrations/003_azure_ad_group_mappings.sql
fi

# Stop proxy
kill $PROXY_PID 2>/dev/null || true

echo "✅ Database schema initialized"

# ==========================================
# STEP 6: Create Secrets in Secret Manager
# ==========================================
echo ""
echo "🔒 Step 6: Creating secrets in Secret Manager..."

# Database password secret
if gcloud secrets describe db-password &>/dev/null; then
  echo "Updating existing db-password secret..."
  echo -n "$DB_APP_PASSWORD" | gcloud secrets versions add db-password --data-file=-
else
  echo "Creating new db-password secret..."
  echo -n "$DB_APP_PASSWORD" | gcloud secrets create db-password \
    --data-file=- \
    --replication-policy="automatic"
fi

# Azure AD Client Secret
if gcloud secrets describe azure-client-secret &>/dev/null; then
  echo "Updating existing azure-client-secret..."
  echo -n "$AZURE_CLIENT_SECRET" | gcloud secrets versions add azure-client-secret --data-file=-
else
  echo "Creating new azure-client-secret..."
  echo -n "$AZURE_CLIENT_SECRET" | gcloud secrets create azure-client-secret \
    --data-file=- \
    --replication-policy="automatic"
fi

# Microsoft Graph Client Secret (if different from Azure)
if [ "$GRAPH_CLIENT_SECRET" != "$AZURE_CLIENT_SECRET" ]; then
  if gcloud secrets describe graph-client-secret &>/dev/null; then
    echo "Updating existing graph-client-secret..."
    echo -n "$GRAPH_CLIENT_SECRET" | gcloud secrets versions add graph-client-secret --data-file=-
  else
    echo "Creating new graph-client-secret..."
    echo -n "$GRAPH_CLIENT_SECRET" | gcloud secrets create graph-client-secret \
      --data-file=- \
      --replication-policy="automatic"
  fi
fi

# Grant Cloud Run access to secrets
echo "Granting Cloud Run access to secrets..."
for secret in db-password azure-client-secret graph-client-secret; do
  if gcloud secrets describe $secret &>/dev/null; then
    gcloud secrets add-iam-policy-binding $secret \
      --member="serviceAccount:$COMPUTE_SA" \
      --role="roles/secretmanager.secretAccessor" \
      --no-user-output-enabled
  fi
done

echo "✅ Secrets configured"

# ==========================================
# STEP 7: Build Container
# ==========================================
echo ""
echo "🏗️  Step 7: Building container image..."
echo "This will take 2-5 minutes..."

gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

echo "✅ Container built successfully"

# ==========================================
# STEP 8: Deploy to Cloud Run
# ==========================================
echo ""
echo "🚀 Step 8: Deploying to Cloud Run..."

# Build environment variables string
ENV_VARS="ENVIRONMENT=production"
ENV_VARS="$ENV_VARS,DB_HOST=/cloudsql/$CONNECTION_NAME"
ENV_VARS="$ENV_VARS,DB_PORT=5432"
ENV_VARS="$ENV_VARS,DB_NAME=$DB_NAME"
ENV_VARS="$ENV_VARS,DB_USER=$DB_USER"
ENV_VARS="$ENV_VARS,GOOGLE_CLOUD_PROJECT=$PROJECT_ID"
ENV_VARS="$ENV_VARS,GOOGLE_GENAI_USE_VERTEXAI=$GOOGLE_GENAI_USE_VERTEXAI"
ENV_VARS="$ENV_VARS,PERSIST_SESSIONS=$PERSIST_SESSIONS"
ENV_VARS="$ENV_VARS,AZURE_TENANT_ID=$AZURE_TENANT_ID"
ENV_VARS="$ENV_VARS,AZURE_CLIENT_ID=$AZURE_CLIENT_ID"
ENV_VARS="$ENV_VARS,AZURE_REDIRECT_URI=$AZURE_REDIRECT_URI"
ENV_VARS="$ENV_VARS,FRONTEND_URL=$FRONTEND_URL"
ENV_VARS="$ENV_VARS,GRAPH_TENANT_ID=$GRAPH_TENANT_ID"
ENV_VARS="$ENV_VARS,GRAPH_CLIENT_ID=$GRAPH_CLIENT_ID"

# Build secrets string
SECRETS="DB_PASSWORD=db-password:latest"
SECRETS="$SECRETS,AZURE_CLIENT_SECRET=azure-client-secret:latest"

# Add Graph secret if different
if [ "$GRAPH_CLIENT_SECRET" != "$AZURE_CLIENT_SECRET" ]; then
  SECRETS="$SECRETS,GRAPH_CLIENT_SECRET=graph-client-secret:latest"
else
  # Use same secret for both
  SECRETS="$SECRETS,GRAPH_CLIENT_SECRET=azure-client-secret:latest"
fi

gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --no-allow-unauthenticated \
  --memory $MEMORY \
  --cpu $CPU \
  --min-instances $MIN_INSTANCES \
  --max-instances $MAX_INSTANCES \
  --timeout $TIMEOUT \
  --add-cloudsql-instances $CONNECTION_NAME \
  --set-env-vars "$ENV_VARS" \
  --set-secrets "$SECRETS"

echo "✅ Service deployed"

# Grant yourself invoker permissions
export USER_EMAIL=$(gcloud config get-value account)
gcloud run services add-iam-policy-binding $SERVICE_NAME \
  --region=$REGION \
  --member="user:$USER_EMAIL" \
  --role="roles/run.invoker" \
  --no-user-output-enabled

# ==========================================
# STEP 9: Verify Deployment
# ==========================================
echo ""
echo "✓ Step 9: Verifying deployment..."

export SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --format 'value(status.url)')

echo "Waiting for service to be ready..."
sleep 10

# Test health endpoint
echo "Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  $SERVICE_URL/health)

HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$HEALTH_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Health check passed!"
  echo "Response:"
  echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
else
  echo "⚠️  Health check returned: $HTTP_CODE"
  echo "Response: $RESPONSE_BODY"
fi

# Test auth status endpoint
echo ""
echo "Testing auth status endpoint..."
AUTH_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  $SERVICE_URL/api/v1/auth/status)

HTTP_CODE=$(echo "$AUTH_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$AUTH_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Auth endpoint working!"
  echo "Response:"
  echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
else
  echo "⚠️  Auth status returned: $HTTP_CODE"
  echo "Response: $RESPONSE_BODY"
fi

# ==========================================
# DEPLOYMENT COMPLETE
# ==========================================
echo ""
echo "======================================"
echo "🎉 DEPLOYMENT COMPLETE!"
echo "======================================"
echo ""
echo "📍 Service Information:"
echo "   Service URL: $SERVICE_URL"
echo "   API Docs: $SERVICE_URL/docs"
echo "   Region: $REGION"
echo "   Database: $CONNECTION_NAME"
echo "   Session Persistence: ENABLED ✅"
echo ""
echo "🔐 Azure AD Configuration:"
echo "   Tenant ID: $AZURE_TENANT_ID"
echo "   Client ID: $AZURE_CLIENT_ID"
echo "   Redirect URI: $AZURE_REDIRECT_URI"
echo "   Frontend URL: $FRONTEND_URL"
echo ""
echo "⚠️  IMPORTANT: Configure Azure AD App Registration!"
echo "   1. Go to: https://portal.azure.com"
echo "   2. Navigate to: Azure AD → App Registrations → Your App"
echo "   3. Go to Authentication → Add Web redirect URI:"
echo "      $AZURE_REDIRECT_URI"
echo "   4. API Permissions → Add:"
echo "      - openid (Delegated)"
echo "      - profile (Delegated)"
echo "      - email (Delegated)"
echo "      - User.Read (Delegated)"
echo "   5. Grant admin consent for your organization"
echo ""
echo "📁 Credentials:"
echo "   Saved to: ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt"
echo ""
echo "======================================"
echo "🧪 Test Commands:"
echo "======================================"
echo ""
echo "# 1. Health Check"
echo "curl -H 'Authorization: Bearer \$(gcloud auth print-identity-token)' \\"
echo "  $SERVICE_URL/health"
echo ""
echo "# 2. Get OAuth2 Login URL (Web Authentication)"
echo "curl -H 'Authorization: Bearer \$(gcloud auth print-identity-token)' \\"
echo "  '$SERVICE_URL/api/v1/auth/login-url?redirect_uri=$AZURE_REDIRECT_URI'"
echo ""
echo "# 3. Check Auth Status"
echo "curl -H 'Authorization: Bearer \$(gcloud auth print-identity-token)' \\"
echo "  $SERVICE_URL/api/v1/auth/status"
echo ""
echo "# 4. Teams Bot Message (Legacy)"
echo "curl -X POST \\"
echo "  -H 'Authorization: Bearer \$(gcloud auth print-identity-token)' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"user_message\": \"Hello\", \"aad_user_id\": \"test-user\", \"user_name\": \"Test User\"}' \\"
echo "  $SERVICE_URL/api/v1/teams/message"
echo ""
echo "# 5. Teams Tab / Web Invoke (Requires Teams SSO token or session cookie)"
echo "curl -X POST \\"
echo "  -H 'Authorization: Bearer YOUR_TEAMS_SSO_TOKEN' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"prompt\": \"Hello\", \"agent_name\": \"search_assistant\"}' \\"
echo "  $SERVICE_URL/api/v1/tabs/invoke"
echo ""
echo "======================================"
echo "📊 Monitoring & Logs:"
echo "======================================"
echo ""
echo "# View real-time logs:"
echo "gcloud logging tail \"resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME\" \\"
echo "  --project $PROJECT_ID"
echo ""
echo "# View in Cloud Console:"
echo "https://console.cloud.google.com/run/detail/$REGION/$SERVICE_NAME/logs?project=$PROJECT_ID"
echo ""
echo "======================================"
echo "📝 Next Steps:"
echo "======================================"
echo ""
echo "1. ✅ Configure Azure AD redirect URI (see above)"
echo "2. ✅ Test OAuth2 login flow with a browser"
echo "3. ✅ Deploy frontend and update FRONTEND_URL"
echo "4. ✅ Update CORS in src/main.py with frontend domain"
echo "5. ✅ Test Teams Tab authentication"
echo "6. ✅ Monitor logs for any errors"
echo ""
echo "======================================"
