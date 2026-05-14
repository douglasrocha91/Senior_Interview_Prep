from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class S3Record:
    bucket: str
    key: str
    size: int
    event_time: str


def parse_records(event: dict[str, Any]) -> list[S3Record]:
    """Extract S3 records from a Lambda S3 event payload."""
    records = []
    for raw in event.get("Records", []):
        s3 = raw.get("s3", {})
        records.append(S3Record(
            bucket=s3["bucket"]["name"],
            key=s3["object"]["key"],
            size=s3["object"].get("size", 0),
            event_time=raw.get("eventTime", ""),
        ))
    return records
