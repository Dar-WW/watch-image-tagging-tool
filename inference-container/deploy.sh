#!/usr/bin/env bash
#
# Build, tag, and push the watch-keypoint-inference container to ECR.
#
# Usage:
#   ./deploy.sh              # build + push
#   ./deploy.sh --no-cache   # build from scratch + push
#
set -euo pipefail

# Disable AWS CLI pager (prevents getting stuck in 'less' with (END))
export AWS_PAGER=""

REGION="eu-central-2"
ACCOUNT_ID="539247452167"
REPO_NAME="watch-keypoint-inference"
IMAGE_TAG="latest"

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
FULL_IMAGE="${ECR_URI}/${REPO_NAME}:${IMAGE_TAG}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_ARGS=""

if [[ "${1:-}" == "--no-cache" ]]; then
    BUILD_ARGS="--no-cache"
    echo "Building with --no-cache"
fi

echo "============================================"
echo "  Watch Keypoint Inference - ECR Deploy"
echo "============================================"
echo "  Region:  ${REGION}"
echo "  Repo:    ${REPO_NAME}"
echo "  Image:   ${FULL_IMAGE}"
echo "============================================"
echo ""

# --- 1. Create ECR repo if it doesn't exist ---
echo "[1/4] Ensuring ECR repository exists..."
if aws --no-cli-pager ecr describe-repositories \
    --repository-names "${REPO_NAME}" \
    --region "${REGION}" &>/dev/null; then
    echo "  Repository '${REPO_NAME}' already exists"
else
    echo "  Creating repository '${REPO_NAME}'..."
    aws --no-cli-pager ecr create-repository \
        --repository-name "${REPO_NAME}" \
        --region "${REGION}" \
        --image-scanning-configuration scanOnPush=true \
        --output text --query 'repository.repositoryUri'
    echo "  Created."
fi
echo ""

# --- 2. Authenticate Docker to ECR (before build so buildx --push works) ---
echo "[2/4] Logging in to ECR..."
aws --no-cli-pager ecr get-login-password --region "${REGION}" \
    | docker login --username AWS --password-stdin "${ECR_URI}"
echo ""

# --- 3. Build for linux/amd64 and push to ECR ---
# --provenance=false ensures a Docker V2 manifest (required by SageMaker)
# --platform linux/amd64 targets SageMaker's runtime architecture
echo "[3/4] Building and pushing Docker image (linux/amd64)..."
docker buildx build \
    --platform linux/amd64 \
    --provenance=false \
    ${BUILD_ARGS} \
    -t "${FULL_IMAGE}" \
    --push \
    "${SCRIPT_DIR}"
echo ""

# --- 5. Clean up old untagged images to save storage ---
echo "Cleaning up untagged images in ECR..."
UNTAGGED=$(aws --no-cli-pager ecr list-images \
    --repository-name "${REPO_NAME}" \
    --region "${REGION}" \
    --filter tagStatus=UNTAGGED \
    --query 'imageIds[*]' \
    --output json 2>/dev/null)

if [[ "${UNTAGGED}" != "[]" && "${UNTAGGED}" != "null" && -n "${UNTAGGED}" ]]; then
    aws --no-cli-pager ecr batch-delete-image \
        --repository-name "${REPO_NAME}" \
        --region "${REGION}" \
        --image-ids "${UNTAGGED}" \
        --output text
    echo "  Cleaned up untagged images."
else
    echo "  No untagged images to clean."
fi

echo ""
echo "============================================"
echo "  Done! Image pushed to:"
echo "  ${FULL_IMAGE}"
echo "============================================"
