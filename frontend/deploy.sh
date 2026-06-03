#!/bin/bash
set -e
BACKEND_URL="https://crisisroute-backend-498212-as.a.run.app" # replace with actual
PROJECT_ID="crisisroute-2026-498212"
REGION="asia-south1"

gcloud run deploy crisisroute-frontend \
  --source . \
  --region ${REGION} \
  --allow-unauthenticated \
  --memory 256Mi \
  --build-env-vars VITE_API_URL=${BACKEND_URL} \
  --project ${PROJECT_ID}

echo "✅ Frontend deployed."
