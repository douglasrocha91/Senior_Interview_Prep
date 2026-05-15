# AWS Setup Guide

Provision real AWS resources: S3 buckets, SQS queues, DLQ, IAM role, and Lambda function.

---

## Prerequisites

- AWS account with billing activated
- AWS CLI installed: `aws --version`
- Valid IAM credentials (see Step 1)

---

## 1. Create an IAM User

Go to the [AWS IAM Console](https://console.aws.amazon.com/iam):

1. **Users** → **Create user**
2. User name: `mini-file-platform-dev`
3. Do **not** enable console access
4. **Attach policies directly** — add all four:
   - `AmazonS3FullAccess`
   - `AmazonSQSFullAccess`
   - `AWSLambda_FullAccess`
   - `IAMFullAccess` ← needed for the deploy script to create the Lambda execution role
5. **Create user** → click the user → **Security credentials** tab
6. **Create access key** → **Command Line Interface (CLI)** → confirm → **Create**
7. Copy both values now. The secret access key is shown only once.

---

## 2. Configure the AWS CLI

Unset any dummy credentials that may be set in your environment:

```bash
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_ENDPOINT_URL
```

Then configure:

```bash
aws configure
```

Fill in:
- AWS Access Key ID: `<your key>`
- AWS Secret Access Key: `<your secret>`
- Default region: `us-east-1`
- Default output format: `json`

Verify:

```bash
aws sts get-caller-identity
```

Expected output includes your account ID and the IAM user ARN.

---

## 3. Provision S3, SQS, and DLQ

```bash
make infra-aws
```

This runs `infra/aws/bootstrap.sh` which:

1. Creates the S3 inbound bucket (`mini-file-platform-inbound`) with public access blocked
2. Creates the S3 results bucket (`mini-file-platform-results`) with public access blocked
3. Creates the DLQ (`file-jobs-dlq`) with a 14-day retention period
4. Creates the main SQS queue (`file-jobs`) with a redrive policy pointing to the DLQ (max 3 receives)
5. Prints the queue URLs

The script is **idempotent** — safe to run multiple times.

### Copy queue URLs to `.env`

The script prints both URLs at the end. Add them to `.env`:

```bash
SQS_FILE_JOBS_URL=https://sqs.us-east-1.amazonaws.com/<account-id>/file-jobs
SQS_DLQ_URL=https://sqs.us-east-1.amazonaws.com/<account-id>/file-jobs-dlq
```

---

## 4. Deploy the Ingest Lambda

```bash
make infra-deploy-lambda
```

This runs `infra/aws/deploy-lambda.sh` which:

1. Creates an IAM execution role (`mini-file-platform-lambda-role`) with S3 read and SQS send permissions
2. Packages the Lambda code (`ingest-lambda/app/` + `shared/`) into a zip
3. Creates or updates the Lambda function (`mini-file-platform-ingest`)
4. Sets the `SQS_FILE_JOBS_URL` environment variable on the function

---

## 5. Wire S3 Events to Lambda

```bash
make infra-wire-s3
```

This runs `infra/aws/wire-s3-notification.sh` which:

1. Adds Lambda invoke permission for the S3 service
2. Configures S3 event notifications on the inbound bucket to trigger the Lambda on every `s3:ObjectCreated:*` event

---

## 6. Verify End-to-End

Upload a file and confirm the Lambda triggers and publishes to SQS:

```bash
# Source .env first
set -a && source .env && set +a

# Upload a test file
make submit-generate-and-submit PARTNER=acme ROWS=5

# Wait ~5 seconds, then check if SQS received the message
aws sqs get-queue-attributes \
  --queue-url "$SQS_FILE_JOBS_URL" \
  --attribute-names ApproximateNumberOfMessages
```

`ApproximateNumberOfMessages` should be 1 after the Lambda fires.

---

## 7. Tear Down All Resources

```bash
make infra-aws-teardown
```

Prompts for confirmation, then empties and deletes both S3 buckets and both SQS queues. The Lambda and IAM role must be deleted manually from the console if needed.

---

## Required `.env` Variables

```bash
AWS_ACCESS_KEY_ID=<your key>
AWS_SECRET_ACCESS_KEY=<your secret>
AWS_DEFAULT_REGION=us-east-1

S3_INBOUND_BUCKET=mini-file-platform-inbound
S3_RESULTS_BUCKET=mini-file-platform-results

SQS_FILE_JOBS_URL=https://sqs.us-east-1.amazonaws.com/<account-id>/file-jobs
SQS_DLQ_URL=https://sqs.us-east-1.amazonaws.com/<account-id>/file-jobs-dlq

LAMBDA_INGEST_FUNCTION_NAME=mini-file-platform-ingest
```
