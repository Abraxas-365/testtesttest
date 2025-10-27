#!/bin/bash

# Cloud SQL setup script

set -e

# Configuration
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-"your-project-id"}
REGION=${REGION:-"us-central1"}
INSTANCE_NAME=${INSTANCE_NAME:-"agents-db"}
DB_NAME=${DB_NAME:-"agents_db"}
ROOT_PASSWORD=${ROOT_PASSWORD:-"$(openssl rand -base64 32)"}

echo "======================================"
echo "Setting up Cloud SQL PostgreSQL"
echo "======================================"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Instance: $INSTANCE_NAME"
echo "Database: $DB_NAME"
echo "======================================"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "Error: gcloud CLI is not installed"
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID

# Enable Cloud SQL API
echo "Enabling Cloud SQL API..."
gcloud services enable sqladmin.googleapis.com

# Create Cloud SQL instance
echo "Creating Cloud SQL instance (this may take several minutes)..."
gcloud sql instances create $INSTANCE_NAME \
    --database-version=POSTGRES_16 \
    --tier=db-f1-micro \
    --region=$REGION \
    --root-password="$ROOT_PASSWORD" \
    --storage-type=SSD \
    --storage-size=10GB \
    --storage-auto-increase \
    --backup-start-time=03:00 \
    --database-flags=max_connections=100

# Create database
echo "Creating database..."
gcloud sql databases create $DB_NAME --instance=$INSTANCE_NAME

# Get connection name
CONNECTION_NAME=$(gcloud sql instances describe $INSTANCE_NAME \
    --format='value(connectionName)')

echo "======================================"
echo "Cloud SQL setup complete!"
echo "======================================"
echo ""
echo "Connection details:"
echo "  Instance: $INSTANCE_NAME"
echo "  Connection Name: $CONNECTION_NAME"
echo "  Database: $DB_NAME"
echo "  Root Password: $ROOT_PASSWORD"
echo ""
echo "Save the root password securely!"
echo ""
echo "Next steps:"
echo "1. Create application database user:"
echo "   gcloud sql users create app_user --instance=$INSTANCE_NAME --password=YOUR_PASSWORD"
echo ""
echo "2. Run schema using Cloud SQL Proxy:"
echo "   cloud_sql_proxy -instances=$CONNECTION_NAME=tcp:5432 &"
echo "   PGPASSWORD=YOUR_PASSWORD psql -h localhost -U app_user -d $DB_NAME -f src/infrastructure/adapters/postgres/schema.sql"
echo ""
echo "3. Update Cloud Run service with connection:"
echo "   gcloud run services update YOUR_SERVICE \\"
echo "     --add-cloudsql-instances $CONNECTION_NAME \\"
echo "     --update-env-vars DB_HOST=/cloudsql/$CONNECTION_NAME"
echo ""
