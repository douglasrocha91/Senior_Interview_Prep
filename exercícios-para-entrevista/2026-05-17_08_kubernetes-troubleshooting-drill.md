# [SAP Concur Prep] 8) Kubernetes Troubleshooting Drill

**Date:** Sunday, 17 May 2026 · 4:00 – 6:00 pm  
**Objective:** Practice diagnosing and fixing common Kubernetes failures quickly under interview pressure.

---

## The Structured Troubleshooting Approach

Before diving into specific failures, commit this loop to muscle memory:

```
1. Observe   — what does the system say? (kubectl get, describe, logs)
2. Hypothesize — form one specific theory
3. Test      — run the smallest command that confirms or refutes it
4. Fix       — change exactly what the theory says to change
5. Verify    — confirm the symptom is gone, not just the error
```

Never jump to step 4 without completing step 3. This discipline is what interviewers are evaluating — they want narration, not guessing.

---

## Drill 1 — CrashLoopBackOff

### Scenario

Your `processor-worker` Pod enters `CrashLoopBackOff` five minutes after deployment.

### Diagnosis flow

```bash
# Step 1: What is the current state?
kubectl get pods -n file-platform

# Step 2: Get the full picture
kubectl describe pod <pod-name> -n file-platform
# Look at: Events section (bottom), Last State, Exit Code, Reason

# Step 3: Read the container logs
kubectl logs <pod-name> -n file-platform
# If the container has already restarted, read the previous run:
kubectl logs <pod-name> -n file-platform --previous

# Step 4: If the logs are empty (container crashes before writing anything)
# Check the Exit Code from describe:
#   Exit code 1  → application error (check logs)
#   Exit code 137 → OOMKilled (hit memory limit)
#   Exit code 139 → segfault
#   Exit code 143 → SIGTERM (graceful shutdown requested, expected)
```

### Common root causes and fixes

| Symptom in describe / logs | Root cause | Fix |
|---|---|---|
| `Error: missing required env var QUEUE_URL` | Missing ConfigMap or wrong key name | Fix `configMapRef` name or key |
| Process exits immediately, no output | Wrong entrypoint or CMD | Correct `command`/`args` in spec |
| `OOMKilled` in Last State | Memory limit too low | Increase `resources.limits.memory` |
| `Error opening /run/secrets/...` | Secret not mounted or wrong path | Verify `volumeMounts` and Secret name |
| App waits for DB connection, times out | Dependency not ready at startup | Add init containers or retry logic |

### Practice task

Introduce a deliberate crash and diagnose it:

```yaml
# Break it: wrong command
spec:
  containers:
    - name: processor
      image: python:3.12-slim
      command: ["python", "nonexistent_script.py"]
```

```bash
kubectl apply -f deployment-broken.yaml
kubectl get pods -n file-platform -w
kubectl describe pod <pod-name> -n file-platform
kubectl logs <pod-name> -n file-platform --previous
```

Write down: what signal told you the root cause? What would you check next if the logs were empty?

---

## Drill 2 — Image Pull Errors

### Scenario

New Pods are stuck in `ErrImagePull` or `ImagePullBackOff`.

### Diagnosis flow

```bash
kubectl describe pod <pod-name> -n file-platform
# Look at the Events section — it will contain the registry error message

# Common event messages:
# "Failed to pull image ... 401 Unauthorized"
# "Failed to pull image ... not found"
# "Failed to pull image ... connection refused"
# "Back-off pulling image"
```

### Common root causes and fixes

| Event message | Root cause | Fix |
|---|---|---|
| `401 Unauthorized` | No image pull secret or credentials expired | Create/update `imagePullSecrets` |
| `manifest unknown` or `not found` | Wrong tag or image does not exist | Fix image name/tag in spec |
| `connection refused` or DNS error | Registry unreachable from node | Check network policies, VPN, registry availability |
| `ImagePullBackOff` (no 401) | Kubernetes is backing off retries after failures | Fix the underlying error; backoff clears automatically |

### Fix: adding an image pull secret

```bash
# Create the pull secret
kubectl create secret docker-registry registry-credentials \
  --docker-server=your-registry.example.com \
  --docker-username=your-user \
  --docker-password=your-token \
  -n file-platform

# Reference it in the Deployment
spec:
  imagePullSecrets:
    - name: registry-credentials
  containers:
    - name: processor
      image: your-registry.example.com/processor-worker:1.2.3
```

### Practice task

```yaml
# Break it: wrong image tag
spec:
  containers:
    - name: processor
      image: python:99.0-slim   # does not exist
```

```bash
kubectl apply -f deployment-bad-image.yaml
kubectl get pods -n file-platform
kubectl describe pod <pod-name> -n file-platform | grep -A 20 Events
```

Write down: what is the difference between `ErrImagePull` and `ImagePullBackOff`?

---

## Drill 3 — Readiness and Liveness Probe Failures

### Scenario

Pods are running but `kubectl get pods` shows `0/1 READY`. Traffic is not being routed to the Pod.

### Diagnosis flow

```bash
# Step 1: Check readiness state
kubectl get pods -n file-platform
# READY column shows 0/1 → readiness probe is failing

# Step 2: Get probe failure details
kubectl describe pod <pod-name> -n file-platform
# Look for: "Readiness probe failed" in Events
# Note: the exact HTTP status or exec output is shown

# Step 3: Test the probe endpoint manually
kubectl exec -n file-platform <pod-name> -- wget -qO- http://localhost:8080/ready
# Or for liveness:
kubectl exec -n file-platform <pod-name> -- wget -qO- http://localhost:8080/healthz
```

### Common root causes and fixes

| Symptom | Root cause | Fix |
|---|---|---|
| `connection refused` on probe port | App started but not listening on that port | Fix `containerPort` or probe port |
| HTTP 404 on probe path | Wrong path in probe definition | Fix `httpGet.path` |
| HTTP 500 from app during startup | App not ready but probe fires too soon | Increase `initialDelaySeconds` or add `startupProbe` |
| Liveness fails → pod restarts in a loop | App is deadlocked or hung | Fix application bug; temporarily increase `failureThreshold` to debug |
| Probe passes but Pod not in endpoints | Label mismatch between Service selector and Pod | Align labels |

### Key distinction to remember

- **Liveness failure** → Kubernetes kills and restarts the container.
- **Readiness failure** → Kubernetes removes the Pod from Service endpoints but does NOT restart it. Traffic stops; container keeps running.

### Practice task

```yaml
# Break it: wrong probe path
livenessProbe:
  httpGet:
    path: /does-not-exist
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 2
```

```bash
kubectl apply -f deployment-bad-probe.yaml
kubectl get pods -n file-platform -w
# Watch the RESTARTS column increase
kubectl describe pod <pod-name> -n file-platform | grep -A 10 "Liveness"
```

Write down: how many seconds until the first restart? Compute it from the probe config above.

---

## Drill 4 — Env and Config Issues

### Scenario

The processor crashes with `KeyError: 'QUEUE_URL'` or processes files with the wrong batch size.

### Diagnosis flow

```bash
# Step 1: Verify what environment variables are actually present in the container
kubectl exec -n file-platform <pod-name> -- env | sort

# Step 2: Check that the ConfigMap exists and has the right keys
kubectl get configmap processor-config -n file-platform -o yaml

# Step 3: Check that the Deployment references the right ConfigMap
kubectl get deployment processor-worker -n file-platform -o yaml | grep -A 5 envFrom

# Step 4: Check that mounted files are present
kubectl exec -n file-platform <pod-name> -- ls /etc/processor/
kubectl exec -n file-platform <pod-name> -- cat /etc/processor/app.properties
```

### Common root causes and fixes

| Symptom | Root cause | Fix |
|---|---|---|
| Env var missing inside container | `configMapRef` name typo | Match name exactly (case-sensitive) |
| Old config value inside running pod | ConfigMap updated but pod not restarted | Restart deployment: `kubectl rollout restart deployment/processor-worker -n file-platform` |
| File not at expected mount path | Wrong `mountPath` or `items` key | Fix `volumeMounts` and `configMap.items` |
| Secret value garbled | Value was double-encoded to base64 when creating secret | Re-create secret with raw value; let Kubernetes encode it |

### Practice task

```bash
# Introduce a typo in the configMapRef name
kubectl edit deployment processor-worker -n file-platform
# Change: configMapRef.name: processor-config
# To:     configMapRef.name: processor-konfig   (wrong)

# Then:
kubectl get pods -n file-platform
kubectl describe pod <pod-name> -n file-platform
# Look for: "configmap processor-konfig not found"
```

Write down: what happens to the Pod if the ConfigMap is missing and the pod uses `envFrom` vs. a specific `valueFrom.configMapKeyRef`?

---

## Drill 5 — Service Not Routing Traffic

### Scenario

The API returns connection errors even though `kubectl get pods` shows all Pods running and ready.

### Diagnosis flow

```bash
# Step 1: Check the Service exists and has the right selector
kubectl get svc -n file-platform
kubectl describe svc api-svc -n file-platform
# Look at: Selector, Endpoints

# Step 2: Check whether the Service has Endpoints (populated = Pods matched the selector)
kubectl get endpoints api-svc -n file-platform
# If "<none>" → the label selector does not match any running Pod

# Step 3: Compare Service selector with Pod labels
kubectl get svc api-svc -n file-platform -o jsonpath='{.spec.selector}'
kubectl get pods -n file-platform --show-labels

# Step 4: If endpoints exist but traffic still fails, test from inside the cluster
kubectl run debug --image=busybox -it --rm -n file-platform -- sh
wget -qO- http://api-svc:80/healthz
```

### Common root causes

| Symptom in describe | Root cause |
|---|---|
| `Endpoints: <none>` | Label mismatch between Service selector and Pod labels |
| `Endpoints: <pod-ip>:8080` but connection refused | Pod port does not match `targetPort` |
| Connection times out (no reset) | Network policy blocking traffic |
| Works from inside cluster, not outside | LoadBalancer pending (no cloud LB provisioned) |

---

## Troubleshooting Checklist

Use this during the interview or a real incident. Check from the top down:

```
[ ] kubectl get pods — what is the phase? (Pending / Running / CrashLoopBackOff / etc.)
[ ] kubectl describe pod — read Events section top to bottom
[ ] kubectl logs --previous — what did the container say before it died?
[ ] kubectl exec -- env — are all required env vars present?
[ ] kubectl get configmap / secret — do the referenced objects exist?
[ ] kubectl get endpoints <svc> — does the Service have Pods behind it?
[ ] kubectl get events --sort-by='.lastTimestamp' -n file-platform — timeline view
[ ] Resource usage: kubectl top pods -n file-platform (if metrics-server is available)
[ ] Node pressure: kubectl describe node <node> | grep -A 5 Conditions
```

---

## Root Cause Analysis Template

After each drill, fill in one entry:

```
Symptom:
First command I ran:
What it showed:
Hypothesis:
Command that confirmed/refuted it:
Root cause:
Fix:
Time to diagnosis (estimate):
What would have slowed me down:
```

---

## Notes: Command Reference

```bash
# State inspection
kubectl get pods -n <ns> -w                        # watch live
kubectl get pods -n <ns> -o wide                   # show node assignment
kubectl describe pod <name> -n <ns>                # full detail + events
kubectl get events -n <ns> --sort-by='.lastTimestamp'

# Logs
kubectl logs <pod> -n <ns>
kubectl logs <pod> -n <ns> --previous             # last terminated container
kubectl logs <pod> -n <ns> -f                     # follow live

# Exec
kubectl exec -it <pod> -n <ns> -- sh              # interactive shell
kubectl exec <pod> -n <ns> -- env                 # dump env vars

# Config verification
kubectl get configmap <name> -n <ns> -o yaml
kubectl get secret <name> -n <ns> -o yaml
kubectl get deployment <name> -n <ns> -o yaml

# Service / networking
kubectl get endpoints <svc> -n <ns>
kubectl run debug --image=busybox -it --rm -n <ns> -- sh

# Rollout
kubectl rollout status deployment/<name> -n <ns>
kubectl rollout history deployment/<name> -n <ns>
kubectl rollout undo deployment/<name> -n <ns>
kubectl rollout restart deployment/<name> -n <ns>
```

---

## Interview Angle

### What interviewers are evaluating

They are not testing whether you have memorized every error message. They want to see a disciplined process: observe first, form a single hypothesis, test it with the smallest possible command, fix exactly what the hypothesis says. Narrate out loud — "I would check the Events section of describe because that is where Kubernetes records the actual failure signal."

### How to avoid guessing

Guessing is restarting pods or re-applying manifests without knowing why. Instead: read the exit code, read the event, form one theory, run one command to confirm it. If that command is inconclusive, form a new theory. This loop is the skill being tested.

### What to say when you are stuck

"I have ruled out X and Y. My next step would be to check Z because..." is a complete and strong answer. Admitting the boundaries of your knowledge while showing a rational next step is more valuable than a confident wrong answer.

### Common interview follow-ups

- "Walk me through how you would debug a pod that passes liveness but never becomes ready." — Check readiness probe separately; check the app's `/ready` logic; check if it depends on an external service that is down.
- "A deployment rollout is stuck at 50%. What do you check?" — `kubectl rollout status`; new pods likely failing readiness; `kubectl describe` the new pod; check logs.
- "How would you debug a performance issue where pods are running but slow?" — `kubectl top pods`; check CPU throttling (difference between usage and limit); check if the app is I/O-bound by reading app metrics.
