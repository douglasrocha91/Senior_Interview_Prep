from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TransactionStatus(str, Enum):
    RECEIVED = "RECEIVED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


@dataclass
class Transaction:
    transaction_id: str
    partner: str
    source_bucket: str
    source_key: str
    status: TransactionStatus
    created_at: str
    updated_at: str
    attempt_count: int = 0
    result_prefix: Optional[str] = None
    error_summary: Optional[str] = None

    def to_dynamo_item(self) -> dict:
        item: dict = {
            "transaction_id": {"S": self.transaction_id},
            "partner": {"S": self.partner},
            "source_bucket": {"S": self.source_bucket},
            "source_key": {"S": self.source_key},
            "status": {"S": self.status.value},
            "created_at": {"S": self.created_at},
            "updated_at": {"S": self.updated_at},
            "attempt_count": {"N": str(self.attempt_count)},
        }
        if self.result_prefix is not None:
            item["result_prefix"] = {"S": self.result_prefix}
        if self.error_summary is not None:
            item["error_summary"] = {"S": self.error_summary}
        return item


@dataclass
class FileJob:
    transaction_id: str
    bucket: str
    key: str
    partner: str
    received_at: str
    schema_version: str
    attempt: int = 0

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "bucket": self.bucket,
            "key": self.key,
            "partner": self.partner,
            "received_at": self.received_at,
            "schema_version": self.schema_version,
            "attempt": self.attempt,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileJob":
        return cls(
            transaction_id=data["transaction_id"],
            bucket=data["bucket"],
            key=data["key"],
            partner=data["partner"],
            received_at=data["received_at"],
            schema_version=data["schema_version"],
            attempt=int(data.get("attempt", 0)),
        )


@dataclass
class ValidationError:
    transaction_id: str
    row_number: int
    field: str
    code: str
    message: str

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "row_number": self.row_number,
            "field": self.field,
            "code": self.code,
            "message": self.message,
        }
