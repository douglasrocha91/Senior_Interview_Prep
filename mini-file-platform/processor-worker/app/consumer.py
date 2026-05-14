from __future__ import annotations

import json

import boto3

from shared.models.transaction import FileJob
from shared.utils.log_config import get_logger

from app.pipeline import process_job

log = get_logger(__name__)

_WAIT_SECONDS = 20  # SQS long-poll maximum
_MAX_MESSAGES = 1   # one at a time keeps the flow readable


def consume_one(queue_url: str) -> bool:
    """
    Long-poll SQS for one message.

    Returns True if a message was received (regardless of processing outcome).
    Returns False if the poll returned empty (caller can loop immediately).
    Deletes the message only when process_job returns True.
    """
    sqs = boto3.client("sqs")
    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=_MAX_MESSAGES,
        WaitTimeSeconds=_WAIT_SECONDS,
        MessageAttributeNames=["All"],
    )

    messages = response.get("Messages", [])
    if not messages:
        return False

    message = messages[0]
    receipt_handle = message["ReceiptHandle"]

    try:
        job = FileJob.from_dict(json.loads(message["Body"]))
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        log.error(
            "malformed SQS message body — leaving in queue for DLQ",
            extra={"error": str(exc)},
        )
        return True

    log.info(
        "received FileJob",
        extra={"transaction_id": job.transaction_id, "key": job.key},
    )

    success = process_job(job)

    if success:
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        log.info("SQS message deleted", extra={"transaction_id": job.transaction_id})
    else:
        log.warning(
            "job failed — message retained for retry",
            extra={"transaction_id": job.transaction_id},
        )

    return True
