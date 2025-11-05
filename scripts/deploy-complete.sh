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
echo "🔐 Step 2: Setting up IAM permissions..."

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
Project: $PROJECT_ID
DB Instance: $DB_INSTANCE_NAME
Database: $DB_NAME
Root User: postgres
Root Password: $DB_ROOT_PASSWORD
App User: $DB_USER
App Password: $DB_APP_PASSWORD
Created: $(date)
EOL
chmod 600 ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt
echo "🔑 Passwords saved to ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt"

# ==========================================
# STEP 5: Initialize Database Schema
# ==========================================
echo ""
echo "📊 Step 5: Initializing database schema..."

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
PGPASSWORD="$DB_APP_PASSWORD" psql -h 127.0.0.1 -U $DB_USER -d $DB_NAME \
  -f src/infrastructure/adapters/postgres/schema.sql

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
# STEP 6: Create Secrets
# ==========================================
echo ""
echo "🔐 Step 6: Creating secrets..."

# Create or update db-password secret
if gcloud secrets describe db-password &>/dev/null; then
  echo "Updating existing secret..."
  echo -n "$DB_APP_PASSWORD" | gcloud secrets versions add db-password --data-file=-
else
  echo "Creating new secret..."
  echo -n "$DB_APP_PASSWORD" | gcloud secrets create db-password \
    --data-file=- \
    --replication-policy="automatic"
fi

# Grant Cloud Run access to secret
gcloud secrets add-iam-policy-binding db-password \
  --member="serviceAccount:$COMPUTE_SA" \
  --role="roles/secretmanager.secretAccessor" \
  --no-user-output-enabled

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
echo "🚢 Step 8: Deploying to Cloud Run..."

gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --no-allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --timeout 300 \
  --add-cloudsql-instances $CONNECTION_NAME \
  --set-env-vars "ENVIRONMENT=production,DB_HOST=/cloudsql/$CONNECTION_NAME,DB_PORT=5432,DB_NAME=$DB_NAME,DB_USER=$DB_USER,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_GENAI_USE_VERTEXAI=TRUE,PERSIST_SESSIONS=false" \
  --set-secrets "DB_PASSWORD=db-password:latest"

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
echo "✅ Step 9: Verifying deployment..."

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
  echo "Response: $RESPONSE_BODY"
else
  echo "⚠️  Health check returned: $HTTP_CODE"
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
echo "📝 Service Information:"
echo "   Service URL: $SERVICE_URL"
echo "   API Docs: $SERVICE_URL/docs"
echo "   Region: $REGION"
echo "   Database: $CONNECTION_NAME"
echo ""
echo "🔑 Credentials:"
echo "   Saved to: ~/.gcp-secrets/db-passwords-${PROJECT_ID}.txt"
echo ""
echo "🧪 Test Commands:"
echo ""
echo "# List agents:"
echo "curl -H 'Authorization: Bearer \$(gcloud auth print-identity-token)' \\"
echo "  $SERVICE_URL/api/v1/agents"
echo ""
echo "# Invoke agent:"
echo "curl -X POST \\"
echo "  -H 'Authorization: Bearer \$(gcloud auth print-identity-token)' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"agent_name\": \"search_assistant\", \"prompt\": \"Hello!\"}' \\"
echo "  $SERVICE_URL/api/v1/invoke"
echo ""
echo "📊 View logs:"
echo "gcloud run services logs read $SERVICE_NAME --region $REGION --limit 50"
echo ""
echo "======================================"

