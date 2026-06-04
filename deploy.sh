#!/bin/bash
set -e
PROJECT_ID="crisisroute-2026-498212"
REGION="asia-south1"
SERVICE="crisisroute-backend"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}"

# Load environment variables from .env if present
if [ -f .env ]; then
  echo "🔑 Loading environment variables from .env..."
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ ! "$line" =~ ^# ]] && [[ ! -z "$line" ]]; then
      export "$line"
    fi
  done < .env
fi

if [ -z "${GEMINI_API_KEY}" ]; then
  GEMINI_API_KEY="${GOOGLE_API_KEY}"
fi

echo "🚀 Deploying CrisisRoute backend..."

gcloud run deploy ${SERVICE} \
  --source . \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 300 \
  --set-env-vars "GEMINI_API_KEY=${GEMINI_API_KEY},ELASTIC_ENDPOINT=${ELASTIC_ENDPOINT},ELASTIC_API_KEY=${ELASTIC_API_KEY},APP_ENV=production" \
  --project ${PROJECT_ID}

echo "✅ Deployed. URL above."
echo "Test: curl https://YOUR_URL/health"
