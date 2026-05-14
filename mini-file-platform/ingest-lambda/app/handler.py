"""Lambda handler: S3 ObjectCreated event → SQS FileJob message.

Entry point reference: app.handler.handler
Environment variables:
    SQS_FILE_JOBS_URL   URL of the file-jobs SQS queue (required)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import boto3

# Ensure 'shared' is importable when running locally outside the Lambda zip.
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from shared.models.transaction import FileJob
from shared.utils.log_config import get_logger
from shared.utils.timestamps import utc_now_iso

from app.s3_event import S3Record, parse_records
from app.validator import IngestError, validate_key, validate_metadata
from app.publisher import publish_file_job

log = get_logger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, int]:
    """Lambda entrypoint. Processes each S3 record independently."""
    queue_url = os.environ["SQS_FILE_JOBS_URL"]
    records = parse_records(event)

    processed = skipped = 0

    for record in records:
        try:
            _process_record(record, queue_url)
            processed += 1
        except IngestError as exc:
            log.warning(
                "record skipped — admission check failed",
                extra={"key": record.key, "reason": str(exc)},
            )
            skipped += 1
        except Exception as exc:
            log.error(
                "record skipped — unexpected error",
                extra={"key": record.key, "error": str(exc)},
                exc_info=True,
            )
            skipped += 1

    log.info("batch complete", extra={"processed": processed, "skipped": skipped})
    return {"processed": processed, "skipped": skipped}


def _process_record(record: S3Record, queue_url: str) -> None:
    # 1. Validate key structure and extract routing fields
    match = validate_key(record.key)
    partner = match.group("partner")
    transaction_id = match.group("transaction_id")

    log.info(
        "processing S3 record",
        extra={"transaction_id": transaction_id, "partner": partner, "key": record.key},
    )

    # 2. Fetch and validate object metadata
    s3 = boto3.client("s3")
    head = s3.head_object(Bucket=record.bucket, Key=record.key)
    # S3 returns metadata keys lowercased
    metadata = {k.lower(): v for k, v in head.get("Metadata", {}).items()}
    validate_metadata(metadata, transaction_id)

    # 3. Build the normalised queue message
    job = FileJob(
        transaction_id=transaction_id,
        bucket=record.bucket,
        key=record.key,
        partner=partner,
        received_at=utc_now_iso(),
        schema_version=metadata.get("schema_version", "v1"),
        attempt=0,
    )

    # 4. Publish to SQS
    message_id = publish_file_job(queue_url, job)

    log.info(
        "FileJob published to SQS",
        extra={"transaction_id": transaction_id, "message_id": message_id},
    )
