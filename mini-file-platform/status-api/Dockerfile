FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" boto3

# Build context must be mini-file-platform/ (parent dir)
COPY shared/ ./shared/
COPY status-api/app/ ./app/

ENV PYTHONPATH=/app

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
