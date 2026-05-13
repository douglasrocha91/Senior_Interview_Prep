#!/usr/bin/env bash
# Creates the transactions table in DynamoDB Local.
# Requires DynamoDB Local to be running (make local-up).

set -euo pipefail

ENDPOINT="${DYNAMODB_ENDPOINT_URL:-http://localhost:8000}"
TABLE="${DYNAMODB_TABLE_TRANSACTIONS:-transactions}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "=== Creating DynamoDB table: $TABLE ==="
echo "Endpoint: $ENDPOINT"
echo ""

# Check if table already exists
if aws dynamodb describe-table \
  --endpoint-url "$ENDPOINT" \
  --region "$REGION" \
  --table-name "$TABLE" \
  --output text > /dev/null 2>&1; then
  echo "[skip] table already exists: $TABLE"
  exit 0
fi

aws dynamodb create-table \
  --endpoint-url "$ENDPOINT" \
  --region "$REGION" \
  --table-name "$TABLE" \
  --attribute-definitions \
    AttributeName=transaction_id,AttributeType=S \
  --key-schema \
    AttributeName=transaction_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --output text > /dev/null

echo "[ok] table created: $TABLE"
echo ""
echo "Schema:"
echo "  PK: transaction_id (String)"
echo "  Attributes (schemaless): partner, source_bucket, source_key,"
echo "    status, created_at, updated_at, attempt_count, result_prefix, error_summary"
