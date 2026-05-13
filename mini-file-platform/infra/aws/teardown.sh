#!/usr/bin/env bash
# Removes AWS resources created by bootstrap.sh.
# WARNING: this deletes S3 buckets and SQS queues permanently.

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
INBOUND_BUCKET="${S3_INBOUND_BUCKET:-mini-file-platform-inbound}"
RESULTS_BUCKET="${S3_RESULTS_BUCKET:-mini-file-platform-results}"
QUEUE_NAME="file-jobs"
DLQ_NAME="file-jobs-dlq"

echo "=== mini-file-platform AWS teardown ==="
read -rp "This will DELETE all resources. Type 'yes' to continue: " confirm
[ "$confirm" = "yes" ] || { echo "Aborted."; exit 1; }

delete_bucket() {
  local bucket="$1"
  if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
    aws s3 rm "s3://$bucket" --recursive --quiet
    aws s3api delete-bucket --bucket "$bucket" --region "$REGION"
    echo "[ok] deleted bucket: $bucket"
  else
    echo "[skip] bucket not found: $bucket"
  fi
}

delete_queue() {
  local name="$1"
  local url
  url=$(aws sqs get-queue-url --queue-name "$name" --region "$REGION" \
    --query QueueUrl --output text 2>/dev/null || true)
  if [ -n "$url" ]; then
    aws sqs delete-queue --queue-url "$url"
    echo "[ok] deleted queue: $name"
  else
    echo "[skip] queue not found: $name"
  fi
}

delete_queue "$QUEUE_NAME"
delete_queue "$DLQ_NAME"
delete_bucket "$INBOUND_BUCKET"
delete_bucket "$RESULTS_BUCKET"

echo ""
echo "=== Teardown complete ==="
