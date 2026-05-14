#!/usr/bin/env bash
# Wires S3 ObjectCreated events on the inbound bucket to the ingest Lambda.
# Run after deploy-lambda.sh completes.
# Prerequisites: AWS CLI configured, Lambda already deployed.

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
FUNCTION_NAME="${LAMBDA_INGEST_FUNCTION_NAME:-mini-file-platform-ingest}"
INBOUND_BUCKET="${S3_INBOUND_BUCKET:-mini-file-platform-inbound}"

echo "=== S3 → Lambda notification wiring ==="
echo "Bucket   : $INBOUND_BUCKET"
echo "Function : $FUNCTION_NAME"
echo "Region   : $REGION"
echo ""

# ─── Get Lambda ARN ───────────────────────────────────────────────────────────

LAMBDA_ARN=$(aws lambda get-function \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --query Configuration.FunctionArn \
  --output text)

echo "Lambda ARN: $LAMBDA_ARN"

# ─── Grant S3 permission to invoke Lambda ─────────────────────────────────────

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Use a stable statement ID so this is idempotent
STATEMENT_ID="s3-invoke-${INBOUND_BUCKET}"

aws lambda remove-permission \
  --function-name "$FUNCTION_NAME" \
  --statement-id "$STATEMENT_ID" \
  --region "$REGION" 2>/dev/null || true

aws lambda add-permission \
  --function-name "$FUNCTION_NAME" \
  --statement-id "$STATEMENT_ID" \
  --action "lambda:InvokeFunction" \
  --principal "s3.amazonaws.com" \
  --source-arn "arn:aws:s3:::$INBOUND_BUCKET" \
  --source-account "$ACCOUNT_ID" \
  --region "$REGION" \
  --output text > /dev/null

echo "[ok] Lambda invoke permission granted to S3"

# ─── Configure S3 event notification ─────────────────────────────────────────

NOTIFICATION_CONFIG=$(cat <<JSON
{
  "LambdaFunctionConfigurations": [
    {
      "LambdaFunctionArn": "$LAMBDA_ARN",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {"Name": "prefix", "Value": "inbox/"},
            {"Name": "suffix", "Value": ".csv.gpg"}
          ]
        }
      }
    }
  ]
}
JSON
)

aws s3api put-bucket-notification-configuration \
  --bucket "$INBOUND_BUCKET" \
  --notification-configuration "$NOTIFICATION_CONFIG"

echo "[ok] S3 notification configured"
echo ""
echo "=== Wiring complete ==="
echo "Upload a .csv.gpg file to s3://$INBOUND_BUCKET/inbox/ to trigger the Lambda."
echo ""
echo "Monitor Lambda logs:"
echo "  aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $REGION"
