# GPG Setup Guide

This guide covers the minimum GPG setup needed to run the submitter-cli locally.

---

## Overview

The platform uses asymmetric encryption:
- The **submitter** encrypts with the recipient's **public key** — no private key access needed at upload time.
- The **processor-worker** decrypts with the **private key** — only the processing path ever holds the secret.

This separation is intentional: it mirrors how real file-based integrations protect data at rest before it reaches the processing environment.

---

## 1. Generate a Key Pair (local dev)

```bash
gpg --batch --gen-key <<EOF
Key-Type: RSA
Key-Length: 4096
Subkey-Type: RSA
Subkey-Length: 4096
Name-Real: Mini File Platform
Name-Email: platform@local.dev
Expire-Date: 0
%no-passphrase
%commit
EOF
```

Verify the key was created:

```bash
gpg --list-keys platform@local.dev
```

---

## 2. Export the Public Key (optional — for sharing)

```bash
gpg --armor --export platform@local.dev > infra/local/platform-public.asc
```

To import on another machine:

```bash
gpg --import infra/local/platform-public.asc
```

---

## 3. Configure the CLI

Set the recipient email in your `.env` file:

```bash
GPG_RECIPIENT_EMAIL=platform@local.dev
```

Optionally override the GnuPG home directory if using an isolated keyring:

```bash
GPG_HOME=/path/to/custom/.gnupg
```

---

## 4. Test Encryption Manually

```bash
echo "test" > /tmp/test.txt
gpg --recipient platform@local.dev --encrypt --armor /tmp/test.txt
cat /tmp/test.txt.asc
```

---

## 5. Export the Private Key for the Processor Worker

The worker needs access to the private key to decrypt files. In a real environment this would come from a secrets manager. Locally:

```bash
gpg --armor --export-secret-key platform@local.dev > infra/local/platform-private.asc
```

**Never commit private key files to version control.**

To import in the worker's keyring:

```bash
gpg --import infra/local/platform-private.asc
```

---

## Key Separation Summary

| Component | Key needed | Why |
|---|---|---|
| submitter-cli | Public key | Encrypts before upload |
| ingest-lambda | None | Only routes, never reads the file content |
| processor-worker | Private key | Decrypts for processing |
| status-api | None | Only reads transaction state |

---

## Interview Talking Points

- **Why GPG and not envelope encryption with KMS?** For this exercise, GnuPG gives us the same conceptual guarantee (asymmetric key separation) without needing a key management service. In production, you'd likely use envelope encryption: a data key encrypted by KMS, stored alongside the file.
- **always_trust flag**: Used in dev because we haven't built a web of trust. In production, you verify the key fingerprint explicitly before trusting.
- **Private key storage**: In production, the private key would live in a secrets manager (AWS Secrets Manager, HashiCorp Vault) and be injected at runtime via environment variables or a mounted Kubernetes Secret.
