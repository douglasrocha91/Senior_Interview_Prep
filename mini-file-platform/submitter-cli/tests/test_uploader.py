import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.uploader import build_s3_key, upload_encrypted_file

_KEY_PATTERN = re.compile(
    r"^inbox/[^/]+/\d{4}/\d{2}/\d{2}/[A-Z0-9]{26}\.csv\.gpg$"
)


def test_build_s3_key_format():
    key = build_s3_key(partner="acme", transaction_id="01JXYZABCDEFGHIJKLMNOPQRST")
    assert _KEY_PATTERN.match(key), f"Unexpected key format: {key}"


def test_build_s3_key_partner_in_path():
    key = build_s3_key(partner="globex", transaction_id="01JXYZABCDEFGHIJKLMNOPQRST")
    assert key.startswith("inbox/globex/")


def test_build_s3_key_ends_with_transaction_id():
    tid = "01JXYZABCDEFGHIJKLMNOPQRST"
    key = build_s3_key(partner="acme", transaction_id=tid)
    assert key.endswith(f"/{tid}.csv.gpg")


@patch("app.uploader.boto3.client")
def test_upload_calls_s3_upload_file(mock_boto_client, tmp_path):
    encrypted = tmp_path / "expenses.csv.gpg"
    encrypted.write_bytes(b"gpg-data")

    mock_s3 = MagicMock()
    mock_boto_client.return_value = mock_s3

    key = upload_encrypted_file(encrypted, "my-bucket", "acme", "TXN-001")

    mock_s3.upload_file.assert_called_once()
    call_args = mock_s3.upload_file.call_args
    assert call_args.args[1] == "my-bucket"  # bucket
    assert call_args.args[2] == key           # s3 key


@patch("app.uploader.boto3.client")
def test_upload_attaches_metadata(mock_boto_client, tmp_path):
    encrypted = tmp_path / "expenses.csv.gpg"
    encrypted.write_bytes(b"gpg-data")

    mock_s3 = MagicMock()
    mock_boto_client.return_value = mock_s3

    upload_encrypted_file(encrypted, "my-bucket", "acme", "TXN-001", schema_version="v2")

    extra_args = mock_s3.upload_file.call_args.kwargs["ExtraArgs"]
    metadata = extra_args["Metadata"]
    assert metadata["transaction_id"] == "TXN-001"
    assert metadata["partner"] == "acme"
    assert metadata["schema_version"] == "v2"
    assert "uploaded_at" in metadata


@patch("app.uploader.boto3.client")
def test_upload_returns_s3_key(mock_boto_client, tmp_path):
    encrypted = tmp_path / "expenses.csv.gpg"
    encrypted.write_bytes(b"gpg-data")
    mock_boto_client.return_value = MagicMock()

    key = upload_encrypted_file(encrypted, "my-bucket", "acme", "TXN-001")
    assert key.startswith("inbox/acme/")
    assert key.endswith(".csv.gpg")
