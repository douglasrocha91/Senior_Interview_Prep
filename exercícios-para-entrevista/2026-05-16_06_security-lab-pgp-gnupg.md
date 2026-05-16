# [SAP Concur Prep] 6) Security Lab: PGP/GnuPG Basics

**Date:** Saturday, 16 May 2026 · 4:00 – 6:00 pm  
**Objective:** Get hands-on with PGP/GnuPG and connect it to secure file handling and compliance requirements.

---

## Setup

Work inside `mini-file-platform/infra/local/gnupg/` or a dedicated scratch directory so keys stay isolated from your main keyring.

```bash
export GNUPGHOME="$(pwd)/gnupg-lab"
mkdir -p "$GNUPGHOME"
chmod 700 "$GNUPGHOME"
```

Using a custom `GNUPGHOME` keeps the lab keys separate and makes cleanup trivial.

---

## Exercise 1 — Generate Keys

### Task

Generate two separate keypairs: one representing a **file sender** (submitter) and one representing a **file receiver** (processor worker).

```bash
# Sender keypair
gpg --batch --gen-key <<EOF
Key-Type: RSA
Key-Length: 4096
Subkey-Type: RSA
Subkey-Length: 4096
Name-Real: Submitter Partner
Name-Email: submitter@acme.example
Expire-Date: 1y
%no-protection
%commit
EOF

# Receiver keypair
gpg --batch --gen-key <<EOF
Key-Type: RSA
Key-Length: 4096
Subkey-Type: RSA
Subkey-Length: 4096
Name-Real: Processor Worker
Name-Email: processor@internal.example
Expire-Date: 1y
%no-protection
%commit
EOF
```

### Verify

```bash
gpg --list-keys
gpg --list-secret-keys
```

### Observe and note

- What is a fingerprint and why does it matter for trust?
- What is the difference between a primary key and a subkey?
- Why is `%no-protection` used here and when would you never use it in production?

---

## Exercise 2 — Export and Import Public Keys

This simulates key exchange between the partner and the internal platform.

```bash
# Sender exports their public key and hands it to the platform
gpg --armor --export submitter@acme.example > submitter-pubkey.asc

# Receiver exports their public key and hands it to the partner
gpg --armor --export processor@internal.example > processor-pubkey.asc

# Inspect an exported key
cat submitter-pubkey.asc
```

### What to note

- Public keys are safe to share. Private keys never leave their owner's system.
- In a real integration, the partner sends their public key over a secure channel (secure email, key server, shared vault). Never accept a key over a channel you cannot verify.

---

## Exercise 3 — Encrypt a File (Sender → Platform)

The submitter encrypts a CSV file using the **receiver's** public key. Only the receiver's private key can decrypt it.

```bash
# Create a sample file
echo "record_id,expense_date,employee_id,currency,amount,description
R001,2026-05-16,EMP042,USD,149.99,Team lunch
R002,2026-05-16,EMP017,EUR,42.00,Transport" > sample-expenses.csv

# Encrypt for the processor worker (recipient = processor)
gpg --recipient processor@internal.example \
    --trust-model always \
    --output sample-expenses.csv.gpg \
    --encrypt sample-expenses.csv

ls -lh sample-expenses.csv sample-expenses.csv.gpg
```

### Verify

```bash
# Confirm the file is not human-readable
file sample-expenses.csv.gpg
strings sample-expenses.csv.gpg | head
```

### What to note

- `--trust-model always` skips the web-of-trust check. In production, sign and verify keys through a proper trust chain or internal PKI.
- The encrypted file reveals nothing about its contents — not even the column names.
- The sender does not need the receiver's private key, ever.

---

## Exercise 4 — Decrypt a File (Platform Receives)

The processor worker decrypts the file using its own private key.

```bash
gpg --output sample-expenses-decrypted.csv \
    --decrypt sample-expenses.csv.gpg

diff sample-expenses.csv sample-expenses-decrypted.csv && echo "Files match."
```

### What to note

- Decryption requires the private key that corresponds to the public key used during encryption.
- If the private key is compromised, all files encrypted to that key are at risk. Key rotation policy matters.
- When does this fail? Try decrypting with the wrong identity and observe the error.

---

## Exercise 5 — Sign a File (Sender Proves Identity)

Encryption protects confidentiality. Signing proves authenticity and integrity.

```bash
# Sender signs the plaintext file with their private key
gpg --local-user submitter@acme.example \
    --armor \
    --detach-sign sample-expenses.csv

ls sample-expenses.csv.asc
```

### Verify the signature

```bash
gpg --verify sample-expenses.csv.asc sample-expenses.csv
echo "Exit code: $?"
```

### Tamper and re-verify

```bash
echo "tampered" >> sample-expenses.csv
gpg --verify sample-expenses.csv.asc sample-expenses.csv
echo "Exit code: $?"
```

### What to note

- A detached signature (`.asc`) is separate from the file itself, which is useful for tooling that needs to read the file independently.
- A valid signature proves the file was not modified after signing AND that the signer held the matching private key.
- Exit code `0` = valid. Exit code `2` = bad signature or key not found.

---

## Exercise 6 — Encrypt and Sign Together

In practice, files should be both encrypted (confidentiality) and signed (authenticity).

```bash
# Restore the original file
echo "record_id,expense_date,employee_id,currency,amount,description
R001,2026-05-16,EMP042,USD,149.99,Team lunch
R002,2026-05-16,EMP017,EUR,42.00,Transport" > sample-expenses.csv

# Encrypt for the processor and sign as the submitter
gpg --recipient processor@internal.example \
    --local-user submitter@acme.example \
    --trust-model always \
    --output sample-expenses-signed.csv.gpg \
    --sign --encrypt sample-expenses.csv

# Decrypt and verify in one step
gpg --output sample-expenses-final.csv \
    --decrypt sample-expenses-signed.csv.gpg
```

GPG will print the signer's key information during decryption. Note it.

---

## Exercise 7 — Key Handling and Operational Precautions

Work through these questions and write a one-paragraph answer for each.

### Questions

1. **Key storage**: Where should private keys live in a Kubernetes deployment? (Think: secrets, volumes, external secret managers.)

2. **Key rotation**: A partner sends you a new public key. What steps do you take before trusting and using it? What happens to files already in flight encrypted to the old key?

3. **Key expiry**: Your processor key expires in 30 days. What is the impact if you do nothing? What is the rotation procedure?

4. **Passphrase protection**: `%no-protection` was used in this lab. Why is passphrase protection important on private keys and how do automated services handle it (hint: `gpg-agent`, `--pinentry-mode loopback`)?

5. **Audit trail**: An auditor asks which key was used to encrypt file `01JXYZABCDEF.csv.gpg`. How would you answer? What metadata would you log at upload time?

---

## Exercise 8 — Connect to the Mini-File-Platform Flow

Review the actual `submitter-cli` and `processor-worker` code in this repo and answer:

1. In `submitter-cli`, where does encryption happen and which key fingerprint is used?
2. In `processor-worker`, where does decryption happen and how is the keyring made available inside Kubernetes?
3. What would happen if the GPG home directory inside the worker container does not have the correct permissions (`700`)?
4. How would you add signature verification to the processor before the CSV is parsed?

---

## Notes: Secure File Exchange Workflow

Write your own summary here after completing the exercises. Template:

```
Sender workflow:
  1.
  2.
  3.

Platform (receiver) workflow:
  1.
  2.
  3.

Key management responsibilities:
  - Sender owns:
  - Platform owns:
  - Shared responsibility:

Risks to watch:
  -
  -
  -
```

---

## Interview Angle

### Why encryption matters in file exchange pipelines

File pipelines carry sensitive business data — expense records, employee IDs, financial amounts. Encryption ensures that even if S3 object ACLs are misconfigured, a network path is intercepted, or a bucket is accessed by an unauthorized party, the file contents remain unreadable without the private key.

### How secrets and keys should be protected

Private keys should never be embedded in container images or committed to version control. In Kubernetes, mount them via a `Secret` volume with restrictive permissions, or source them from an external secret manager (AWS Secrets Manager, HashiCorp Vault). Passphrases should be injected via environment variables from secrets, not hardcoded.

### Operational risks to watch

- **Key sprawl**: multiple copies of a private key reduce control surface. Centralise storage.
- **No expiry policy**: keys without expiry accumulate risk indefinitely.
- **Missing signature verification**: encryption without signature means you cannot detect file substitution by a third party with access to the public key.
- **Wrong key used at rest**: if the platform stores decrypted files anywhere, those are now at risk without their own encryption-at-rest layer.
- **Audit gap**: if the system does not log which key fingerprint was used per file, forensic investigation after a breach becomes much harder.

---

## Cleanup

```bash
# Remove the lab keyring entirely
rm -rf "$GNUPGHOME"
unset GNUPGHOME
```
