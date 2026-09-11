#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$REPO_ROOT/infra"
FRONTEND_DIR="$REPO_ROOT/frontend"
OUTPUTS_FILE="$INFRA_DIR/cdk-outputs.json"

echo "==> Installing infra (CDK) dependencies"
( cd "$INFRA_DIR" && npm install )

echo "==> Installing frontend dependencies"
( cd "$FRONTEND_DIR" && npm install )

echo "==> Building frontend (pass 1 — placeholder API URL, needed so the S3 asset exists)"
( cd "$FRONTEND_DIR" && npm run build )

echo "==> cdk deploy (pass 1 — provisions S3 / Lambda / API Gateway / CloudFront)"
( cd "$INFRA_DIR" && npx cdk deploy --require-approval never --outputs-file "$OUTPUTS_FILE" )

API_BASE_URL="$(python3 -c "
import json
with open('$OUTPUTS_FILE') as f:
    outputs = json.load(f)
stack = next(iter(outputs.values()))
print(stack['ApiBaseUrl'])
")"
SITE_URL="$(python3 -c "
import json
with open('$OUTPUTS_FILE') as f:
    outputs = json.load(f)
stack = next(iter(outputs.values()))
print(stack['SiteUrl'])
")"

echo "==> Rebuilding frontend with the real API URL: $API_BASE_URL"
( cd "$FRONTEND_DIR" && VITE_API_BASE_URL="$API_BASE_URL" npm run build )

echo "==> cdk deploy (pass 2 — uploads the correctly-built frontend, invalidates CloudFront)"
( cd "$INFRA_DIR" && npx cdk deploy --require-approval never --outputs-file "$OUTPUTS_FILE" )

echo ""
echo "Deployed. Site: $SITE_URL"
echo "API base: $API_BASE_URL"
