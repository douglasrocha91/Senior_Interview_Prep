from __future__ import annotations

import csv
import io
import json
from typing import List

import boto3

from shared.models.transaction import ValidationError
from shared.utils.log_config import get_logger

log = get_logger(__name__)


def write_results(bucket: str, prefix: str, rows: List[dict]) -> None:
    """Write validated rows to S3 as a CSV."""
    if not rows:
        return

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

    key = f"{prefix}output.csv"
    boto3.client("s3").put_object(
        Bucket=bucket, Key=key, Body=buf.getvalue().encode("utf-8")
    )
    log.info("results written", extra={"bucket": bucket, "key": key, "rows": len(rows)})


def write_errors(bucket: str, prefix: str, errors: List[ValidationError]) -> None:
    """Write validation errors to S3 as a JSON Lines file."""
    if not errors:
        return

    body = "\n".join(json.dumps(e.to_dict()) for e in errors).encode("utf-8")
    key = f"{prefix}errors.jsonl"
    boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=body)
    log.info("errors written", extra={"bucket": bucket, "key": key, "count": len(errors)})
