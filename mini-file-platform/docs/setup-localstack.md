# LocalStack — Setup Guide

LocalStack emulates AWS S3 and SQS locally on port 4566. Used for the full local E2E flow without a real AWS account.

---

## Why LocalStack

The lab uses real AWS for S3, SQS, and Lambda by default. When your AWS account is not yet active or you want a fully offline setup, LocalStack replaces S3 and SQS transparently — boto3 1.29+ reads `AWS_ENDPOINT_URL` natively, so no code changes are required.

---

## Prerequisites

- Docker Desktop installed and **running**

---

## 1. Start LocalStack

A LocalStack 3.0 container already exists in this project. Start it:

```bash
docker start localstack-main
```

Wait a few seconds, then verify it is healthy:

```bash
curl -s http://localhost:4566/_localstack/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
svcs = d.get('services', {})
available = [k for k, v in svcs.items() if v == 'available']
print(f'LocalStack ready — {len(available)} services available')
"
```

If the container does not exist yet, create it:

```bash
docker run -d \
  --name localstack-main \
  -p 4566:4566 \
  localstack/localstack:3.0
```

---

## 2. Create S3 Buckets

> **Important:** Do not use `aws s3 cp - s3://...` with stdin piping against LocalStack 3.0. It triggers a chunked-upload trailer header that LocalStack rejects with `InvalidRequest`. Use file paths or boto3 directly.

```bash
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

aws --endpoint-url http://localhost:4566 s3 mb s3://mini-file-platform-inbound
aws --endpoint-url http://localhost:4566 s3 mb s3://mini-file-platform-results
```

Verify:

```bash
aws --endpoint-url http://localhost:4566 s3 ls
```

---

## 3. Create SQS Queues

```bash
# Dead-letter queue first
aws --endpoint-url http://localhost:4566 sqs create-queue \
  --queue-name file-jobs-dlq

# Main job queue
aws --endpoint-url http://localhost:4566 sqs create-queue \
  --queue-name file-jobs
```

Note the `QueueUrl` values in the output — you need them for `.env`.

---

## 4. Configure DLQ Redrive Policy

This tells SQS to move messages to the DLQ after 3 failed receives:

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

## 5. Configure `.env`

Add these to your `.env` file:

```bash
# Fake credentials — LocalStack does not validate them
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1

# boto3 reads this natively (no code changes needed)
AWS_ENDPOINT_URL=http://localhost:4566

# Bucket names
S3_INBOUND_BUCKET=mini-file-platform-inbound
S3_RESULTS_BUCKET=mini-file-platform-results

# SQS queue URLs (LocalStack format)
SQS_FILE_JOBS_URL=http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/file-jobs
SQS_DLQ_URL=http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/file-jobs-dlq
```

boto3 1.29+ automatically routes all S3 and SQS calls to `AWS_ENDPOINT_URL` when that variable is set — zero code changes required.

---

## 6. Verify Everything

```bash
source .env

# S3 — list buckets
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  aws --endpoint-url http://localhost:4566 s3 ls

# SQS — list queues
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  aws --endpoint-url http://localhost:4566 sqs list-queues

# boto3 path (confirms the env var works end-to-end)
python3 -c "
import boto3
s3 = boto3.client('s3')
print('S3 buckets:', [b['Name'] for b in s3.list_buckets()['Buckets']])
sqs = boto3.client('sqs')
print('SQS queues:', sqs.list_queues().get('QueueUrls', []))
"
```

---

## 7. Upload Files to LocalStack S3

Because stdin piping fails on LocalStack 3.0, always upload from a file:

```bash
# Via AWS CLI (file path, not stdin)
aws --endpoint-url http://localhost:4566 s3 cp /path/to/file.csv.gpg \
  s3://mini-file-platform-inbound/inbox/acme/2026/05/14/file.csv.gpg

# Via boto3 (always works)
python3 -c "
import boto3
s3 = boto3.client('s3')
with open('/path/to/file.csv.gpg', 'rb') as f:
    s3.put_object(Bucket='mini-file-platform-inbound', Key='inbox/acme/...', Body=f.read())
"
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Connection refused` on 4566 | Container not running | `docker start localstack-main` |
| `InvalidRequest` on s3 cp | Stdin pipe with chunked upload | Upload from file path instead |
| Queue URL not resolving | DNS for `localhost.localstack.cloud` | Use `127.0.0.1` in place of the hostname, or ensure DNS resolves locally |
| boto3 still hits real AWS | `AWS_ENDPOINT_URL` not exported | Run `set -a && source .env && set +a` before make targets |
