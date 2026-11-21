#!/bin/bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-europe-west2}"
AR_REPO="${GCP_AR_REPO:-qe-as-a-service}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/qe-agents:latest"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RENDERED_YAML="$(mktemp -t qe-agents.yaml.XXXXXX)"
trap 'rm -f "${RENDERED_YAML}"' EXIT

python3 "${SCRIPT_DIR}/stage-agents.py" "${REPO_ROOT}" "${PROJECT_ID}" "${IMAGE}" \
  "${SCRIPT_DIR}/agents-cloudbuild.yaml" "${SCRIPT_DIR}/agents.gcloudignore"
sed -e "s/REPLACE_GCP_PROJECT_ID/${PROJECT_ID}/g" \
    -e "s/REPLACE_GCP_REGION/${REGION}/g" \
    -e "s|${REGION}-docker.pkg.dev/${PROJECT_ID}/qe-as-a-service/qe-agents:latest|${IMAGE}|g" \
  "${SCRIPT_DIR}/agents-service.yaml" > "${RENDERED_YAML}"
gcloud run services replace "${RENDERED_YAML}" --project "${PROJECT_ID}" --region "${REGION}"
URL="$(gcloud run services describe qe-agents --project "${PROJECT_ID}" --region "${REGION}" --format 'value(status.url)')"
gcloud run services update qe-agents --project "${PROJECT_ID}" --region "${REGION}" \
  --update-env-vars "QE_AGENT_BASE_URL=${URL}"
echo "QE agent service: ${URL}"
echo "Internal ingress and Cloud Run IAM authentication are required; grant run.invoker only to trusted callers."
echo "Verify the service IAM policy has no allUsers/allAuthenticatedUsers invoker binding before use."
