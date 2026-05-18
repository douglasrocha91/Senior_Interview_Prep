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

**Output observed:**

```
/tmp/gpg-lab/pubring.kbx
------------------------
pub   rsa4096 2026-05-18 [SCEAR] [expires: 2027-05-18]
      45AEF90C0C521E1D0548C86553C54028DD9DB7DA
uid           [ultimate] Submitter Partner <submitter@acme.example>
sub   rsa4096 2026-05-18 [SEA] [expires: 2027-05-18]
      E770692AB94B1ACE3606E2FC24C2D0B0ED5B02B8

pub   rsa4096 2026-05-18 [SCEAR] [expires: 2027-05-18]
      C5DE297D1B1C5D5C6A9CE96142BAF392995ED005
uid           [ultimate] Processor Worker <processor@internal.example>
sub   rsa4096 2026-05-18 [SEA] [expires: 2027-05-18]
      B4EB0A9947B42C99C53ADC4C0A6BB10EB66789CD
```

### Observe and note

- What is a fingerprint and why does it matter for trust?
- What is the difference between a primary key and a subkey?
- Why is `%no-protection` used here and when would you never use it in production?

### Answers

**Fingerprint:** A 40-character hex hash (SHA-1 over the public key material) that uniquely identifies a key — for example `45AEF90C0C521E1D0548C86553C54028DD9DB7DA`. Two keys can share the same email address (`submitter@acme.example`), but no two valid keys share a fingerprint. Before trusting a key you must verify the fingerprint out-of-band (phone call, in-person, PGP web of trust, or internal PKI), never trust just the email label.

**Primary key vs subkey:** The primary key (`pub`/`sec`) is the identity anchor — it is used for certifying (signing) other people's keys and cannot be rotated without changing your identity. Subkeys (`sub`/`ssb`) handle day-to-day cryptographic operations (encryption `[E]`, signing `[S]`). The `[SCEAR]` flags on the primary key mean it can Sign, Certify, Encrypt, Authenticate, and Restrict. Separating them lets you store the primary key offline (air-gapped hardware) while rotating subkeys periodically without invalidating your web-of-trust signatures.

**`%no-protection`:** Omits the passphrase from the private key file so the key can be used in non-interactive scripts. Acceptable in a disposable lab. In production you would never use it because an unprotected private key file is immediately usable by anyone who can read it — no further credential required. Production keys must have a strong passphrase, managed by `gpg-agent` or a hardware security module.

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

### Answers

**Public vs private:** The exported `.asc` file starts with `-----BEGIN PGP PUBLIC KEY BLOCK-----` and contains only the public material — sharing it cannot leak the private key. The private key lives only in the `GNUPGHOME` directory (`secring.gpg` or the `pubring.kbx` for GnuPG 2.x) and must never leave its owner's machine.

**Secure channel matters:** A man-in-the-middle could substitute their own public key for the partner's during the exchange. If you encrypt a file to that key, the attacker can decrypt it. Mitigation: always compare fingerprints via a separate, trusted channel before importing a key. At SAP Concur scale this is enforced by an internal certificate authority or a key management service that signs partner keys.

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

**Output observed:**

```
-rw-r--r--  151B  sample-expenses.csv
-rw-r--r--  734B  sample-expenses.csv.gpg

sample-expenses.csv.gpg: PGP RSA encrypted session key - keyid: 0A6BB10E B66789CD RSA (Encrypt or Sign) 4096b

strings output: binary garbage (,[J  fRJ>x  )xE& ...)
```

### What to note

- `--trust-model always` skips the web-of-trust check. In production, sign and verify keys through a proper trust chain or internal PKI.
- The encrypted file reveals nothing about its contents — not even the column names.
- The sender does not need the receiver's private key, ever.

### Answers

**`--trust-model always`:** Instructs GPG to encrypt even if the recipient's key is not marked as trusted in the web-of-trust model. Acceptable in a lab or controlled internal environment where fingerprints were verified at onboarding. In a public-facing or multi-partner production system, you would instead sign the partner's key after fingerprint verification (`gpg --sign-key`) and set `--trust-model pgp`, so GPG refuses to encrypt to an unverified key.

**Encrypted file reveals nothing:** The `file` command returns `PGP RSA encrypted session key` — the file type is known but the contents (column names, values, employee IDs) are completely hidden. The only metadata visible in the PKESK packet is the key ID used for encryption (`0A6BB10EB66789CD`), which identifies the recipient's subkey.

**Asymmetric envelope:** GPG uses a hybrid scheme: it generates a random symmetric session key, encrypts the file content with that key (AES-256), then encrypts the session key with the recipient's RSA public key. The sender only needs the public key — the private key stays exclusively with the platform.

---

## Exercise 4 — Decrypt a File (Platform Receives)

The processor worker decrypts the file using its own private key.

```bash
gpg --output sample-expenses-decrypted.csv \
    --decrypt sample-expenses.csv.gpg

diff sample-expenses.csv sample-expenses-decrypted.csv && echo "Files match."
```

**Output observed:**

```
gpg: encrypted with rsa4096 key, ID 0A6BB10EB66789CD, created 2026-05-18
      "Processor Worker <processor@internal.example>"
Files match.
```

### What to note

- Decryption requires the private key that corresponds to the public key used during encryption.
- If the private key is compromised, all files encrypted to that key are at risk. Key rotation policy matters.
- When does this fail? Try decrypting with the wrong identity and observe the error.

### Answers

**Wrong identity failure:** If you try to decrypt with a key that does not have the matching private key, GPG prints `gpg: decryption failed: No secret key` and exits with code 2. The file is unreadable. This is the correct and expected behaviour — there is no fallback.

**Key ID in decrypt output:** GPG prints the key ID (`0A6BB10EB66789CD`) and its owner during decryption. This is the subkey ID that appears in the encrypted session key packet. Logging this at processing time gives you a complete audit trail: which subkey decrypted which file, and when.

**Compromise impact:** Because the same private key is used to decrypt all files encrypted to it, a compromised key exposes every file ever encrypted to that key — including historical files sitting in S3. This is why rotation policy and short expiry windows matter: a rotated key limits the blast radius to files encrypted in the current key period.

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

**Output observed:**

```
gpg: Signature made Sun 17 May 22:49:00 2026 -03
gpg:                using RSA key E770692AB94B1ACE3606E2FC24C2D0B0ED5B02B8
gpg:                issuer "submitter@acme.example"
gpg: Good signature from "Submitter Partner <submitter@acme.example>" [ultimate]
Exit code: 0
```

### Tamper and re-verify

```bash
echo "tampered" >> sample-expenses.csv
gpg --verify sample-expenses.csv.asc sample-expenses.csv
echo "Exit code: $?"
```

**Output observed:**

```
gpg: Signature made Sun 17 May 22:49:00 2026 -03
gpg:                using RSA key E770692AB94B1ACE3606E2FC24C2D0B0ED5B02B8
gpg:                issuer "submitter@acme.example"
gpg: BAD signature from "Submitter Partner <submitter@acme.example>" [ultimate]
Exit code: 1
```

### What to note

- A detached signature (`.asc`) is separate from the file itself, which is useful for tooling that needs to read the file independently.
- A valid signature proves the file was not modified after signing AND that the signer held the matching private key.
- Exit code `0` = valid. Exit code `1` = bad signature. Exit code `2` = key not found or other error.

### Answers

**Detached vs inline signature:** A detached signature (`.asc` file) allows the original file to be processed without any GPG-aware tooling — a CSV parser can still open `sample-expenses.csv` directly. An inline/clearsign signature wraps the content inside a PGP block, which works better for text messages but complicates file processing pipelines.

**What "bad signature" means:** GPG recomputes the hash of the file and compares it against the decrypted signature value. After appending `"tampered"`, the hash changes, the comparison fails, and GPG returns exit code `1` (not `2` — `2` is reserved for key-lookup errors). In a pipeline, you must treat any non-zero exit code from `gpg --verify` as a hard rejection, not a warning.

**The signing key used:** The signature was made with subkey `E770692AB94B1ACE3606E2FC24C2D0B0ED5B02B8` (the `[S]` signing subkey of the submitter's keypair, not the primary key). This is the expected behaviour — GPG prefers the signing subkey automatically.

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

**Output observed during decrypt:**

```
gpg: encrypted with rsa4096 key, ID 0A6BB10EB66789CD, created 2026-05-18
      "Processor Worker <processor@internal.example>"
gpg: Signature made Sun 17 May 22:49:12 2026 -03
gpg:                using RSA key E770692AB94B1ACE3606E2FC24C2D0B0ED5B02B8
gpg:                issuer "submitter@acme.example"
gpg: Good signature from "Submitter Partner <submitter@acme.example>" [ultimate]
Files match.
```

GPG prints the signer's key information during decryption automatically — both decryption and signature verification happen in one pass. The platform must check the exit code and parse the `Good signature` line to enforce the signature requirement; a missing signature does not fail by default with `--decrypt` alone.

---

## Exercise 7 — Key Handling and Operational Precautions

Work through these questions and write a one-paragraph answer for each.

### Questions

1. **Key storage**: Where should private keys live in a Kubernetes deployment? (Think: secrets, volumes, external secret managers.)

2. **Key rotation**: A partner sends you a new public key. What steps do you take before trusting and using it? What happens to files already in flight encrypted to the old key?

3. **Key expiry**: Your processor key expires in 30 days. What is the impact if you do nothing? What is the rotation procedure?

4. **Passphrase protection**: `%no-protection` was used in this lab. Why is passphrase protection important on private keys and how do automated services handle it (hint: `gpg-agent`, `--pinentry-mode loopback`)?

5. **Audit trail**: An auditor asks which key was used to encrypt file `01JXYZABCDEF.csv.gpg`. How would you answer? What metadata would you log at upload time?

### Answers

**1. Key storage in Kubernetes:** The GPG private key (exported as an armored block with `gpg --armor --export-secret-keys`) should be stored as a Kubernetes `Secret` of type `Opaque`. Mount it into the worker container as a volume under a restricted path such as `/run/secrets/gpg-privkey.asc`, set file permissions to `0400`, and point `GPG_HOME` at a directory where an init container has imported the key on startup. For production, replace the native Kubernetes Secret with an External Secrets Operator integration backed by AWS Secrets Manager or HashiCorp Vault — the key material then never touches etcd in plaintext. Never embed the private key in the container image or pass it via environment variable (it would appear in `env` output and pod descriptions).

**2. Key rotation procedure:** Before trusting a new partner public key: (1) receive the key file over a verified channel (not plain email), (2) import it with `gpg --import partner-new-pubkey.asc`, (3) verify the fingerprint out-of-band by calling the partner and reading the fingerprint aloud, (4) sign the key with your platform key only after confirmation (`gpg --sign-key partner@acme.example`). For files already in flight encrypted to the old key: do not immediately remove the old key from the keyring. Keep both keys active through a grace period (typically 2–4 weeks) so any files uploaded before the cutover can still be decrypted. Set a hard cutover date, then archive the old key securely and document it as "retired — decryption only".

**3. Key expiry impact:** If you do nothing, GPG will refuse to encrypt new files to an expired key and `--decrypt` will succeed but show a warning. Partners whose tooling checks expiry will reject the key entirely. The rotation procedure: (1) generate a new keypair well before expiry (at least 2 weeks out), (2) distribute the new public key to all partners via the same verified channel used originally, (3) update the Kubernetes Secret with the new private key and restart the worker, (4) confirm a full round-trip (encrypt → upload → decrypt) with a test file, (5) extend or revoke the old key. Key renewal (extending expiry without new key material) is an option but does not improve security; generating a new keypair is preferred.

**4. Passphrase protection:** A private key file without a passphrase is immediately usable by anyone who obtains it — an attacker who reads the file (via a misconfigured volume mount, a S3 path traversal, a container escape) can decrypt all past and future files without any further credential. In automated services, `gpg-agent` handles the passphrase: it is started with the container, the passphrase is injected once from a Kubernetes Secret via `--pinentry-mode loopback`, and the agent caches it in memory for the session. The private key file on disk remains passphrase-protected (encrypted), but the running agent can use it without re-prompting. This means an attacker needs both the key file and the running agent session — two factors instead of one.

**5. Audit trail:** At upload time (when `submitter-cli` calls `encrypt_file()`), log a structured JSON line: `{"event": "file_encrypted", "file_id": "01JXYZABCDEF", "recipient_key_id": "B4EB0A9947B42C99", "recipient_fingerprint": "C5DE297D1B1C5D5C6A9CE96142BAF392995ED005", "encrypted_at": "2026-05-17T22:38:00Z", "partner": "acme"}`. The key ID is available from `gnupg.GPG().list_keys()` matched by recipient email. To answer the auditor retroactively without logs: run `gpg --list-packets 01JXYZABCDEF.csv.gpg` — the PKESK packet contains the key ID (`0A6BB10EB66789CD`) used for the session key, which identifies the recipient subkey and therefore the keypair.

---

## Exercise 8 — Connect to the Mini-File-Platform Flow

Review the actual `submitter-cli` and `processor-worker` code in this repo and answer:

1. In `submitter-cli`, where does encryption happen and which key fingerprint is used?
2. In `processor-worker`, where does decryption happen and how is the keyring made available inside Kubernetes?
3. What would happen if the GPG home directory inside the worker container does not have the correct permissions (`700`)?
4. How would you add signature verification to the processor before the CSV is parsed?

### Answers

**1. Encryption in submitter-cli:** Encryption happens in `submitter-cli/app/crypto.py`, function `encrypt_file()` (line 7). It calls `gnupg.GPG(gnupghome=gpg_home).encrypt_file()` with `recipients=[recipient_email]` and `always_trust=True`. The code does **not** use a fingerprint — it looks up the key by email address in the keyring. The caller passes `gpg_home` as a parameter (read from the `GPG_HOME` environment variable in `main.py`). This means the keyring must already contain the processor's public key imported under `processor@internal.example` — the email is the only identifier used, which is why out-of-band fingerprint verification before key import is critical.

**2. Decryption in processor-worker:** Decryption happens in `processor-worker/app/decryptor.py`, function `decrypt_file()` (line 13). It reads `GPG_HOME` from `os.environ.get("GPG_HOME")` — if the variable is unset, `gnupg.GPG()` defaults to `~/.gnupg`. In the current Kubernetes manifest (`infra/kubernetes/processor-worker-deployment.yaml`), `GPG_HOME` is not set and there is no volume mounting a keyring. The production approach would be: (1) store the private key as a Kubernetes Secret, (2) mount it as a volume, (3) run an init container that imports the key into a writable `emptyDir` used as `GPG_HOME`, (4) set `GPG_HOME` via `env` in the Deployment spec pointing at that `emptyDir`.

**3. Wrong permissions on GPG_HOME:** GnuPG enforces that the home directory is owned by the current user and has mode `700`. If permissions are wrong (e.g., `755` or world-readable), GPG prints `WARNING: unsafe permissions on homedir '/path/.gnupg'` and refuses to operate, returning a non-zero exit code. In the worker, `decrypt_file()` would raise `RuntimeError("GPG decryption failed: ...")` on every message, causing the worker to NACK all SQS messages and enter a permanent failure loop. The pod would remain `Running` but all files would fail processing silently unless the error is properly surfaced in CloudWatch.

**4. Adding signature verification:** After `gpg.decrypt_file()` succeeds, inspect `result.stderr` for the signature status line. A robust approach: check `result.trust_text` (`"ultimately trusted"`, `"fully trusted"`) or parse for `"Good signature from"`. If neither is present, raise an exception before passing the decrypted path to the CSV parser. Better still, require partners to upload a detached signature (`.asc`) alongside the encrypted file, then call `gpg.verify_file(sig_file, data_filename=decrypted_path)` and assert `verify_result.valid is True`. This separates concerns: decryption is independent of signature verification, and you can enforce which partner fingerprint is allowed per tenant.

---

## Notes: Secure File Exchange Workflow

```
Sender workflow:
  1. Obtain the platform's public key and verify its fingerprint out-of-band
  2. Encrypt the file using the platform's public key (gpg --encrypt --recipient)
  3. Optionally sign the encrypted file with the sender's private key (--sign --encrypt in one pass)
  4. Upload the .gpg file to the agreed S3 prefix

Platform (receiver) workflow:
  1. Download the encrypted .gpg file from S3 (triggered by SQS event)
  2. Decrypt using the platform's private key (processor-worker/app/decryptor.py)
  3. Verify the sender's embedded signature if present (check result.trust_text)
  4. Parse and validate the decrypted CSV, then store results

Key management responsibilities:
  - Sender owns: their private signing key; distributing their public key via a verified channel
  - Platform owns: the platform's private decryption key (in Kubernetes Secret, never in image); distributing the platform's public key to partners
  - Shared responsibility: fingerprint verification before key import; rotation coordination with agreed cutover dates; grace-period policy for in-flight files

Risks to watch:
  - Unprotected private key file reachable via volume mount misconfiguration or container escape
  - No expiry policy: keys without expiry accumulate compromise risk indefinitely
  - Missing signature verification: encryption without authentication allows a third party with the public key to substitute a malicious file
  - Decrypted file written to a shared or world-readable path before parsing is complete
  - No audit log of which key ID was used per file, making forensic investigation after a breach very slow
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
