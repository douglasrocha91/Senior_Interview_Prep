from __future__ import annotations

import json

import boto3

# shared is on sys.path when running in Lambda (packaged at zip root)
# and via conftest.py when running tests locally.
from shared.models.transaction import FileJob


def publish_file_job(queue_url: str, job: FileJob) -> str:
    """Send a FileJob message to SQS. Returns the SQS MessageId."""
    sqs = boto3.client("sqs")
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(job.to_dict()),
        MessageAttributes={
            "partner": {
                "DataType": "String",
                "StringValue": job.partner,
            },
            "schema_version": {
                "DataType": "String",
                "StringValue": job.schema_version,
            },
        },
    )
    return response["MessageId"]
