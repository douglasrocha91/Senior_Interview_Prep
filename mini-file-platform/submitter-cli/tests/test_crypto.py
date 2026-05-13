from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.crypto import encrypt_file


def _make_gpg_result(ok: bool, stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.ok = ok
    result.stderr = stderr
    return result


@patch("app.crypto.gnupg.GPG")
def test_encrypt_file_returns_gpg_path(mock_gpg_class, tmp_path):
    input_file = tmp_path / "expenses.csv"
    input_file.write_text("record_id,amount\n001,99.00\n")

    mock_gpg = MagicMock()
    mock_gpg_class.return_value = mock_gpg
    mock_gpg.encrypt_file.return_value = _make_gpg_result(ok=True)

    # Create the expected output so the path exists
    expected = tmp_path / "expenses.csv.gpg"
    expected.write_bytes(b"encrypted")

    result = encrypt_file(input_file, "test@example.com")
    assert result == expected


@patch("app.crypto.gnupg.GPG")
def test_encrypt_file_uses_correct_recipient(mock_gpg_class, tmp_path):
    input_file = tmp_path / "expenses.csv"
    input_file.write_text("data")

    mock_gpg = MagicMock()
    mock_gpg_class.return_value = mock_gpg
    mock_gpg.encrypt_file.return_value = _make_gpg_result(ok=True)

    (tmp_path / "expenses.csv.gpg").write_bytes(b"enc")
    encrypt_file(input_file, "partner@acme.com")

    call_kwargs = mock_gpg.encrypt_file.call_args
    assert "partner@acme.com" in call_kwargs.kwargs.get("recipients", call_kwargs.args[1] if len(call_kwargs.args) > 1 else [])


@patch("app.crypto.gnupg.GPG")
def test_encrypt_file_raises_on_failure(mock_gpg_class, tmp_path):
    input_file = tmp_path / "expenses.csv"
    input_file.write_text("data")

    mock_gpg = MagicMock()
    mock_gpg_class.return_value = mock_gpg
    mock_gpg.encrypt_file.return_value = _make_gpg_result(ok=False, stderr="key not found")

    with pytest.raises(RuntimeError, match="GPG encryption failed"):
        encrypt_file(input_file, "nobody@example.com")


@patch("app.crypto.gnupg.GPG")
def test_encrypt_file_passes_gpg_home(mock_gpg_class, tmp_path):
    input_file = tmp_path / "expenses.csv"
    input_file.write_text("data")
    (tmp_path / "expenses.csv.gpg").write_bytes(b"enc")

    mock_gpg = MagicMock()
    mock_gpg_class.return_value = mock_gpg
    mock_gpg.encrypt_file.return_value = _make_gpg_result(ok=True)

    encrypt_file(input_file, "test@example.com", gpg_home="/custom/.gnupg")
    mock_gpg_class.assert_called_once_with(gnupghome="/custom/.gnupg")
