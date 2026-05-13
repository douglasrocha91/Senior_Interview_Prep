from pathlib import Path
from typing import Optional

import gnupg


def encrypt_file(
    input_path: Path,
    recipient_email: str,
    gpg_home: Optional[str] = None,
) -> Path:
    """Encrypt *input_path* for *recipient_email* and return the .gpg output path.

    Uses always_trust so the recipient key does not need to be locally signed —
    acceptable for a dev/interview environment, not for production.
    """
    gpg = gnupg.GPG(gnupghome=gpg_home)
    output_path = input_path.with_suffix(input_path.suffix + ".gpg")

    with open(input_path, "rb") as fh:
        result = gpg.encrypt_file(
            fh,
            recipients=[recipient_email],
            output=str(output_path),
            always_trust=True,
        )

    if not result.ok:
        raise RuntimeError(
            f"GPG encryption failed for {input_path}: {result.stderr.strip()}"
        )

    return output_path
