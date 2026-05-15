# Failure Scenarios Guide

The platform distinguishes two failure classes with different behaviors:

| Class | Example | Worker returns | SQS message | DynamoDB status |
|---|---|---|---|---|
| **Business failure** | Validation errors in CSV | `True` | Deleted | `PROCESSED` + `error_summary` |
| **Infrastructure failure** | Decrypt failed, S3 key missing | `False` | Retained for retry | `FAILED` |
| **Poison message** | Malformed JSON body | `True` (skipped) | Retained → DLQ | No record created |

---

## Prerequisites

- LocalStack running: `docker start localstack-main`
- DynamoDB Local running (in-memory mode): see `docs/setup-dynamodb-local.md`
- `.env` sourced: `set -a && source .env && set +a`
- `check-transaction.sh` helper: see `docs/e2e-local.md`

---

## Scenario 1 — Corrupt File (Decrypt Failure)

**What it simulates:** A file uploaded to S3 that is not a valid GPG-encrypted file. The decryptor receives garbage and fails.

**Expected outcome:** `FAILED` in DynamoDB. Worker returns `False` — message stays in SQS and will be retried up to 3 times before going to DLQ.

```bash
make scenario-corrupt
```

The script:
1. Uploads a plaintext file with a `.csv.gpg` extension to S3
2. Publishes an SQS message pointing to it
3. Prints the `transaction_id`

Then run the worker:

```bash
make worker-run
# Press Ctrl+C after the message is consumed
```

Expected log output:

```json
{"level": "ERROR", "logger": "app.pipeline", "message": "infrastructure failure",
 "reason": "Decrypt failed: GPG decryption failed: no valid OpenPGP data found"}
{"level": "INFO", "logger": "app.store", "message": "transaction status updated", "status": "FAILED"}
```

Verify:

```bash
bash /tmp/check-transaction.sh <TID>
# status: FAILED
# No errors.jsonl artifact (infra failure, not validation)
```

---

## Scenario 2 — Missing S3 Key (Download Failure)

**What it simulates:** An SQS message that references an S3 object that does not exist. The download step throws a 404.

**Expected outcome:** `FAILED` in DynamoDB. Worker returns `False` — message stays in SQS for retry.

```bash
make scenario-missing
```

Run the worker:

```bash
make worker-run
# Press Ctrl+C after the message is consumed
```

Expected log output:

```json
{"level": "ERROR", "logger": "app.pipeline", "message": "infrastructure failure",
 "reason": "Download failed: An error occurred (404) when calling the HeadObject operation: Not Found"}
{"level": "INFO", "logger": "app.store", "message": "transaction status updated", "status": "FAILED"}
```

Verify:

```bash
bash /tmp/check-transaction.sh <TID>
# status: FAILED
```

---

## Scenario 3 — Poison Message (Malformed JSON)

**What it simulates:** An SQS message whose body is not valid JSON — or valid JSON missing required fields. The consumer cannot parse it into a `FileJob`.

**Expected outcome:** Consumer logs an error and returns `True` (message counts as "consumed") without calling `process_job`. No DynamoDB record is created. The message is **not deleted** by the consumer, so SQS retains it and increments the receive count. After 3 receives, SQS routes it to the DLQ automatically.

```bash
make scenario-poison
```

Run the worker **three times** (or run it once and let visibility timeout expire twice more) to exhaust the retry count:

```bash
make worker-run   # first receive — logs parse error, does not delete
# Ctrl+C, wait for visibility timeout (30s), then:
make worker-run   # second receive
# Ctrl+C, wait again:
make worker-run   # third receive → SQS routes to DLQ
```

Check the DLQ:

```bash
make scenario-dlq
# file-jobs-dlq: 1 message(s)
```

Expected worker log output on each receive:

```json
{"level": "ERROR", "logger": "app.consumer", "message": "malformed SQS message body — leaving in queue for DLQ"}
```

---

## Scenario 4 — DLQ Inspection

Check how many messages are in each queue at any time:

```bash
make scenario-dlq
```

Output:

```
=== DLQ status ===
  file-jobs (main) : 0 mensagem(s)
  file-jobs-dlq    : 1 mensagem(s)

  Mensagens no DLQ (peek):
    (corpo não é JSON válido — poison message)
```

---

## Retry vs DLQ — Interview Talking Points

**Why does infrastructure failure return `False` instead of deleting the message?**

SQS visibility timeout is the retry mechanism. When the worker does not delete a message, SQS makes it visible again after the visibility timeout expires (default 30s). This gives the system a chance to recover — a transient S3 failure resolves itself on the next attempt. Deleting the message on failure would silently drop work.

**Why does the poison message consumer return `True` but not delete the message?**

Returning `True` tells the outer consumer loop that the receive was "handled" — no retry storm. But the consumer intentionally skips `delete_message`. SQS counts the receive regardless, so after `maxReceiveCount` (3) the DLQ redrive takes over. The poison message is isolated without crashing the worker.

**Why 3 retries before DLQ?**

Enough to cover transient failures (a brief S3 outage, a network blip) without filling the main queue with permanently broken messages. In production this is tuned per workload — higher for idempotent jobs, lower for time-sensitive ones.

**What happens to FAILED transactions in DynamoDB?**

They stay there permanently as an audit trail. A separate remediation process (not in this lab) would read FAILED records and decide whether to requeue, discard, or alert.
