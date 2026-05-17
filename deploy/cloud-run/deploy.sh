#!/bin/bash
# Deploy QEaaS webhook receiver to Cloud Run
# Prerequisites:
#   - gcloud auth login + application-default login
#   - Artifact Registry Docker repo `qe-as-a-service` in ${REGION}:
#       gcloud artifacts repositories create qe-as-a-service \
#         --repository-format=docker --location=${REGION}
#   - Secret Manager secrets (see end of this script for the list)
#
# Run from anywhere:
#   GCP_PROJECT_ID=my-project ./deploy/cloud-run/deploy.sh

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-europe-west2}"
AR_REPO="${GCP_AR_REPO:-qe-as-a-service}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/qe-as-a-service-webhook"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RENDERED_YAML="$(mktemp -t qe-service.yaml.XXXXXX)"
trap 'rm -f "${RENDERED_YAML}"' EXIT

echo "Building image to ${IMAGE}..."
gcloud builds submit \
  --tag "${IMAGE}:latest" \
  --project "${PROJECT_ID}" \
  "${REPO_ROOT}"

echo "Rendering service.yaml (PROJECT_ID=${PROJECT_ID}, REGION=${REGION})..."
sed -e "s/REPLACE_GCP_PROJECT_ID/${PROJECT_ID}/g" \
    -e "s/REPLACE_GCP_REGION/${REGION}/g" \
  "${SCRIPT_DIR}/service.yaml" > "${RENDERED_YAML}"

echo "Deploying to Cloud Run..."
gcloud run services replace "${RENDERED_YAML}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}"

echo "Getting webhook URL..."
WEBHOOK_URL=$(gcloud run services describe qe-as-a-service-webhook \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format "value(status.url)")

echo ""
echo "Webhook receiver deployed: ${WEBHOOK_URL}"
echo ""
echo "Configure the following webhooks:"
echo "  GitHub:          ${WEBHOOK_URL}/webhooks/github"
echo "  Jira:            ${WEBHOOK_URL}/webhooks/jira"
echo "  Confluence:      ${WEBHOOK_URL}/webhooks/confluence"
echo "  GCP Monitoring:  ${WEBHOOK_URL}/webhooks/gcp-monitoring"
echo ""
echo "Required secrets in Secret Manager:"
echo "  anthropic-api-key"
echo "  github-webhook-secret"
echo "  jira-webhook-secret"
echo "  confluence-webhook-secret"
echo "  pubsub-push-audience      # set to: ${WEBHOOK_URL}/webhooks/gcp-monitoring"
echo ""
echo "Pub/Sub push subscription must be created with:"
echo "  --push-auth-service-account=<service-account>"
echo "  --push-auth-token-audience=${WEBHOOK_URL}/webhooks/gcp-monitoring"
