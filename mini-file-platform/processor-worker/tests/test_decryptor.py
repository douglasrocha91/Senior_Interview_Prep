from unittest.mock import MagicMock, patch

import pytest

from app.decryptor import decrypt_file


@patch("app.decryptor.gnupg.GPG")
def test_decrypt_calls_gpg_decrypt_file(mock_gpg_cls, tmp_path):
    mock_gpg = MagicMock()
    mock_gpg.decrypt_file.return_value = MagicMock(ok=True)
    mock_gpg_cls.return_value = mock_gpg

    src = tmp_path / "file.csv.gpg"
    src.write_bytes(b"encrypted")

    decrypt_file(src, tmp_path / "file.csv")

    mock_gpg.decrypt_file.assert_called_once()


@patch("app.decryptor.gnupg.GPG")
def test_decrypt_raises_on_failure(mock_gpg_cls, tmp_path):
    mock_gpg = MagicMock()
    mock_gpg.decrypt_file.return_value = MagicMock(ok=False, status="bad key", stderr="no key")
    mock_gpg_cls.return_value = mock_gpg

    src = tmp_path / "file.csv.gpg"
    src.write_bytes(b"bad")

    with pytest.raises(RuntimeError, match="GPG decryption failed"):
        decrypt_file(src, tmp_path / "file.csv")


@patch("app.decryptor.gnupg.GPG")
def test_decrypt_uses_gpg_home_from_env(mock_gpg_cls, tmp_path, monkeypatch):
    monkeypatch.setenv("GPG_HOME", "/custom/gpg")
    mock_gpg = MagicMock()
    mock_gpg.decrypt_file.return_value = MagicMock(ok=True)
    mock_gpg_cls.return_value = mock_gpg

    src = tmp_path / "file.csv.gpg"
    src.write_bytes(b"data")

    decrypt_file(src, tmp_path / "file.csv")

    mock_gpg_cls.assert_called_once_with(gnupghome="/custom/gpg")


@patch("app.decryptor.gnupg.GPG")
def test_decrypt_passes_output_path(mock_gpg_cls, tmp_path):
    mock_gpg = MagicMock()
    mock_gpg.decrypt_file.return_value = MagicMock(ok=True)
    mock_gpg_cls.return_value = mock_gpg

    src = tmp_path / "file.csv.gpg"
    src.write_bytes(b"data")
    dest = tmp_path / "file.csv"

    decrypt_file(src, dest)

    call_kwargs = mock_gpg.decrypt_file.call_args.kwargs
    assert call_kwargs["output"] == str(dest)
    assert call_kwargs["always_trust"] is True
