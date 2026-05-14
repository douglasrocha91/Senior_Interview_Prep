import pytest

from app.validator import IngestError, validate_key, validate_metadata

_VALID_KEY = "inbox/acme/2026/05/13/01JXYZABCDEFGHIJKLMNOPQRST.csv.gpg"
_VALID_TID = "01JXYZABCDEFGHIJKLMNOPQRST"
_VALID_META = {
    "transaction_id": _VALID_TID,
    "partner": "acme",
    "schema_version": "v1",
}


# ─── validate_key ─────────────────────────────────────────────────────────────

def test_valid_key_passes():
    match = validate_key(_VALID_KEY)
    assert match is not None


def test_valid_key_extracts_partner():
    match = validate_key(_VALID_KEY)
    assert match.group("partner") == "acme"


def test_valid_key_extracts_transaction_id():
    match = validate_key(_VALID_KEY)
    assert match.group("transaction_id") == _VALID_TID


def test_key_missing_inbox_prefix_fails():
    with pytest.raises(IngestError, match="does not match"):
        validate_key("uploads/acme/2026/05/13/01JXYZABCDEFGHIJKLMNOPQRST.csv.gpg")


def test_key_wrong_extension_fails():
    with pytest.raises(IngestError):
        validate_key("inbox/acme/2026/05/13/01JXYZABCDEFGHIJKLMNOPQRST.csv")


def test_key_missing_gpg_suffix_fails():
    with pytest.raises(IngestError):
        validate_key("inbox/acme/2026/05/13/01JXYZABCDEFGHIJKLMNOPQRST.csv.zip")


def test_key_short_transaction_id_fails():
    with pytest.raises(IngestError):
        validate_key("inbox/acme/2026/05/13/TOOSHORT.csv.gpg")


def test_key_extra_segments_fails():
    with pytest.raises(IngestError):
        validate_key("inbox/acme/2026/05/13/extra/01JXYZABCDEFGHIJKLMNOPQRST.csv.gpg")


# ─── validate_metadata ────────────────────────────────────────────────────────

def test_valid_metadata_passes():
    validate_metadata(_VALID_META, _VALID_TID)  # no exception


def test_missing_transaction_id_fails():
    meta = {k: v for k, v in _VALID_META.items() if k != "transaction_id"}
    with pytest.raises(IngestError, match="transaction_id"):
        validate_metadata(meta, _VALID_TID)


def test_missing_partner_fails():
    meta = {k: v for k, v in _VALID_META.items() if k != "partner"}
    with pytest.raises(IngestError, match="partner"):
        validate_metadata(meta, _VALID_TID)


def test_missing_schema_version_fails():
    meta = {k: v for k, v in _VALID_META.items() if k != "schema_version"}
    with pytest.raises(IngestError, match="schema_version"):
        validate_metadata(meta, _VALID_TID)


def test_mismatched_transaction_id_fails():
    with pytest.raises(IngestError, match="does not match"):
        validate_metadata(_VALID_META, "DIFFERENTTRANSACTIONIDVALUE")
