from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.downloader import download_file

_BUCKET = "mini-file-platform-inbound"
_KEY = "inbox/acme/2026/05/13/01JXYZABCDEFGHIJKLMNOPQRST.csv.gpg"


@patch("app.downloader.boto3.client")
def test_download_calls_s3_download_file(mock_boto, tmp_path):
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3
    dest = tmp_path / "file.csv.gpg"

    download_file(_BUCKET, _KEY, dest)

    mock_s3.download_file.assert_called_once_with(_BUCKET, _KEY, str(dest))


@patch("app.downloader.boto3.client")
def test_download_propagates_s3_errors(mock_boto, tmp_path):
    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = RuntimeError("NoSuchKey")
    mock_boto.return_value = mock_s3

    with pytest.raises(RuntimeError, match="NoSuchKey"):
        download_file(_BUCKET, _KEY, tmp_path / "file.csv.gpg")
