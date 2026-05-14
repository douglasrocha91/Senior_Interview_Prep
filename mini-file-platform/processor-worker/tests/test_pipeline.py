from unittest.mock import patch

import pytest

from shared.models.transaction import FileJob, TransactionStatus, ValidationError
from app.pipeline import process_job

_TID = "01JXYZABCDEFGHIJKLMNOPQRST"
_TABLE = "transactions"
_RESULTS_BUCKET = "mini-file-platform-results"

_PATCHES = [
    "app.pipeline.download_file",
    "app.pipeline.decrypt_file",
    "app.pipeline.validate_csv",
    "app.pipeline.upsert_transaction",
    "app.pipeline.update_status",
    "app.pipeline.write_results",
    "app.pipeline.write_errors",
]


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


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("DYNAMODB_TABLE_TRANSACTIONS", _TABLE)
    monkeypatch.setenv("S3_RESULTS_BUCKET", _RESULTS_BUCKET)


def _patch_all(**overrides):
    """Return a context manager that patches all pipeline sub-functions."""
    defaults = {
        "app.pipeline.download_file": None,
        "app.pipeline.decrypt_file": None,
        "app.pipeline.validate_csv": ([{"record_id": "X"}], []),
        "app.pipeline.upsert_transaction": None,
        "app.pipeline.update_status": None,
        "app.pipeline.write_results": None,
        "app.pipeline.write_errors": None,
    }
    defaults.update(overrides)
    return defaults


# ─── Happy path ───────────────────────────────────────────────────────────────

def test_happy_path_returns_true(file_job):
    with patch("app.pipeline.download_file"), \
         patch("app.pipeline.decrypt_file"), \
         patch("app.pipeline.validate_csv", return_value=([{"record_id": "X"}], [])), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status"), \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors"):
        assert process_job(file_job) is True


def test_happy_path_marks_processed(file_job):
    with patch("app.pipeline.download_file"), \
         patch("app.pipeline.decrypt_file"), \
         patch("app.pipeline.validate_csv", return_value=([{"record_id": "X"}], [])), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status") as mock_update, \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors"):
        process_job(file_job)
        mock_update.assert_called_once_with(_TABLE, _TID, TransactionStatus.PROCESSED)


def test_happy_path_upserts_processing_first(file_job):
    with patch("app.pipeline.download_file"), \
         patch("app.pipeline.decrypt_file"), \
         patch("app.pipeline.validate_csv", return_value=([{"record_id": "X"}], [])), \
         patch("app.pipeline.upsert_transaction") as mock_upsert, \
         patch("app.pipeline.update_status"), \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors"):
        process_job(file_job)
        mock_upsert.assert_called_once_with(
            table=_TABLE,
            job=file_job,
            status=TransactionStatus.PROCESSING,
            result_prefix=f"results/{_TID}/",
        )


def test_happy_path_writes_results(file_job):
    rows = [{"record_id": "X"}]
    with patch("app.pipeline.download_file"), \
         patch("app.pipeline.decrypt_file"), \
         patch("app.pipeline.validate_csv", return_value=(rows, [])), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status"), \
         patch("app.pipeline.write_results") as mock_write, \
         patch("app.pipeline.write_errors"):
        process_job(file_job)
        mock_write.assert_called_once()


# ─── Validation errors ────────────────────────────────────────────────────────

def test_validation_errors_still_returns_true(file_job):
    err = ValidationError(_TID, 2, "amount", "REQUIRED", "required")
    with patch("app.pipeline.download_file"), \
         patch("app.pipeline.decrypt_file"), \
         patch("app.pipeline.validate_csv", return_value=([], [err])), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status"), \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors"):
        assert process_job(file_job) is True


def test_validation_errors_marks_processed_with_summary(file_job):
    err = ValidationError(_TID, 2, "amount", "REQUIRED", "required")
    with patch("app.pipeline.download_file"), \
         patch("app.pipeline.decrypt_file"), \
         patch("app.pipeline.validate_csv", return_value=([], [err])), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status") as mock_update, \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors"):
        process_job(file_job)
        mock_update.assert_called_once_with(
            _TABLE, _TID, TransactionStatus.PROCESSED, error_summary="1 validation error(s)"
        )


def test_validation_errors_writes_error_file(file_job):
    err = ValidationError(_TID, 2, "amount", "REQUIRED", "required")
    with patch("app.pipeline.download_file"), \
         patch("app.pipeline.decrypt_file"), \
         patch("app.pipeline.validate_csv", return_value=([], [err])), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status"), \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors") as mock_write_errors:
        process_job(file_job)
        mock_write_errors.assert_called_once()


# ─── Infrastructure failures ──────────────────────────────────────────────────

def test_download_failure_returns_false(file_job):
    with patch("app.pipeline.download_file", side_effect=RuntimeError("NoSuchKey")), \
         patch("app.pipeline.decrypt_file"), \
         patch("app.pipeline.validate_csv"), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status"), \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors"):
        assert process_job(file_job) is False


def test_download_failure_marks_failed(file_job):
    with patch("app.pipeline.download_file", side_effect=RuntimeError("NoSuchKey")), \
         patch("app.pipeline.decrypt_file"), \
         patch("app.pipeline.validate_csv"), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status") as mock_update, \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors"):
        process_job(file_job)
        assert mock_update.call_args.args[2] == TransactionStatus.FAILED


def test_decrypt_failure_returns_false(file_job):
    with patch("app.pipeline.download_file"), \
         patch("app.pipeline.decrypt_file", side_effect=RuntimeError("bad key")), \
         patch("app.pipeline.validate_csv"), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status"), \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors"):
        assert process_job(file_job) is False


def test_decrypt_failure_marks_failed(file_job):
    with patch("app.pipeline.download_file"), \
         patch("app.pipeline.decrypt_file", side_effect=RuntimeError("bad key")), \
         patch("app.pipeline.validate_csv"), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status") as mock_update, \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors"):
        process_job(file_job)
        assert mock_update.call_args.args[2] == TransactionStatus.FAILED


def test_csv_parse_failure_returns_false(file_job):
    with patch("app.pipeline.download_file"), \
         patch("app.pipeline.decrypt_file"), \
         patch("app.pipeline.validate_csv", side_effect=ValueError("missing columns")), \
         patch("app.pipeline.upsert_transaction"), \
         patch("app.pipeline.update_status"), \
         patch("app.pipeline.write_results"), \
         patch("app.pipeline.write_errors"):
        assert process_job(file_job) is False
