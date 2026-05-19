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

### Answers

**PR-blocking vs deploy-blocking stages:**
Stages 1–3 (lint, tests, security scan) should block every PR merge because they validate code correctness and security posture — problems they catch are the author's responsibility to fix before the code lands. Stages 4–7 (build, push, deploy, smoke) should only block on merge to `main`, because building and pushing Docker images on every feature branch is wasteful and staging environments are shared. Exception: running `docker build --no-push` on PRs is cheap and catches Dockerfile errors before merge without polluting ECR.

**Minimum set on every PR:** Lint, unit tests, and security scan at medium+ severity. These three together validate correctness, style, and dependencies in under 5 minutes and cost no external resources (no Docker daemon, no AWS calls). Coverage reporting can be PR-only advisory during early project phase, then promoted to blocking once a baseline is established.

**Why lint runs before tests, not in parallel:** Lint is the cheapest check (< 30s) and catches syntax and import errors that would also cause test failures. If lint and tests ran in parallel, a commit with a broken import would waste 2–5 minutes of test compute on a job that was always going to fail for the same reason. Serialising them forces the cheapest check first. In practice, lint and security scan can run in parallel with each other (both fast), then tests run after both pass — that is a slightly better topology than pure sequential for this repo.

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

### Answers

**`ruff format --check` vs `ruff check`:** They cover completely different concerns. `ruff check` runs the linter — it flags rule violations: unused imports, undefined names, shadowed builtins, style patterns. `ruff format --check` runs the code formatter in read-only mode — it verifies that the file would not change if the formatter were applied. A file can pass `ruff check` but still fail `ruff format --check` if it has inconsistent spacing or line breaks. Both should be required; omitting the format check means style diverges silently over time.

**`pyproject.toml` `line-length = 100` vs default 88:** Ruff picks up `pyproject.toml` automatically when invoked from the directory that contains it or any parent directory. In the job above, `ruff check ingest-lambda/` is invoked from the repo root, so ruff looks for a `pyproject.toml` in `.`, then in `ingest-lambda/` — it will find `mini-file-platform/ingest-lambda/pyproject.toml` if the working directory is `mini-file-platform/`. If the job runs from the repo root without `working-directory: mini-file-platform`, ruff uses its own defaults (line-length 88) and will flag all lines between 89 and 100 chars. Fix: add `working-directory: mini-file-platform` to the lint step, or add a root-level `ruff.toml` that sets `line-length = 100` as the shared default.

**Adding `mypy` without slowing unrelated services:** Use a separate job that only triggers when `processor-worker/` files change, detected with the `dorny/paths-filter` action. Example:

```yaml
  type-check:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: changes
        with:
          filters: |
            worker:
              - 'mini-file-platform/processor-worker/**'
              - 'mini-file-platform/shared/**'
      - name: mypy processor-worker
        if: steps.changes.outputs.worker == 'true'
        run: |
          pip install mypy boto3-stubs python-gnupg-stubs
          mypy mini-file-platform/processor-worker/app
```

This way, mypy runs only when processor-worker or shared files change. For PRs that only touch `status-api/`, the type-check job exits immediately.

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

### Answers

**Matrix parallelism vs cost:** Parallelism reduces wall-clock time dramatically — four 2-minute test suites take 2 minutes total instead of 8. The cost is 4× the CI compute minutes consumed. On GitHub Actions, parallel jobs each consume minutes independently from the plan quota. For a team committing frequently, this adds up. The practical trade-off: if test feedback speed matters more than CI cost (usually true for a focused interview-prep project), parallelise. If the team is on a free plan with limited minutes, run sequentially. The right answer in production is almost always to parallelise and optimise each suite to be fast rather than serialize slow suites.

**When to remove `needs: lint` and run tests in parallel with lint:** When tests are significantly slower than lint (e.g., lint is 20s, tests are 10 min), running them in parallel gives faster overall feedback: the developer gets both lint and test results in 10 minutes instead of 10:20. The downside is wasting compute if lint would have caught the root cause of a test failure anyway. Remove the dependency when the team's top priority is fast PR feedback time, or when lint and tests almost never fail for the same reason (mature codebase with clean style discipline).

**Testing `shared/` transitively vs dedicated tests:** Transitive coverage: every service's test suite installs and exercises `shared/` code indirectly. If `processor-worker` tests call `shared.utils.ids.generate_id()`, that function is covered. The risk: if the test suite covers only the happy path of `shared/models/transaction.py` as called from the worker, edge cases in the model's validation logic are invisible. A bug in `shared/` that is only triggered by `status-api` might not be caught until `status-api` tests run. Fix: add a `shared/tests/` directory with tests for every public function in `shared/models/`, `shared/utils/`, and `shared/schemas/`. Also add `shared` to the matrix so its tests run independently. Additionally, add a paths-filter: any change to `shared/` forces all four service test suites to run, even if only `shared/` changed.

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

### Answers

**Severity threshold risks:**
- **Too low (low severity):** Bandit flags many low-severity issues in legitimate code — using `subprocess`, writing to temporary files, using `assert` statements. These generate constant noise. Developers start suppressing findings with `# nosec` comments indiscriminately or stop looking at the report entirely. The scan becomes security theater: it runs, it fails, no one reads it.
- **Too high (critical only):** Most real exploitable patterns in Python application code — hardcoded credentials, use of `eval()` with user input, unsafe `yaml.load()` calls, `subprocess` with shell injection — are classified as medium severity. Setting critical-only means the scan will almost never fire and provides no meaningful protection. **Medium is the right default:** it catches real issues while keeping the false-positive rate manageable.

**What `pip-audit` catches vs misses:**
- **Catches:** (1) Known CVEs in direct and transitive dependencies tracked in the Python Packaging Advisory Database (e.g., a `boto3` sub-dependency with a known RCE). (2) Packages that have been yanked from PyPI due to security issues, even if not formally assigned a CVE.
- **Misses:** Vulnerabilities in OS-level packages installed in the Docker image (the `gnupg` and `apt-get` packages in `processor-worker/Dockerfile` are invisible to `pip-audit`). For those, use a container image scanner like **Trivy** or **Grype** on the built image in the build stage.

**`if: always()` importance for developer experience:** Without it, the upload step is skipped when the Bandit job fails — which is exactly the moment when the developer needs the report. The scan exit code is non-zero, GitHub shows the job as failed, but there is no artifact to open. The developer must re-run the job locally to see what triggered the failure. `if: always()` ensures the JSON report is always available as a downloadable artifact in the Actions UI, even for a failing run, so the developer can open it immediately and see exactly which file and line number triggered the finding.

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

### Answers

**SHA tag vs `:latest` only:** `:latest` is a mutable pointer — every push overwrites it. If a bad build gets pushed, the previous `:latest` is permanently gone from ECR; rollback becomes "rebuild the old commit," which takes minutes and requires someone to know which commit was previously running. A SHA tag (`abc12345`) is immutable: every commit produces a unique tag that cannot be overwritten. You can always roll back instantly with `kubectl set image ... processor-worker:abc12345`. It also gives you a precise audit trail — `kubectl get pod -o yaml | grep image` tells you exactly which commit is running in production.

**`--platform manylinux2014_x86_64 --only-binary=:all:`:** Lambda runs on Amazon Linux 2 (x86_64). If you build the ZIP on macOS (arm64 Apple Silicon) or on a GitHub Actions runner using an ARM CPU, `pip install` downloads wheels compiled for that architecture. A Python wheel containing a C extension (like `cryptography`) compiled for arm64 will `ImportError` immediately on Lambda's x86_64 runtime. `--platform manylinux2014_x86_64` forces pip to fetch wheels compatible with Amazon Linux's x86 ABI, and `--only-binary=:all:` prevents pip from falling back to compiling from source (which would produce the wrong architecture). For a pure-Python library like `boto3`, this is not strictly necessary — but it is the correct practice for any Lambda ZIP build to make it architecture-agnostic.

**`shared/` change and Docker build cache:** Docker checksums every file in the build context when evaluating whether to reuse a cached layer. When `shared/` changes, the `COPY shared/ ./shared/` instruction invalidates that layer and all subsequent layers in the Dockerfile — the layer is rebuilt from scratch. This works correctly only if the build context is the `mini-file-platform/` parent directory (`docker build -f processor-worker/Dockerfile .` run from `mini-file-platform/`), which is exactly what the Makefile does. If the build context were scoped to `processor-worker/` only, the `shared/` directory would not be in context and the COPY would fail with "file not found."

**S3 vs direct ZIP upload:** `aws lambda update-function-code --zip-file` has a hard 50 MB inline payload limit. S3 supports Lambda ZIPs up to 250 MB. More importantly: uploading to S3 first decouples build from deploy. The build job uploads once with the commit SHA in the key (`lambda/ingest-lambda-abc12345.zip`), and both the staging and production deploy jobs reference the same immutable artifact by key. This enables rollback without rebuilding: `update-function-code --s3-key lambda/ingest-lambda-abc12344.zip` points back to the previous commit's ZIP. It also gives you a versioned artifact store useful for auditing.

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

### Answers

**What `kubectl rollout status --timeout=120s` waits for:** It polls until the Deployment's `.status.updatedReplicas` equals `.spec.replicas` AND all updated replicas report `Available` — which requires their readiness probes to return success. If the new pods fail the readiness probe (wrong endpoint, app not yet listening, GPG keyring not loaded), they never become `Available`, `rollout status` times out after 120s, and exits with a non-zero code that fails the CI job. This is why the readiness probe in the Deployment spec must be correct and realistic: if `initialDelaySeconds` is too short, the probe fires before the app is ready, the rollout blocks CI, and the pipeline halts every deploy until the probe config is fixed.

**`environment: staging` beyond naming:** It activates three GitHub Actions features: (1) **Environment secrets** — values stored under the `staging` environment in repo settings, separate from repository-level secrets, so staging credentials are isolated from production ones. (2) **Protection rules** — you can require approval from specific reviewers before the job executes (useful for the production environment). (3) **Deployment history** — GitHub records each run of a job with `environment: staging` as a deployment event, visible in the repository's "Environments" tab with the commit SHA, timestamp, and who approved it. This gives a clean audit trail of what was deployed to staging and when.

**Risk of end-to-end smoke test in production:** Uploading a real file in production creates real DynamoDB records, charges for SQS message processing, and generates noise in monitoring dashboards and partner-facing status endpoints. If the file uses a real partner ID, it could also affect partner billing or reporting. Better approaches for production deploy gates: (1) use a dedicated synthetic partner (`partner: ci-canary`) flagged to be excluded from SLA monitoring and partner reporting; (2) measure the error rate of the ingest Lambda and processor-worker for 5 minutes post-deploy and fail if it rises above baseline — no synthetic traffic needed; (3) run a canary deploy (10% traffic to new version) and watch CloudWatch alarms before promoting to 100%.

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

### Answers

**Rollback vs roll forward:**
- **Rollback:** revert to the previous known-good version immediately. Use when the bug is unclear, the fix is not trivial, the on-call engineer is not the code owner, or when every additional minute of degradation has a measurable cost (SLA breach, partner impact). Rollback trades recency for stability.
- **Roll forward:** write a fix and deploy it as the next version. Use when the fix is obvious and small (a one-line config change, a wrong default value), when the team can ship it in under 15 minutes, or when rolling back is itself risky — for example, if the new version ran a schema migration or changed the DynamoDB record structure that the old version cannot handle. Roll forward is generally preferred in fast-moving teams because it keeps the team in a deploy-forward posture rather than treating the last commit as sacred.
- **The decision heuristic:** if you know the fix in under 5 minutes, roll forward. If you are still diagnosing, roll back first, then diagnose and roll forward once the fix is ready.

**What must be true in the CI pipeline for Lambda alias rollback:** Every deploy must call `aws lambda publish-version` (or pass `--publish` to `update-function-code`) to create an immutable numbered version snapshot. Without this, all deploys overwrite `$LATEST` and there are no numbered versions to point the alias to. The CI job should also tag each published version with the git SHA in its description (`--description "SHA: $GITHUB_SHA"`) so the mapping from version number to commit is traceable without relying on external records.

**`kubectl rollout undo` revision limit:** Default `revisionHistoryLimit` is `10` — Kubernetes keeps the last 10 ReplicaSet snapshots per Deployment. `rollout undo` with no arguments rolls back to revision N-1 (the immediately previous revision). To go further: `kubectl rollout history deployment/<name> -n <ns>` lists all stored revisions; `kubectl rollout undo --to-revision=3` targets a specific one. Control the limit with `spec.revisionHistoryLimit` in the Deployment manifest — set it to `5` for small repos to reduce API server storage, or keep `10` for services where you might need to trace multiple releases back.

---

## Exercise 8 — Connect to This Repo

Review the existing `Makefile`, `pyproject.toml` files, and `Dockerfile` in `mini-file-platform/` and answer:

1. The `Makefile` `test` target runs all four service tests sequentially. In CI, how would you parallelize this without changing the Makefile?

2. The `Makefile` `lint` target only covers `submitter-cli/` and `shared/`. What would you add to cover `ingest-lambda/`, `processor-worker/`, and `status-api/`?

3. The `processor-worker/Dockerfile` runs `pip install --no-cache-dir boto3 python-gnupg` without pinning versions. What is the risk for a CI/CD pipeline, and how would you fix it?

4. There is no `requirements.txt` or `pip-audit` integration today. Write the `pip-audit` command you would add as a pre-commit hook and as a CI job step for `processor-worker`.

5. The current `Dockerfile` does not run as a non-root user. Add the two lines needed to fix this, and explain why it matters in the context of the GPG keyring permissions.

### Answers

**1. Parallelise tests without changing the Makefile:** Use the GitHub Actions matrix strategy (as shown in Exercise 3) and invoke `pytest` directly in CI, bypassing the Makefile's sequential `test` target entirely. The CI job maps each matrix entry to its service directory and runs `pytest <service>/tests/` with the right `PYTHONPATH`. The Makefile `test` target remains useful for local sequential runs; CI uses its own invocation. This is the cleanest split: the Makefile is for local development convenience, CI is free to parallelise however it wants.

**2. Extend the `lint` Makefile target:**

```makefile
lint:
	@$(VENV)/bin/ruff check ingest-lambda/ processor-worker/ status-api/ submitter-cli/ shared/
	@$(VENV)/bin/ruff format --check ingest-lambda/ processor-worker/ status-api/ submitter-cli/ shared/
```

The existing target only covers `submitter-cli/` and `shared/`. Adding `ingest-lambda/ processor-worker/ status-api/` brings full coverage. Adding `ruff format --check` (currently absent from the Makefile) enforces formatting locally as well, not just in CI.

**3. Risk of unpinned dependencies in the Dockerfile:**

```dockerfile
# Current — unpinned, non-reproducible
RUN pip install --no-cache-dir boto3 python-gnupg
```

Two CI builds of the same commit on different days can produce different images if a new `boto3` or `python-gnupg` release lands between them. A breaking change in a minor version (e.g., `python-gnupg` 0.5.3 changes a return type) could silently break the worker in a build that passes all tests (because tests also install the same unpinned version). Fix: generate a pinned `requirements.txt` using `pip-compile` from `pip-tools`, commit it, and install from it in the Dockerfile:

```bash
# Generate once, commit the result:
pip-compile processor-worker/pyproject.toml -o processor-worker/requirements.txt
```

```dockerfile
# Pinned, reproducible
COPY processor-worker/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
```

Update pins periodically with `pip-compile --upgrade` as part of scheduled dependency maintenance.

**4. `pip-audit` as pre-commit hook and CI step:**

Pre-commit hook (add to `.pre-commit-config.yaml`):
```yaml
repos:
  - repo: local
    hooks:
      - id: pip-audit-processor
        name: pip-audit processor-worker
        language: system
        entry: pip-audit -r mini-file-platform/processor-worker/pyproject.toml
        files: mini-file-platform/processor-worker/pyproject\.toml
        pass_filenames: false
```

CI job step (added to the `security` job):
```yaml
      - name: Audit processor-worker dependencies
        run: |
          pip-audit \
            -r mini-file-platform/processor-worker/pyproject.toml \
            --strict \
            --output json \
            --output-file pip-audit-processor.json

      - name: Upload pip-audit report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: pip-audit-processor
          path: pip-audit-processor.json
```

`--strict` makes any vulnerability a hard failure. Without it, `pip-audit` exits 0 even when vulnerabilities are found (it only exits non-zero on tool errors by default in some versions).

**5. Non-root user in Dockerfile:**

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends gnupg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir boto3 python-gnupg

COPY shared/ ./shared/
COPY processor-worker/app/ ./app/

ENV PYTHONPATH=/app

# Add these two lines:
RUN useradd -m appuser
USER appuser

CMD ["python", "-m", "app.main"]
```

**Why it matters for GPG:** GnuPG enforces that the home directory (`GPG_HOME`) is owned by the current user and has mode `700`. If the container runs as root, the keyring works but the container has no resource restrictions — any process escape gives full host root. Running as `appuser` limits the blast radius: a compromised container cannot write to system paths outside `/app` and cannot read other users' files. More practically, many Kubernetes clusters enforce `PodSecurityAdmission` with the `restricted` profile, which blocks containers running as root (UID 0) entirely. A container that passes CI but is rejected by admission control at deploy time is a painful surprise. Fixing it in the Dockerfile is the right place.

---

## Notes: Pipeline Design Decisions

```
What blocks a PR merge:
  - Lint failure (ruff check or ruff format --check on any service or shared/)
  - Any unit test failure in any of the four services
  - Security scan: pip-audit CVE at medium+ severity OR Bandit finding at medium
    severity + medium confidence on application code

What blocks a production deploy (but not a PR):
  - Staging smoke test failure (end-to-end file processing did not reach PROCESSED)
  - kubectl rollout status times out or exits non-zero (new pods never became Ready)

What is advisory-only (never blocks):
  - Low-severity Bandit findings (logged as artifact, visible to devs, not gating)
  - Coverage report when below threshold during initial project ramp-up (promote
    to blocking once the team establishes and agrees on a baseline)

Why Lambda versioning matters for rollback:
  Each deploy publishes an immutable, numbered version snapshot of the ZIP and
  its configuration. Rollback is an alias pointer update (< 5s) requiring no
  rebuild and no redeploy. Without versioning, $LATEST is overwritten on every
  deploy and there is nothing to point back to — rollback becomes "rebuild the
  previous commit," which takes several minutes and requires knowing which
  commit was previously running.

Why image tags must be immutable (never overwrite :latest in production):
  :latest is mutable — a new push silently replaces it. If a pod restarts or
  autoscaling adds a replica, Kubernetes pulls :latest and gets the new (possibly
  broken) image even though no deploy was requested. Immutable SHA tags guarantee
  that the image running in a pod never changes unless someone explicitly changes
  the image reference in the Deployment manifest. They also make the audit trail
  unambiguous: the image tag in kubectl describe is the exact commit SHA.

One thing unique to this repo's pipeline because of the GPG dependency:
  The processor-worker Docker image requires gnupg installed via apt-get. After
  building the image, the pipeline should verify this with a one-line smoke check:
    docker run --rm $REGISTRY/processor-worker:$TAG gpg --version
  This catches Dockerfile regressions (e.g., someone removes the apt-get layer)
  before the image is pushed to ECR. Additionally, the ubuntu-latest GitHub
  Actions runner has gpg pre-installed, so processor-worker tests pass in CI;
  but Alpine-based runners do not — avoid Alpine for jobs that exercise gnupg.
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
