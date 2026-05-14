"""Orchestrates the full file processing pipeline for one FileJob.

Return value contract (used by consumer.py to decide SQS message fate):
  True  → delete the message. The job reached a terminal business outcome
          (success or validation errors). Re-processing would not change the result.
  False → leave the message in the queue. An infrastructure error occurred
          (download / decrypt failed). SQS will retry; DLQ catches persistent failures.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from shared.models.transaction import FileJob, TransactionStatus
from shared.utils.log_config import get_logger

from app.decryptor import decrypt_file
from app.downloader import download_file
from app.result_writer import write_errors, write_results
from app.store import update_status, upsert_transaction
from app.validator import validate_csv

log = get_logger(__name__)


def process_job(job: FileJob) -> bool:
    tid = job.transaction_id
    table = os.environ["DYNAMODB_TABLE_TRANSACTIONS"]
    results_bucket = os.environ["S3_RESULTS_BUCKET"]
    result_prefix = f"results/{tid}/"

    upsert_transaction(
        table=table,
        job=job,
        status=TransactionStatus.PROCESSING,
        result_prefix=result_prefix,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # inbox/.../ULID.csv.gpg → encrypted_path = ULID.csv.gpg, decrypted = ULID.csv
        encrypted_path = tmp / Path(job.key).name
        decrypted_path = tmp / Path(job.key).stem

        try:
            download_file(bucket=job.bucket, key=job.key, dest=encrypted_path)
        except Exception as exc:
            return _infra_fail(table, tid, f"Download failed: {exc}")

        try:
            decrypt_file(src=encrypted_path, dest=decrypted_path)
        except Exception as exc:
            return _infra_fail(table, tid, f"Decrypt failed: {exc}")

        try:
            rows, errors = validate_csv(path=decrypted_path, transaction_id=tid)
        except Exception as exc:
            return _infra_fail(table, tid, f"CSV parse failed: {exc}")

        write_results(bucket=results_bucket, prefix=result_prefix, rows=rows)
        if errors:
            write_errors(bucket=results_bucket, prefix=result_prefix, errors=errors)

        if errors:
            summary = f"{len(errors)} validation error(s)"
            update_status(table, tid, TransactionStatus.PROCESSED, error_summary=summary)
            log.info(
                "job processed with errors",
                extra={"transaction_id": tid, "error_count": len(errors)},
            )
        else:
            update_status(table, tid, TransactionStatus.PROCESSED)
            log.info(
                "job processed successfully",
                extra={"transaction_id": tid, "row_count": len(rows)},
            )

    return True


def _infra_fail(table: str, transaction_id: str, reason: str) -> bool:
    log.error("infrastructure failure", extra={"transaction_id": transaction_id, "reason": reason})
    update_status(table, transaction_id, TransactionStatus.FAILED, error_summary=reason)
    return False
