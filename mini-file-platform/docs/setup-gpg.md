# GPG Setup Guide

The platform uses asymmetric encryption: the submitter encrypts with a public key, and the processor-worker decrypts with the private key. This guide covers key generation, path constraints, and verification.

---

## Key Separation

| Component | Key needed | Why |
|---|---|---|
| `submitter-cli` | Public key | Encrypts before upload — no secret needed |
| `ingest-lambda` | None | Routes messages, never reads file content |
| `processor-worker` | Private key | Decrypts for processing |
| `status-api` | None | Only reads transaction state |

This separation mirrors real file-based integrations: the sender cannot decrypt what it uploads.

---

## 1. Install GPG

```bash
brew install gnupg   # macOS
```

Verify:

```bash
gpg --version
```

---

## 2. macOS Socket Path Constraint

GPG uses a Unix domain socket for the agent. On macOS, socket paths have a **104-character limit**. If your project directory path is long, GPG will fail with:

```
gpg: can't connect to the gpg-agent: File name too long
gpg: agent_genkey failed: No agent running
```

**Fix:** always use a short path for `GPG_HOME`:

```bash
# Good — short path
export GPG_HOME=/tmp/mfp-gpg

# Bad — path too long on deep directory trees
export GPG_HOME=./infra/local/gnupg
```

---

## 3. Generate a Key Pair

```bash
mkdir -p /tmp/mfp-gpg && chmod 700 /tmp/mfp-gpg

gpg --homedir /tmp/mfp-gpg --batch --gen-key <<'EOF'
%no-protection
Key-Type: RSA
Key-Length: 2048
Subkey-Type: RSA
Subkey-Length: 2048
Name-Real: Mini File Platform Lab
Name-Email: lab@mini-file-platform.local
Expire-Date: 0
%commit
EOF
```

`%no-protection` disables the passphrase — acceptable for a local lab, not for production.

Verify:

```bash
gpg --homedir /tmp/mfp-gpg --list-keys
```

Expected output:

```
pub   rsa2048 2026-05-14 [SCEAR]
      4548272DA93E90DFA7A67CBD84742B7A3F479A86
uid           [ultimate] Mini File Platform Lab <lab@mini-file-platform.local>
```

---

## 4. Configure `.env`

```bash
GPG_RECIPIENT_EMAIL=lab@mini-file-platform.local
GPG_HOME=/tmp/mfp-gpg
```

Note: `/tmp/mfp-gpg` is cleared on system restart. Re-run Step 3 after each reboot, or copy the keyring to a persistent location.

---

## 5. Verify Encryption Works

```bash
python3 -c "
import gnupg, tempfile
from pathlib import Path

gpg = gnupg.GPG(gnupghome='/tmp/mfp-gpg')
tmp = Path(tempfile.mktemp(suffix='.txt'))
tmp.write_text('hello world')

result = gpg.encrypt_file(
    open(tmp, 'rb'),
    recipients=['lab@mini-file-platform.local'],
    output=str(tmp) + '.gpg',
    always_trust=True,
)
print('ok:', result.ok)
print('encrypted file exists:', Path(str(tmp) + '.gpg').exists())
"
```

---

## 6. Export and Share the Public Key

If another developer needs to run the submitter against your worker's key:

```bash
gpg --homedir /tmp/mfp-gpg --armor --export lab@mini-file-platform.local \
  > infra/local/platform-public.asc
```

They import it with:

```bash
gpg --import infra/local/platform-public.asc
```

---

## 7. Export the Private Key (for the Worker)

In production, the private key comes from a secrets manager. Locally:

```bash
gpg --homedir /tmp/mfp-gpg --armor --export-secret-key lab@mini-file-platform.local \
  > infra/local/platform-private.asc
```

Import in another environment:

```bash
gpg --import infra/local/platform-private.asc
```

`infra/local/platform-private.asc` and `infra/local/platform-public.asc` are gitignored.

---

## Interview Talking Points

- **Why GPG and not KMS envelope encryption?** GPG gives the same conceptual guarantee — asymmetric key separation — without requiring a key management service. In production, you'd use envelope encryption: a per-file data key encrypted by KMS, stored alongside the file.
- **`always_trust` flag:** Used in dev because we haven't built a web of trust. In production, you verify the key fingerprint explicitly.
- **`%no-protection` (no passphrase):** Acceptable in an automated pipeline where the private key is injected at runtime from a secrets manager. You never type a passphrase in a worker process.
- **Private key storage:** AWS Secrets Manager or HashiCorp Vault, injected as a Kubernetes Secret or environment variable at pod startup.
