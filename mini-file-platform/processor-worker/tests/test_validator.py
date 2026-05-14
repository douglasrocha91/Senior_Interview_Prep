import csv
from pathlib import Path

import pytest

from app.validator import validate_csv

_TID = "01JXYZABCDEFGHIJKLMNOPQRST"

_VALID_ROW = {
    "record_id": "ACME-00001",
    "expense_date": "2026-05-13",
    "employee_id": "EMP-1234",
    "currency": "USD",
    "amount": "42.50",
    "description": "Business lunch",
}


def _write_csv(tmp_path: Path, rows: list, fieldnames: list = None) -> Path:
    if fieldnames is None:
        fieldnames = list(_VALID_ROW.keys())
    path = tmp_path / "test.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


# ─── Happy path ───────────────────────────────────────────────────────────────

def test_valid_row_returns_no_errors(tmp_path):
    path = _write_csv(tmp_path, [_VALID_ROW])
    rows, errors = validate_csv(path, _TID)
    assert len(rows) == 1
    assert len(errors) == 0


def test_multiple_valid_rows(tmp_path):
    data = [{**_VALID_ROW, "record_id": f"ACME-{i:05d}"} for i in range(1, 6)]
    path = _write_csv(tmp_path, data)
    rows, errors = validate_csv(path, _TID)
    assert len(rows) == 5
    assert errors == []


# ─── record_id ────────────────────────────────────────────────────────────────

def test_missing_record_id_produces_required_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "record_id": ""}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "record_id" and e.code == "REQUIRED" for e in errors)


def test_duplicate_record_id_produces_error(tmp_path):
    path = _write_csv(tmp_path, [_VALID_ROW, _VALID_ROW])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "record_id" and e.code == "DUPLICATE" for e in errors)


# ─── expense_date ─────────────────────────────────────────────────────────────

def test_missing_expense_date_produces_required_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "expense_date": ""}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "expense_date" and e.code == "REQUIRED" for e in errors)


def test_invalid_expense_date_produces_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "expense_date": "not-a-date"}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "expense_date" and e.code == "INVALID_DATE" for e in errors)


# ─── employee_id ──────────────────────────────────────────────────────────────

def test_missing_employee_id_produces_required_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "employee_id": ""}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "employee_id" and e.code == "REQUIRED" for e in errors)


# ─── currency ─────────────────────────────────────────────────────────────────

def test_missing_currency_produces_required_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "currency": ""}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "currency" and e.code == "REQUIRED" for e in errors)


def test_currency_wrong_length_produces_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "currency": "US"}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "currency" and e.code == "INVALID_LENGTH" for e in errors)


# ─── amount ───────────────────────────────────────────────────────────────────

def test_missing_amount_produces_required_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "amount": ""}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "amount" and e.code == "REQUIRED" for e in errors)


def test_zero_amount_produces_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "amount": "0"}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "amount" and e.code == "INVALID_AMOUNT" for e in errors)


def test_negative_amount_produces_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "amount": "-5.00"}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "amount" and e.code == "INVALID_AMOUNT" for e in errors)


def test_non_numeric_amount_produces_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "amount": "abc"}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "amount" and e.code == "INVALID_AMOUNT" for e in errors)


# ─── description ──────────────────────────────────────────────────────────────

def test_description_too_long_produces_error(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "description": "x" * 201}])
    _, errors = validate_csv(path, _TID)
    assert any(e.field == "description" and e.code == "INVALID_LENGTH" for e in errors)


def test_empty_description_is_valid(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "description": ""}])
    rows, errors = validate_csv(path, _TID)
    assert len(rows) == 1
    assert errors == []


# ─── Structural errors ────────────────────────────────────────────────────────

def test_missing_required_column_raises(tmp_path):
    path = _write_csv(tmp_path, [{"record_id": "X"}], fieldnames=["record_id"])
    with pytest.raises(ValueError, match="missing required columns"):
        validate_csv(path, _TID)


def test_error_transaction_id_matches(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "record_id": ""}])
    _, errors = validate_csv(path, _TID)
    assert all(e.transaction_id == _TID for e in errors)


def test_error_row_number_is_correct(tmp_path):
    path = _write_csv(tmp_path, [{**_VALID_ROW, "record_id": ""}])
    _, errors = validate_csv(path, _TID)
    # Row 1 = header, so first data row = 2
    assert errors[0].row_number == 2
