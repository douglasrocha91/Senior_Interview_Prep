# DynamoDB Local — Setup Guide

Local emulation of DynamoDB via Docker. Used for transaction state persistence without managed AWS spend.

---

## Prerequisites

- Docker Desktop installed and **running**
- AWS CLI installed (credentials can be fake for local use)

---

## 1. Start the Container

```bash
make local-up
```

This runs `docker compose -f infra/local/docker-compose.yml up -d` and waits until port 8000 is ready.

### Volume permission error (known issue)

The docker-compose file mounts a persistent volume. On some macOS setups the container reports `unhealthy` and logs:

```
SQLiteException: [14] unable to open database file
```

**Fix:** run in in-memory mode instead (data is lost on container restart, which is fine for the lab):

```bash
docker run -d \
  --name mini-file-platform-dynamodb \
  -p 8000:8000 \
  amazon/dynamodb-local:2.5.4 \
  -jar DynamoDBLocal.jar -inMemory -sharedDb
```

---

## 2. Create the Transactions Table

```bash
make local-table
```

This runs `infra/local/create-table.sh`. The script is idempotent — safe to run multiple times.

### What the table looks like

| Attribute | Type | Role |
|---|---|---|
| `transaction_id` | String | Partition key (PK) |
| `partner` | String | schemaless attribute |
| `source_bucket` | String | schemaless attribute |
| `source_key` | String | schemaless attribute |
| `status` | String | `RECEIVED / QUEUED / PROCESSING / PROCESSED / FAILED` |
| `created_at` | String | ISO-8601 timestamp |
| `updated_at` | String | ISO-8601 timestamp |
| `attempt_count` | Number | SQS delivery count |
| `result_prefix` | String | S3 prefix for output artifacts |
| `error_summary` | String | Populated on failure or validation errors |

DynamoDB is schemaless — only `transaction_id` needs to be declared at table creation time.

---

## 3. Verify It Is Working

```bash
make local-verify
```

Writes a test record and reads it back. Expected output:

```
=== Writing test record to DynamoDB Local ===
=== Reading test record back ===
{
    "Item": {
        "transaction_id": {"S": "TEST-VERIFY"},
        "status": {"S": "RECEIVED"}
    }
}
[ok] DynamoDB Local is working correctly
```

---

## 4. Query Records Manually

Set these env vars first (or source `.env`):

```bash
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
export DYNAMODB_ENDPOINT_URL=http://localhost:8000
```

**Get a transaction by ID:**

```bash
aws --endpoint-url http://localhost:8000 dynamodb get-item \
  --table-name transactions \
  --key '{"transaction_id":{"S":"YOUR_TID_HERE"}}' \
  --output json
```

**Readable output (flatten DynamoDB type wrappers):**

```bash
aws --endpoint-url http://localhost:8000 dynamodb get-item \
  --table-name transactions \
  --key '{"transaction_id":{"S":"YOUR_TID_HERE"}}' \
  --output json | python3 -c "
import sys, json
item = json.load(sys.stdin).get('Item', {})
for k, v in item.items():
    val = v.get('S') or v.get('N') or '(null)'
    print(f'  {k:25s}: {val}')
"
```

**Scan all transactions (dev only — avoid on large tables):**

```bash
aws --endpoint-url http://localhost:8000 dynamodb scan \
  --table-name transactions \
  --output json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data['Items']:
    tid = item['transaction_id']['S']
    status = item.get('status', {}).get('S', '?')
    print(f'{tid}  {status}')
"
```

---

## 5. Stop the Container

```bash
make local-down
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Connection refused` on port 8000 | Container not running | `make local-up` or `docker start mini-file-platform-dynamodb` |
| Container shows `unhealthy` | SQLite volume permission error | Use in-memory mode (see Step 1) |
| `Read timeout` from AWS CLI | IPv6 vs IPv4 resolution issue | Use `http://127.0.0.1:8000` instead of `http://localhost:8000` |
| Table already exists error | `local-table` ran before | Script is idempotent — error is safe to ignore |
| Port 8000 in use | Another service running | Change host port in docker-compose.yml or stop the conflict |

---

## Required `.env` Variables

```bash
DYNAMODB_ENDPOINT_URL=http://localhost:8000
DYNAMODB_TABLE_TRANSACTIONS=transactions
```
