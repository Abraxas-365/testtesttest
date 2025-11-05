#!/bin/bash
set -e

source deploy-config.sh

echo "🔄 Redeploying $SERVICE_NAME..."

# Rebuild container
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# Update service
gcloud run services update $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --region $REGION

export SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --format 'value(status.url)')

echo "✅ Redeployment complete!"
echo "Service URL: $SERVICE_URL"
