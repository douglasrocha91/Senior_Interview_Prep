# [SAP Concur Prep] 12) Mock Implementation: Queue-Based File Transaction Service

**Date:** Thursday, 21 May 2026  
**Objective:** Build a practical queue-based file transaction service in Python with tests and operational behavior — implement the core workflow, add retry/DLQ semantics, write tests for happy and failure paths, and track simple operational metrics.

---

## Context: What You Are Building

A file transaction service receives work from a queue (SQS-like), processes each file job, persists state (DynamoDB-like), and routes failures to a dead-letter queue. The expected workflow:

```
[SQS file-jobs queue]
        │
        ▼
  FileJobConsumer.run()
        │
        ├─ poll_message()
        │       │
        │       ▼
        │  process_job(message)
        │       │
        │  ┌────┴────┐
        │  │ success │ → update_status(PROCESSED) → delete_message() → metrics.record_success()
        │  └────┬────┘
        │       │ failure (retryable)
        │       ▼
        │  retry_count < MAX_RETRIES?
        │       ├── yes → re-enqueue with backoff → metrics.record_retry()
        │       └── no  → send_to_dlq() → update_status(FAILED) → metrics.record_dlq()
        │
        └─ loop
```

Key properties this implementation must provide:

| Property | Target | Why |
|---|---|---|
| At-least-once delivery | Every message is processed or ends in DLQ | No silent drops |
| Idempotency | Re-processing the same `transaction_id` does not corrupt state | DLQ redrive safety |
| Retry with backoff | Transient infra failures get a second chance | Avoid DLQ thrash on temporary blips |
| DLQ routing | Permanent failures are isolated, not discarded | Auditability and redrive |
| Observability | Success, retry, DLQ, and latency counts are tracked | Production health visibility |

---

## Exercise 1 — Implement the Core Workflow

### Concept

The consumer loop is the heart of the service. It must: poll for a message, dispatch to the processor, handle the outcome (success/failure), and loop safely. The two correctness constraints are **at-least-once delivery** (do not delete until processing succeeded) and **idempotency** (the same message processed twice must leave state identical to processing it once).

### Task

Implement `FileJobConsumer` with a single-message processing loop. Use the stub interfaces below — do not implement persistence or queue backends here; stub them out.

```python
# file_transaction_service/consumer.py

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2  # exponential base: 2^attempt seconds


@dataclass
class Message:
    transaction_id: str
    file_key: str          # S3 key or equivalent
    receive_count: int = 1
    receipt_handle: str = ""


@dataclass
class Metrics:
    successes: int = 0
    retries: int = 0
    dlq_sends: int = 0
    failures: int = 0
    processing_times: list = field(default_factory=list)

    def record_success(self, elapsed: float) -> None:
        self.successes += 1
        self.processing_times.append(elapsed)

    def record_retry(self) -> None:
        self.retries += 1

    def record_dlq(self) -> None:
        self.dlq_sends += 1

    def record_failure(self) -> None:
        self.failures += 1

    def summary(self) -> dict:
        avg = (
            sum(self.processing_times) / len(self.processing_times)
            if self.processing_times else 0.0
        )
        return {
            "successes": self.successes,
            "retries": self.retries,
            "dlq_sends": self.dlq_sends,
            "failures": self.failures,
            "avg_processing_time_s": round(avg, 3),
        }


class QueueClient:
    """Stub — real impl wraps boto3 SQS."""

    def receive_message(self) -> Optional[Message]:
        raise NotImplementedError

    def delete_message(self, receipt_handle: str) -> None:
        raise NotImplementedError

    def send_to_dlq(self, message: Message) -> None:
        raise NotImplementedError

    def re_enqueue(self, message: Message, delay_seconds: int) -> None:
        raise NotImplementedError


class StatusStore:
    """Stub — real impl wraps boto3 DynamoDB."""

    def update_status(self, transaction_id: str, status: str) -> None:
        raise NotImplementedError

    def get_status(self, transaction_id: str) -> Optional[str]:
        raise NotImplementedError


def process_file(file_key: str) -> bool:
    """Stub — real impl downloads, validates, transforms, writes result.
    Returns True on success, raises on infra error, returns False on business error."""
    raise NotImplementedError


class FileJobConsumer:
    def __init__(
        self,
        queue: QueueClient,
        store: StatusStore,
        metrics: Metrics,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self.queue = queue
        self.store = store
        self.metrics = metrics
        self.max_retries = max_retries

    def run_once(self) -> None:
        """Poll one message and process it. Called in a loop by the caller."""
        message = self.queue.receive_message()
        if message is None:
            return

        # Idempotency guard: skip if already in a terminal state.
        current = self.store.get_status(message.transaction_id)
        if current in ("PROCESSED", "FAILED"):
            logger.info(
                "Skipping %s — already in terminal state %s",
                message.transaction_id,
                current,
            )
            self.queue.delete_message(message.receipt_handle)
            return

        start = time.monotonic()
        try:
            success = process_file(message.file_key)
        except Exception as exc:
            elapsed = time.monotonic() - start
            self._handle_infra_failure(message, exc)
            return

        elapsed = time.monotonic() - start

        if success:
            self.store.update_status(message.transaction_id, "PROCESSED")
            self.queue.delete_message(message.receipt_handle)
            self.metrics.record_success(elapsed)
            logger.info("Processed %s in %.3fs", message.transaction_id, elapsed)
        else:
            # Business failure (e.g. malformed content): no retry, straight to DLQ.
            self.store.update_status(message.transaction_id, "FAILED")
            self.queue.send_to_dlq(message)
            self.queue.delete_message(message.receipt_handle)
            self.metrics.record_dlq()
            logger.warning("Business failure for %s — sent to DLQ", message.transaction_id)

    def _handle_infra_failure(self, message: Message, exc: Exception) -> None:
        """Retry with exponential backoff; route to DLQ after max_retries."""
        attempt = message.receive_count  # 1-based: first receive is attempt 1
        logger.warning(
            "Infra failure for %s (attempt %d): %s",
            message.transaction_id,
            attempt,
            exc,
        )
        if attempt < self.max_retries:
            delay = BASE_BACKOFF_SECONDS ** attempt
            self.queue.re_enqueue(message, delay_seconds=delay)
            self.metrics.record_retry()
            logger.info(
                "Re-enqueued %s with %ds backoff", message.transaction_id, delay
            )
        else:
            self.store.update_status(message.transaction_id, "FAILED")
            self.queue.send_to_dlq(message)
            self.metrics.record_dlq()
            logger.error(
                "Max retries exhausted for %s — sent to DLQ", message.transaction_id
            )
```

### Observe and note

- Why is the idempotency guard placed *before* calling `process_file`, not after?
- Why does a business failure (malformed content, `success = False`) go straight to the DLQ without retrying?
- What would break if you called `delete_message` *before* `update_status`?

### Answers

**Idempotency guard placement:** The guard must run before processing to catch the case where the worker crashes *after* writing `PROCESSED` to the store but *before* deleting the message. SQS re-delivers the message (receipt handle expired), and without the guard the file would be processed a second time. Checking at the top of `run_once` collapses the redelivery into a cheap no-op. If the guard were placed after processing, the first check would always miss (status is still `PENDING`) and the duplicate work would be done before the guard could block it.

**Business failure goes straight to DLQ:** Retrying a message with malformed content will fail the same way every time — it is not a transient condition. Each retry wastes capacity, burns the `receive_count` budget, and delays real work behind it. The correct behavior is to isolate it immediately so an operator can inspect and remediate the input. Retries are for *transient* infra errors (timeouts, throttling, temporary unavailability) where the fault is in the environment, not the message. Conflating the two leads to either a DLQ-full-of-good-files problem (retry count too low) or a poison-message-blocking-the-queue problem (retry count too high on business failures).

**Deleting before updating status:** The delete is the acknowledgment to the queue that processing is complete. If the worker deletes the message first and then crashes before writing `PROCESSED` to the store, the file has been consumed but its final state is never recorded. The partner would query the status API and see `PENDING` forever — or no record at all. The message is gone; there is nothing to redrive. The invariant is: **persist state, then acknowledge to the queue**. The reverse order violates at-least-once delivery in the worst possible way: silent, unrecoverable, and invisible unless you are watching carefully.

---

## Exercise 2 — Add Retry Policy and DLQ Semantics

### Concept

Retry policy is the contract between transient failure and durability. Too few retries: healthy files hit the DLQ during a brief blip. Too many retries: a poison message stays in the queue long enough to crowd out legitimate work. DLQ semantics define what happens after that contract is exhausted — the message must be preserved (not dropped) and observable (depth alertable). Backoff prevents retry storms from amplifying load on an already-struggling dependency.

### Task

Extend the implementation above by writing a `RetryPolicy` that can be injected into the consumer. The policy encapsulates the retry decision and backoff calculation separately from the consumer loop.

```python
# file_transaction_service/retry_policy.py

import math
from dataclasses import dataclass


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_backoff_seconds: float = 2.0
    max_backoff_seconds: float = 60.0
    jitter: bool = True

    def should_retry(self, attempt: int) -> bool:
        """attempt is 1-based (first failure is attempt 1)."""
        return attempt < self.max_retries

    def backoff_seconds(self, attempt: int) -> float:
        """Exponential backoff with optional full jitter."""
        import random
        raw = min(
            self.base_backoff_seconds ** attempt,
            self.max_backoff_seconds,
        )
        if self.jitter:
            return random.uniform(0, raw)
        return raw

    def is_retryable(self, exc: Exception) -> bool:
        """Classify exception: retryable (infra) vs. permanent (business logic).
        In production, map specific exception types from the AWS SDK.
        """
        retryable_markers = ("Throttling", "ServiceUnavailable", "timeout", "ConnectionError")
        msg = str(type(exc).__name__) + str(exc)
        return any(m.lower() in msg.lower() for m in retryable_markers)
```

Then show how the updated `_handle_infra_failure` in the consumer uses this policy:

```python
# Updated method in FileJobConsumer (uses injected RetryPolicy)

def _handle_infra_failure(self, message: Message, exc: Exception) -> None:
    attempt = message.receive_count

    if not self.policy.is_retryable(exc):
        # Non-retryable infra error (e.g., access denied, corrupt decrypt key):
        # treat as permanent failure — DLQ immediately.
        self.store.update_status(message.transaction_id, "FAILED")
        self.queue.send_to_dlq(message)
        self.metrics.record_dlq()
        logger.error(
            "Non-retryable error for %s: %s — sent to DLQ", message.transaction_id, exc
        )
        return

    if self.policy.should_retry(attempt):
        delay = self.policy.backoff_seconds(attempt)
        self.queue.re_enqueue(message, delay_seconds=int(delay))
        self.metrics.record_retry()
        logger.info(
            "Retry %d/%d for %s in %.1fs",
            attempt, self.policy.max_retries, message.transaction_id, delay,
        )
    else:
        self.store.update_status(message.transaction_id, "FAILED")
        self.queue.send_to_dlq(message)
        self.metrics.record_dlq()
        logger.error(
            "Retries exhausted (%d) for %s — DLQ", self.policy.max_retries, message.transaction_id
        )
```

### Observe and note

- Why add jitter to exponential backoff?
- What is the practical difference between `max_retries = 3` and `max_retries = 10` for a 30-second outage?
- Why does a non-retryable infra error (e.g., `AccessDeniedException`) skip retries and go straight to DLQ?

### Answers

**Jitter:** Without jitter, all workers that receive the same error at the same moment re-enqueue their messages with the same delay and hit the downstream service as a synchronized burst — a "thundering herd." Full jitter (uniform random between 0 and the capped exponential) spreads retries across the backoff window so the downstream sees a gradual increase in load, not a spike. This is especially important when many workers share the same downstream (SQS → DynamoDB): a synchronized retry storm can retrigger the throttling that caused the failures in the first place.

**`max_retries = 3` vs. `10` for a 30-second outage:** With `max_retries = 3` and a 30-second visibility timeout, three retries span roughly 90 seconds — a message from a 30-second outage has a good chance of surviving if the outage resolves before the third attempt. With `max_retries = 10`, messages survive outages of several minutes, but poison messages stay in the queue much longer (crowding legitimate work) and the effective "retry window" is measured in minutes. The right value depends on your SLA and your visibility timeout. For a 15-minute SLA, exhausting retries in under 5 minutes (3 retries with backoff) leaves ~10 minutes to still recover; 10 retries could burn the entire SLA budget before routing to the DLQ. The trade-off: resilience vs. blast radius on poison messages.

**Non-retryable infra errors bypass retries:** `AccessDeniedException` means the worker's IAM credentials do not permit the action — retrying the same operation with the same credentials will fail identically every time, burning the retry budget and delaying good messages behind it. Similarly, a corrupt decryption key, a missing S3 bucket, or a schema mismatch are all *configuration or deployment problems*, not transient blips — they require an operator to fix the root cause. Routing them to the DLQ immediately makes them visible (via DLQ depth alert) without wasting queue capacity on futile retries. The key judgment call is classifying exceptions correctly: if in doubt, lean toward retrying (transient errors are more common than permanent config failures under steady state), but always add explicit non-retryable mappings as you discover them.

---

## Exercise 3 — Write Tests for Happy Path and Failure Path

### Concept

Tests for a queue-based service need to be isolated (no real SQS, DynamoDB, or S3), deterministic (no timing), and focused on *observable behavior*: what did the consumer write to the store, what did it send to the DLQ, how did the metrics change? Mock the queue and store; test the consumer logic. The golden rule: **test behavior, not implementation details**.

### Task

Write pytest tests covering: happy path, idempotency guard, business failure (DLQ), infra failure with retry, and max-retries DLQ routing.

```python
# tests/test_consumer.py

import pytest
from unittest.mock import MagicMock, patch, call
from file_transaction_service.consumer import (
    FileJobConsumer, Message, Metrics, QueueClient, StatusStore
)
from file_transaction_service.retry_policy import RetryPolicy


def make_message(transaction_id="txn-001", receive_count=1) -> Message:
    return Message(
        transaction_id=transaction_id,
        file_key=f"inbound/{transaction_id}.csv",
        receive_count=receive_count,
        receipt_handle=f"handle-{transaction_id}",
    )


def make_consumer(
    queue: QueueClient,
    store: StatusStore,
    metrics: Metrics = None,
    policy: RetryPolicy = None,
) -> FileJobConsumer:
    return FileJobConsumer(
        queue=queue,
        store=store,
        metrics=metrics or Metrics(),
        policy=policy or RetryPolicy(max_retries=3, jitter=False),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_processes_and_deletes(tmp_path):
    queue = MagicMock(spec=QueueClient)
    store = MagicMock(spec=StatusStore)
    metrics = Metrics()

    msg = make_message()
    queue.receive_message.return_value = msg
    store.get_status.return_value = None  # first time, no status

    with patch("file_transaction_service.consumer.process_file", return_value=True):
        consumer = make_consumer(queue, store, metrics)
        consumer.run_once()

    store.update_status.assert_called_once_with("txn-001", "PROCESSED")
    queue.delete_message.assert_called_once_with(msg.receipt_handle)
    queue.send_to_dlq.assert_not_called()
    assert metrics.successes == 1
    assert metrics.dlq_sends == 0


# ---------------------------------------------------------------------------
# Idempotency guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("terminal_status", ["PROCESSED", "FAILED"])
def test_idempotency_guard_skips_terminal_messages(terminal_status):
    queue = MagicMock(spec=QueueClient)
    store = MagicMock(spec=StatusStore)
    metrics = Metrics()

    msg = make_message()
    queue.receive_message.return_value = msg
    store.get_status.return_value = terminal_status

    with patch("file_transaction_service.consumer.process_file") as mock_process:
        consumer = make_consumer(queue, store, metrics)
        consumer.run_once()

    mock_process.assert_not_called()
    store.update_status.assert_not_called()
    queue.delete_message.assert_called_once_with(msg.receipt_handle)
    assert metrics.successes == 0


# ---------------------------------------------------------------------------
# Business failure → immediate DLQ
# ---------------------------------------------------------------------------

def test_business_failure_sends_to_dlq_without_retry():
    queue = MagicMock(spec=QueueClient)
    store = MagicMock(spec=StatusStore)
    metrics = Metrics()

    msg = make_message()
    queue.receive_message.return_value = msg
    store.get_status.return_value = None

    with patch("file_transaction_service.consumer.process_file", return_value=False):
        consumer = make_consumer(queue, store, metrics)
        consumer.run_once()

    store.update_status.assert_called_once_with("txn-001", "FAILED")
    queue.send_to_dlq.assert_called_once_with(msg)
    queue.re_enqueue.assert_not_called()
    assert metrics.dlq_sends == 1
    assert metrics.retries == 0


# ---------------------------------------------------------------------------
# Infra failure → retry with backoff
# ---------------------------------------------------------------------------

def test_infra_failure_retries_below_max():
    queue = MagicMock(spec=QueueClient)
    store = MagicMock(spec=StatusStore)
    metrics = Metrics()
    policy = RetryPolicy(max_retries=3, base_backoff_seconds=2.0, jitter=False)

    # receive_count=1 means first attempt — still below max_retries=3
    msg = make_message(receive_count=1)
    queue.receive_message.return_value = msg
    store.get_status.return_value = None

    with patch(
        "file_transaction_service.consumer.process_file",
        side_effect=TimeoutError("upstream timeout"),
    ):
        consumer = make_consumer(queue, store, metrics, policy)
        consumer.run_once()

    queue.re_enqueue.assert_called_once_with(msg, delay_seconds=2)  # 2^1 = 2s
    queue.send_to_dlq.assert_not_called()
    store.update_status.assert_not_called()
    assert metrics.retries == 1
    assert metrics.dlq_sends == 0


# ---------------------------------------------------------------------------
# Max retries exhausted → DLQ
# ---------------------------------------------------------------------------

def test_max_retries_exhausted_sends_to_dlq():
    queue = MagicMock(spec=QueueClient)
    store = MagicMock(spec=StatusStore)
    metrics = Metrics()
    policy = RetryPolicy(max_retries=3, jitter=False)

    # receive_count=3 means third attempt — equals max_retries, so DLQ
    msg = make_message(receive_count=3)
    queue.receive_message.return_value = msg
    store.get_status.return_value = None

    with patch(
        "file_transaction_service.consumer.process_file",
        side_effect=ConnectionError("DynamoDB unreachable"),
    ):
        consumer = make_consumer(queue, store, metrics, policy)
        consumer.run_once()

    store.update_status.assert_called_once_with("txn-001", "FAILED")
    queue.send_to_dlq.assert_called_once_with(msg)
    queue.re_enqueue.assert_not_called()
    assert metrics.dlq_sends == 1
    assert metrics.retries == 0


# ---------------------------------------------------------------------------
# Empty queue — no-op
# ---------------------------------------------------------------------------

def test_empty_queue_is_a_noop():
    queue = MagicMock(spec=QueueClient)
    store = MagicMock(spec=StatusStore)
    metrics = Metrics()

    queue.receive_message.return_value = None

    with patch("file_transaction_service.consumer.process_file") as mock_process:
        consumer = make_consumer(queue, store, metrics)
        consumer.run_once()

    mock_process.assert_not_called()
    store.update_status.assert_not_called()
    assert metrics.successes == 0
```

### Observe and note

- Why use `MagicMock(spec=QueueClient)` rather than a plain `MagicMock()`?
- The idempotency test checks that `process_file` is *not called* and that `delete_message` *is called*. Why is each assertion important on its own?
- Why does `test_infra_failure_retries_below_max` pass `jitter=False` to the policy?

### Answers

**`spec=QueueClient` vs. plain `MagicMock`:** `spec` restricts the mock to the interface defined by `QueueClient`: calling a method that does not exist on the real class raises `AttributeError` instead of silently creating a new mock attribute. This makes the test catch typos and interface drift immediately — if the consumer calls `queue.recieve_message()` (misspelled), a specced mock fails the test; an unspecced mock would silently return another mock and the bug would reach production. It also documents which interface the mock is standing in for, making the test easier to read.

**Two separate assertions in the idempotency test:** `process_file` not called confirms the guard *prevented work* — the processing logic was skipped entirely, not just its side effects. `delete_message` called confirms the guard *cleaned up after itself* — the message was acknowledged to the queue, preventing an infinite re-delivery loop. Checking only one would leave a gap: if the guard skipped processing but forgot to delete, the message would be re-delivered indefinitely; if processing was skipped but delete was also skipped, SQS would re-deliver and the consumer would check the guard again, which would pass, but that wastes SQS receive calls on a message we already know is terminal.

**`jitter=False` in the retry test:** Jitter adds randomness (`random.uniform(0, raw)`), making the expected backoff value non-deterministic. The test asserts `queue.re_enqueue.assert_called_once_with(msg, delay_seconds=2)` — that exact value. With jitter enabled, the call might pass `delay_seconds=1` or `delay_seconds=0`, failing the assertion even when the logic is correct. Disabling jitter makes the test deterministic without testing the randomness itself (which is a stdlib property). The separation is principled: test the *policy logic* (exponential formula, backoff caps, retry count) deterministically; test the jitter behavior in isolation with a patched `random.uniform` if you care about coverage.

---

## Exercise 4 — Track Simple Operational Metrics

### Concept

Metrics are the bridge between code behavior and production observability. For an on-call engineer looking at a dashboard at 2am, the most important signals from a file transaction service are: throughput (successes/sec), error rate (failures/sec), DLQ depth trend (are we accumulating bad messages?), and processing latency (p50/p99, not just average). A minimal metrics implementation must capture these without requiring a real metrics backend — it should be instrumentable in tests and swappable for Prometheus, CloudWatch, or Datadog in production.

### Task

Extend `Metrics` to compute latency percentiles and emit a CloudWatch-compatible summary. Then show the hook points in the consumer where each metric is recorded.

```python
# file_transaction_service/metrics.py

import time
import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Metrics:
    successes: int = 0
    retries: int = 0
    dlq_sends: int = 0
    failures: int = 0
    processing_times: List[float] = field(default_factory=list)
    _start_time: float = field(default_factory=time.monotonic, repr=False)

    def record_success(self, elapsed: float) -> None:
        self.successes += 1
        self.processing_times.append(elapsed)

    def record_retry(self) -> None:
        self.retries += 1

    def record_dlq(self) -> None:
        self.dlq_sends += 1

    def record_failure(self) -> None:
        self.failures += 1

    def percentile(self, p: float) -> float:
        """Return the p-th percentile of processing times (0–100)."""
        if not self.processing_times:
            return 0.0
        sorted_times = sorted(self.processing_times)
        idx = math.ceil((p / 100) * len(sorted_times)) - 1
        return sorted_times[max(0, idx)]

    def throughput_per_second(self) -> float:
        elapsed = time.monotonic() - self._start_time
        if elapsed == 0:
            return 0.0
        return self.successes / elapsed

    def error_rate(self) -> float:
        total = self.successes + self.dlq_sends
        if total == 0:
            return 0.0
        return self.dlq_sends / total

    def summary(self) -> dict:
        return {
            "successes": self.successes,
            "retries": self.retries,
            "dlq_sends": self.dlq_sends,
            "failures": self.failures,
            "throughput_per_sec": round(self.throughput_per_second(), 3),
            "error_rate": round(self.error_rate(), 4),
            "p50_processing_time_s": round(self.percentile(50), 3),
            "p99_processing_time_s": round(self.percentile(99), 3),
        }

    def log_summary(self) -> None:
        logger.info("Metrics summary: %s", self.summary())

    def emit_cloudwatch(self, cw_client, namespace: str = "FileTransactionService") -> None:
        """Emit key metrics to CloudWatch. Call on a periodic flush timer in production."""
        summary = self.summary()
        metric_data = [
            {"MetricName": "Successes",       "Value": summary["successes"],           "Unit": "Count"},
            {"MetricName": "DLQSends",        "Value": summary["dlq_sends"],           "Unit": "Count"},
            {"MetricName": "Retries",         "Value": summary["retries"],             "Unit": "Count"},
            {"MetricName": "ThroughputPerSec","Value": summary["throughput_per_sec"],  "Unit": "Count/Second"},
            {"MetricName": "ErrorRate",       "Value": summary["error_rate"],          "Unit": "None"},
            {"MetricName": "P50ProcessingTime","Value": summary["p50_processing_time_s"],"Unit": "Seconds"},
            {"MetricName": "P99ProcessingTime","Value": summary["p99_processing_time_s"],"Unit": "Seconds"},
        ]
        cw_client.put_metric_data(Namespace=namespace, MetricData=metric_data)
```

**Hook points in the consumer (annotated):**

```python
# In run_once(), after successful processing:
self.metrics.record_success(elapsed)   # → increments successes, appends latency sample

# In run_once(), after business failure:
self.metrics.record_dlq()             # → increments dlq_sends

# In _handle_infra_failure(), on retry:
self.metrics.record_retry()           # → increments retries

# In _handle_infra_failure(), on max-retries DLQ:
self.metrics.record_dlq()             # → increments dlq_sends
```

**Which metrics trigger alerts in production:**

```
Alert: DLQSends > 0 for 5 consecutive minutes
  → At least one message stream is in permanent failure. Inspect DLQ immediately.

Alert: ErrorRate > 0.05 (5%)
  → More than 1 in 20 jobs is ending in DLQ. Likely a class of bad input or a dependency problem.

Alert: P99ProcessingTime > visibility_timeout × 0.8
  → Jobs are close to exceeding visibility timeout, risking duplicate processing.

Alert: ThroughputPerSec falling while queue depth is rising
  → Classic backlog signal — cross-reference with SQS ApproximateAgeOfOldestMessage.
```

### Observe and note

- Why track p99 processing time specifically (not just average)?
- Why is `error_rate` defined as `dlq_sends / (successes + dlq_sends)` rather than `failures / total_messages`?
- What is the practical value of `emit_cloudwatch` being a separate, injectable call rather than embedded in `record_success`?

### Answers

**P99 over average:** The average hides the tail. If 99 jobs complete in 1 second and 1 job takes 60 seconds, the average is ~1.6 seconds — which looks fine. But that single 60-second job would expire the visibility timeout if it is set to 30 seconds, causing a duplicate delivery. The p99 reveals the tail behavior that drives reprocessing risk, DLQ risk, and the upper bound for setting visibility timeouts. In a production SLA conversation ("95% of files within 15 minutes"), the p99 (or p95) of *your service's processing time* is directly load-bearing. Average-only metrics lead to incorrect timeout configuration.

**Error rate formula:** `dlq_sends / (successes + dlq_sends)` measures the fraction of *completed jobs* that ended in permanent failure — i.e., the fraction of partner files that the service could not deliver. This is the customer-facing metric: of the files we handled, how many did we fail? Using `failures` (raw exception count) in the denominator would conflate retried exceptions with true failures: a job that fails twice but succeeds on the third try increments `failures` twice but `dlq_sends` zero times. The raw exception count is an internal metric; the DLQ rate is the external one.

**`emit_cloudwatch` as a separate call:** Embedding the emit inside `record_success` would call `put_metric_data` on every single processed message — potentially thousands of API calls per minute, triggering CloudWatch throttling and adding per-message latency. Separating the emit as a periodic flush (e.g., every 60 seconds on a timer) batches the data and keeps the hot path (message processing) free of network calls. It also makes the metrics class independently testable: you can call `record_success` a thousand times in a unit test, inspect `metrics.summary()`, and never touch CloudWatch. Injectability (passing `cw_client` as an argument) allows tests to pass a mock client, and production deployments to pass a real one — the same separation-of-concerns principle as the queue and store stubs.

---

## Exercise 5 — Connect to This Repo

Review `processor-worker/app/consumer.py`, `docs/failure-scenarios.md`, and `infra/kubernetes/processor-worker-deployment.yaml`, then answer:

1. The repo's consumer uses a global `_MAX_MESSAGES = 1` constant. How does this compare to the `RetryPolicy` injection pattern above, and which is easier to test?

2. `docs/failure-scenarios.md` defines infrastructure failures as returning `False` and triggering a retry via SQS. Compare that to the implementation above where infra failures raise exceptions. Which is safer and why?

3. The `Metrics` class above tracks `processing_times` in memory. In a long-running worker pod, what is the risk of this approach, and how would you fix it without changing the interface?

4. The repo has no test for the DLQ redrive path. Write one sentence describing the test case you would add, and which two mock assertions would confirm it.

5. `processor-worker` has no readiness probe on the SQS polling loop. Using the metrics above, propose a simple liveness check that would let Kubernetes detect a stalled consumer.

### Answers

**1. Constant vs. injected policy:** A global `_MAX_MESSAGES = 1` is fine for controlling concurrency but it is a baked-in value — tests cannot change it without monkeypatching the module. The `RetryPolicy` injection pattern makes the policy a first-class parameter: tests pass `RetryPolicy(max_retries=1)` to exercise the DLQ path immediately, or `RetryPolicy(max_retries=10)` to test deep retry behavior, without touching production constants. The injected approach also makes it easy to change policy per environment (staging vs. production) without code changes. The repo's pattern is common and acceptable for small projects; injection becomes essential when you want orthogonal, parameterized test coverage of the retry logic.

**2. `False` return vs. exception for infra failure:** Returning `False` loses the error context — you cannot distinguish a DynamoDB timeout from a permission error from a corrupt response; they all look the same. Raising a typed exception preserves the cause, enables `is_retryable()` classification, and allows logging with the actual error message. The `False` pattern also conflates business failures (bad input) and infra failures into the same return value, forcing the consumer to treat them identically. Raising exceptions — and catching them explicitly in the consumer — is safer because it makes the error type part of the contract and enables nuanced handling (retry vs. immediate DLQ vs. alarm). The repo's approach works for the simple two-state (success/failure) case but breaks down as soon as you need to handle multiple failure classes differently.

**3. In-memory `processing_times` growth:** Over hours or days, an unbounded list accumulates millions of floats — several hundred MB of memory per worker pod, eventually causing OOMKilled. Fix without changing the interface: replace the list with a fixed-size circular buffer (e.g., `collections.deque(maxlen=10_000)`) so only the most recent N samples are kept. Percentiles computed over a rolling window of recent samples are more operationally meaningful than a lifetime average anyway: they reflect current performance, not the average since the pod started three weeks ago. The interface (`record_success(elapsed)`, `percentile(p)`) stays identical; only the storage backing changes.

**4. DLQ redrive test case:** "When a message with `receive_count = MAX_RETRIES` fails with an infra exception, `send_to_dlq` is called with that message and `update_status` is called with `'FAILED'`."

**5. Liveness check using metrics:** Expose a `/healthz` endpoint (or a simple file-based check) that returns unhealthy if `time.monotonic() - last_successful_poll_time > LIVENESS_THRESHOLD` (e.g., 120 seconds). The consumer updates `last_successful_poll_time` after each `receive_message` call (even if the queue was empty). A stalled consumer — one that has stopped polling due to an unhandled exception or deadlock — will fail the check after the threshold, and Kubernetes will restart the pod. This is more reliable than a CPU/memory probe because a stalled consumer may appear healthy on system metrics while silently processing zero messages.

---

## Notes: Queue-Based File Service — Quick Reference

```
CORE LOOP INVARIANTS
  [ ] Delete message AFTER persisting state (never before)
  [ ] Idempotency guard runs BEFORE calling process_file
  [ ] Business failure → DLQ immediately (no retry)
  [ ] Infra failure → retry with backoff → DLQ after max_retries
  [ ] Empty queue → no-op (do not log as error)

RETRY POLICY CHECKLIST
  [ ] max_retries sized to SLA budget (exhausted retries < SLA window)
  [ ] Exponential backoff with jitter (prevent thundering herd)
  [ ] Backoff capped (max_backoff_seconds) to avoid multi-minute waits
  [ ] Retryable vs. non-retryable exception classification
  [ ] Non-retryable errors → DLQ immediately (do not waste retry budget)

TEST COVERAGE MATRIX
  happy path          → PROCESSED in store, message deleted, success metric
  already PROCESSED   → process_file not called, message deleted, no metric change
  already FAILED      → process_file not called, message deleted, no metric change
  business failure    → FAILED in store, sent to DLQ, no re-enqueue
  infra failure #1    → re-enqueued with backoff, no DLQ, no store write
  infra failure #3    → FAILED in store, sent to DLQ, no re-enqueue
  empty queue         → no calls to store or queue ops, no metrics recorded

KEY METRICS AND THEIR ALERT THRESHOLDS
  DLQSends > 0 for 5+ minutes     → permanent failure class, inspect DLQ
  ErrorRate > 0.05                 → 1 in 20 jobs failing — investigate input or dependency
  P99 > 0.8 × visibility_timeout  → duplicate delivery risk — raise timeout or speed up processing
  ThroughputPerSec dropping        → cross-reference with SQS oldest-message age
```

---

## Interview Angle

### What interviewers are evaluating

They want to see **disciplined service design**, not just code that runs. The signals they listen for: do you separate concerns (consumer loop, retry policy, metrics, queue/store interfaces)? Do you explain *why* each design decision exists — not just what the code does? Can you reason about failure modes (what breaks if delete comes before update, what happens on duplicate delivery, when should a message retry vs. DLQ)? Implement the minimum required and name the trade-offs; over-engineering is as penalized as under-engineering.

### On making the service resilient

Three properties carry the most weight: **at-least-once delivery** (never delete before persisting), **idempotency** (re-processing is safe), and **error classification** (retryable infra vs. permanent business failure). Name all three and explain how your implementation provides each. If you cannot explain idempotency concretely — "processing the same `transaction_id` twice writes the same status, so no corruption" — the interviewer will probe until you can.

### On what guarantees the service provides

Be precise: the service guarantees *at-least-once processing with DLQ isolation after N retries*. It does **not** guarantee exactly-once (the idempotent design makes duplicates safe, not impossible). It does not guarantee the DLQ is empty — it guarantees messages are preserved there for operator action. It does not guarantee SLA compliance if the downstream is down — it guarantees messages are safe in the queue for up to 14 days. Name what you guarantee and what you do not; senior engineers know the limits of their systems.

### On how to observe the service in production

Lead with the four signals: **throughput** (successes/sec — are we keeping up?), **error rate** (DLQ sends / completions — what fraction are permanent failures?), **latency tail** (p99 processing time vs. visibility timeout — are we at duplicate-delivery risk?), and **DLQ depth** (is bad-message accumulation trending up?). Then name the alert thresholds and what action each triggers. Metrics without alerts are just expensive logs; alerts without runbooks are just noise. Say both.

### Common interview follow-ups

- "How would you handle a poison message that crashes the worker instead of returning False?" — It raises an exception, hits the infra-failure path, retries up to `max_retries`, then goes to DLQ. As long as the exception is caught at the `run_once` level (not leaked to the main loop), the worker stays alive. The key is a broad `except Exception` at the consumer boundary that routes unexpected errors through the infra-failure path.
- "What if the DLQ itself is unavailable?" — `send_to_dlq` raises. The message is not deleted; SQS re-delivers it. You accumulate retries against a DLQ that is unreachable. In that scenario you should log an alarm (`dlq_unavailable` metric), back off, and keep the message visible in the main queue rather than silently dropping it.
- "How would you scale this to process 10,000 files per minute?" — More consumer pods (horizontal scale), bounded by downstream (DynamoDB/S3) throughput. Each pod is independent; the SQS queue serializes coordination implicitly. Add KEDA autoscaling on queue depth. Name the ceilings: DynamoDB provisioned throughput, S3 request rate, network bandwidth per pod.
- "What is the difference between this pattern and a competing-consumers pattern?" — This **is** the competing-consumers pattern: multiple pods poll the same SQS queue, and SQS's visibility timeout ensures (with high probability) that each message is processed by one pod at a time. The idempotency design handles the rare duplicate delivery case that arises when a consumer times out.
