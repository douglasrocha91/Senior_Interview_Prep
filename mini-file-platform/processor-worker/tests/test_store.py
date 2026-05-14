from unittest.mock import MagicMock, patch

import pytest

from shared.models.transaction import FileJob, TransactionStatus
from app.store import update_status, upsert_transaction

_TID = "01JXYZABCDEFGHIJKLMNOPQRST"
_TABLE = "transactions"


@pytest.fixture
def file_job():
    return FileJob(
        transaction_id=_TID,
        bucket="mini-file-platform-inbound",
        key="inbox/acme/2026/05/13/01JXYZABCDEFGHIJKLMNOPQRST.csv.gpg",
        partner="acme",
        received_at="2026-05-13T00:00:00Z",
        schema_version="v1",
        attempt=0,
    )


# ─── upsert_transaction ───────────────────────────────────────────────────────

@patch("app.store.boto3.client")
def test_upsert_calls_put_item(mock_boto, file_job):
    mock_dynamo = MagicMock()
    mock_boto.return_value = mock_dynamo

    upsert_transaction(_TABLE, file_job, TransactionStatus.PROCESSING, "results/TID/")

    mock_dynamo.put_item.assert_called_once()


@patch("app.store.boto3.client")
def test_upsert_sets_correct_status(mock_boto, file_job):
    mock_dynamo = MagicMock()
    mock_boto.return_value = mock_dynamo

    upsert_transaction(_TABLE, file_job, TransactionStatus.PROCESSING, "results/TID/")

    item = mock_dynamo.put_item.call_args.kwargs["Item"]
    assert item["status"]["S"] == "PROCESSING"


@patch("app.store.boto3.client")
def test_upsert_increments_attempt_count(mock_boto, file_job):
    mock_dynamo = MagicMock()
    mock_boto.return_value = mock_dynamo
    file_job.attempt = 2

    upsert_transaction(_TABLE, file_job, TransactionStatus.PROCESSING, "results/TID/")

    item = mock_dynamo.put_item.call_args.kwargs["Item"]
    assert item["attempt_count"]["N"] == "3"


@patch("app.store.boto3.client")
def test_upsert_sets_result_prefix(mock_boto, file_job):
    mock_dynamo = MagicMock()
    mock_boto.return_value = mock_dynamo

    upsert_transaction(_TABLE, file_job, TransactionStatus.PROCESSING, "results/TID/")

    item = mock_dynamo.put_item.call_args.kwargs["Item"]
    assert item["result_prefix"]["S"] == "results/TID/"


# ─── update_status ────────────────────────────────────────────────────────────

@patch("app.store.boto3.client")
def test_update_status_calls_update_item(mock_boto):
    mock_dynamo = MagicMock()
    mock_boto.return_value = mock_dynamo

    update_status(_TABLE, _TID, TransactionStatus.PROCESSED)

    mock_dynamo.update_item.assert_called_once()


@patch("app.store.boto3.client")
def test_update_status_sets_correct_status_value(mock_boto):
    mock_dynamo = MagicMock()
    mock_boto.return_value = mock_dynamo

    update_status(_TABLE, _TID, TransactionStatus.FAILED)

    values = mock_dynamo.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":s"]["S"] == "FAILED"


@patch("app.store.boto3.client")
def test_update_status_includes_error_summary(mock_boto):
    mock_dynamo = MagicMock()
    mock_boto.return_value = mock_dynamo

    update_status(_TABLE, _TID, TransactionStatus.FAILED, error_summary="Download failed: timeout")

    values = mock_dynamo.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":e"]["S"] == "Download failed: timeout"


@patch("app.store.boto3.client")
def test_update_status_no_error_summary_omits_field(mock_boto):
    mock_dynamo = MagicMock()
    mock_boto.return_value = mock_dynamo

    update_status(_TABLE, _TID, TransactionStatus.PROCESSED)

    values = mock_dynamo.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert ":e" not in values


@patch("app.store.boto3.client")
def test_update_status_uses_dynamo_endpoint_from_env(mock_boto, monkeypatch):
    monkeypatch.setenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8000")
    mock_dynamo = MagicMock()
    mock_boto.return_value = mock_dynamo

    update_status(_TABLE, _TID, TransactionStatus.PROCESSED)

    mock_boto.assert_called_with("dynamodb", endpoint_url="http://localhost:8000")
