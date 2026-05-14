from __future__ import annotations

import re

# Expected key: inbox/{partner}/{yyyy}/{mm}/{dd}/{transaction_id}.csv.gpg
_KEY_PATTERN = re.compile(
    r"^inbox/(?P<partner>[^/]+)/\d{4}/\d{2}/\d{2}/(?P<transaction_id>[A-Z0-9]{26})\.csv\.gpg$"
)

_REQUIRED_METADATA = frozenset({"transaction_id", "partner", "schema_version"})


class IngestError(Exception):
    """Raised when a record fails admission checks and should be skipped."""


def validate_key(key: str) -> re.Match:
    """Validate the S3 key format. Returns the regex match on success."""
    match = _KEY_PATTERN.match(key)
    if not match:
        raise IngestError(
            f"S3 key does not match expected pattern "
            f"'inbox/{{partner}}/yyyy/mm/dd/{{transaction_id}}.csv.gpg': {key!r}"
        )
    return match


def validate_metadata(metadata: dict[str, str], transaction_id_from_key: str) -> None:
    """Validate required metadata fields and consistency with the S3 key."""
    missing = _REQUIRED_METADATA - set(metadata.keys())
    if missing:
        raise IngestError(f"Missing required metadata fields: {sorted(missing)}")

    meta_tid = metadata.get("transaction_id", "")
    if meta_tid != transaction_id_from_key:
        raise IngestError(
            f"Metadata transaction_id {meta_tid!r} does not match "
            f"key transaction_id {transaction_id_from_key!r}"
        )
