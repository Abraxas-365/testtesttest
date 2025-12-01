#!/bin/bash
# ============================================================================
# Deployment Configuration
# ============================================================================
# This file contains all configuration variables for the deployment script.
# Copy this file and customize the values for your environment.

# GCP Configuration
export PROJECT_ID="your-project-id"
export REGION="us-east4"
export SERVICE_NAME="grupodc-agent-backend-dev"

# Database Configuration
export DB_INSTANCE_NAME="adk-agents-db"
export DB_NAME="agents_db"
export DB_USER="agents_app"

# Database Passwords (CHANGE THESE!)
# Use strong, randomly generated passwords in production
export DB_ROOT_PASSWORD="$(openssl rand -base64 32)"
export DB_APP_PASSWORD="$(openssl rand -base64 32)"

# ============================================================================
# AZURE AD / MICROSOFT ENTRA ID CONFIGURATION
# ============================================================================
# Get these values from: https://portal.azure.com → Azure AD → App Registrations

# Azure AD Tenant ID (Directory ID)
export AZURE_TENANT_ID="your-tenant-id-guid"

# Azure AD Application (Client) ID
export AZURE_CLIENT_ID="8f932a37-a7f6-4fe8-be5e-a72ab69758cf"

# Azure AD Client Secret (CHANGE THIS!)
# Get this from: Azure AD → App Registrations → Your App → Certificates & secrets
export AZURE_CLIENT_SECRET="your-client-secret"

# OAuth2 Configuration
# After deployment, update this with your actual Cloud Run URL
export AZURE_REDIRECT_URI="https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback"

# Frontend URL
# Update this with your frontend URL after deployment
export FRONTEND_URL="http://localhost:5173"

# ============================================================================
# MICROSOFT GRAPH API CONFIGURATION (Optional)
# ============================================================================
# Usually these should be the SAME as AZURE_* values above
# Only set different values if using a separate App Registration for Graph API

export GRAPH_TENANT_ID="$AZURE_TENANT_ID"
export GRAPH_CLIENT_ID="$AZURE_CLIENT_ID"
export GRAPH_CLIENT_SECRET="$AZURE_CLIENT_SECRET"

# ============================================================================
# JWT CONFIGURATION
# ============================================================================

# JWT Secret Key for signing OAuth2 web tokens
# Generate a strong random key for production
export JWT_SECRET_KEY="$(openssl rand -base64 32)"

# ============================================================================
# DEPLOYMENT OPTIONS
# ============================================================================

# Session Management
# Always use persistent sessions in production
export PERSIST_SESSIONS="true"

# Vertex AI Configuration
export GOOGLE_GENAI_USE_VERTEXAI="TRUE"

# Cloud Run Configuration
export MEMORY="1Gi"
export CPU="1"
export MIN_INSTANCES="0"
export MAX_INSTANCES="10"
export TIMEOUT="300"

# ============================================================================
# VALIDATION
# ============================================================================

# Check required variables
if [ "$PROJECT_ID" = "your-project-id" ]; then
  echo "⚠️  ERROR: Please set PROJECT_ID in deploy-config.sh"
  exit 1
fi

if [ "$AZURE_TENANT_ID" = "your-tenant-id-guid" ]; then
  echo "⚠️  ERROR: Please set AZURE_TENANT_ID in deploy-config.sh"
  exit 1
fi

if [ "$AZURE_CLIENT_SECRET" = "your-client-secret" ]; then
  echo "⚠️  ERROR: Please set AZURE_CLIENT_SECRET in deploy-config.sh"
  exit 1
fi

echo "✅ Configuration validated"
