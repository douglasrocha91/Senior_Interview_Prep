import json
import os

import boto3


def get_errors(bucket: str, key: str) -> list[dict]:
    s3 = boto3.client("s3")
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
    except s3.exceptions.NoSuchKey:
        return []
    except Exception:
        return []
    lines = resp["Body"].read().decode().splitlines()
    errors = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                errors.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return errors


def errors_key(result_prefix: str) -> str:
    return f"{result_prefix}errors.jsonl"
