import csv
from pathlib import Path

import pytest

from app.generator import generate_csv, _COLUMNS


def test_csv_has_correct_columns(tmp_path):
    output = tmp_path / "test.csv"
    generate_csv(output, rows=5, partner="acme")
    with open(output, newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == _COLUMNS


def test_csv_row_count(tmp_path):
    output = tmp_path / "test.csv"
    generate_csv(output, rows=10, partner="acme")
    with open(output, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 10


def test_record_ids_are_unique(tmp_path):
    output = tmp_path / "test.csv"
    generate_csv(output, rows=20, partner="acme")
    with open(output, newline="") as fh:
        ids = [row["record_id"] for row in csv.DictReader(fh)]
    assert len(ids) == len(set(ids))


def test_partner_prefix_in_record_id(tmp_path):
    output = tmp_path / "test.csv"
    generate_csv(output, rows=3, partner="globex")
    with open(output, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert all(r["record_id"].startswith("GLOBEX-") for r in rows)


def test_amounts_are_positive(tmp_path):
    output = tmp_path / "test.csv"
    generate_csv(output, rows=30, partner="acme")
    with open(output, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert all(float(r["amount"]) > 0 for r in rows)


def test_currency_length_is_three(tmp_path):
    output = tmp_path / "test.csv"
    generate_csv(output, rows=30, partner="acme")
    with open(output, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert all(len(r["currency"]) == 3 for r in rows)


def test_creates_parent_directories(tmp_path):
    output = tmp_path / "nested" / "dir" / "test.csv"
    generate_csv(output, rows=1, partner="acme")
    assert output.exists()


def test_returns_output_path(tmp_path):
    output = tmp_path / "test.csv"
    result = generate_csv(output, rows=1, partner="acme")
    assert result == output
