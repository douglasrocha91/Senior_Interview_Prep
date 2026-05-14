import os
from unittest.mock import MagicMock, patch

import pytest

from app.handler import handler

_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789/file-jobs"
_BUCKET = "mini-file-platform-inbound"
_VALID_KEY = "inbox/acme/2026/05/13/01JXYZABCDEFGHIJKLMNOPQRST.csv.gpg"
_VALID_TID = "01JXYZABCDEFGHIJKLMNOPQRST"

_VALID_METADATA = {
    "transaction_id": _VALID_TID,
    "partner": "acme",
    "schema_version": "v1",
    "uploaded_at": "2026-05-13T00:00:00+00:00",
}


def _make_event(key: str = _VALID_KEY, bucket: str = _BUCKET) -> dict:
    return {
        "Records": [{
            "eventTime": "2026-05-13T00:00:00Z",
            "s3": {
                "bucket": {"name": bucket},
                "object": {"key": key, "size": 2048},
            },
        }]
    }


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("SQS_FILE_JOBS_URL", _QUEUE_URL)


def _mock_s3(metadata: dict = _VALID_METADATA) -> MagicMock:
    mock = MagicMock()
    mock.head_object.return_value = {"Metadata": metadata}
    return mock


def _mock_sqs() -> MagicMock:
    mock = MagicMock()
    mock.send_message.return_value = {"MessageId": "test-msg-id"}
    return mock


def _boto_factory(s3_mock: MagicMock, sqs_mock: MagicMock):
    """Dispatch boto3.client() calls to the right mock by service name.

    handler.py and publisher.py both import the same boto3 module, so patching
    per-module paths targets the same object and the second patch overwrites the
    first. A single patch("boto3.client") with side_effect avoids the collision.
    """
    def factory(service, **kwargs):
        return s3_mock if service == "s3" else sqs_mock
    return factory


# ─── Happy path ───────────────────────────────────────────────────────────────

@patch("boto3.client")
def test_happy_path_returns_processed_count(mock_boto):
    s3_mock = _mock_s3()
    sqs_mock = _mock_sqs()
    mock_boto.side_effect = _boto_factory(s3_mock, sqs_mock)

    result = handler(_make_event(), context=None)

    assert result == {"processed": 1, "skipped": 0}


@patch("boto3.client")
def test_happy_path_publishes_to_sqs(mock_boto):
    s3_mock = _mock_s3()
    sqs_mock = _mock_sqs()
    mock_boto.side_effect = _boto_factory(s3_mock, sqs_mock)

    handler(_make_event(), context=None)

    sqs_mock.send_message.assert_called_once()


# ─── Validation failures ──────────────────────────────────────────────────────

@patch("boto3.client")
def test_invalid_key_skips_record(mock_boto):
    s3_mock = _mock_s3()
    sqs_mock = _mock_sqs()
    mock_boto.side_effect = _boto_factory(s3_mock, sqs_mock)

    result = handler(_make_event(key="wrong/path/file.csv"), context=None)

    assert result == {"processed": 0, "skipped": 1}
    sqs_mock.send_message.assert_not_called()


@patch("boto3.client")
def test_missing_metadata_skips_record(mock_boto):
    incomplete_meta = {"partner": "acme"}  # missing transaction_id and schema_version
    s3_mock = _mock_s3(metadata=incomplete_meta)
    sqs_mock = _mock_sqs()
    mock_boto.side_effect = _boto_factory(s3_mock, sqs_mock)

    result = handler(_make_event(), context=None)

    assert result == {"processed": 0, "skipped": 1}
    sqs_mock.send_message.assert_not_called()


@patch("boto3.client")
def test_mismatched_transaction_id_skips_record(mock_boto):
    bad_meta = {**_VALID_METADATA, "transaction_id": "DIFFERENTTRANSACTIONIDVALUE"}
    s3_mock = _mock_s3(metadata=bad_meta)
    sqs_mock = _mock_sqs()
    mock_boto.side_effect = _boto_factory(s3_mock, sqs_mock)

    result = handler(_make_event(), context=None)

    assert result == {"processed": 0, "skipped": 1}


# ─── Multi-record batch ───────────────────────────────────────────────────────

@patch("boto3.client")
def test_mixed_batch_processes_valid_skips_invalid(mock_boto):
    s3_mock = _mock_s3()
    sqs_mock = _mock_sqs()
    mock_boto.side_effect = _boto_factory(s3_mock, sqs_mock)

    event = {
        "Records": [
            {
                "eventTime": "2026-05-13T00:00:00Z",
                "s3": {"bucket": {"name": _BUCKET}, "object": {"key": _VALID_KEY, "size": 1}},
            },
            {
                "eventTime": "2026-05-13T00:00:00Z",
                "s3": {"bucket": {"name": _BUCKET}, "object": {"key": "bad/key.txt", "size": 1}},
            },
        ]
    }

    result = handler(event, context=None)

    assert result["processed"] == 1
    assert result["skipped"] == 1


# ─── Unexpected errors ────────────────────────────────────────────────────────

@patch("boto3.client")
def test_unexpected_s3_error_skips_without_propagating(mock_boto):
    s3_mock = MagicMock()
    s3_mock.head_object.side_effect = RuntimeError("connection timeout")
    sqs_mock = _mock_sqs()
    mock_boto.side_effect = _boto_factory(s3_mock, sqs_mock)

    result = handler(_make_event(), context=None)

    assert result == {"processed": 0, "skipped": 1}
