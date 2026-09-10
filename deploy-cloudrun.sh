#!/usr/bin/env bash
# Deploy the backend to Google Cloud Run from source (uses the root Dockerfile).
#
# Prereqs: gcloud CLI installed & logged in (`gcloud auth login`), a GCP project
# with billing enabled.
#
# Usage:
#   GROQ_API_KEY=xxx JWT_SECRET=xxx CORS_ORIGINS=https://your-app.vercel.app \
#     ./deploy-cloudrun.sh [PROJECT_ID] [REGION] [SERVICE]
#
# Secrets are read from env vars (not CLI args) so they don't linger in shell
# history. For production prefer Secret Manager over --set-env-vars.
set -euo pipefail

PROJECT="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${2:-us-central1}"
SERVICE="${3:-incident-rca-api}"

: "${GROQ_API_KEY:?Set GROQ_API_KEY}"
: "${JWT_SECRET:?Set JWT_SECRET (a long random string)}"
CORS_ORIGINS="${CORS_ORIGINS:-*}"

if [ -z "${PROJECT}" ]; then
  echo "No project set. Pass PROJECT_ID as \$1 or run: gcloud config set project <id>" >&2
  exit 1
fi

echo "Deploying '${SERVICE}' to project '${PROJECT}' in '${REGION}'…"

gcloud config set project "${PROJECT}"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
# Our build (~10 min: PyTorch + index bake) exceeds Cloud Build's 600s default.
gcloud config set builds/timeout 1800

gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --memory 4Gi \
  --cpu 2 \
  --timeout 300 \
  --allow-unauthenticated \
  --set-env-vars "GROQ_API_KEY=${GROQ_API_KEY},JWT_SECRET=${JWT_SECRET},CORS_ORIGINS=${CORS_ORIGINS}"

echo
echo "Done. Service URL:"
gcloud run services describe "${SERVICE}" --region "${REGION}" --format 'value(status.url)'
