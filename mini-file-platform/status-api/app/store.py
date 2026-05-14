import os
from typing import Optional

import boto3


def _dynamo():
    endpoint = os.environ.get("DYNAMODB_ENDPOINT_URL")
    kwargs = {"endpoint_url": endpoint} if endpoint else {}
    return boto3.client("dynamodb", **kwargs)


def get_transaction(table: str, transaction_id: str) -> Optional[dict]:
    resp = _dynamo().get_item(
        TableName=table,
        Key={"transaction_id": {"S": transaction_id}},
    )
    item = resp.get("Item")
    if not item:
        return None
    return _deserialize(item)


def _deserialize(item: dict) -> dict:
    out: dict = {}
    for k, v in item.items():
        if "S" in v:
            out[k] = v["S"]
        elif "N" in v:
            out[k] = int(v["N"])
        elif "NULL" in v:
            out[k] = None
        else:
            out[k] = v
    return out
