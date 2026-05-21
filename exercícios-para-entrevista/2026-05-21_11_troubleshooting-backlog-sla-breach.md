# [SAP Concur Prep] 11) Troubleshooting Drill: Backlog and SLA Breach

**Date:** Thursday, 21 May 2026  
**Objective:** Practice incident-style thinking for high-volume file traffic, queue growth, and partial failures — produce a written incident plan with containment, recovery, and follow-up steps.

---

## Context: The Pipeline and Its SLA

Before reasoning about an incident, fix the system and its promise in your head:

```
[submitter-cli] → S3 inbound → ingest-lambda → SQS (file-jobs) → [processor-worker] → S3 results
                                                      │                    ↓
                                                      │            DynamoDB (status)
                                              (DLQ: file-jobs-dlq)         ↑
                                                                   [status-api] ← partner HTTP
```

| Property | Value | Where it comes from |
|---|---|---|
| SLA | 95% of files reach `PROCESSED` within **15 minutes** of upload | Partner contract (assumed for this drill) |
| Queue | `file-jobs` SQS, visibility timeout **30s** | `docs/failure-scenarios.md` |
| Retries | `maxReceiveCount = 3`, then routed to `file-jobs-dlq` | DLQ redrive policy |
| Worker concurrency | `processor-worker` Deployment, **1 message at a time per pod** (`_MAX_MESSAGES = 1`) | `processor-worker/app/consumer.py` |
| Long-poll | `WaitTimeSeconds = 20` | `consumer.py` |
| Failure classes | business → `PROCESSED`+errors / infra → `FAILED`+retry / poison → DLQ | `docs/failure-scenarios.md` |

The single most important number to compute in any backlog incident:

```
drain time = queue_depth / (worker_throughput_msgs_per_sec)

worker_throughput ≈ (number of ready pods) × (1 / seconds_per_message)
```

If `drain time` is climbing or already exceeds the SLA window, you are in (or heading into) an SLA breach. Everything else is in service of bringing that number down safely.

---

## The Incident Response Loop

Commit this to muscle memory — it is the spine of every answer in this drill:

```
1. Detect    — confirm the symptom with a metric, not a hunch (queue depth, oldest-message age)
2. Triage    — assess customer impact and severity; declare an incident if SLA is at risk
3. Contain   — stop the bleeding (cap the inflow, isolate poison, prevent cascade)
4. Diagnose  — find the bottleneck or fault with the smallest decisive check
5. Recover   — drain safely (scale out, redrive DLQ) without re-breaking anything
6. Verify    — confirm oldest-message age is falling and SLA is recovering
7. Follow up — blameless write-up, action items, guardrails to prevent recurrence
```

Two rules that separate senior incident handling from junior:
- **Contain before you fully diagnose.** You do not need root cause to stop customer harm.
- **Protect customer impact over your own curiosity.** Capture evidence, then recover; do a full RCA after the bleeding stops.

---

## Exercise 1 — Detect and Triage the Backlog

### Concept

A backlog is not "the queue has messages" — a healthy queue always has some. A backlog is **depth growing faster than it drains**, or **oldest message age exceeding the SLA budget**. The two metrics that matter are `ApproximateNumberOfMessagesVisible` (depth) and `ApproximateAgeOfOldestMessage` (latency). Depth tells you *how much* work is waiting; age tells you *whether the SLA is already breaking*.

### Task

You are paged: "files are slow." List the first signals you inspect, in order, and what each one tells you.

```
Signal 1 — SQS ApproximateAgeOfOldestMessage (file-jobs)
  → Is the SLA already breached? If oldest message > 15 min, yes. This is the
    customer-facing number. Inspect FIRST.

Signal 2 — SQS ApproximateNumberOfMessagesVisible (depth) + its slope
  → How big is the backlog and is it growing or shrinking? Slope matters more
    than the absolute number. Flat-and-large is different from small-and-rising.

Signal 3 — SQS NumberOfMessagesReceived/Deleted by the worker (throughput)
  → Are workers draining at all? Deleted/min ≈ 0 means processing has stalled,
    not just that inflow spiked.

Signal 4 — DLQ depth (file-jobs-dlq)
  → Is this a poison-message storm? A rising DLQ alongside the backlog points to
    bad input, not capacity.

Signal 5 — processor-worker pod health (kubectl get pods, READY, RESTARTS)
  → Are the consumers even alive? CrashLoop / 0-ready pods = zero throughput
    regardless of queue size.

Signal 6 — Inflow rate (ingest-lambda invocations / S3 PUT rate)
  → Is this a demand spike (partner dumped a batch) or a capacity collapse
    (workers died)? Same backlog, opposite remedies.
```

### Observe and note

- Why inspect *oldest message age* before queue depth?
- What is the difference in remedy between "depth rising, throughput normal" and "depth rising, throughput collapsed"?
- When do you declare an incident vs. just keep watching?

### Answers

**Why oldest-message age first:** Depth is an internal number; age is the customer's experience. A queue can hold 50,000 messages and still be fine if it is draining in 3 minutes — and a queue of 200 messages can be an active SLA breach if the oldest has been stuck for 40 minutes behind a stalled consumer. Age maps directly onto the SLA clock ("95% within 15 minutes"), so it tells you immediately whether you are in violation and how much budget remains. You triage severity off age, then use depth and throughput to plan the fix.

**Depth rising + throughput normal vs. depth rising + throughput collapsed:**
- *Throughput normal* (workers still deleting messages at the usual rate): this is a **demand spike** — inflow exceeds capacity. Remedy is to **add capacity** (scale out worker replicas) and/or **shed/slow inflow**. The system is healthy, just undersized for the moment.
- *Throughput collapsed* (deletes ≈ 0): this is a **processing fault** — a downstream dependency is down (DynamoDB unreachable, S3 throttling), the workers are crashing, or every message is failing and being retried. Adding replicas does nothing if each new pod also fails. Remedy is to **find and fix the fault first**; scaling comes after throughput is restored.

The cheap discriminator: look at deletes/min. Same backlog shape, completely different root cause and fix. This is the single most common trap in a backlog interview question — candidates reflexively say "scale up" without checking whether the workers are processing at all.

**When to declare an incident:** Declare when the SLA is breached or the projection says it will breach before you can fix it without coordination. Concretely: oldest-message age has crossed (or will cross within the drain-time estimate) the 15-minute budget, *and* the trend is not self-correcting. A short spike that is already draining on its own does not need a declared incident — declaring has a cost (people, comms, focus). Senior judgment is declaring early enough to mobilize but not crying wolf on every transient blip. If unsure, declare at a low severity; downgrading is cheap, a silent breach is not.

---

## Exercise 2 — Diagnose SLA Breach Causes

### Concept

An SLA breach in this pipeline has a small number of distinct root causes, and each leaves a different fingerprint across the same handful of metrics. Diagnosis is pattern-matching the fingerprint, not guessing.

### Task

Fill in the diagnosis table: for each root cause, what the signals look like and the smallest command/check that confirms it.

| Root cause | Fingerprint | Confirming check |
|---|---|---|
| **Demand spike** (partner batch dump) | Depth ↑, age ↑, throughput **normal**, DLQ flat, inflow (Lambda invocations) spiked | CloudWatch: `ingest-lambda` Invocations and S3 PUT count jumped at T0 |
| **Worker capacity collapse** | Depth ↑, age ↑, throughput **→ 0**, pods not Ready / CrashLoop | `kubectl get pods -n mini-file-platform` shows 0/N Ready or RESTARTS climbing |
| **Downstream dependency slow/down** | Depth ↑, throughput **low but nonzero**, worker logs show timeouts to DynamoDB/S3, many `FAILED` | `kubectl logs` shows `infrastructure failure`; DynamoDB/S3 latency/throttle metrics elevated |
| **Poison-message storm** | DLQ ↑ fast, depth may be flat, worker busy but few `PROCESSED`, repeated parse errors | `make scenario-dlq` / check DLQ depth; logs show `malformed SQS message body` |
| **Per-message slowdown** (big files / GPG) | Throughput ↓ (seconds_per_message ↑), CPU high, no errors, depth creeps | Worker CPU at limit (`kubectl top pods`); processing-duration metric per file rising |
| **Retry amplification** | Effective inflow > real inflow; same transaction_ids reappear; visibility-timeout expiries | Logs show same `transaction_id` received 2–3×; `ApproximateNumberOfMessagesNotVisible` high |

### Observe and note

- How does a too-short visibility timeout *create* a backlog out of nothing?
- Why can a single slow downstream dependency look identical to a capacity problem at first glance?
- What is the failure mode if the worker marks infra failures as `FAILED` but the file is actually fine?

### Answers

**Too-short visibility timeout creates phantom load:** The worker takes, say, 45 seconds to download + decrypt + validate + write a large file, but the queue's visibility timeout is 30 seconds. SQS makes the message visible again at 30s — before the worker finishes — so a *second* pod picks up the same message and starts processing it in parallel. Both eventually finish; one deletes it, the other's delete may fail or operate on a stale receipt handle. Net effect: every slow message is processed two or three times, the queue's effective load is 2–3× the real inflow, and `ApproximateNumberOfMessagesNotVisible` balloons. You burn capacity reprocessing work you already did, and the backlog grows even though no extra files arrived. The fix is to set visibility timeout safely above the p99 processing time (e.g., 6× the average), or extend it heartbeat-style during long processing. This is a classic "the backlog is self-inflicted" cause and a strong thing to name in an interview.

**Slow dependency vs. capacity — why they look alike:** Both show depth rising and the customer waiting. The discriminator is *throughput shape and worker state*. Capacity collapse → throughput at or near zero, pods unhealthy. Slow dependency → throughput is **low but nonzero**, pods are healthy and busy, and the worker *logs* tell the truth: repeated `infrastructure failure` / timeout lines pointing at DynamoDB or S3. Adding worker replicas against a slow dependency often makes it *worse* — more pods hammer the already-struggling dependency (or trip its throttling), reducing throughput further. So you must read the logs before you scale: scaling is the right move for capacity, the wrong move for a saturated downstream.

**Falsely marking a healthy file `FAILED`:** If a transient downstream blip (DynamoDB throttling, S3 5xx) causes `process_job` to return `False`, the file is genuinely fine but gets retried up to 3× and then lands in the DLQ as if it were broken input. Under load this is dangerous: a dependency wobble during a spike can dump thousands of *valid* files into the DLQ, turning a temporary slowdown into a pile of stuck transactions that now require manual redrive. The mitigation is to distinguish *retryable* infra errors (throttling, timeouts → back off and retry, do not count hard against `maxReceiveCount` if possible) from *permanent* errors (object truly missing, decrypt of genuine garbage), and to size `maxReceiveCount` and backoff so a brief dependency blip does not exhaust retries.

---

## Exercise 3 — Containment: Stop the Bleeding

### Concept

Containment buys time and caps customer harm *before* you understand everything. Good containment is reversible, fast, and targeted at the dominant cause from Exercise 2. You are not fixing the root cause yet — you are stopping it from getting worse.

### Task

For each dominant cause, write the containment action and why it is safe (reversible).

```
Cause: Demand spike (healthy system, too much inflow)
  Contain → Scale out processor-worker replicas now (kubectl scale / raise HPA max).
            Optionally request the partner pause/throttle the batch upload.
  Safe?   → Yes. Scaling out is reversible (scale back later). No data touched.

Cause: Poison-message storm
  Contain → Let SQS route poison to the DLQ (already automatic after 3 receives) —
            do NOT delete them. If a known-bad batch is identified, stop that
            partner's inflow at the source (disable the S3 prefix / Lambda trigger
            for that prefix) so good traffic is not starved behind parse failures.
  Safe?   → Yes. DLQ isolates bad input without losing it; isolation is reversible.

Cause: Downstream dependency slow/down (DynamoDB / S3)
  Contain → Do NOT scale workers (would amplify load on the dependency). Reduce
            concurrency if needed. Pause non-critical writers. Open a parallel
            track to recover the dependency (throttling limits, capacity, failover).
  Safe?   → Yes. Reducing concurrency only slows processing; nothing is dropped.
            Messages wait safely in SQS (up to 14-day retention).

Cause: Visibility-timeout reprocessing
  Contain → Increase the queue's visibility timeout above p99 processing time
            immediately. This stops duplicate pickups right away.
  Safe?   → Yes. Larger visibility timeout only delays redelivery of genuinely
            stuck messages; it cannot lose work.

Cross-cutting:
  - Communicate: post incident channel, set severity, notify stakeholders/partner.
  - Preserve evidence: snapshot metrics, grab logs, note timestamps for the RCA.
  - Remember the safety net: SQS retains messages up to 14 days. The backlog is
    uncomfortable, not lost. That fact lowers the pressure to do something rash.
```

### Observe and note

- Why is "the queue retains messages for up to 14 days" a containment fact, not just trivia?
- When is throttling *your own inflow* the right first move, and when is it harmful?
- Why is scaling workers the *wrong* containment step for a downstream-dependency incident?

### Answers

**14-day retention as a containment fact:** It reframes the incident. The worst-case outcome of a backlog is not data loss — it is *delay*. Knowing messages survive for 14 days means you can confidently slow or pause processing to protect a fragile downstream, take time to redrive the DLQ carefully, or hold traffic while you fix a bug, all without losing a single file. Junior responders panic because they implicitly fear the queue will "overflow" and drop work; senior responders use retention as headroom to recover *safely* rather than *fast-and-reckless*. State this explicitly in an interview — it shows you understand the durability guarantees you are standing on.

**Throttling your own inflow — when right, when harmful:** Right when the bottleneck is downstream and irreducible in the moment (DynamoDB at its throttle ceiling, S3 5xx-ing): slowing inflow prevents the backlog from growing while you recover the dependency, and prevents the dependency from being pushed further into failure. Harmful when the system is actually healthy and just needs capacity (a demand spike) — there, throttling inflow needlessly delays the partner's files when you could simply add workers and drain fast. Throttle inflow to protect a fragile downstream; add capacity to absorb a healthy spike. Diagnosing which (Exercise 2) is the prerequisite.

**Scaling is wrong for a downstream incident:** Each worker pod independently calls DynamoDB and S3. If those are the bottleneck (throttling, slow), adding pods multiplies the call rate against an already-saturated dependency — you push it deeper into throttling, throughput drops further, and you may trip cascading failures or exhaust retries on otherwise-good files. The fix for a saturated dependency is *less* concurrency plus capacity/limit work on the dependency itself, not more consumers. Reflexive "scale up" is the most common wrong answer here precisely because it is correct for the *demand-spike* case and people pattern-match without diagnosing.

---

## Exercise 4 — Plan Safe Partial Recovery

### Concept

Recovery is draining the backlog and clearing the DLQ **without re-triggering the incident**. "Safe" and "partial" are the key words: you recover in controlled increments, watching the customer-facing metric fall, ready to stop if you see the fault return. A reckless full-throttle drain can re-saturate the very dependency that caused the breach.

### Task

Write the staged recovery plan for a mixed incident (demand spike that also pushed some good files into the DLQ during a brief DynamoDB throttle).

```
Stage 0 — Precondition
  Confirm the root fault is contained (DynamoDB throttle resolved / capacity raised).
  Do not start draining into a still-broken dependency.

Stage 1 — Restore throughput on the live queue
  Scale processor-worker incrementally (e.g., 3 → 6 → 12 replicas), pausing ~2 min
  between steps to watch:
    - ApproximateAgeOfOldestMessage falling (the SLA number recovering)
    - DynamoDB/S3 latency staying healthy (not re-saturating)
  If downstream latency climbs, stop scaling — you found the new ceiling.

Stage 2 — Verify the live queue is draining
  Throughput (deletes/min) > inflow (Lambda invocations/min). Drain time estimate
  now shrinking. Oldest-message age trending toward < 15 min.

Stage 3 — Triage the DLQ before redriving
  Sample DLQ messages. Separate:
    (a) genuinely poison (malformed JSON, truly corrupt files) — keep isolated,
        do NOT redrive blindly; they will just fail again and waste capacity.
    (b) good files that failed only due to the transient throttle — these are
        safe to redrive once the dependency is healthy.

Stage 4 — Redrive the DLQ in small batches
  Move category (b) back to file-jobs in controlled batches (SQS DLQ redrive,
  capped maxNumberOfMessagesPerSecond). Watch the same two metrics. Redriving the
  whole DLQ at once can re-spike the dependency — defeating the recovery.

Stage 5 — Scale back down
  Once oldest-message age is comfortably under SLA and DLQ is drained/triaged,
  return replicas to baseline (or let the HPA do it). Confirm steady state holds.
```

### Observe and note

- Why redrive the DLQ in capped batches instead of all at once?
- Why must you triage the DLQ before redriving, and what is idempotency's role?
- What single metric tells you the recovery is actually working?

### Answers

**Capped-batch redrive:** A DLQ that filled during a 10-minute throttle can hold thousands of messages. Redriving them all into `file-jobs` at once creates an instant second spike on top of whatever live traffic is already there — the same load pattern that caused the breach. If the dependency is still near its ceiling, you re-trigger the incident with your own recovery action. Capping the redrive rate (and watching downstream latency between batches) lets you pour the backlog back in at a pace the system can absorb. Recovery should be a controlled drip, not a flush.

**Triage before redrive + idempotency:** Blindly redriving the DLQ sends genuinely poison messages straight back through three more receive attempts before they return to the DLQ — pure wasted capacity during an incident, and noise that hides the real recoverable work. So you separate truly-bad input (keep isolated, handle manually) from good-files-caught-in-the-blast (safe to redrive). Idempotency matters because some DLQ files may have *partially* processed before failing — e.g., the DynamoDB status write succeeded but the S3 result write did not. Reprocessing must be safe to repeat: writing the same `transaction_id` status again, or the same result object again, must not corrupt state or double-count. If processing is idempotent (keyed on `transaction_id`), redrive is safe even for partially-processed files; if it is not, you risk duplicate side effects and must dedupe first. Naming idempotency here is a strong senior signal.

**The one metric that proves recovery:** `ApproximateAgeOfOldestMessage` falling and crossing back under the 15-minute SLA budget. Depth falling is necessary but not sufficient (depth can fall while the *oldest, most-breached* messages still sit stuck behind something). Age is the customer's actual wait time and the SLA's definition — when the oldest message is young again, the breach is over. Throughput > inflow is the *leading* indicator (it predicts age will fall); age crossing under SLA is the *confirming* indicator.

---

## Exercise 5 — Frame the Incident Response Narrative

### Concept

How you *tell* the incident story is itself part of the skill being assessed. A good narrative is calm, ordered, customer-first, and honest about uncertainty. It follows the loop, names the customer-facing metric throughout, and ends with prevention — not blame.

### Task

Write the incident narrative as you would speak it in a debrief (or an interview "walk me through how you'd handle this").

```
"At 14:02 we were paged that file processing was slow. I first checked the
 oldest-message age on the file-jobs queue — it was 11 minutes and climbing
 toward our 15-minute SLA, so I declared a Sev-2 and opened the incident channel.

 Depth was rising and, critically, worker throughput was still normal — deletes
 per minute were healthy and the pods were all Ready. That pattern said demand
 spike, not capacity collapse. CloudWatch confirmed it: ingest-lambda invocations
 had tripled at 13:55 — a partner had dumped a large batch.

 To contain, I scaled processor-worker from 3 to 6 replicas immediately, since
 scaling out is reversible and touches no data, and I asked the partner to pause
 the remainder of their upload. I also confirmed our safety net: SQS retains
 messages for 14 days, so nothing was at risk of being lost — the issue was delay,
 not data loss.

 During the spike a brief DynamoDB throttle pushed a few hundred *valid* files
 into the DLQ. So recovery had two tracks. On the live queue, I scaled in steps —
 6 then 12 replicas — pausing to confirm oldest-message age was falling and
 DynamoDB latency stayed healthy. Once the live queue was draining faster than
 inflow, I triaged the DLQ, separated the throttle-victims from any genuine poison,
 and redrove the good ones back in capped batches so I wouldn't re-spike DynamoDB.

 By 14:41 oldest-message age was back under 4 minutes, well inside SLA. I scaled
 replicas back to baseline and confirmed steady state. Follow-ups: add an HPA on
 queue depth so this scales automatically, alert on oldest-message age (not just
 depth), distinguish retryable infra errors from permanent ones so a throttle
 blip doesn't fill the DLQ with good files, and review the partner onboarding to
 rate-limit bulk uploads."
```

### Observe and note

- What makes this narrative "senior" rather than "junior"?
- Why mention the 14-day retention and reversibility *out loud*?
- Why do the follow-ups matter as much as the fix?

### Answers

**What makes it senior:** It leads with the *customer-facing* metric and the SLA, not internal trivia. It *diagnoses before acting* (throughput-normal → demand spike) instead of reflexively scaling. Every action is justified by why it is *safe* (reversible, no data touched). It handles the *partial* failure (DLQ of good files) as a distinct, careful track rather than lumping everything together. It recovers in *controlled increments* with a stop condition. And it ends with *systemic prevention*, not "we scaled up and it was fine." Junior narratives jump to a fix, omit the metric that defines success, and treat recovery as one big button.

**Saying retention and reversibility out loud:** It demonstrates you understand the guarantees you are leaning on, and it is what *justifies* a calm, staged response. "Nothing is lost, only delayed" is the sentence that licenses you to recover safely instead of recklessly — and an interviewer wants to hear that you know *why* you can afford to be careful. It also reassures stakeholders in a real debrief: the scariest words in an incident are "did we lose data?", and answering that proactively de-escalates the room.

**Why follow-ups carry weight:** An incident you fix manually but do not prevent will recur — and the next on-call may not pattern-match it as fast. The follow-ups convert a one-time heroic recovery into a durable improvement: autoscaling removes the manual scale step, alerting on *age* (not just depth) catches the right symptom earlier, and the retryable-vs-permanent error distinction stops a dependency blip from manufacturing a DLQ full of good files. Interviewers weight this heavily because it is the difference between someone who *fights fires* and someone who *makes the system stop catching fire*.

---

## Exercise 6 — Connect to This Repo

Review `processor-worker/app/consumer.py`, `docs/failure-scenarios.md`, and `infra/kubernetes/processor-worker-deployment.yaml`, then answer:

1. The consumer sets `_MAX_MESSAGES = 1` and processes one message at a time per pod. Under a backlog, what is the *only* way to increase throughput, and what is the trade-off?

2. `docs/failure-scenarios.md` says infra failures return `False` and the message is retried up to 3 times before the DLQ. During a DynamoDB outage, what happens to the queue, and how would you prevent good files from draining into the DLQ?

3. The poison-message scenario relies on a 30-second visibility timeout to re-deliver. If average processing time rose above 30s under load, what new failure would appear, and how would you fix it?

4. There is no autoscaling on `processor-worker` today. Write the conceptual HPA/KEDA trigger you would add so the worker scales on backlog automatically.

5. The status-api reads transaction state from DynamoDB. During a backlog, what will a partner polling status see, and how would you keep that experience honest?

### Answers

**1. Increasing throughput with `_MAX_MESSAGES = 1`:** Because each pod processes strictly one message at a time, the *only* lever for throughput is **horizontal scale — more pods** (`kubectl scale deployment/processor-worker` or a higher HPA max). You cannot get a single pod to do more concurrent work without changing the code. The trade-off: every added pod is another independent consumer hitting S3 and DynamoDB, so throughput scales linearly only until a downstream dependency becomes the bottleneck. Past that point, more pods reduce throughput (contention/throttling). So the scaling answer is always bounded by downstream capacity — name that bound in the interview. (A code-level alternative is to raise `_MAX_MESSAGES` and process a batch, but that increases per-pod blast radius and complicates the delete/retry logic; horizontal scale is the safer operational lever.)

**2. DynamoDB outage behavior + protecting good files:** Every `process_job` that needs to write status hits the outage, returns `False`, and the message is retried. With `maxReceiveCount = 3`, a sustained outage longer than `3 × visibility_timeout` will march *valid* files through all three receives and into the DLQ — turning a transient dependency outage into a pile of stuck-but-fine transactions. To prevent it: (a) **contain by pausing/slowing consumption** during the outage so messages wait in `file-jobs` (14-day retention) instead of burning retries — e.g., scale the worker to 0 or pause polling until DynamoDB is back; (b) distinguish *retryable* infra errors (throttle/timeout → back off, ideally without consuming the receive budget) from *permanent* ones; (c) raise `maxReceiveCount` / add backoff so a short outage cannot exhaust retries. The key insight: a healthy queue with paused consumers is far better than a DLQ full of good files.

**3. Processing time exceeding the 30s visibility timeout:** SQS would re-deliver each in-flight message *before the worker finished*, so a second pod would pick up and reprocess the same file — **duplicate processing**, wasted capacity, `ApproximateNumberOfMessagesNotVisible` climbing, and a backlog that grows from reprocessing rather than new inflow. Fix: raise the visibility timeout well above p99 processing time (rule of thumb 6× average), or extend visibility heartbeat-style (`ChangeMessageVisibility`) during long jobs. If processing is idempotent on `transaction_id`, duplicates are merely wasteful; if not, they can corrupt state — another reason to make `process_job` idempotent.

**4. Conceptual autoscaling trigger:** Use **KEDA** with an SQS scaler so the worker scales on *queue backlog*, which a CPU-based HPA would miss (a pod blocked on a slow download is idle on CPU but the queue is still growing):

```yaml
# Conceptual KEDA ScaledObject for processor-worker
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: processor-worker-scaler
  namespace: mini-file-platform
spec:
  scaleTargetRef:
    name: processor-worker
  minReplicaCount: 1
  maxReplicaCount: 20          # bounded by downstream (DynamoDB/S3) capacity
  triggers:
    - type: aws-sqs-queue
      metadata:
        queueURL: <file-jobs-url>
        queueLength: "10"      # target ~10 backlog messages per pod
        awsRegion: us-east-1
```

`queueLength: 10` means KEDA targets roughly 10 visible messages per replica — backlog grows, replicas grow, backlog drains, replicas shrink to `minReplicaCount`. Cap `maxReplicaCount` at the point where downstream becomes the bottleneck so autoscaling cannot self-inflict a dependency saturation incident.

**5. Partner status experience during a backlog + keeping it honest:** A partner polling `status-api` for a freshly uploaded file sees **no record / not-found or a `PENDING`-style state**, because the worker has not reached that message yet to write a DynamoDB row — the file is sitting in `file-jobs`, untouched. The risk is the partner interpreting "not found" as "lost" and re-uploading, *adding* to the backlog (retry amplification from the outside). To keep it honest: write an early `RECEIVED`/`QUEUED` status at ingest time (e.g., from `ingest-lambda` when it publishes to SQS) so the file has a visible state the instant it is accepted, and surface an honest "queued, processing may be delayed" message during a known incident rather than a bare 404. An accurate "we have it, it's queued" status prevents the customer from making the backlog worse.

---

## Notes: Backlog Incident Playbook (Quick Reference)

```
FIRST 60 SECONDS — detect & triage
  [ ] SQS ApproximateAgeOfOldestMessage (file-jobs)  → SLA breached? (>15 min)
  [ ] SQS depth + slope                              → how big, growing or shrinking?
  [ ] Worker deletes/min (throughput)                → draining or stalled (≈0)?
  [ ] DLQ depth                                       → poison storm?
  [ ] kubectl get pods                               → consumers alive & Ready?
  [ ] ingest-lambda invocations / S3 PUTs            → demand spike or capacity loss?
  → Declare incident if age is over (or will cross) SLA and not self-correcting.

DIAGNOSE — match the fingerprint (throughput is the key discriminator)
  throughput normal + inflow spiked     → DEMAND SPIKE       → scale out
  throughput ≈ 0 + pods unhealthy       → CAPACITY COLLAPSE  → fix pods, then scale
  throughput low + infra-failure logs   → SLOW DEPENDENCY    → do NOT scale; recover dep
  DLQ rising fast + parse errors        → POISON STORM       → isolate bad input
  duplicates / NotVisible high          → VISIBILITY TIMEOUT → raise timeout

CONTAIN — reversible, fast, targeted
  [ ] Right lever for the cause (scale OUT for spike; scale DOWN for slow dep)
  [ ] Isolate poison in DLQ (do not delete)
  [ ] Raise visibility timeout if reprocessing
  [ ] Communicate; set severity; notify partner
  [ ] Remember: SQS retains 14 days → delay, not loss

RECOVER — staged, watch the customer metric
  [ ] Confirm root fault contained before draining
  [ ] Scale in increments; pause to watch age fall + downstream stay healthy
  [ ] Triage DLQ: poison vs. good-files-caught-in-blast
  [ ] Redrive DLQ in capped batches (idempotent processing makes this safe)
  [ ] Scale back to baseline once age is comfortably under SLA

FOLLOW UP — make it not recur
  [ ] Autoscale on queue depth (KEDA), not CPU
  [ ] Alert on oldest-message AGE, not just depth
  [ ] Retryable vs. permanent error classification
  [ ] Early RECEIVED status at ingest for honest partner visibility
  [ ] Blameless postmortem; rate-limit bulk partner uploads
```

---

## Interview Angle

### What interviewers are evaluating

They want to see **disciplined incident thinking under pressure**, not a list of AWS commands. The signal they are listening for: do you *diagnose before you act*, do you lead with the *customer-facing* metric, and do you recover *safely* rather than just fast? The single biggest differentiator is resisting the reflex to "just scale up" and instead asking "is the worker even processing?" first. Narrate the loop out loud: detect → triage → contain → diagnose → recover → verify → follow up.

### On prioritization

Prioritize by customer impact, then by reversibility. The first action should be the one that *caps harm and is easy to undo* — scaling out, isolating poison, throttling inflow. Save irreversible actions (deleting DLQ messages, purging the queue) for last, if ever. Frame it as: "I'd protect the customer first with reversible containment, preserve evidence, then diagnose, then recover in controlled steps."

### On the first signals you would inspect

Always start with **oldest-message age** (is the SLA breaching?) and **throughput** (are we draining at all?). Those two answer "how bad" and "what kind." Depth alone is a trap — it does not tell you whether you are breaching or whether workers are even alive. Saying "depth is rising" without checking throughput is the junior answer.

### On protecting customer impact while recovering fast

The tension is real: fast recovery (full-throttle drain, redrive everything) can re-trigger the incident. Resolve it by leaning on durability — "SQS holds messages for 14 days, so this is delay, not loss" — which licenses a *staged, watched* recovery. You recover as fast as the downstream can safely absorb, and no faster, watching oldest-message age fall as your proof.

### Common interview follow-ups

- "The queue is empty but partners still report missing files." — Check the DLQ; check whether ingest-lambda is even publishing (S3 trigger broken?); check status-api/DynamoDB for the records.
- "You scaled to 20 pods and throughput went *down*." — Downstream saturation (DynamoDB/S3 throttling). Too many consumers; scale *back* and fix the dependency. Classic over-scaling trap.
- "How do you decide between fixing forward and rolling back during a backlog?" — If a recent deploy caused the throughput collapse, roll back first (fastest path to restored throughput), then diagnose. If it is pure demand, there is nothing to roll back — scale.
- "How would you prevent this entirely?" — Autoscale on queue depth, alert on oldest-message age, classify retryable vs. permanent errors, rate-limit bulk uploads, load-test to know your real per-pod throughput and downstream ceilings *before* an incident.
- "What if the DLQ itself is huge and full of unknown messages?" — Sample first, never blind-redrive; categorize; redrive recoverable in capped batches; handle genuine poison out-of-band. The DLQ is a triage queue, not a retry button.
