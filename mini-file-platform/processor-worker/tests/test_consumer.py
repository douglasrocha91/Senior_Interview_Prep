import json
from unittest.mock import MagicMock, patch

from shared.models.transaction import FileJob
from app.consumer import consume_one

_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789/file-jobs"
_RECEIPT = "AQEBabcdef..."
_TID = "01JXYZABCDEFGHIJKLMNOPQRST"


def _sqs_message(body: dict = None) -> dict:
    if body is None:
        body = {
            "transaction_id": _TID,
            "bucket": "mini-file-platform-inbound",
            "key": f"inbox/acme/2026/05/13/{_TID}.csv.gpg",
            "partner": "acme",
            "received_at": "2026-05-13T00:00:00Z",
            "schema_version": "v1",
            "attempt": 0,
        }
    return {"Body": json.dumps(body), "ReceiptHandle": _RECEIPT}


def _mock_sqs(messages: list = None) -> MagicMock:
    mock = MagicMock()
    mock.receive_message.return_value = {"Messages": messages or []}
    return mock


# ─── Empty poll ───────────────────────────────────────────────────────────────

@patch("app.consumer.process_job")
@patch("app.consumer.boto3.client")
def test_returns_false_when_queue_is_empty(mock_boto, mock_process):
    mock_boto.return_value = _mock_sqs([])

    assert consume_one(_QUEUE_URL) is False
    mock_process.assert_not_called()


# ─── Successful processing ────────────────────────────────────────────────────

@patch("app.consumer.process_job", return_value=True)
@patch("app.consumer.boto3.client")
def test_returns_true_when_message_received(mock_boto, mock_process):
    mock_boto.return_value = _mock_sqs([_sqs_message()])
    assert consume_one(_QUEUE_URL) is True


@patch("app.consumer.process_job", return_value=True)
@patch("app.consumer.boto3.client")
def test_deletes_message_after_success(mock_boto, mock_process):
    mock_sqs = _mock_sqs([_sqs_message()])
    mock_boto.return_value = mock_sqs

    consume_one(_QUEUE_URL)

    mock_sqs.delete_message.assert_called_once_with(
        QueueUrl=_QUEUE_URL, ReceiptHandle=_RECEIPT
    )


# ─── Failed processing ────────────────────────────────────────────────────────

@patch("app.consumer.process_job", return_value=False)
@patch("app.consumer.boto3.client")
def test_does_not_delete_message_on_failure(mock_boto, mock_process):
    mock_sqs = _mock_sqs([_sqs_message()])
    mock_boto.return_value = mock_sqs

    consume_one(_QUEUE_URL)

    mock_sqs.delete_message.assert_not_called()


# ─── Malformed message ────────────────────────────────────────────────────────

@patch("app.consumer.process_job")
@patch("app.consumer.boto3.client")
def test_malformed_json_body_does_not_crash(mock_boto, mock_process):
    bad_msg = {"Body": "not-json", "ReceiptHandle": _RECEIPT}
    mock_boto.return_value = _mock_sqs([bad_msg])

    result = consume_one(_QUEUE_URL)

    assert result is True
    mock_process.assert_not_called()
    mock_boto.return_value.delete_message.assert_not_called()


@patch("app.consumer.process_job")
@patch("app.consumer.boto3.client")
def test_missing_required_field_does_not_crash(mock_boto, mock_process):
    bad_body = {"transaction_id": _TID}  # missing bucket, key, etc.
    mock_boto.return_value = _mock_sqs([_sqs_message(bad_body)])

    result = consume_one(_QUEUE_URL)

    assert result is True
    mock_process.assert_not_called()


# ─── SQS long-poll ───────────────────────────────────────────────────────────

@patch("app.consumer.process_job", return_value=False)
@patch("app.consumer.boto3.client")
def test_uses_long_poll_wait_time(mock_boto, mock_process):
    mock_sqs = _mock_sqs([])
    mock_boto.return_value = mock_sqs

    consume_one(_QUEUE_URL)

    kwargs = mock_sqs.receive_message.call_args.kwargs
    assert kwargs.get("WaitTimeSeconds", 0) > 0
