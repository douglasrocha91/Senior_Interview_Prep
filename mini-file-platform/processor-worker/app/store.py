from __future__ import annotations

import os
from typing import Optional

import boto3

from shared.models.transaction import FileJob, Transaction, TransactionStatus
from shared.utils.log_config import get_logger
from shared.utils.timestamps import utc_now_iso

log = get_logger(__name__)


def _dynamo():
    endpoint = os.environ.get("DYNAMODB_ENDPOINT_URL")
    return boto3.client("dynamodb", endpoint_url=endpoint)


def upsert_transaction(
    table: str,
    job: FileJob,
    status: TransactionStatus,
    result_prefix: str,
) -> None:
    """Write (or overwrite) a transaction record, incrementing attempt_count."""
    now = utc_now_iso()
    txn = Transaction(
        transaction_id=job.transaction_id,
        partner=job.partner,
        source_bucket=job.bucket,
        source_key=job.key,
        status=status,
        created_at=now,
        updated_at=now,
        attempt_count=job.attempt + 1,
        result_prefix=result_prefix,
    )
    _dynamo().put_item(TableName=table, Item=txn.to_dynamo_item())
    log.info(
        "transaction upserted",
        extra={"transaction_id": job.transaction_id, "status": status.value},
    )


def update_status(
    table: str,
    transaction_id: str,
    status: TransactionStatus,
    error_summary: Optional[str] = None,
) -> None:
    """Update status and updated_at on an existing transaction record."""
    expr = "SET #s = :s, updated_at = :u"
    names = {"#s": "status"}
    values: dict = {
        ":s": {"S": status.value},
        ":u": {"S": utc_now_iso()},
    }

    if error_summary is not None:
        expr += ", error_summary = :e"
        values[":e"] = {"S": error_summary}

    _dynamo().update_item(
        TableName=table,
        Key={"transaction_id": {"S": transaction_id}},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    log.info(
        "transaction status updated",
        extra={"transaction_id": transaction_id, "status": status.value},
    )
