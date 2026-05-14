from __future__ import annotations

import os
from pathlib import Path

import gnupg

from shared.utils.log_config import get_logger

log = get_logger(__name__)


def decrypt_file(src: Path, dest: Path) -> None:
    """Decrypt a GPG-encrypted file. Raises RuntimeError on failure."""
    gpg_home = os.environ.get("GPG_HOME")
    gpg = gnupg.GPG(gnupghome=gpg_home)

    with open(src, "rb") as f:
        result = gpg.decrypt_file(f, output=str(dest), always_trust=True)

    if not result.ok:
        raise RuntimeError(f"GPG decryption failed: {result.status} — {result.stderr}")

    log.info("file decrypted", extra={"src": str(src), "dest": str(dest)})
