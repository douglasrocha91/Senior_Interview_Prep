# Local E2E Walkthrough

Complete step-by-step guide to run the full pipeline locally using LocalStack (S3 + SQS) and DynamoDB Local — no real AWS account required.

---

## Prerequisites

Install these tools before starting:

```bash
brew install gnupg kind kubectl awscli
```

- Python 3.11+
- Docker Desktop (running)

---

## Phase 1 — Start Infrastructure

### DynamoDB Local

```bash
docker run -d \
  --name mini-file-platform-dynamodb \
  -p 8000:8000 \
  amazon/dynamodb-local:2.5.4 \
  -jar DynamoDBLocal.jar -inMemory -sharedDb
```

Wait 3 seconds, then create the transactions table:

```bash
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  aws --endpoint-url http://localhost:8000 --region us-east-1 \
  dynamodb create-table \
  --table-name transactions \
  --attribute-definitions AttributeName=transaction_id,AttributeType=S \
  --key-schema AttributeName=transaction_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --output text > /dev/null && echo "[ok] table created"
```

### LocalStack

```bash
docker start localstack-main
```

Wait 5 seconds, then create S3 buckets and SQS queues:

```bash
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1

aws --endpoint-url http://localhost:4566 s3 mb s3://mini-file-platform-inbound
aws --endpoint-url http://localhost:4566 s3 mb s3://mini-file-platform-results
aws --endpoint-url http://localhost:4566 sqs create-queue --queue-name file-jobs-dlq
aws --endpoint-url http://localhost:4566 sqs create-queue --queue-name file-jobs
```

Configure the DLQ redrive policy (3 retries before messages move to DLQ):

```bash
DLQ_ARN=$(aws --endpoint-url http://localhost:4566 sqs get-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/file-jobs-dlq \
  --attribute-names QueueArn \
  --query Attributes.QueueArn --output text)

aws --endpoint-url http://localhost:4566 sqs set-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/file-jobs \
  --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"
```

---

## Phase 2 — Generate GPG Keys (one-time)

```bash
mkdir -p /tmp/mfp-gpg && chmod 700 /tmp/mfp-gpg

gpg --homedir /tmp/mfp-gpg --batch --gen-key <<'GPGEOF'
%no-protection
Key-Type: RSA
Key-Length: 2048
Subkey-Type: RSA
Subkey-Length: 2048
Name-Real: Mini File Platform Lab
Name-Email: lab@mini-file-platform.local
Expire-Date: 0
%commit
GPGEOF
```

Verify:

```bash
gpg --homedir /tmp/mfp-gpg --list-keys
```

Note: `/tmp/mfp-gpg` is cleared on system restart. Re-run this phase after each reboot.

---

## Phase 3 — Create `.env`

Copy the example and fill in the values:

```bash
cp .env.example .env
```

Minimum required content for local E2E:

```bash
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
AWS_ENDPOINT_URL=http://localhost:4566

S3_INBOUND_BUCKET=mini-file-platform-inbound
S3_RESULTS_BUCKET=mini-file-platform-results

SQS_FILE_JOBS_URL=http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/file-jobs
SQS_DLQ_URL=http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/file-jobs-dlq

DYNAMODB_ENDPOINT_URL=http://localhost:8000
DYNAMODB_TABLE_TRANSACTIONS=transactions

GPG_RECIPIENT_EMAIL=lab@mini-file-platform.local
GPG_HOME=/tmp/mfp-gpg
```

Source the file:

```bash
set -a && source .env && set +a
```

---

## Phase 4 — Generate and Upload a CSV

```bash
make submit-generate-and-submit PARTNER=acme ROWS=20
```

Expected output:

```
generated : /tmp/acme_expenses.csv (20 rows)
transaction_id : 01KRMD...
s3_key         : inbox/acme/2026/05/14/01KRMD....csv.gpg
```

Copy the `transaction_id` value — you will use it in the next steps.

---

## Phase 5 — Create Helper Scripts

Save these two scripts. They are designed to run as single files to avoid multiline paste issues in zsh.

### sqs-send.sh

```bash
cat > /tmp/sqs-send.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail
TID="${1:?Usage: sqs-send.sh <transaction_id>}"
QUEUE_URL="${SQS_FILE_JOBS_URL:?SQS_FILE_JOBS_URL not set}"
BODY=$(printf '{"transaction_id":"%s","bucket":"mini-file-platform-inbound","key":"inbox/acme/2026/05/14/%s.csv.gpg","partner":"acme","received_at":"%s","schema_version":"v1","attempt":0}' \
  "$TID" "$TID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)")
aws --endpoint-url http://localhost:4566 sqs send-message \
  --queue-url "$QUEUE_URL" \
  --message-body "$BODY"
echo "[ok] mensagem publicada para: $TID"
SCRIPT
```

### check-transaction.sh

```bash
cat > /tmp/check-transaction.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail
TID="${1:?Usage: check-transaction.sh <transaction_id>}"
ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
DYNAMO="${DYNAMODB_ENDPOINT_URL:-http://localhost:8000}"
RESULTS="${S3_RESULTS_BUCKET:-mini-file-platform-results}"

echo "=== Status no DynamoDB ==="
aws --endpoint-url "$DYNAMO" dynamodb get-item \
  --table-name transactions \
  --key "{\"transaction_id\":{\"S\":\"$TID\"}}" \
  --output json | python3 -c "
import sys, json
item = json.load(sys.stdin).get('Item', {})
for k, v in item.items():
    val = v.get('S') or v.get('N') or '(null)'
    print(f'  {k:25s}: {val}')
"

echo ""
echo "=== Artifacts no S3 ==="
aws --endpoint-url "$ENDPOINT" s3 ls "s3://$RESULTS/results/$TID/" 2>/dev/null || echo "  (nenhum artifact)"

echo ""
echo "=== Erros de validação ==="
aws --endpoint-url "$ENDPOINT" s3 cp \
  "s3://$RESULTS/results/$TID/errors.jsonl" - 2>/dev/null | \
  python3 -c "
import sys, json
lines = [l for l in sys.stdin if l.strip()]
if not lines:
    print('  (sem erros)')
else:
    for l in lines:
        e = json.loads(l)
        print(f\"  row {e['row_number']:2d} | {e['field']:12s} | {e['code']:16s} | {e['message']}\")
" || echo "  (sem arquivo de erros)"
SCRIPT
```

---

## Phase 6 — Publish the SQS Message

```bash
bash /tmp/sqs-send.sh YOUR_TID_HERE
```

---

## Phase 7 — Run the Worker

```bash
make worker-run
```

Watch the JSON logs. When the worker finishes processing and shows no new messages, press `Ctrl+C`.

---

## Phase 8 — Check the Result

```bash
bash /tmp/check-transaction.sh YOUR_TID_HERE
```

Expected output for a successful run:

```
=== Status no DynamoDB ===
  transaction_id           : 01KRMD...
  status                   : PROCESSED
  partner                  : acme
  attempt_count            : 1
  result_prefix            : results/01KRMD.../

=== Artifacts no S3 ===
2026-05-14 20:41:47    633 output.csv

=== Erros de validação ===
  (sem erros)
```

---

## Phase 9 — Query the Status API

Open a second terminal:

```bash
cd mini-file-platform
set -a && source .env && set +a
make api-run
```

In the original terminal:

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/transactions/YOUR_TID_HERE | python3 -m json.tool
curl -s http://localhost:8080/transactions/YOUR_TID_HERE/errors | python3 -m json.tool
```

---

## Complete Flow Summary

```
make submit-generate-and-submit   → generates CSV, encrypts with GPG, uploads to S3
bash /tmp/sqs-send.sh <TID>       → simulates Lambda (publishes job to SQS)
make worker-run                   → consumes SQS, downloads, decrypts, validates, stores
bash /tmp/check-transaction.sh    → shows DynamoDB status + S3 artifacts + validation errors
curl http://localhost:8080/...    → queries status API (requires make api-run in second terminal)
```
