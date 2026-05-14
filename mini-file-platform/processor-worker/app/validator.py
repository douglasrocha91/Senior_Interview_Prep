from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Tuple

from shared.models.transaction import ValidationError
from shared.utils.log_config import get_logger

log = get_logger(__name__)

_REQUIRED_COLUMNS = {"record_id", "expense_date", "employee_id", "currency", "amount"}
_MAX_DESCRIPTION_LEN = 200


def validate_csv(
    path: Path, transaction_id: str
) -> Tuple[List[dict], List[ValidationError]]:
    """Parse CSV and validate each row. Returns (valid_rows, errors)."""
    rows: List[dict] = []
    errors: List[ValidationError] = []
    seen_record_ids: set[str] = set()

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError("CSV file has no headers")

        missing_cols = _REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing_cols:
            raise ValueError(f"CSV missing required columns: {sorted(missing_cols)}")

        for row_num, row in enumerate(reader, start=2):  # row 1 = header
            row_errors = _validate_row(row, row_num, transaction_id, seen_record_ids)
            errors.extend(row_errors)
            if not row_errors:
                rows.append(dict(row))

    log.info(
        "CSV validated",
        extra={"path": str(path), "valid_rows": len(rows), "errors": len(errors)},
    )
    return rows, errors


def _validate_row(
    row: dict,
    row_num: int,
    transaction_id: str,
    seen_ids: set[str],
) -> List[ValidationError]:
    errors: List[ValidationError] = []

    def err(field: str, code: str, message: str) -> ValidationError:
        return ValidationError(
            transaction_id=transaction_id,
            row_number=row_num,
            field=field,
            code=code,
            message=message,
        )

    # record_id — required and unique
    record_id = (row.get("record_id") or "").strip()
    if not record_id:
        errors.append(err("record_id", "REQUIRED", "record_id is required"))
    elif record_id in seen_ids:
        errors.append(err("record_id", "DUPLICATE", f"Duplicate record_id: {record_id!r}"))
    else:
        seen_ids.add(record_id)

    # expense_date — required, valid ISO date
    expense_date = (row.get("expense_date") or "").strip()
    if not expense_date:
        errors.append(err("expense_date", "REQUIRED", "expense_date is required"))
    else:
        try:
            date.fromisoformat(expense_date)
        except ValueError:
            errors.append(
                err("expense_date", "INVALID_DATE", f"Not a valid date: {expense_date!r}")
            )

    # employee_id — required
    if not (row.get("employee_id") or "").strip():
        errors.append(err("employee_id", "REQUIRED", "employee_id is required"))

    # currency — required, exactly 3 characters
    currency = (row.get("currency") or "").strip()
    if not currency:
        errors.append(err("currency", "REQUIRED", "currency is required"))
    elif len(currency) != 3:
        errors.append(
            err("currency", "INVALID_LENGTH", f"currency must be 3 characters, got: {currency!r}")
        )

    # amount — required, numeric, > 0
    amount_raw = (row.get("amount") or "").strip()
    if not amount_raw:
        errors.append(err("amount", "REQUIRED", "amount is required"))
    else:
        try:
            amount = Decimal(amount_raw)
            if amount <= 0:
                errors.append(
                    err("amount", "INVALID_AMOUNT", f"amount must be > 0, got: {amount}")
                )
        except InvalidOperation:
            errors.append(
                err("amount", "INVALID_AMOUNT", f"amount must be numeric, got: {amount_raw!r}")
            )

    # description — optional, length-limited
    description = row.get("description") or ""
    if len(description) > _MAX_DESCRIPTION_LEN:
        errors.append(
            err(
                "description",
                "INVALID_LENGTH",
                f"description exceeds {_MAX_DESCRIPTION_LEN} characters",
            )
        )

    return errors
