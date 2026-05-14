#!/usr/bin/env bash
# Packages and deploys the ingest-lambda to AWS.
# Run from the mini-file-platform/ root directory.
# Prerequisites: AWS CLI configured, .env sourced.

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
FUNCTION_NAME="${LAMBDA_INGEST_FUNCTION_NAME:-mini-file-platform-ingest}"
ROLE_NAME="mini-file-platform-lambda-role"
RUNTIME="python3.12"
HANDLER="app.handler.handler"
TIMEOUT=30
MEMORY=256
BUILD_DIR="/tmp/mini-file-platform-lambda-build"
ZIP_PATH="/tmp/mini-file-platform-ingest.zip"

echo "=== mini-file-platform Lambda deploy ==="
echo "Function : $FUNCTION_NAME"
echo "Region   : $REGION"
echo ""

# ─── IAM Role ─────────────────────────────────────────────────────────────────

ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" \
  --query Role.Arn --output text 2>/dev/null || true)

if [ -z "$ROLE_ARN" ]; then
  echo "Creating IAM role: $ROLE_NAME"
  ROLE_ARN=$(aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' \
    --query Role.Arn --output text)

  aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "mini-file-platform-lambda-policy" \
    --policy-document "{
      \"Version\": \"2012-10-17\",
      \"Statement\": [
        {
          \"Effect\": \"Allow\",
          \"Action\": [\"s3:GetObject\", \"s3:HeadObject\"],
          \"Resource\": \"arn:aws:s3:::${S3_INBOUND_BUCKET:-mini-file-platform-inbound}/*\"
        },
        {
          \"Effect\": \"Allow\",
          \"Action\": \"sqs:SendMessage\",
          \"Resource\": \"*\"
        },
        {
          \"Effect\": \"Allow\",
          \"Action\": [
            \"logs:CreateLogGroup\",
            \"logs:CreateLogStream\",
            \"logs:PutLogEvents\"
          ],
          \"Resource\": \"arn:aws:logs:*:*:*\"
        }
      ]
    }"

  echo "[ok] IAM role created: $ROLE_ARN"
  echo "Waiting 10s for IAM role propagation..."
  sleep 10
else
  echo "[skip] IAM role already exists: $ROLE_ARN"
fi

# ─── Package ──────────────────────────────────────────────────────────────────

echo ""
echo "Building Lambda package..."
rm -rf "$BUILD_DIR" && mkdir -p "$BUILD_DIR"

# Copy Lambda app code
cp -r ingest-lambda/app "$BUILD_DIR/app"

# Copy shared package (required at Lambda zip root)
cp -r shared "$BUILD_DIR/shared"

# Create zip
cd "$BUILD_DIR"
zip -r "$ZIP_PATH" . -x "*.pyc" -x "*/__pycache__/*" > /dev/null
cd - > /dev/null

ZIP_SIZE=$(du -sh "$ZIP_PATH" | cut -f1)
echo "[ok] package ready: $ZIP_PATH ($ZIP_SIZE)"

# ─── Deploy or Update ─────────────────────────────────────────────────────────

echo ""
EXISTING=$(aws lambda get-function --function-name "$FUNCTION_NAME" \
  --region "$REGION" --query Configuration.FunctionName --output text 2>/dev/null || true)

QUEUE_URL="${SQS_FILE_JOBS_URL:-}"

if [ -z "$EXISTING" ]; then
  echo "Creating Lambda function: $FUNCTION_NAME"
  aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime "$RUNTIME" \
    --handler "$HANDLER" \
    --role "$ROLE_ARN" \
    --zip-file "fileb://$ZIP_PATH" \
    --timeout "$TIMEOUT" \
    --memory-size "$MEMORY" \
    --environment "Variables={SQS_FILE_JOBS_URL=$QUEUE_URL,LOG_LEVEL=INFO}" \
    --region "$REGION" \
    --output text > /dev/null
  echo "[ok] Lambda created"
else
  echo "Updating Lambda function code: $FUNCTION_NAME"
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://$ZIP_PATH" \
    --region "$REGION" \
    --output text > /dev/null

  aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --environment "Variables={SQS_FILE_JOBS_URL=$QUEUE_URL,LOG_LEVEL=INFO}" \
    --region "$REGION" \
    --output text > /dev/null
  echo "[ok] Lambda updated"
fi

echo ""
echo "Next: run 'make infra-wire-s3' to connect S3 events to this Lambda."
