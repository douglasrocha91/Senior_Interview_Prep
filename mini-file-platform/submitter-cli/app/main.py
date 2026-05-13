"""mini-file-platform submitter CLI.

Usage:
    python -m app.main generate --partner acme --rows 50
    python -m app.main submit --file /tmp/expenses.csv --partner acme
    python -m app.main generate-and-submit --partner acme --rows 50

Environment variables required for submit:
    GPG_RECIPIENT_EMAIL   Email of the GPG public key used for encryption
    S3_INBOUND_BUCKET     Target S3 bucket
    GPG_HOME              (optional) Path to a custom GnuPG home directory
"""

import os
import sys
from pathlib import Path

# Adds mini-file-platform/ to sys.path so 'shared' is importable
# when running without installing the package (e.g. python -m app.main).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import click

from shared.utils.ids import generate_ulid
from shared.utils.log_config import get_logger

from app.generator import generate_csv
from app.crypto import encrypt_file
from app.uploader import upload_encrypted_file

log = get_logger(__name__)


def _require_env(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        raise click.ClickException(f"Environment variable {var!r} is required but not set.")
    return value


def _do_submit(file_path: Path, partner: str, schema_version: str) -> tuple[str, str]:
    """Core submit logic shared between 'submit' and 'generate-and-submit'."""
    recipient = _require_env("GPG_RECIPIENT_EMAIL")
    bucket = _require_env("S3_INBOUND_BUCKET")
    gpg_home = os.environ.get("GPG_HOME") or None
    transaction_id = generate_ulid()

    log.info("encrypting file", extra={"transaction_id": transaction_id, "file": str(file_path)})
    encrypted_path = encrypt_file(file_path, recipient, gpg_home=gpg_home)

    log.info("uploading to S3", extra={"transaction_id": transaction_id, "bucket": bucket})
    key = upload_encrypted_file(encrypted_path, bucket, partner, transaction_id, schema_version)

    return transaction_id, key


@click.group()
def cli() -> None:
    """mini-file-platform submitter — encrypt and upload expense files."""


@cli.command()
@click.option("--partner", required=True, help="Partner identifier (e.g. acme)")
@click.option("--rows", default=50, show_default=True, help="Number of expense rows")
@click.option("--output", default=None, help="Output CSV path (default: /tmp/{partner}_expenses.csv)")
def generate(partner: str, rows: int, output: str | None) -> None:
    """Generate a sample expense CSV file."""
    output_path = Path(output) if output else Path(f"/tmp/{partner}_expenses.csv")
    path = generate_csv(output_path, rows=rows, partner=partner)
    click.echo(f"generated : {path}")
    click.echo(f"rows      : {rows}")


@cli.command()
@click.option("--file", "file_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--partner", required=True, help="Partner identifier")
@click.option("--schema-version", default="v1", show_default=True)
def submit(file_path: Path, partner: str, schema_version: str) -> None:
    """Encrypt and upload a CSV file to S3."""
    transaction_id, key = _do_submit(file_path, partner, schema_version)
    click.echo(f"transaction_id : {transaction_id}")
    click.echo(f"s3_key         : {key}")


@cli.command("generate-and-submit")
@click.option("--partner", required=True, help="Partner identifier")
@click.option("--rows", default=50, show_default=True)
@click.option("--schema-version", default="v1", show_default=True)
def generate_and_submit(partner: str, rows: int, schema_version: str) -> None:
    """Generate a CSV and immediately encrypt and upload it."""
    output_path = Path(f"/tmp/{partner}_expenses.csv")
    generate_csv(output_path, rows=rows, partner=partner)
    click.echo(f"generated : {output_path} ({rows} rows)")

    transaction_id, key = _do_submit(output_path, partner, schema_version)
    click.echo(f"transaction_id : {transaction_id}")
    click.echo(f"s3_key         : {key}")


if __name__ == "__main__":
    cli()
