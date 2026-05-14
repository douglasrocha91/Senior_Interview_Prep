from __future__ import annotations

from pathlib import Path

import boto3

from shared.utils.log_config import get_logger

log = get_logger(__name__)


def download_file(bucket: str, key: str, dest: Path) -> None:
    """Download an S3 object to a local path."""
    s3 = boto3.client("s3")
    log.info("downloading file", extra={"bucket": bucket, "key": key, "dest": str(dest)})
    s3.download_file(bucket, key, str(dest))
