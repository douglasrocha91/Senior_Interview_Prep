from unittest.mock import MagicMock, patch

from shared.models.transaction import ValidationError
from app.result_writer import write_errors, write_results

_BUCKET = "mini-file-platform-results"
_PREFIX = "results/01JXYZABCDEFGHIJKLMNOPQRST/"
_TID = "01JXYZABCDEFGHIJKLMNOPQRST"


# ─── write_results ────────────────────────────────────────────────────────────

@patch("app.result_writer.boto3.client")
def test_write_results_calls_put_object(mock_boto):
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3

    write_results(_BUCKET, _PREFIX, [{"record_id": "X", "amount": "10.00"}])

    mock_s3.put_object.assert_called_once()


@patch("app.result_writer.boto3.client")
def test_write_results_uses_correct_key(mock_boto):
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3

    write_results(_BUCKET, _PREFIX, [{"record_id": "X"}])

    kwargs = mock_s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == _BUCKET
    assert kwargs["Key"] == f"{_PREFIX}output.csv"


@patch("app.result_writer.boto3.client")
def test_write_results_body_contains_header(mock_boto):
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3

    write_results(_BUCKET, _PREFIX, [{"record_id": "X-001", "amount": "5.00"}])

    body = mock_s3.put_object.call_args.kwargs["Body"].decode("utf-8")
    assert "record_id" in body
    assert "X-001" in body


@patch("app.result_writer.boto3.client")
def test_write_results_skips_when_empty(mock_boto):
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3

    write_results(_BUCKET, _PREFIX, [])

    mock_s3.put_object.assert_not_called()


# ─── write_errors ─────────────────────────────────────────────────────────────

@patch("app.result_writer.boto3.client")
def test_write_errors_calls_put_object(mock_boto):
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3

    write_errors(_BUCKET, _PREFIX, [ValidationError(_TID, 2, "amount", "REQUIRED", "required")])

    mock_s3.put_object.assert_called_once()


@patch("app.result_writer.boto3.client")
def test_write_errors_uses_jsonl_key(mock_boto):
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3

    write_errors(_BUCKET, _PREFIX, [ValidationError(_TID, 2, "amount", "REQUIRED", "required")])

    kwargs = mock_s3.put_object.call_args.kwargs
    assert kwargs["Key"] == f"{_PREFIX}errors.jsonl"


@patch("app.result_writer.boto3.client")
def test_write_errors_body_is_valid_jsonl(mock_boto):
    import json
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3
    error = ValidationError(_TID, 2, "amount", "REQUIRED", "amount is required")

    write_errors(_BUCKET, _PREFIX, [error])

    body = mock_s3.put_object.call_args.kwargs["Body"].decode("utf-8")
    parsed = json.loads(body)
    assert parsed["field"] == "amount"
    assert parsed["code"] == "REQUIRED"


@patch("app.result_writer.boto3.client")
def test_write_errors_skips_when_empty(mock_boto):
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3

    write_errors(_BUCKET, _PREFIX, [])

    mock_s3.put_object.assert_not_called()
