#!/usr/bin/env bash
# Creates the AWS resources required for the mini-file-platform.
# Safe to run multiple times — existing resources are skipped.
# Prerequisites: AWS CLI configured, .env sourced with S3_INBOUND_BUCKET etc.

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
INBOUND_BUCKET="${S3_INBOUND_BUCKET:-mini-file-platform-inbound}"
RESULTS_BUCKET="${S3_RESULTS_BUCKET:-mini-file-platform-results}"
QUEUE_NAME="file-jobs"
DLQ_NAME="file-jobs-dlq"
MAX_RECEIVE_COUNT="${SQS_MAX_RECEIVE_COUNT:-3}"
VISIBILITY_TIMEOUT="${SQS_VISIBILITY_TIMEOUT:-30}"

echo "=== mini-file-platform AWS bootstrap ==="
echo "Region : $REGION"
echo "Inbound : $INBOUND_BUCKET"
echo "Results : $RESULTS_BUCKET"
echo ""

# ─── S3 Buckets ──────────────────────────────────────────────────────────────

create_bucket() {
  local bucket="$1"
  if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
    echo "[skip] bucket already exists: $bucket"
  else
    if [ "$REGION" = "us-east-1" ]; then
      aws s3api create-bucket --bucket "$bucket" --region "$REGION"
    else
      aws s3api create-bucket --bucket "$bucket" --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION"
    fi
    # Block all public access
    aws s3api put-public-access-block --bucket "$bucket" \
      --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    echo "[ok] created bucket: $bucket"
  fi
}

create_bucket "$INBOUND_BUCKET"
create_bucket "$RESULTS_BUCKET"

# ─── SQS Dead-Letter Queue ────────────────────────────────────────────────────

DLQ_URL=$(aws sqs get-queue-url --queue-name "$DLQ_NAME" --region "$REGION" \
  --query QueueUrl --output text 2>/dev/null || true)

if [ -n "$DLQ_URL" ]; then
  echo "[skip] DLQ already exists: $DLQ_NAME"
else
  DLQ_URL=$(aws sqs create-queue --queue-name "$DLQ_NAME" --region "$REGION" \
    --attributes VisibilityTimeout="$VISIBILITY_TIMEOUT" \
    --query QueueUrl --output text)
  echo "[ok] created DLQ: $DLQ_NAME"
fi

DLQ_ARN=$(aws sqs get-queue-attributes --queue-url "$DLQ_URL" \
  --attribute-names QueueArn \
  --query Attributes.QueueArn --output text)

# ─── SQS Main Queue ──────────────────────────────────────────────────────────

QUEUE_URL=$(aws sqs get-queue-url --queue-name "$QUEUE_NAME" --region "$REGION" \
  --query QueueUrl --output text 2>/dev/null || true)

if [ -n "$QUEUE_URL" ]; then
  echo "[skip] queue already exists: $QUEUE_NAME"
else
  REDRIVE_POLICY=$(printf '{"deadLetterTargetArn":"%s","maxReceiveCount":"%s"}' \
    "$DLQ_ARN" "$MAX_RECEIVE_COUNT")
  QUEUE_URL=$(aws sqs create-queue --queue-name "$QUEUE_NAME" --region "$REGION" \
    --attributes \
      VisibilityTimeout="$VISIBILITY_TIMEOUT" \
      "RedrivePolicy=$REDRIVE_POLICY" \
    --query QueueUrl --output text)
  echo "[ok] created queue: $QUEUE_NAME"
fi

# ─── Output ──────────────────────────────────────────────────────────────────

echo ""
echo "=== Resource URLs (add these to your .env) ==="
echo "SQS_FILE_JOBS_URL=$QUEUE_URL"
echo "SQS_FILE_JOBS_DLQ_URL=$DLQ_URL"
echo ""
echo "S3 inbound prefix convention:"
echo "  inbox/{partner}/{yyyy}/{mm}/{dd}/{transaction_id}.csv.gpg"
echo ""
echo "Next step: wire S3 event notification to Lambda after Phase 3."
