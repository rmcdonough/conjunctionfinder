#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$REPO_ROOT/infra"

echo "==> cdk destroy"
( cd "$INFRA_DIR" && npx cdk destroy --force )

echo "Torn down. The auto-created ECR repository for the Lambda image asset"
echo "may still hold old image versions — check 'aws ecr describe-repositories'"
echo "if you want those gone too; CDK does not currently auto-delete it."
