# Kubernetes Setup Guide

Deploy the processor-worker and status-api to a local kind cluster.

---

## Prerequisites

- Docker Desktop installed and **running**
- `kind` installed: `brew install kind`
- `kubectl` installed: `brew install kubectl`
- Images built locally (see Step 3)

---

## 1. Create the Cluster

```bash
make cluster-up
```

This creates a single-node kind cluster named `mini-file-platform` with port 30080 mapped to host port 8080 (for the status API). The `mini-file-platform` namespace is also applied.

The command is **idempotent** — if the cluster already exists it skips creation and only re-applies the namespace.

Verify:

```bash
make cluster-status
```

---

## 2. Understand the Image Build Context

The Dockerfiles for `processor-worker` and `status-api` both `COPY shared/` as a dependency. Because `shared/` lives at the project root (not inside the service directory), the Docker build context must be the **project root** (`mini-file-platform/`), not the service subdirectory.

This is why the build command uses `-f $$svc/Dockerfile .` (dot = project root as context):

```bash
docker build -t mini-file-platform/processor-worker:dev \
  -f processor-worker/Dockerfile .
```

---

## 3. Build Service Images

```bash
make build
```

Builds both `processor-worker` and `status-api` images tagged as `:dev`.

---

## 4. Load Images into kind

kind clusters do not pull images from Docker Hub by default. Images must be loaded directly into the cluster nodes:

```bash
make cluster-load
```

This calls `kind load docker-image` for each service image. The Kubernetes manifests use `imagePullPolicy: Never` to ensure the locally loaded image is used.

---

## 5. Create the Kubernetes Secret

AWS credentials and other secrets must not be committed to git. A template is provided at `infra/kubernetes/secret.yaml`. Copy and fill it:

```bash
cp infra/kubernetes/secret.yaml infra/kubernetes/secret.local.yaml
```

Edit `secret.local.yaml` and replace the `REPLACE_ME` values:

```yaml
stringData:
  AWS_ACCESS_KEY_ID: "your-actual-key-id"
  AWS_SECRET_ACCESS_KEY: "your-actual-secret"
```

`infra/kubernetes/secret.local.yaml` is gitignored — it will never be committed.

---

## 6. Deploy to the Cluster

```bash
# Make sure SQS_QUEUE_URL is set — it is substituted into ConfigMap at deploy time
set -a && source .env && set +a

make cluster-deploy
```

This does the following in order:

1. Validates `SQS_QUEUE_URL` is set (fails fast if missing)
2. Runs `envsubst` on `configmap.yaml` to inject `SQS_QUEUE_URL` from the environment, then applies it
3. Applies `secret.local.yaml` (skipped with a warning if the file does not exist)
4. Applies `processor-worker-deployment.yaml`
5. Applies `status-api-deployment.yaml` (includes a NodePort Service on port 30080)

### Why envsubst for the ConfigMap

`SQS_QUEUE_URL` is environment-specific (different per AWS account/region). Committing it would couple the manifest to a single environment. `envsubst` reads the value from the shell environment at deploy time, so the committed YAML contains only the placeholder `${SQS_QUEUE_URL}`.

---

## 7. Verify the Rollout

```bash
make cluster-rollout
```

Restarts both deployments and waits until they are ready. Equivalent to:

```bash
kubectl rollout restart deployment/processor-worker -n mini-file-platform
kubectl rollout restart deployment/status-api -n mini-file-platform
kubectl rollout status deployment/processor-worker -n mini-file-platform
kubectl rollout status deployment/status-api -n mini-file-platform
```

---

## 8. Test the Status API

```bash
curl http://localhost:8080/health
# {"status":"ok"}

curl http://localhost:8080/transactions/<TID>
```

---

## Useful kubectl Commands

```bash
# List all resources in the namespace
kubectl get all -n mini-file-platform

# Stream worker logs
kubectl logs -f deployment/processor-worker -n mini-file-platform

# Stream API logs
kubectl logs -f deployment/status-api -n mini-file-platform

# Inspect environment variables in a running pod
kubectl exec -n mini-file-platform \
  $(kubectl get pod -n mini-file-platform -l app=processor-worker -o name | head -1) \
  -- env | grep -E "SQS|DYNAMO|S3|GPG"

# Restart a single deployment
kubectl rollout restart deployment/processor-worker -n mini-file-platform

# Describe a pod (shows events, image pull errors, etc.)
kubectl describe pod -n mini-file-platform -l app=processor-worker
```

---

## Tear Down

```bash
make cluster-down
```

Deletes the entire kind cluster including all workloads.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ImagePullBackOff` | Image not loaded into kind | `make cluster-load` |
| Pod in `CrashLoopBackOff` | Missing env var or secret | Check logs with `kubectl logs`, verify ConfigMap and Secret |
| Status API not reachable on :8080 | Port mapping not applied | Verify `cluster-config.yaml` has `hostPort: 8080` and cluster was created with that config |
| `SQS_QUEUE_URL not set` error on deploy | `.env` not sourced | `set -a && source .env && set +a` before `make cluster-deploy` |
| ConfigMap has empty SQS_QUEUE_URL | envsubst not installed | `brew install gettext` |
