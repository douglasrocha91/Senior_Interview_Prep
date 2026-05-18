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

---

## Notes: Kubernetes Object Summary

Write your own mapping here after completing the exercises. Template:

```
Object → Purpose → File-processing service it maps to
Pod →
Deployment →
Service →
ConfigMap →
Secret →
Liveness probe →
Readiness probe →
Resource limits →
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
