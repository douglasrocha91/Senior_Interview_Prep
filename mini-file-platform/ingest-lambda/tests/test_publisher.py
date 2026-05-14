import json
from unittest.mock import MagicMock, patch

from shared.models.transaction import FileJob
from app.publisher import publish_file_job

_JOB = FileJob(
    transaction_id="01JXYZABCDEFGHIJKLMNOPQRST",
    bucket="mini-file-platform-inbound",
    key="inbox/acme/2026/05/13/01JXYZABCDEFGHIJKLMNOPQRST.csv.gpg",
    partner="acme",
    received_at="2026-05-13T00:00:00+00:00",
    schema_version="v1",
    attempt=0,
)
_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789/file-jobs"


@patch("app.publisher.boto3.client")
def test_publish_calls_send_message(mock_boto):
    mock_sqs = MagicMock()
    mock_sqs.send_message.return_value = {"MessageId": "msg-001"}
    mock_boto.return_value = mock_sqs

    publish_file_job(_QUEUE_URL, _JOB)

    mock_sqs.send_message.assert_called_once()


@patch("app.publisher.boto3.client")
def test_publish_sends_to_correct_queue(mock_boto):
    mock_sqs = MagicMock()
    mock_sqs.send_message.return_value = {"MessageId": "msg-001"}
    mock_boto.return_value = mock_sqs

    publish_file_job(_QUEUE_URL, _JOB)

    call_kwargs = mock_sqs.send_message.call_args.kwargs
    assert call_kwargs["QueueUrl"] == _QUEUE_URL


@patch("app.publisher.boto3.client")
def test_publish_body_is_valid_file_job(mock_boto):
    mock_sqs = MagicMock()
    mock_sqs.send_message.return_value = {"MessageId": "msg-001"}
    mock_boto.return_value = mock_sqs

    publish_file_job(_QUEUE_URL, _JOB)

    body = json.loads(mock_sqs.send_message.call_args.kwargs["MessageBody"])
    assert body["transaction_id"] == _JOB.transaction_id
    assert body["bucket"] == _JOB.bucket
    assert body["key"] == _JOB.key
    assert body["partner"] == _JOB.partner
    assert body["schema_version"] == _JOB.schema_version
    assert body["attempt"] == 0


@patch("app.publisher.boto3.client")
def test_publish_includes_partner_attribute(mock_boto):
    mock_sqs = MagicMock()
    mock_sqs.send_message.return_value = {"MessageId": "msg-001"}
    mock_boto.return_value = mock_sqs

    publish_file_job(_QUEUE_URL, _JOB)

    attrs = mock_sqs.send_message.call_args.kwargs["MessageAttributes"]
    assert "partner" in attrs
    assert attrs["partner"]["StringValue"] == "acme"


@patch("app.publisher.boto3.client")
def test_publish_returns_message_id(mock_boto):
    mock_sqs = MagicMock()
    mock_sqs.send_message.return_value = {"MessageId": "msg-abc"}
    mock_boto.return_value = mock_sqs

    result = publish_file_job(_QUEUE_URL, _JOB)
    assert result == "msg-abc"
