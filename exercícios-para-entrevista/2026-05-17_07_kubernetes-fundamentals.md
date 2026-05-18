# [SAP Concur Prep] 7) Kubernetes Fundamentals for Interview

**Date:** Sunday, 17 May 2026 · 9:30 am – 12:00 pm  
**Objective:** Review the Kubernetes concepts most likely to come up in a production interview for file processing systems.

---

## Setup

All manifests in this exercise target a local cluster (kind, minikube, or Docker Desktop). Apply them with:

```bash
kubectl apply -f <file>.yaml
kubectl get all -n file-platform
```

Create a dedicated namespace to keep things tidy:

```bash
kubectl create namespace file-platform
```

---

## Exercise 1 — Pods

### Concept

A Pod is the smallest deployable unit in Kubernetes. It wraps one or more containers that share network and storage.

### Task

Write a bare Pod manifest for the `processor-worker` and apply it.

```yaml
# pod-processor.yaml
apiVersion: v1
kind: Pod
metadata:
  name: processor-worker
  namespace: file-platform
  labels:
    app: processor-worker
spec:
  containers:
    - name: processor
      image: python:3.12-slim
      command: ["python", "-c", "import time; time.sleep(3600)"]
      resources:
        requests:
          cpu: "100m"
          memory: "128Mi"
        limits:
          cpu: "500m"
          memory: "256Mi"
```

```bash
kubectl apply -f pod-processor.yaml
kubectl get pod processor-worker -n file-platform
kubectl describe pod processor-worker -n file-platform
```

### Observe and note

- What is the difference between `requests` and `limits`?
- What happens if a container exceeds its memory limit?
- Why would you almost never run a bare Pod in production?

### Answers

**Requests vs limits:** `requests` is the minimum guaranteed resource allocation — the scheduler uses it to decide which node has enough capacity to place the pod. `limits` is the maximum the container is allowed to consume. A container can use more than its `requests` if the node has spare capacity (burstable), but it can never exceed `limits`. CPU over-limit → container is throttled (slowed down, not killed). Memory over-limit → container is OOMKilled immediately.

**Exceeds memory limit:** The Linux kernel OOM killer terminates the container process. Kubernetes records `OOMKilled` in the pod's `LastState.Reason`. The container is restarted by the kubelet (if `restartPolicy` is `Always` or `OnFailure`). If it keeps hitting the limit and restarting, the pod enters `CrashLoopBackOff`.

**Why never a bare Pod in production:** A bare Pod has no controller watching it. If the pod crashes, the node fails, or the node is drained for maintenance, no one recreates it. There is no rolling update, no replica management, no self-healing. In production, always use a Deployment (stateless workloads), StatefulSet (stateful), or Job/CronJob (batch) — these controllers manage Pod lifecycle automatically.

---

## Exercise 2 — Deployments

### Concept

A Deployment manages a ReplicaSet, which maintains a desired number of identical Pod replicas and handles rolling updates.

### Task

Convert the Pod above into a Deployment with 2 replicas.

```yaml
# deployment-processor.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: processor-worker
  namespace: file-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: processor-worker
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels:
        app: processor-worker
    spec:
      containers:
        - name: processor
          image: python:3.12-slim
          command: ["python", "-c", "import time; time.sleep(3600)"]
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
```

```bash
kubectl apply -f deployment-processor.yaml
kubectl rollout status deployment/processor-worker -n file-platform
kubectl get pods -n file-platform -l app=processor-worker
```

### Verify rolling update

Change the image tag, apply, and watch the rollout:

```bash
kubectl set image deployment/processor-worker processor=python:3.11-slim -n file-platform
kubectl rollout status deployment/processor-worker -n file-platform
kubectl rollout history deployment/processor-worker -n file-platform
kubectl rollout undo deployment/processor-worker -n file-platform
```

### Observe and note

- What does `maxUnavailable: 1` mean in terms of service availability?
- What is the difference between a Deployment and a StatefulSet? When would a file processor use each?
- How does `kubectl rollout undo` work internally (which revision does it roll back to)?

### Answers

**`maxUnavailable: 1`:** During a rolling update with 2 replicas, at most 1 pod can be unavailable at any time. This means at least 1 pod is always running and handling requests throughout the update. Combined with `maxSurge: 1`, Kubernetes can spin up 1 extra pod (total: 3) before terminating the old ones, making the update faster. Setting `maxUnavailable: 0` would give zero-downtime rollouts at the cost of requiring a free node for the surge pod.

**Deployment vs StatefulSet:** A Deployment is for stateless workloads — all pods are interchangeable and can be killed and recreated in any order. Each pod gets a random suffix (`processor-worker-7d4f9b-xkj2p`). A StatefulSet is for stateful workloads — each pod gets a stable hostname (`worker-0`, `worker-1`), a stable network identity, and an ordered startup/shutdown sequence. For a file processor reading from SQS (stateless), a Deployment is correct. A StatefulSet would only be needed if each worker instance needed to own a specific partition of data (e.g., Kafka consumer group with sticky partition assignment).

**`kubectl rollout undo` internals:** Kubernetes stores Deployment history as a series of ReplicaSet snapshots, each annotated with a revision number. `rollout undo` with no arguments rolls back to the immediately previous revision (revision N-1). `rollout undo --to-revision=3` targets a specific revision. The undo operation creates a new ReplicaSet config equal to the old one — it does not modify history, it adds a new revision. You can see all revisions with `kubectl rollout history deployment/<name>`.

---

## Exercise 3 — Services

### Concept

A Service provides a stable network endpoint (DNS name + ClusterIP) to a dynamic set of Pods selected by labels.

### Task

Expose the `processor-worker` Deployment internally and an `api-service` externally.

```yaml
# service-processor.yaml
apiVersion: v1
kind: Service
metadata:
  name: processor-worker-svc
  namespace: file-platform
spec:
  selector:
    app: processor-worker
  ports:
    - port: 8080
      targetPort: 8080
  type: ClusterIP
```

```yaml
# service-api.yaml
apiVersion: v1
kind: Service
metadata:
  name: api-svc
  namespace: file-platform
spec:
  selector:
    app: api-service
  ports:
    - port: 80
      targetPort: 8000
  type: LoadBalancer
```

```bash
kubectl apply -f service-processor.yaml
kubectl apply -f service-api.yaml
kubectl get svc -n file-platform
```

### Observe and note

- What are the four Service types and when would you use each (`ClusterIP`, `NodePort`, `LoadBalancer`, `ExternalName`)?
- How does kube-proxy implement `ClusterIP` (iptables vs. IPVS)?
- Why is the `selector` the critical link between a Service and its Pods?

### Answers

**Four Service types:**
- `ClusterIP` (default): exposes the service on an internal cluster-only IP. Use for any service that only needs to be reachable by other pods (e.g., the processor-worker's metrics endpoint consumed by Prometheus inside the cluster).
- `NodePort`: exposes the service on a static port on every node's IP (range 30000–32767). Use for dev/staging access without a cloud load balancer, or for on-premises clusters without cloud integration.
- `LoadBalancer`: provisions an external cloud load balancer (AWS ALB/NLB, GCP LB) with a public IP. Use for production-facing APIs that need to be reachable from outside the cluster (e.g., `status-api` serving partner polling requests).
- `ExternalName`: maps the service to a DNS name via a CNAME record (`my-db.example.com`). Use to give cluster workloads a stable internal DNS alias for an external service (RDS, ElastiCache), so you can swap the external endpoint without changing application config.

**kube-proxy iptables vs IPVS:** With iptables mode (default in most clusters), kube-proxy writes iptables NAT rules for each Service endpoint. When a pod sends traffic to the ClusterIP, the kernel intercepts it and randomly selects one backend pod IP via a chain of iptables rules. With IPVS mode, kube-proxy uses the Linux kernel's IPVS (IP Virtual Server) table instead, which scales better for large clusters (O(1) vs O(N) rule lookup). IPVS also supports more load-balancing algorithms (round-robin, least connection, etc.) but requires the `ip_vs` kernel module.

**Why selector is critical:** The selector is the only mechanism that dynamically populates the Service's Endpoints object. When you create a Service, the endpoints controller watches for Pods that match all labels in the selector and are in `Ready` state — it writes their IPs into the Endpoints object. kube-proxy then uses those IPs for traffic routing. If the selector does not match any Pod (typo, label mismatch), `kubectl get endpoints <svc>` shows `<none>` and all traffic is dropped silently.

---

## Exercise 4 — ConfigMaps

### Concept

A ConfigMap decouples non-sensitive configuration from container images. Values can be injected as environment variables or mounted as files.

### Task

Create a ConfigMap for the processor's queue and batch settings, then consume it two ways.

```yaml
# configmap-processor.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: processor-config
  namespace: file-platform
data:
  QUEUE_URL: "https://sqs.us-east-1.amazonaws.com/123456789/file-upload-queue"
  BATCH_SIZE: "10"
  POLL_INTERVAL_SECONDS: "5"
  LOG_LEVEL: "INFO"
  app.properties: |
    queue.url=https://sqs.us-east-1.amazonaws.com/123456789/file-upload-queue
    batch.size=10
    poll.interval=5
```

```yaml
# Consume as env vars and as a mounted file
spec:
  containers:
    - name: processor
      image: python:3.12-slim
      envFrom:
        - configMapRef:
            name: processor-config
      volumeMounts:
        - name: config-volume
          mountPath: /etc/processor
  volumes:
    - name: config-volume
      configMap:
        name: processor-config
        items:
          - key: app.properties
            path: app.properties
```

```bash
kubectl apply -f configmap-processor.yaml
kubectl get configmap processor-config -n file-platform -o yaml
kubectl exec -n file-platform <pod-name> -- env | grep QUEUE
kubectl exec -n file-platform <pod-name> -- cat /etc/processor/app.properties
```

### Observe and note

- What happens to a running Pod when you update a ConfigMap and it is mounted as a volume? And when injected as `envFrom`?
- Why should credentials never go in a ConfigMap?
- What is the difference between `env`, `envFrom`, and `valueFrom.configMapKeyRef`?

### Answers

**ConfigMap update behaviour:** When a ConfigMap is mounted as a **volume**, Kubernetes syncs the updated content into the running pod within approximately 1–2 minutes (controlled by `kubelet --sync-frequency`). The application must detect the file change and re-read it — this is not automatic. When injected via **`envFrom`** (environment variables), the update has **no effect** on the running pod. Environment variables are set once at container start and never refreshed. The only way to pick up a ConfigMap change via `envFrom` is to restart the pod (`kubectl rollout restart deployment/<name>`).

**Why credentials never go in a ConfigMap:** ConfigMaps are stored unencrypted in etcd and are readable by any entity with `get configmap` permission in the namespace. They appear in plaintext in `kubectl get configmap -o yaml` output and in pod manifests. Credentials require at minimum a Kubernetes Secret (which enables RBAC restrictions and etcd encryption-at-rest), and ideally an external secret manager.

**`env` vs `envFrom` vs `valueFrom.configMapKeyRef`:**
- `env` with `valueFrom.configMapKeyRef`: injects a single specific key from a ConfigMap into a named env var. Fine-grained control. The var name in the container can differ from the ConfigMap key.
- `envFrom` with `configMapRef`: injects all keys from a ConfigMap as env vars, using the ConfigMap key names directly. Convenient but couples the container's env namespace to the ConfigMap structure.
- Plain `env` with hardcoded `value`: static value baked into the manifest. Use only for truly constant, non-environment-specific values.

---

## Exercise 5 — Secrets

### Concept

Secrets hold sensitive data (passwords, tokens, keys). By default they are base64-encoded, not encrypted — but they integrate with RBAC and can be backed by external secret managers.

### Task

Create a Secret for the AWS credentials used by the processor.

```bash
kubectl create secret generic aws-credentials \
  --from-literal=AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE \
  --from-literal=AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
  -n file-platform
```

```yaml
# Mount in deployment
spec:
  containers:
    - name: processor
      envFrom:
        - secretRef:
            name: aws-credentials
```

```bash
kubectl get secret aws-credentials -n file-platform -o yaml
# Note: values are base64, not encrypted
echo "d0phbHJYVXRuRkVNSS9LN01ERU5HL2JQeFJmaUNZRVhBTVBMRUtFWQ==" | base64 --decode
```

### Observe and note

- What does "base64 encoded, not encrypted" actually mean for security?
- How does Kubernetes RBAC restrict which pods and users can read a Secret?
- What is the difference between mounting a secret as a volume vs. injecting as env vars in terms of security posture?
- How would you integrate AWS Secrets Manager or HashiCorp Vault instead of native Secrets?

### Answers

**Base64 encoded, not encrypted:** Base64 is a reversible encoding, not encryption. Anyone who can read the Secret object (via `kubectl get secret -o yaml`, etcd access, or a cluster backup) can decode the value with `base64 --decode` in one second. The only security benefit over a ConfigMap is that the Kubernetes API and etcd can be configured to encrypt Secret objects at rest using AES-256 (`--encryption-provider-config`), and RBAC can grant different permissions to Secrets vs ConfigMaps. Without encryption-at-rest enabled, Secrets and ConfigMaps are equally exposed at the etcd level.

**RBAC restriction:** Access is controlled via RBAC `Role`/`ClusterRole` rules. A typical setup: the namespace's `ServiceAccount` bound to a `Role` that allows only `get` on specific Secret names — not `list` or `watch`, which would allow enumeration of all secrets. Example: `rules: [{apiGroups: [""], resources: ["secrets"], resourceNames: ["aws-credentials"], verbs: ["get"]}]`. Human operators get read access to their namespace's secrets; developers in other namespaces cannot access them at all.

**Volume mount vs env var for Secrets — security posture:**
- **Volume mount** is generally safer: the secret value is written to a `tmpfs` (in-memory filesystem), not to disk. It is rotated automatically when the Secret is updated (same sync as ConfigMap volumes). It is not visible in `/proc/<pid>/environ` or in crash dumps.
- **Env var injection** (`secretRef`) is less safe: the secret appears in `/proc/<pid>/environ` (readable by any process with access to `/proc` on the node), in `kubectl describe pod` output's env section, and in many logging libraries that dump all env vars on startup. Environment variables are also harder to rotate without restarting the pod.
For AWS credentials specifically, prefer a volume mount or, better, use IRSA (IAM Roles for Service Accounts) and eliminate the secret entirely.

**AWS Secrets Manager / Vault integration:** Use the [External Secrets Operator (ESO)](https://external-secrets.io/). Define an `ExternalSecret` CR that references an `aws-credentials` path in Secrets Manager. ESO syncs the value into a native Kubernetes Secret on a configurable schedule (e.g., every 1h). Your Deployment references the Kubernetes Secret as normal — no application code change. For HashiCorp Vault, use the Vault Agent Injector or ESO's Vault provider. The advantage: secret rotation in Secrets Manager automatically propagates to the cluster without manual `kubectl` operations.

---

## Exercise 6 — Probes

### Concept

Probes let Kubernetes determine whether a container is alive (liveness) and ready to receive traffic (readiness). A startup probe is used for slow-starting containers.

### Task

Add all three probes to the processor worker.

```yaml
spec:
  containers:
    - name: processor
      image: python:3.12-slim
      livenessProbe:
        httpGet:
          path: /healthz
          port: 8080
        initialDelaySeconds: 10
        periodSeconds: 15
        failureThreshold: 3
      readinessProbe:
        httpGet:
          path: /ready
          port: 8080
        initialDelaySeconds: 5
        periodSeconds: 10
        failureThreshold: 3
      startupProbe:
        httpGet:
          path: /healthz
          port: 8080
        failureThreshold: 30
        periodSeconds: 10
```

### Observe and note

- What happens when liveness fails? What happens when readiness fails? Are these the same?
- Why is a startup probe useful for workers that load large ML models or warm a large cache?
- What is `initialDelaySeconds` and why can removing it cause restart loops?
- A probe can use `httpGet`, `exec`, or `tcpSocket` — when would you choose each?

### Answers

**Liveness failure vs readiness failure — not the same:**
- **Liveness failure** → Kubernetes considers the container stuck or deadlocked. It kills the container and restarts it (respecting `restartPolicy`). The pod's `RESTARTS` counter increments.
- **Readiness failure** → Kubernetes removes the pod from the Service's Endpoints object. Traffic from other services stops reaching it. The container is **not** restarted — it keeps running. `kubectl get pods` shows `0/1 READY`.
The critical distinction: readiness is a "don't send me traffic" signal; liveness is a "I am broken, restart me" signal. A pod can be alive but not ready (e.g., warming up a connection pool). Never conflate the two probes.

**Why a startup probe is useful for slow starters:** The startup probe disables liveness and readiness checks while it runs, giving the container time to complete initialization. With the config above (`failureThreshold: 30`, `periodSeconds: 10`), the container has up to 300 seconds (5 minutes) to start before the liveness probe takes over. Without a startup probe, if a worker takes 90 seconds to load a model but `livenessProbe.initialDelaySeconds` is only 10s and `failureThreshold` is 3, the liveness probe fires 3 times during loading, concludes the container is dead, and restarts it — creating a restart loop before the container ever becomes healthy.

**`initialDelaySeconds`:** The number of seconds after the container starts before the first probe fires. Removing it means the first probe fires immediately at startup. If the application is not yet listening on the probe port (still importing modules, connecting to DB, etc.), the probe returns `connection refused`, which counts as a failure. With `failureThreshold: 3` and `periodSeconds: 15`, the container would be killed after 45 seconds even if it would have been healthy given more time.

**Probe type selection:**
- `httpGet`: use when the application exposes an HTTP health endpoint (most web services and APIs). Cleanest option — the app controls what "healthy" means.
- `exec`: use when there is no HTTP server (batch workers, CLI tools). Run a script or command inside the container (`exec: command: ["python", "-c", "import check; check.run()"]`). Higher overhead since it forks a process.
- `tcpSocket`: use when the application listens on a TCP port but does not speak HTTP (databases, message brokers, Redis). Only checks that the port accepts connections — does not test application logic.

---

## Exercise 7 — Resource Limits (Complete Manifest)

### Task

Write a complete, production-grade manifest combining everything above. Map it to the real `processor-worker` in this repo.

```yaml
# processor-deployment-full.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: processor-worker
  namespace: file-platform
  labels:
    app: processor-worker
    version: "1.0"
spec:
  replicas: 2
  selector:
    matchLabels:
      app: processor-worker
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels:
        app: processor-worker
    spec:
      serviceAccountName: processor-sa
      containers:
        - name: processor
          image: your-registry/processor-worker:latest
          ports:
            - containerPort: 8080
          envFrom:
            - configMapRef:
                name: processor-config
            - secretRef:
                name: aws-credentials
          resources:
            requests:
              cpu: "200m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 15
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          volumeMounts:
            - name: config-volume
              mountPath: /etc/processor
              readOnly: true
      volumes:
        - name: config-volume
          configMap:
            name: processor-config
```

### Observe and note

- What would happen if `requests` were set very low but `limits` were very high on a node under memory pressure?
- What is a `QoS class` and how does Kubernetes determine Guaranteed, Burstable, or BestEffort?
- What is a `PodDisruptionBudget` and why would you add one alongside this Deployment?

### Answers

**Low requests, high limits under memory pressure:** The scheduler places the pod on a node based on `requests`, so a pod with very low requests can be scheduled on an already-loaded node. If actual usage grows toward the high limit, the node may run out of memory. When the node is under memory pressure, the kubelet uses the QoS class to decide which pods to evict first: `BestEffort` pods go first, then `Burstable` (which this scenario produces — requests < limits). The processor-worker could be evicted mid-file, dropping the SQS message if visibility timeout expires before re-queuing. Setting requests close to actual steady-state usage avoids this.

**QoS classes:**
- `Guaranteed`: `requests == limits` for both CPU and memory on every container in the pod. The pod is never throttled below its requests and is the last to be evicted. Use for critical, latency-sensitive workloads.
- `Burstable`: at least one container has `requests < limits`, or requests are set but limits are not. The pod can burst but may be throttled or evicted under pressure. Suitable for the processor-worker — it has predictable steady-state but may spike during large CSV parsing.
- `BestEffort`: no `requests` or `limits` set at all. Evicted first under any pressure. Never use in production.

**PodDisruptionBudget (PDB):** A PDB caps the number of pods from a Deployment that can be simultaneously unavailable due to voluntary disruptions (node drains, cluster upgrades, manual evictions). Example: `minAvailable: 1` on this 2-replica Deployment ensures at least 1 processor-worker is always running even when a node is being drained for maintenance. Without a PDB, `kubectl drain` can terminate all pods at once, causing all in-flight SQS messages to time out. Adding a PDB is a 5-line manifest with a significant reliability improvement for any Deployment with `replicas >= 2`.

---

## Notes: Kubernetes Object Summary

```
Object → Purpose → File-processing service it maps to

Pod → Smallest runnable unit; one or more containers sharing network/storage
    → Each processor-worker or api-service instance is a Pod

Deployment → Manages replicas, rolling updates, and self-healing for stateless workloads
           → processor-worker (2 replicas, rolling update on new image tag)
           → status-api (serves partner HTTP requests, scales independently)

Service → Stable DNS name + ClusterIP that load-balances traffic to matching Pods
        → ClusterIP for internal services (processor metrics scraped by Prometheus)
        → LoadBalancer for status-api (external partner polling endpoint)

ConfigMap → Non-sensitive configuration decoupled from images; injected as env vars or files
          → QUEUE_URL, BATCH_SIZE, POLL_INTERVAL_SECONDS, LOG_LEVEL for processor-worker

Secret → Sensitive data with RBAC controls and optional etcd encryption-at-rest
       → AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY for SQS and S3 access
       → GPG private key (mounted as a volume, imported into GPG_HOME by init container)

Liveness probe → Detects deadlocked or hung containers and triggers an automatic restart
              → processor-worker /healthz: confirms the SQS polling loop is alive

Readiness probe → Gates traffic routing; removes pod from Service endpoints when not ready
               → processor-worker /ready: reports ready once GPG keyring is loaded and SQS connection established
               → status-api /ready: reports ready once DB/DynamoDB connection is verified

Resource limits → Requests: scheduler placement and QoS class assignment
               → Limits: hard ceiling; CPU → throttling; Memory → OOMKill
               → processor-worker: requests 200m/256Mi, limits 1/512Mi (Burstable QoS)
```

---

## Interview Angle

### Why each primitive exists

Each Kubernetes object solves a specific reliability or operations problem. Pods group containers with a shared lifecycle. Deployments add self-healing and rolling updates. Services decouple caller from instance IPs. ConfigMaps and Secrets separate configuration from code. Probes give the scheduler feedback so it does not route traffic to broken instances. Resource limits prevent one noisy tenant from starving others on the node.

### How this maps to a production file-processing service

The `processor-worker` in this repo is a natural worker Deployment: stateless, horizontally scalable, consumes a queue. The `api-service` is a ClusterIP or LoadBalancer target. ConfigMaps hold queue URLs and batch sizes. Secrets hold AWS credentials and GPG key references. Readiness probes keep the worker out of rotation while it initializes its keyring or warms the SQS long-poll connection.

### Common interview follow-ups

- "What happens during a rolling update if a new Pod fails its readiness probe?" — The rollout pauses; old Pods stay up.
- "How do you ensure zero downtime?" — `maxUnavailable: 0` + correct readiness probe + appropriate `terminationGracePeriodSeconds`.
- "How would you scale the worker based on queue depth?" — KEDA with an SQS scaler.
- "What is the difference between a Deployment and a Job/CronJob?" — Deployments run continuously; Jobs run to completion.
