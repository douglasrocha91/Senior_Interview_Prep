#!/usr/bin/env bash
# Failure scenario runner for mini-file-platform local E2E.
# Usage: bash infra/local/failure-scenarios.sh <scenario>
#
# Scenarios:
#   corrupt-file   Upload a file encrypted with the wrong key (decrypt fails)
#   missing-key    Put a message pointing to a non-existent S3 key (download fails)
#   poison         Put a malformed JSON message (consumer skips it)
#   dlq-check      Show how many messages are in the DLQ

set -euo pipefail

SCENARIO="${1:?Usage: $0 <corrupt-file|missing-key|poison|dlq-check>}"
ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
DYNAMO_ENDPOINT="${DYNAMODB_ENDPOINT_URL:-http://localhost:8000}"
QUEUE_URL="${SQS_FILE_JOBS_URL:?SQS_FILE_JOBS_URL not set}"
INBOUND="${S3_INBOUND_BUCKET:-mini-file-platform-inbound}"

_ulid() {
  python3 -c "
import time, random, string
t = int(time.time() * 1000)
chars = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
ts = ''
for _ in range(10):
    ts = chars[t % 32] + ts
    t //= 32
rand = ''.join(random.choices(chars, k=16))
print(ts + rand)
"
}

_send_sqs() {
  local tid="$1" key="$2"
  aws --endpoint-url "$ENDPOINT" sqs send-message \
    --queue-url "$QUEUE_URL" \
    --message-body "{\"transaction_id\":\"$tid\",\"bucket\":\"$INBOUND\",\"key\":\"$key\",\"partner\":\"acme\",\"received_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"schema_version\":\"v1\",\"attempt\":0}" \
    --output text > /dev/null
}

_dynamo_status() {
  local tid="$1"
  aws --endpoint-url "$DYNAMO_ENDPOINT" dynamodb get-item \
    --table-name transactions \
    --key "{\"transaction_id\":{\"S\":\"$tid\"}}" \
    --query 'Item.status.S' --output text 2>/dev/null || echo "NOT FOUND"
}

# ─── Scenario: corrupt file ───────────────────────────────────────────────────

scenario_corrupt_file() {
  echo ""
  echo "=== Scenario: decrypt failure (arquivo corrompido) ==="
  echo "Simula um arquivo que não foi encriptado com a chave correta."
  echo ""

  TID=$(_ulid)
  KEY="inbox/acme/2026/05/14/$TID.csv.gpg"

  # Upload um arquivo de texto simples com extensão .csv.gpg (não é GPG real)
  CORRUPT_TMP=$(mktemp /tmp/corrupt_XXXXXX.gpg)
  echo "this is not a valid gpg file" > "$CORRUPT_TMP"
  VENV_PYTHON="$(dirname "$0")/../../.venv/bin/python3"
  "$VENV_PYTHON" -c "
import boto3, os, sys
s3 = boto3.client('s3', endpoint_url='$ENDPOINT',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID','test'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY','test'),
    region_name=os.environ.get('AWS_DEFAULT_REGION','us-east-1'))
with open('$CORRUPT_TMP','rb') as f:
    s3.put_object(Bucket='$INBOUND', Key='$KEY', Body=f.read())
print('[ok] arquivo corrompido enviado para S3')
"
  rm -f "$CORRUPT_TMP"

  echo "transaction_id : $TID"
  echo "s3_key         : $KEY"
  echo "arquivo        : texto simples com extensão .csv.gpg (GPG inválido)"
  echo ""
  echo "Publicando no SQS..."
  _send_sqs "$TID" "$KEY"
  echo "[ok] mensagem publicada"
  echo ""
  echo "Rode agora: make worker-run"
  echo "Depois:     bash /tmp/check-transaction.sh $TID"
  echo ""
  echo "Resultado esperado: status=FAILED, mensagem retida no SQS para retry"
  export LAST_TID="$TID"
}

# ─── Scenario: missing S3 key ─────────────────────────────────────────────────

scenario_missing_key() {
  echo ""
  echo "=== Scenario: download failure (S3 key inexistente) ==="
  echo "Simula uma mensagem que aponta para um arquivo que não existe no S3."
  echo ""

  TID=$(_ulid)
  KEY="inbox/acme/2026/05/14/$TID.csv.gpg"

  # Não faz upload — o arquivo não vai existir no S3
  echo "transaction_id : $TID"
  echo "s3_key         : $KEY"
  echo "arquivo        : NÃO EXISTE no S3"
  echo ""
  echo "Publicando no SQS..."
  _send_sqs "$TID" "$KEY"
  echo "[ok] mensagem publicada"
  echo ""
  echo "Rode agora: make worker-run"
  echo "Depois:     bash /tmp/check-transaction.sh $TID"
  echo ""
  echo "Resultado esperado: status=FAILED, mensagem retida no SQS para retry"
}

# ─── Scenario: poison message ─────────────────────────────────────────────────

scenario_poison() {
  echo ""
  echo "=== Scenario: poison message (JSON malformado) ==="
  echo "Simula uma mensagem que o consumer não consegue parsear."
  echo ""

  # Envia JSON inválido
  aws --endpoint-url "$ENDPOINT" sqs send-message \
    --queue-url "$QUEUE_URL" \
    --message-body "this is not json at all {broken" \
    --output text > /dev/null

  echo "[ok] mensagem malformada publicada"
  echo ""
  echo "Rode agora: make worker-run"
  echo ""
  echo "Resultado esperado:"
  echo "  - consumer loga erro e NÃO chama process_job"
  echo "  - mensagem NÃO é deletada (fica no SQS)"
  echo "  - após 3 receives, vai para o DLQ automaticamente"
  echo "  - NENHUM registro criado no DynamoDB"
}

# ─── DLQ check ────────────────────────────────────────────────────────────────

scenario_dlq_check() {
  echo ""
  echo "=== DLQ status ==="

  DLQ_URL="${SQS_DLQ_URL:?SQS_DLQ_URL not set}"

  MAIN_COUNT=$(aws --endpoint-url "$ENDPOINT" sqs get-queue-attributes \
    --queue-url "$QUEUE_URL" \
    --attribute-names ApproximateNumberOfMessages \
    --query 'Attributes.ApproximateNumberOfMessages' --output text)

  DLQ_COUNT=$(aws --endpoint-url "$ENDPOINT" sqs get-queue-attributes \
    --queue-url "$DLQ_URL" \
    --attribute-names ApproximateNumberOfMessages \
    --query 'Attributes.ApproximateNumberOfMessages' --output text)

  echo "  file-jobs (main) : $MAIN_COUNT mensagem(s)"
  echo "  file-jobs-dlq    : $DLQ_COUNT mensagem(s)"

  if [ "$DLQ_COUNT" -gt 0 ]; then
    echo ""
    echo "  Mensagens no DLQ (peek):"
    aws --endpoint-url "$ENDPOINT" sqs receive-message \
      --queue-url "$DLQ_URL" \
      --max-number-of-messages 1 \
      --visibility-timeout 0 \
      --query 'Messages[0].Body' --output text 2>/dev/null | python3 -c "
import sys, json
try:
    body = json.loads(sys.stdin.read())
    print('    transaction_id:', body.get('transaction_id','N/A'))
    print('    key:           ', body.get('key','N/A'))
except:
    print('    (corpo não é JSON válido — poison message)')
" || true
  fi
}

# ─── Dispatch ─────────────────────────────────────────────────────────────────

case "$SCENARIO" in
  corrupt-file) scenario_corrupt_file ;;
  missing-key)  scenario_missing_key ;;
  poison)       scenario_poison ;;
  dlq-check)    scenario_dlq_check ;;
  *) echo "Scenario desconhecido: $SCENARIO"; exit 1 ;;
esac
