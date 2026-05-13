.DEFAULT_GOAL := help
.PHONY: help \
        infra-aws infra-aws-teardown \
        local-up local-down local-table local-verify \
        cluster-up cluster-down cluster-status \
        infra-up infra-down \
        venv \
        submit-generate submit-submit submit-generate-and-submit \
        build test lint clean

VENV       := .venv
PYTHON     := $(VENV)/bin/python3
PIP        := $(VENV)/bin/pip
PYTEST     := $(VENV)/bin/pytest
PROJECT_ROOT := $(shell pwd)

# Load .env if present
-include .env
export

# ─── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "mini-file-platform — available targets"
	@echo ""
	@echo "  AWS infrastructure"
	@echo "    infra-aws          Create S3 buckets, SQS queue, and DLQ in AWS"
	@echo "    infra-aws-teardown Delete all AWS resources (destructive)"
	@echo ""
	@echo "  Local infrastructure"
	@echo "    local-up           Start DynamoDB Local in Docker"
	@echo "    local-down         Stop DynamoDB Local"
	@echo "    local-table        Create the transactions table in DynamoDB Local"
	@echo "    local-verify       Write and read a test record to verify DynamoDB Local"
	@echo ""
	@echo "  Kubernetes"
	@echo "    cluster-up         Create the kind cluster and apply namespace"
	@echo "    cluster-down       Delete the kind cluster"
	@echo "    cluster-status     Show cluster nodes and namespaces"
	@echo ""
	@echo "  Combined"
	@echo "    infra-up           Run local-up + local-table + cluster-up"
	@echo "    infra-down         Run local-down + cluster-down"
	@echo ""
	@echo "  Submitter CLI"
	@echo "    venv               Create the shared Python virtualenv"
	@echo "    submit-generate    Generate a sample CSV (PARTNER=acme ROWS=50)"
	@echo "    submit-submit      Encrypt and upload an existing CSV (FILE=path PARTNER=acme)"
	@echo "    submit-generate-and-submit  Generate + encrypt + upload (PARTNER=acme ROWS=50)"
	@echo ""
	@echo "  Development"
	@echo "    build              Build all service images"
	@echo "    test               Run all service tests"
	@echo "    lint               Run ruff on all Python sources"
	@echo "    clean              Remove build artifacts"
	@echo ""

# ─── AWS Infrastructure ───────────────────────────────────────────────────────

infra-aws:
	@chmod +x infra/aws/bootstrap.sh
	@bash infra/aws/bootstrap.sh

infra-aws-teardown:
	@chmod +x infra/aws/teardown.sh
	@bash infra/aws/teardown.sh

# ─── Local Infrastructure (DynamoDB Local) ────────────────────────────────────

local-up:
	docker compose -f infra/local/docker-compose.yml up -d
	@echo "Waiting for DynamoDB Local to be ready..."
	@until curl -sf http://localhost:8000 > /dev/null 2>&1; do sleep 1; done
	@echo "[ok] DynamoDB Local is ready at http://localhost:8000"

local-down:
	docker compose -f infra/local/docker-compose.yml down

local-table:
	@chmod +x infra/local/create-table.sh
	@bash infra/local/create-table.sh

local-verify:
	@echo "=== Writing test record to DynamoDB Local ==="
	@aws dynamodb put-item \
		--endpoint-url "$${DYNAMODB_ENDPOINT_URL:-http://localhost:8000}" \
		--region "$${AWS_DEFAULT_REGION:-us-east-1}" \
		--table-name "$${DYNAMODB_TABLE_TRANSACTIONS:-transactions}" \
		--item '{"transaction_id":{"S":"TEST-VERIFY"},"status":{"S":"RECEIVED"}}'
	@echo "=== Reading test record back ==="
	@aws dynamodb get-item \
		--endpoint-url "$${DYNAMODB_ENDPOINT_URL:-http://localhost:8000}" \
		--region "$${AWS_DEFAULT_REGION:-us-east-1}" \
		--table-name "$${DYNAMODB_TABLE_TRANSACTIONS:-transactions}" \
		--key '{"transaction_id":{"S":"TEST-VERIFY"}}'
	@echo "[ok] DynamoDB Local is working correctly"

# ─── Kubernetes (kind) ────────────────────────────────────────────────────────

cluster-up:
	@if kind get clusters 2>/dev/null | grep -q "^mini-file-platform$$"; then \
		echo "[skip] cluster already exists: mini-file-platform"; \
	else \
		kind create cluster --config infra/kubernetes/cluster-config.yaml; \
		echo "[ok] cluster created"; \
	fi
	kubectl apply -f infra/kubernetes/namespace.yaml
	@echo "[ok] namespace applied"

cluster-down:
	kind delete cluster --name mini-file-platform

cluster-status:
	@echo "=== Cluster nodes ==="
	kubectl get nodes
	@echo ""
	@echo "=== Namespaces ==="
	kubectl get namespaces

# ─── Combined Targets ─────────────────────────────────────────────────────────

infra-up: local-up local-table cluster-up
	@echo ""
	@echo "=== Local infrastructure is ready ==="
	@echo "  DynamoDB Local : http://localhost:8000"
	@echo "  kind cluster   : mini-file-platform"
	@echo ""
	@echo "Next: run 'make infra-aws' to provision AWS resources."

infra-down: local-down cluster-down
	@echo "=== Local infrastructure stopped ==="

# ─── Virtualenv ───────────────────────────────────────────────────────────────

venv:
	@if [ ! -d "$(VENV)" ]; then \
		python3 -m venv $(VENV); \
		echo "[ok] virtualenv created at $(VENV)"; \
	else \
		echo "[skip] virtualenv already exists"; \
	fi
	$(PIP) install -q "click>=8.1" "python-gnupg>=0.5.2" "boto3>=1.34" \
	                  "pytest>=8.0" "pytest-mock>=3.14"
	@echo "[ok] dependencies installed"

# ─── Submitter CLI ────────────────────────────────────────────────────────────

PARTNER ?= acme
ROWS    ?= 50
FILE    ?=

submit-generate: venv
	PYTHONPATH="$(PROJECT_ROOT)" $(PYTHON) -m app.main generate \
		--partner $(PARTNER) --rows $(ROWS)

submit-submit: venv
	@[ -n "$(FILE)" ] || (echo "Usage: make submit-submit FILE=path/to/file.csv PARTNER=acme" && exit 1)
	PYTHONPATH="$(PROJECT_ROOT)" $(PYTHON) -m app.main submit \
		--file $(FILE) --partner $(PARTNER)

submit-generate-and-submit: venv
	PYTHONPATH="$(PROJECT_ROOT)" $(PYTHON) -m app.main generate-and-submit \
		--partner $(PARTNER) --rows $(ROWS)

# ─── Development ──────────────────────────────────────────────────────────────

build:
	@echo "Building service images..."
	@for svc in submitter-cli processor-worker status-api; do \
		if [ -f "$$svc/Dockerfile" ]; then \
			docker build -t "mini-file-platform/$$svc:dev" "$$svc"; \
		else \
			echo "[skip] no Dockerfile yet: $$svc"; \
		fi; \
	done

test: venv
	PYTHONPATH="$(PROJECT_ROOT)" $(PYTEST) submitter-cli/tests/ -v

lint:
	@$(VENV)/bin/ruff check submitter-cli/ shared/ 2>/dev/null || \
	 python3 -m ruff check submitter-cli/ shared/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
