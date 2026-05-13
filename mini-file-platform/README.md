# Mini File Platform

A distributed file processing platform with submission, ingestion, processing, and status tracking capabilities.

## Structure

- `submitter-cli/`: Command-line interface for submitting files
- `ingest-lambda/`: AWS Lambda function for initial file processing
- `processor-worker/`: Worker service for processing files
- `status-api/`: API service for checking processing status
- `shared/`: Shared models, schemas, and utilities
- `infra/`: Infrastructure configurations (AWS, Kubernetes, local)
- `sample-files/`: Example files for testing
- `docs/`: Documentation

## Getting Started

See individual service READMEs for specific setup instructions.

## Makefile Commands

Run `make help` to see available commands.