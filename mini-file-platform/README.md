# Mini File Platform

A compact but realistic end-to-end file ingestion platform built for senior interview preparation. Modeled after SAP Concur-style integration workflows, the system preserves the architectural roles of a production platform while staying cheap and fast to implement.

---

## Architecture

```
[submitter-cli] → S3 inbound → Lambda → SQS → [processor-worker] → S3 results
                                                       ↓
                                               DynamoDB Local (state)
                                                       ↑
                                              [status-api] ← HTTP client
```

### End-to-End Flow

1. A local Python CLI creates or receives a CSV file
2. The CLI encrypts the file with GnuPG
3. The encrypted file is uploaded to the S3 inbound bucket with metadata
4. S3 triggers a Lambda function on upload
5. Lambda validates the object key and metadata, then publishes a job to SQS
6. A Python worker running in local Kubernetes consumes the SQS message
7. The worker downloads and decrypts the file from S3
8. The worker validates and processes the CSV
9. The worker stores transaction status in DynamoDB Local
10. The worker writes result artifacts and validation errors back to S3
11. A FastAPI status service exposes the transaction state for inspection

### Technology Choices

| Layer | Technology | Why |
|---|---|---|
| Object storage | Amazon S3 | Realistic for file-based integrations, cheap at study volumes |
| Event entrypoint | AWS Lambda | Minimal serverless component for event-driven ingestion |
| Messaging | Amazon SQS + DLQ | Decoupling, retries, and poison message handling |
| Processing runtime | kind (local Kubernetes) | Kubernetes practice without EKS cost |
| State store | DynamoDB Local | NoSQL mental model without managed spend |
| Status access | FastAPI | Minimal boilerplate, fast HTTP layer |
| Cryptography | GnuPG | Directly matches the target role requirement |
| Ingest client | Python CLI | Demonstrates when a script is better than a service |

---

## Repository Structure

```
mini-file-platform/
  Makefile                   # All lifecycle commands
  .env.example               # Environment variable template
  submitter-cli/             # Phase 2: encrypt and upload files
  ingest-lambda/             # Phase 3: S3 event → SQS
  processor-worker/          # Phase 4: SQS consumer, core logic
  status-api/                # Phase 5: FastAPI, transaction queries
  shared/                    # Schemas, enums, utilities
  infra/
    aws/                     # S3 + SQS bootstrap and teardown scripts
    local/                   # DynamoDB Local via Docker Compose
    kubernetes/              # kind cluster config and namespace
  sample-files/              # CSV fixtures for testing
  docs/                      # Architecture notes
```

---

## Quick Start

```bash
# 1. Copy and fill in environment variables
cp .env.example .env

# 2. Start DynamoDB Local and kind cluster
make infra-up

# 3. Verify DynamoDB Local is working
make local-verify

# 4. Provision AWS resources (requires valid credentials in .env)
make infra-aws
```

Run `make help` to see all available targets.

---

## Domain Model

### TransactionStatus (enum)
`RECEIVED` → `QUEUED` → `PROCESSING` → `PROCESSED` / `FAILED`

### Transaction (DynamoDB item)
| Field | Type | Description |
|---|---|---|
| `transaction_id` | String (PK) | ULID, globally unique |
| `partner` | String | Source partner identifier |
| `source_bucket` | String | S3 inbound bucket |
| `source_key` | String | Full S3 object key |
| `status` | String | Current lifecycle status |
| `created_at` | String | ISO-8601 timestamp |
| `updated_at` | String | ISO-8601 timestamp |
| `attempt_count` | Number | SQS delivery attempts |
| `result_prefix` | String | S3 prefix for output artifacts |
| `error_summary` | String | Null unless failed |

### S3 Key Convention
```
inbox/{partner}/{yyyy}/{mm}/{dd}/{transaction_id}.csv.gpg
results/{transaction_id}/output.csv
results/{transaction_id}/errors.json
```

### SQS Message Schema
```json
{
  "transaction_id": "01JXYZABCDEF",
  "bucket": "mini-file-platform-inbound",
  "key": "inbox/acme/2026/05/13/01JXYZABCDEF.csv.gpg",
  "partner": "acme",
  "received_at": "2026-05-13T00:00:00Z",
  "schema_version": "v1",
  "attempt": 0
}
```

---

## Progress

### Phase 0 — Foundation
- [x] Repository structure created
- [x] `.env.example` with all required variables
- [x] `Makefile` with lifecycle targets
- [x] Service directory skeletons (`submitter-cli`, `ingest-lambda`, `processor-worker`, `status-api`, `shared`)

### Phase 1 — Base Infrastructure
- [x] `infra/aws/bootstrap.sh` — creates S3 buckets, SQS queue, and DLQ (idempotent)
- [x] `infra/aws/teardown.sh` — removes all AWS resources with confirmation
- [x] `infra/local/docker-compose.yml` — DynamoDB Local on port 8000
- [x] `infra/local/create-table.sh` — creates `transactions` table
- [x] `infra/kubernetes/cluster-config.yaml` — kind single-node cluster with port mapping
- [x] `infra/kubernetes/namespace.yaml` — `mini-file-platform` namespace
- [ ] Run `make infra-aws` against real AWS account and confirm resource creation
- [ ] Run `make infra-up` and `make local-verify` to confirm DynamoDB Local is working
- [ ] Bootstrap kind cluster and verify with `make cluster-status`

### Phase 2 — Submitter CLI
- [x] `sample-files/expenses_sample.csv` — 10-row fixture for manual testing
- [x] `docs/gpg-setup.md` — key pair generation, export, and interview talking points
- [x] `shared/models/transaction.py` — `TransactionStatus`, `Transaction`, `FileJob`, `ValidationError`
- [x] `shared/utils/ids.py` — ULID generator (no external dependency)
- [x] `shared/utils/log_config.py` — JSON structured logging with `transaction_id` correlation
- [x] `shared/utils/timestamps.py` — UTC helpers
- [x] `submitter-cli/app/generator.py` — generates valid expense CSVs
- [x] `submitter-cli/app/crypto.py` — GPG encryption via `python-gnupg`
- [x] `submitter-cli/app/uploader.py` — S3 upload with canonical key and metadata
- [x] `submitter-cli/app/main.py` — Click CLI: `generate`, `submit`, `generate-and-submit`
- [x] 18 unit tests passing (`test_generator`, `test_crypto`, `test_uploader`)
- [x] Makefile targets: `venv`, `submit-generate`, `submit-submit`, `submit-generate-and-submit`, `test`
- [ ] Run `make infra-aws` and execute a real end-to-end upload to verify S3 + metadata

### Phase 3 — Ingest Lambda
- [ ] `ingest-lambda/app/handler.py` — parse S3 event payload
- [ ] Validate key prefix, file extension, and required metadata
- [ ] Publish normalized `FileJob` message to SQS
- [ ] Wire S3 event notification to Lambda
- [ ] Unit tests in `ingest-lambda/tests/`

### Phase 4 — Processor Worker
- [ ] `processor-worker/app/consumer.py` — SQS long polling
- [ ] Download encrypted file from S3
- [ ] Decrypt with GPG
- [ ] Parse and validate CSV rows
- [ ] Persist status transitions to DynamoDB Local (`PROCESSING` → `PROCESSED` / `FAILED`)
- [ ] Write result artifacts and error report to S3
- [ ] Delete SQS message only on success
- [ ] Unit and integration tests in `processor-worker/tests/`

### Phase 5 — Status API
- [ ] `status-api/app/main.py` — FastAPI application
- [ ] `GET /health`
- [ ] `GET /transactions/{id}`
- [ ] `GET /transactions/{id}/errors`
- [ ] Response schemas aligned with domain model
- [ ] Unit tests in `status-api/tests/`

### Phase 6 — Containerization and Kubernetes
- [ ] `Dockerfile` for `processor-worker`
- [ ] `Dockerfile` for `status-api`
- [ ] Kubernetes `Deployment` for worker
- [ ] Kubernetes `Deployment` for status API
- [ ] Kubernetes `Service` for status API (NodePort 30080)
- [ ] `ConfigMap` and `Secret` definitions for configuration injection
- [ ] Load images into kind and deploy to `mini-file-platform` namespace
- [ ] Verify logs, restarts, and config injection with `kubectl`

### Phase 7 — Failure Scenarios and Recovery
- [ ] Invalid schema file test (wrong columns)
- [ ] Duplicate `record_id` within a file
- [ ] GPG decryption failure
- [ ] Poison message → DLQ routing after max retries
- [ ] Verify status transitions and error summaries in DynamoDB
- [ ] Verify error artifacts written to S3

### Phase 8 — Lightweight Observability
- [ ] JSON structured logging in all components
- [ ] `transaction_id` correlated across all log lines
- [ ] Basic counters: `jobs_processed`, `jobs_failed`
- [ ] Health summary endpoint (optional)
- [ ] Demonstrate full trace of a failed transaction from logs alone

### Phase 9 — Interview Readiness
- [ ] 5–8 minute system walkthrough script
- [ ] Trade-off narrative for each technology choice
- [ ] Explanation of deliberate simplifications vs production gaps
- [ ] Prepared answers: idempotency, retries, secrets, scaling, observability
- [ ] End-to-end demo runbook (single `make` sequence from upload to status query)
