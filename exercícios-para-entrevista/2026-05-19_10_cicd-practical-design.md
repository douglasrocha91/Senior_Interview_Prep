# [SAP Concur Prep] 10) CI/CD Practical Design

**Date:** Tuesday, 19 May 2026  
**Objective:** Design a practical CI/CD pipeline for Python services and Lambda packaging with quality gates.

---

## Context: Services in This Repo

Before writing any pipeline, map what you are shipping:

| Service | Type | Artifact | Test runner | Linter |
|---|---|---|---|---|
| `ingest-lambda` | AWS Lambda | `.zip` | pytest | ruff |
| `processor-worker` | Docker / Kubernetes Deployment | OCI image | pytest | ruff |
| `status-api` | Docker / Kubernetes Deployment | OCI image | pytest | ruff |
| `submitter-cli` | CLI tool (partner-side) | not deployed to cluster | pytest | ruff |

All services share a `shared/` library. A change there must trigger tests for every service that imports it.

---

## Exercise 1 — Define Pipeline Stages

### Concept

A well-structured pipeline moves code from commit to production through distinct stages where each stage can fail fast without wasting work on later stages. The order matters: cheap checks (lint) run before expensive ones (build, deploy).

### Task

Draw the pipeline as a linear sequence of stages. Map each stage to one or more of the services above.

```
[ push / PR ] 
     │
     ▼
┌──────────────┐
│  1. Lint &   │  ruff check on all changed services + shared/
│  type check  │  fast fail: < 30s
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  2. Unit     │  pytest per service in isolation
│  tests       │  with coverage threshold
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  3. Security │  pip-audit (dependency CVEs)
│  scan        │  Bandit (SAST — static code analysis)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  4. Build    │  Docker build (processor-worker, status-api)
│  & package   │  Lambda zip (ingest-lambda)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  5. Push     │  Push images to ECR (tag: git SHA)
│  artifacts   │  Upload Lambda zip to S3 staging prefix
└──────┬───────┘
       │ (only on merge to main)
       ▼
┌──────────────┐
│  6. Deploy   │  kubectl rollout + Lambda update-function-code
│  to staging  │  smoke test: hit /health endpoints
└──────┬───────┘
       │ (manual approval gate or auto if smoke passes)
       ▼
┌──────────────┐
│  7. Deploy   │  same procedure, production namespace/account
│  to prod     │  post-deploy verification
└──────────────┘
```

### Observe and note

- Which stage should block a PR from being merged vs. which stage should only block the deploy?
- What is the minimum set of stages you would require on every PR (not just on merge to main)?
- Why run lint before tests instead of in parallel?

---

## Exercise 2 — Lint and Type Check Stage

### Concept

Linting enforces code style and catches common bugs cheaply. In this repo, `ruff` covers both lint and (optionally) type-annotation checks.

### Task

Write the GitHub Actions job that runs `ruff` across all changed services. Only re-lint services whose source files changed.

```yaml
# .github/workflows/ci.yml  (excerpt)
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install ruff
        run: pip install ruff>=0.9

      - name: Lint all services
        run: |
          ruff check ingest-lambda/ processor-worker/ status-api/ submitter-cli/ shared/

      - name: Check formatting
        run: |
          ruff format --check ingest-lambda/ processor-worker/ status-api/ submitter-cli/ shared/
```

### Observe and note

- What does `ruff format --check` do vs. `ruff check`?
- The existing `pyproject.toml` files set `line-length = 100`. What happens if the CI machine uses the default ruff config (line-length 88)?
- How would you add `mypy` type checking for `processor-worker` without making the job slow for unrelated services?

---

## Exercise 3 — Unit Test Stage

### Concept

Unit tests validate behaviour in isolation. Coverage thresholds enforce that new code is tested. In this repo, each service has its own `tests/` directory and `pyproject.toml`.

### Task

Write the GitHub Actions job that runs pytest for all four services, publishing coverage, and fails if coverage drops below a threshold.

```yaml
  test:
    runs-on: ubuntu-latest
    needs: lint
    strategy:
      matrix:
        service: [ingest-lambda, processor-worker, status-api, submitter-cli]
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        working-directory: mini-file-platform
        run: |
          pip install pytest pytest-cov pytest-mock
          pip install -e ${{ matrix.service }}
          pip install -e shared  # shared library consumed by all services

      - name: Run tests with coverage
        working-directory: mini-file-platform
        run: |
          pytest ${{ matrix.service }}/tests/ \
            --cov=${{ matrix.service }}/app \
            --cov-report=term-missing \
            --cov-fail-under=80 \
            -v

      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        with:
          name: coverage-${{ matrix.service }}
          path: .coverage
```

### Observe and note

- The `matrix` strategy runs the four services in parallel. What is the trade-off between parallelism and cost?
- `needs: lint` means tests only run if lint passes. When would you remove this dependency and run in parallel instead?
- The `shared/` library has no tests of its own. How would you ensure it is tested transitively, and what is the risk of not having dedicated shared tests?

---

## Exercise 4 — Security Scanning Stage

### Concept

Security scans fall into two categories: **dependency auditing** (known CVEs in installed packages) and **SAST** (static analysis of your own code for dangerous patterns). Both should block a release.

### Task

Add a security scan job using `pip-audit` for dependencies and `bandit` for SAST.

```yaml
  security:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install audit tools
        run: pip install pip-audit bandit

      - name: Audit dependencies — ingest-lambda
        run: pip-audit -r mini-file-platform/ingest-lambda/pyproject.toml

      - name: Audit dependencies — processor-worker
        run: pip-audit -r mini-file-platform/processor-worker/pyproject.toml

      - name: Audit dependencies — status-api
        run: pip-audit -r mini-file-platform/status-api/pyproject.toml

      - name: Bandit SAST scan
        run: |
          bandit -r mini-file-platform/ingest-lambda/app \
                    mini-file-platform/processor-worker/app \
                    mini-file-platform/status-api/app \
                    mini-file-platform/shared/ \
                 --severity-level medium \
                 --confidence-level medium \
                 -f json -o bandit-report.json

      - name: Upload Bandit report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: bandit-report
          path: bandit-report.json
```

### Observe and note

- `--severity-level medium` means Bandit only fails on medium or higher severity findings. What is the risk of setting it too low (low severity) vs. too high (critical only)?
- `pip-audit` checks against the PyPI Advisory Database. Name two types of CVE it would catch vs. one type it would miss.
- `if: always()` on the upload step means the artifact is uploaded even if the scan fails. Why is this important for developer experience?

---

## Exercise 5 — Build and Package Stage

### Concept

This repo has two packaging patterns: **Docker images** for the long-running services (processor-worker, status-api) and a **Lambda deployment ZIP** for ingest-lambda. Each has its own constraints.

### Task A — Docker build

```yaml
  build-docker:
    runs-on: ubuntu-latest
    needs: [test, security]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Set image tag
        id: tag
        run: echo "sha=${GITHUB_SHA::8}" >> "$GITHUB_OUTPUT"

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/ci-ecr-push
          aws-region: us-east-1

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push processor-worker
        working-directory: mini-file-platform
        env:
          REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          TAG: ${{ steps.tag.outputs.sha }}
        run: |
          docker build \
            -t $REGISTRY/processor-worker:$TAG \
            -t $REGISTRY/processor-worker:latest \
            -f processor-worker/Dockerfile .
          docker push $REGISTRY/processor-worker:$TAG
          docker push $REGISTRY/processor-worker:latest

      - name: Build and push status-api
        working-directory: mini-file-platform
        env:
          REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          TAG: ${{ steps.tag.outputs.sha }}
        run: |
          docker build \
            -t $REGISTRY/status-api:$TAG \
            -t $REGISTRY/status-api:latest \
            -f status-api/Dockerfile .
          docker push $REGISTRY/status-api:$TAG
          docker push $REGISTRY/status-api:latest
```

### Task B — Lambda ZIP packaging

```yaml
  build-lambda:
    runs-on: ubuntu-latest
    needs: [test, security]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Package ingest-lambda
        run: |
          # Install dependencies into a package directory
          pip install \
            --target mini-file-platform/ingest-lambda/package \
            --platform manylinux2014_x86_64 \
            --implementation cp \
            --python-version 3.11 \
            --only-binary=:all: \
            boto3

          # Copy application code into the package directory
          cp -r mini-file-platform/ingest-lambda/app \
                mini-file-platform/ingest-lambda/package/

          # Zip the entire package directory — Lambda expects this layout
          cd mini-file-platform/ingest-lambda/package
          zip -r ../../../ingest-lambda-${{ github.sha }}.zip .

      - name: Upload zip to S3 staging prefix
        run: |
          aws s3 cp ingest-lambda-${{ github.sha }}.zip \
            s3://${{ vars.ARTIFACTS_BUCKET }}/lambda/ingest-lambda-${{ github.sha }}.zip
```

### Observe and note

- The Docker build uses `GITHUB_SHA::8` (first 8 chars of the commit SHA) as the image tag. Why is this better than tagging with `latest` only?
- The Lambda ZIP uses `--platform manylinux2014_x86_64 --only-binary=:all:`. Why is this flag necessary when building on macOS or ARM-based CI runners?
- The `Dockerfile` for `processor-worker` copies the `shared/` directory. What happens at CI time if `shared/` is modified but the Docker build cache is from a run that predates the change?
- What is the advantage of uploading the Lambda ZIP to S3 rather than passing it directly to `update-function-code`?

---

## Exercise 6 — Deploy Gates and Staging

### Concept

A deploy gate is a checkpoint where the pipeline verifies the state of the system before allowing the next step. Gates can be automated (smoke tests, health checks) or manual (human approval). The goal is to catch problems in staging before they reach production.

### Task

Write the staging deploy job and the smoke test that acts as an automated gate.

```yaml
  deploy-staging:
    runs-on: ubuntu-latest
    needs: [build-docker, build-lambda]
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials (staging)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/ci-deploy-staging
          aws-region: us-east-1

      - name: Update processor-worker in staging cluster
        run: |
          aws eks update-kubeconfig --name mini-file-platform-staging
          kubectl set image deployment/processor-worker \
            processor-worker=${{ vars.ECR_REGISTRY }}/processor-worker:${{ github.sha::8 }} \
            -n mini-file-platform
          kubectl rollout status deployment/processor-worker \
            -n mini-file-platform --timeout=120s

      - name: Update ingest-lambda in staging
        run: |
          aws lambda update-function-code \
            --function-name ingest-lambda-staging \
            --s3-bucket ${{ vars.ARTIFACTS_BUCKET }} \
            --s3-key lambda/ingest-lambda-${{ github.sha }}.zip
          aws lambda wait function-updated \
            --function-name ingest-lambda-staging

      - name: Smoke test — status-api health
        run: |
          curl --retry 5 --retry-delay 3 --fail \
            https://staging.mini-file-platform.internal/health

      - name: Smoke test — upload and trace a file end-to-end
        run: |
          FILE_ID=$(python mini-file-platform/submitter-cli/smoke_test.py \
            --env staging --partner acme)
          # Poll status endpoint until PROCESSED or timeout 60s
          for i in $(seq 1 12); do
            STATUS=$(curl -sf https://staging.mini-file-platform.internal/status/$FILE_ID \
              | jq -r '.status')
            [ "$STATUS" = "PROCESSED" ] && exit 0
            sleep 5
          done
          echo "Smoke test timed out — file $FILE_ID did not reach PROCESSED"
          exit 1
```

### Observe and note

- The `kubectl rollout status --timeout=120s` command fails the job if the rollout does not complete in 2 minutes. What Kubernetes condition does it wait for, and why is readiness probe configuration critical here?
- `environment: staging` in GitHub Actions does more than set a name. What does it enable in terms of secrets and approvals?
- The end-to-end smoke test uploads a real file through the full pipeline. What is the risk of running this test in production? What would you do differently for a production deploy gate?

---

## Exercise 7 — Rollback Thinking

### Concept

A rollback is not just "undo the deploy" — it requires knowing exactly what state to return to, how long it takes, and whether the old code is compatible with any state changes (database migrations, schema changes, queue message formats) that the new version may have introduced.

### Task

For each service, define the rollback mechanism and the conditions that should trigger it.

```
Service: processor-worker (Kubernetes Deployment)
─────────────────────────────────────────────────
Rollback command:
  kubectl rollout undo deployment/processor-worker -n mini-file-platform

How it works:
  Kubernetes switches back to the previous ReplicaSet (the last known-good image tag).
  The old pods come up; new pods are terminated.

Rollback trigger:
  - Error rate in CloudWatch > X% within 10 minutes of deploy
  - kubectl rollout status reports failed rollout
  - Smoke test fails in staging

Time to rollback:
  ~30–60 seconds (same as a rolling update in reverse)

Gotcha:
  If the new version wrote a new DynamoDB attribute or changed a message schema,
  rolling back the code does not remove that data. Old code must handle the new
  field being present (additive-only schema changes).
```

```
Service: ingest-lambda (AWS Lambda)
────────────────────────────────────
Rollback command:
  aws lambda update-alias \
    --function-name ingest-lambda \
    --name live \
    --function-version $PREVIOUS_VERSION

How it works:
  Lambda versions are immutable snapshots. The `live` alias points to a version number.
  Rolling back means pointing the alias back to the previous version — instantaneous,
  no traffic disruption.

Rollback trigger:
  - Lambda error rate > 1% on the `live` alias within 5 minutes (CloudWatch alarm)
  - AWS CodeDeploy canary alarm fires (if using weighted alias routing)

Time to rollback:
  < 5 seconds (alias pointer update)

Gotcha:
  Lambda versions include the ZIP package but not environment variables or
  concurrency settings — those are on the function config, not the version.
  A config change requires a separate rollback step.
```

### Observe and note

- What is the difference between a **rollback** and a **roll forward**? When would you choose each?
- The Lambda rollback relies on versioning and aliases. What must be true in the CI pipeline to make this possible?
- A `kubectl rollout undo` rolls back to the previous ReplicaSet. What is the maximum number of revisions Kubernetes keeps by default, and how do you control it?

---

## Exercise 8 — Connect to This Repo

Review the existing `Makefile`, `pyproject.toml` files, and `Dockerfile` in `mini-file-platform/` and answer:

1. The `Makefile` `test` target runs all four service tests sequentially. In CI, how would you parallelize this without changing the Makefile?

2. The `Makefile` `lint` target only covers `submitter-cli/` and `shared/`. What would you add to cover `ingest-lambda/`, `processor-worker/`, and `status-api/`?

3. The `processor-worker/Dockerfile` runs `pip install --no-cache-dir boto3 python-gnupg` without pinning versions. What is the risk for a CI/CD pipeline, and how would you fix it?

4. There is no `requirements.txt` or `pip-audit` integration today. Write the `pip-audit` command you would add as a pre-commit hook and as a CI job step for `processor-worker`.

5. The current `Dockerfile` does not run as a non-root user. Add the two lines needed to fix this, and explain why it matters in the context of the GPG keyring permissions.

---

## Notes: Pipeline Design Decisions

Write your own rationale here after completing the exercises. Template:

```
What blocks a PR merge:
  -
  -
  -

What blocks a production deploy (but not a PR):
  -
  -

What is advisory-only (never blocks):
  -
  -

Why Lambda versioning matters for rollback:


Why image tags must be immutable (never overwrite :latest in production):


One thing unique to this repo's pipeline because of the GPG dependency:
```

---

## Interview Angle

### How automation reduces deployment risk

Manual deployments are error-prone because they depend on a human following the same sequence of steps correctly every time, under pressure, possibly at 2 AM. A pipeline encodes the sequence once and executes it identically on every commit. The risk reduction is not from the automation itself — it is from the consistency: the same linter that caught a bug on the last PR runs on this one too, with the same threshold, without anyone deciding to skip it.

### How to catch problems early

Early stages should be cheap and fast (lint: < 1 min), later stages can be expensive (integration tests: 5–10 min). If a commit fails lint, the test runner never spends compute. Every stage that runs before production is an opportunity to catch a class of problem that staging might not. The cost of a false positive (a check that blocks a good commit) is much lower than the cost of a false negative (a broken commit reaching production).

### How to decide what must block a release

A check should block if its failure indicates a state that would cause user-facing harm or data loss in production. Lint failures → code style, probably not blocking in isolation, but enforced to keep the codebase consistent. Test failures → always blocking. Security CVEs → blocking at medium+, advisory at low. Coverage drops → blocking if threshold crossed. Performance regressions → advisory unless severe (hard to define a universal threshold).

In a file processing pipeline specifically: a bug in the Lambda validator that allows malformed files to queue silently, or a decryption error that surfaces only in prod, has high cost — failed processing, SLA breach, unhappy partners. The pipeline should be conservative.

### Common interview follow-ups

- "What would you do if the smoke test is flaky?" — Mark flaky tests and quarantine them; do not let a flaky gate block all deploys. Fix the flakiness as a priority-1 bug.
- "How do you handle database migrations in the deploy pipeline?" — Run migrations as a pre-deploy step; make them backwards-compatible (never remove a column in the same release that removes the code reading it).
- "How would you add a canary deploy for the processor-worker?" — Use KEDA + weighted routing or a dedicated canary Deployment with a fraction of replicas; monitor error rate before shifting full traffic.
- "What is the difference between a CI pipeline and a CD pipeline?" — CI validates every commit (lint, test, scan, build). CD automates delivery to an environment. You can have CI without CD (manual deploy after the build), but CD without CI is risky.
