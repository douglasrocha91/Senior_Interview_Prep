import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_TID = "01JXYZABCDEFGHIJKLMNOPQRST"
_TABLE = "transactions"
_RESULTS_BUCKET = "mini-file-platform-results"

_TRANSACTION = {
    "transaction_id": _TID,
    "partner": "acme",
    "source_bucket": "mini-file-platform-inbound",
    "source_key": f"inbox/acme/2026/05/13/{_TID}.csv.gpg",
    "status": "PROCESSED",
    "created_at": "2026-05-13T00:00:00Z",
    "updated_at": "2026-05-13T00:01:00Z",
    "attempt_count": 1,
    "result_prefix": f"results/{_TID}/",
    "error_summary": None,
}


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("DYNAMODB_TABLE_TRANSACTIONS", _TABLE)
    monkeypatch.setenv("S3_RESULTS_BUCKET", _RESULTS_BUCKET)


# ─── Health ───────────────────────────────────────────────────────────────────

def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ─── GET /transactions/{id} ───────────────────────────────────────────────────

@patch("app.main.get_transaction", return_value=_TRANSACTION)
def test_get_transaction_returns_record(mock_get):
    resp = client.get(f"/transactions/{_TID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["transaction_id"] == _TID
    assert data["status"] == "PROCESSED"
    assert data["partner"] == "acme"


@patch("app.main.get_transaction", return_value=_TRANSACTION)
def test_get_transaction_calls_store_with_table(mock_get):
    client.get(f"/transactions/{_TID}")
    mock_get.assert_called_once_with(_TABLE, _TID)


@patch("app.main.get_transaction", return_value=None)
def test_get_transaction_not_found_returns_404(mock_get):
    resp = client.get(f"/transactions/NOTEXIST")
    assert resp.status_code == 404


# ─── GET /transactions/{id}/errors ────────────────────────────────────────────

@patch("app.main.get_errors", return_value=[])
@patch("app.main.get_transaction", return_value=_TRANSACTION)
def test_get_errors_returns_empty_list_when_no_errors(mock_get, mock_errors):
    resp = client.get(f"/transactions/{_TID}/errors")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("app.main.get_errors", return_value=[
    {"transaction_id": _TID, "row_number": 2, "field": "amount", "code": "REQUIRED", "message": "required"},
])
@patch("app.main.get_transaction", return_value=_TRANSACTION)
def test_get_errors_returns_error_list(mock_get, mock_errors):
    resp = client.get(f"/transactions/{_TID}/errors")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["code"] == "REQUIRED"
    assert data[0]["field"] == "amount"


@patch("app.main.get_transaction", return_value=None)
def test_get_errors_not_found_returns_404(mock_get):
    resp = client.get(f"/transactions/NOTEXIST/errors")
    assert resp.status_code == 404


@patch("app.main.get_errors", return_value=[])
@patch("app.main.get_transaction", return_value={**_TRANSACTION, "result_prefix": None})
def test_get_errors_no_prefix_returns_empty(mock_get, mock_errors):
    resp = client.get(f"/transactions/{_TID}/errors")
    assert resp.status_code == 200
    assert resp.json() == []
    mock_errors.assert_not_called()


@patch("app.main.get_errors", return_value=[])
@patch("app.main.get_transaction", return_value=_TRANSACTION)
def test_get_errors_calls_correct_s3_key(mock_get, mock_errors):
    client.get(f"/transactions/{_TID}/errors")
    mock_errors.assert_called_once_with(
        _RESULTS_BUCKET,
        f"results/{_TID}/errors.jsonl",
    )
