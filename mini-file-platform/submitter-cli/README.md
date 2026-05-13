# submitter-cli

Python CLI responsible for the ingest entry point of the mini-file-platform.

It generates or receives a CSV expense file, encrypts it with GnuPG, and uploads
the encrypted file to the S3 inbound bucket with the required metadata. This is
the first step in the end-to-end pipeline.

---

## Responsibilities

| Step | What happens |
|---|---|
| Generate | Produces a randomised expense CSV with valid structure |
| Encrypt | Encrypts the CSV with the recipient's GPG public key |
| Upload | Uploads the `.csv.gpg` to S3 with canonical key and metadata |
| Output | Prints `transaction_id` and `s3_key` to stdout |

---

## Prerequisites

### 1. Python virtualenv

From the project root (`mini-file-platform/`):

```bash
make venv
```

This creates `.venv/` and installs all dependencies.

### 2. GPG key

The CLI encrypts using the recipient's public key. See [`../docs/gpg-setup.md`](../docs/gpg-setup.md) for full instructions.

Quick setup for local dev:

```bash
gpg --batch --gen-key <<EOF
Key-Type: RSA
Key-Length: 4096
Name-Real: Mini File Platform
Name-Email: platform@local.dev
Expire-Date: 0
%no-passphrase
%commit
EOF
```

### 3. Environment variables

Copy `.env.example` to `.env` at the project root and fill in:

```bash
GPG_RECIPIENT_EMAIL=platform@local.dev   # email matching your GPG key
S3_INBOUND_BUCKET=mini-file-platform-inbound
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
```

---

## Commands

### `generate` — create a sample CSV

```bash
# Default: 50 rows, saved to /tmp/acme_expenses.csv
make submit-generate PARTNER=acme

# Custom output and row count
make submit-generate PARTNER=acme ROWS=100

# Run directly
PYTHONPATH=.. .venv/bin/python -m app.main generate --partner acme --rows 50 --output /tmp/my.csv
```

### `submit` — encrypt and upload an existing CSV

```bash
make submit-submit PARTNER=acme FILE=/tmp/acme_expenses.csv

# Run directly
PYTHONPATH=.. .venv/bin/python -m app.main submit \
    --file /tmp/acme_expenses.csv \
    --partner acme
```

Expected output:

```
transaction_id : 01JXY3ABCDEFGHIJKLMNOPQRST
s3_key         : inbox/acme/2026/05/13/01JXY3ABCDEFGHIJKLMNOPQRST.csv.gpg
```

### `generate-and-submit` — do everything in one command

```bash
make submit-generate-and-submit PARTNER=acme ROWS=50

# Run directly
PYTHONPATH=.. .venv/bin/python -m app.main generate-and-submit \
    --partner acme --rows 50
```

---

## S3 Object Convention

| Attribute | Value |
|---|---|
| Key format | `inbox/{partner}/{yyyy}/{mm}/{dd}/{transaction_id}.csv.gpg` |
| Metadata: `transaction_id` | ULID — time-sortable, 26 characters |
| Metadata: `partner` | Partner identifier string |
| Metadata: `uploaded_at` | ISO-8601 UTC timestamp |
| Metadata: `schema_version` | `v1` (default) |

These metadata fields are read by the Lambda in Phase 3 to build the SQS message.

---

## CSV Schema

| Column | Type | Validation (enforced by processor-worker) |
|---|---|---|
| `record_id` | String | Required, unique within file |
| `expense_date` | ISO-8601 date | Required, valid date |
| `employee_id` | String | Required |
| `currency` | String | Required, exactly 3 characters |
| `amount` | Decimal | Required, greater than zero |
| `description` | String | Optional, max 200 characters |

---

## Running Tests

```bash
# From project root
make test

# Or directly
PYTHONPATH=. .venv/bin/pytest submitter-cli/tests/ -v
```

18 tests covering generator, GPG encryption (mocked), and S3 uploader (mocked).

---

## Module Structure

```
submitter-cli/
  app/
    main.py        # Click CLI entry point — three commands
    generator.py   # CSV generation with randomised valid data
    crypto.py      # GPG file encryption via python-gnupg
    uploader.py    # S3 upload with canonical key and metadata
  tests/
    conftest.py          # sys.path setup for shared imports
    test_generator.py    # 8 tests — structure, uniqueness, validity
    test_crypto.py       # 4 tests — mocked GPG calls and error handling
    test_uploader.py     # 6 tests — mocked boto3, key format, metadata
  pyproject.toml         # Dependencies and pytest config
```

---

## Design Decisions

**Why a CLI and not a service?**
This step happens once per file submission. It has no persistent state, no concurrency requirement, and no need for an HTTP interface. A script is the right tool. Adding a service here would create infrastructure overhead with no architectural benefit.

**Why `python-gnupg` and not subprocess directly?**
`python-gnupg` provides a clean Python interface over the GPG binary and handles output parsing and error detection. Calling GPG via subprocess would require parsing stderr manually.

**Why `always_trust=True`?**
In a local dev environment the recipient key is not in the web of trust. `always_trust` bypasses the trust check without modifying the keyring. In production you would verify the key fingerprint explicitly before trusting.

**Why ULIDs instead of UUIDs?**
ULIDs are lexicographically sortable by creation time, which makes S3 keys naturally ordered and DynamoDB scans more predictable. They are also more readable (Crockford Base32, no hyphens).
