from datetime import timezone, datetime
from pathlib import Path

import boto3


def build_s3_key(partner: str, transaction_id: str) -> str:
    """Return the canonical S3 key: inbox/{partner}/{yyyy}/{mm}/{dd}/{tid}.csv.gpg"""
    now = datetime.now(timezone.utc)
    return (
        f"inbox/{partner}/{now.year:04d}/{now.month:02d}/{now.day:02d}"
        f"/{transaction_id}.csv.gpg"
    )


def upload_encrypted_file(
    file_path: Path,
    bucket: str,
    partner: str,
    transaction_id: str,
    schema_version: str = "v1",
) -> str:
    """Upload *file_path* to S3 with the canonical key and metadata. Returns the key."""
    key = build_s3_key(partner, transaction_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    s3 = boto3.client("s3")
    s3.upload_file(
        str(file_path),
        bucket,
        key,
        ExtraArgs={
            "Metadata": {
                "transaction_id": transaction_id,
                "partner": partner,
                "uploaded_at": now_iso,
                "schema_version": schema_version,
            }
        },
    )
    return key
