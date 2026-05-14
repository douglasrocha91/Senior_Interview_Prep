import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.store import get_transaction
from app.s3_reader import get_errors, errors_key

app = FastAPI(title="mini-file-platform status API")

_TABLE = lambda: os.environ["DYNAMODB_TABLE_TRANSACTIONS"]
_RESULTS_BUCKET = lambda: os.environ["S3_RESULTS_BUCKET"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/transactions/{transaction_id}")
def get_transaction_status(transaction_id: str):
    item = get_transaction(_TABLE(), transaction_id)
    if item is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return JSONResponse(content=item)


@app.get("/transactions/{transaction_id}/errors")
def get_transaction_errors(transaction_id: str):
    item = get_transaction(_TABLE(), transaction_id)
    if item is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    prefix = item.get("result_prefix")
    if not prefix:
        return []
    errors = get_errors(_RESULTS_BUCKET(), errors_key(prefix))
    return errors
