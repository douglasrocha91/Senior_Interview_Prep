FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends gnupg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir boto3 python-gnupg

# Build context must be mini-file-platform/ (parent dir)
COPY shared/ ./shared/
COPY processor-worker/app/ ./app/

ENV PYTHONPATH=/app

CMD ["python", "-m", "app.main"]
