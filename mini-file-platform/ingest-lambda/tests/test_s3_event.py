from app.s3_event import parse_records, S3Record

_VALID_KEY = "inbox/acme/2026/05/13/01JXYZABCDEFGHIJKLMNOPQRST.csv.gpg"


def _make_event(*keys: str, bucket: str = "my-bucket") -> dict:
    return {
        "Records": [
            {
                "eventTime": "2026-05-13T00:00:00Z",
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key, "size": 1024},
                },
            }
            for key in keys
        ]
    }


def test_parse_single_record():
    records = parse_records(_make_event(_VALID_KEY))
    assert len(records) == 1
    assert isinstance(records[0], S3Record)


def test_parse_extracts_bucket():
    records = parse_records(_make_event(_VALID_KEY, bucket="test-bucket"))
    assert records[0].bucket == "test-bucket"


def test_parse_extracts_key():
    records = parse_records(_make_event(_VALID_KEY))
    assert records[0].key == _VALID_KEY


def test_parse_extracts_size():
    records = parse_records(_make_event(_VALID_KEY))
    assert records[0].size == 1024


def test_parse_extracts_event_time():
    records = parse_records(_make_event(_VALID_KEY))
    assert records[0].event_time == "2026-05-13T00:00:00Z"


def test_parse_multiple_records():
    event = _make_event("inbox/a/2026/05/13/AAAAAAAAAAAAAAAAAAAAAAAAAA.csv.gpg",
                        "inbox/b/2026/05/13/BBBBBBBBBBBBBBBBBBBBBBBBBB.csv.gpg")
    records = parse_records(event)
    assert len(records) == 2


def test_parse_empty_event():
    records = parse_records({"Records": []})
    assert records == []


def test_parse_missing_records_key():
    records = parse_records({})
    assert records == []
