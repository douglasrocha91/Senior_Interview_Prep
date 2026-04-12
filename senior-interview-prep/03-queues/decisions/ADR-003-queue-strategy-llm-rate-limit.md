# ADR-003: Queue Strategy for LLM Rate Limiting with Token Bucket

**Status:** Accepted  
**Context:** System receiving variable LLM requests with strict provider rate limits  
**Date:** 2026-04

## Context
Our system receives bursty traffic from users requiring LLM processing, but LLM providers (OpenAI, Anthropic) enforce strict rate limits (e.g., 1000 requests per minute). Without proper rate limiting, we risk:
- Exceeding provider quotas and getting blocked
- Wasting money on retries and exponential backoff
- Poor user experience from frequent 429 errors
- Inability to smooth bursty traffic for consistent provider usage

We need a queue-based solution that respects provider rate limits while minimizing cost per request and maintaining acceptable latency.

## Decision
Use AWS SQS Standard queue with token bucket algorithm consumers and Dead Letter Queue (DLQ). Producers push requests to SQS; consumer fleet uses token bucket to throttle LLM API calls to provider limits; failed messages go to DLQ for inspection.

## Alternatives Considered

| Option | Description | Advantage | Disadvantage |
|--------|-------------|-----------|--------------|
| Direct Rate Limiting in API Gateway | Throttle at entry point using gateway rate limits | Simple, no additional infrastructure | Doesn't smooth bursts, loses requests during spikes, no batching opportunity |
| Fixed Window Consumer | Consumer processes N requests per fixed time window | Simple to understand and implement | Can cause bursts at window edges, inefficient quota usage |
| Leaky Bucket Consumer | Consumer processes requests at fixed rate | Smooths output, prevents bursts | Underutilizes quota during low traffic, cannot burst |
| **Token Bucket Consumer (chosen)** | Consumer accumulates tokens up to burst limit, spends tokens per request | Allows bursting up to limit, smooths long-term rate, efficient quota usage | Requires token management state, slightly more complex |
| SQS FIFO Queue | Guaranteed ordering and exactly-once processing | Ordering guarantees, exactly-once semantics | Limited throughput (~300 msg/s), higher cost, unnecessary for our use case |

## Consequences

**Positive:**
- Rate limit compliance: Token bucket ensures we never exceed provider RPM/TPM limits
- Burst handling: Can accumulate tokens during low usage to handle traffic spikes
- Cost efficiency: Enables batching of LLM calls (multiple requests per token) to reduce per-request cost
- Failure isolation: DLQ captures repeatedly failing messages for inspection without clogging main queue
- Operational simplicity: Uses managed AWS service with built-in scaling and monitoring

**Negative / Accepted Trade-offs:**
- Increased latency: Messages may wait in queue during high traffic (accepted given burst smoothing benefits)
- Duplicate processing: SQS Standard provides at-least-once delivery (mitigated by idempotent consumers)
- Queue management overhead: Need to monitor queue depth and set appropriate alarms (accepted operational complexity)

## Relationships
- Impacts: Cache design (queued requests may benefit from cache warming), Circuit breaker design (queue depth affects breaker thresholds)
- Depends on: Idempotent LLM consumers, proper visibility timeout settings, DLQ alarm configuration

## How to Defend in an Interview
"I chose an SQS Standard queue with token bucket consuming consumers for LLM rate limiting because it provides the best balance of rate limit compliance, burst handling, and cost efficiency. The token bucket algorithm allows us to smooth bursty traffic while still enabling bursts up to our limit when needed, maximizing our utilization of the LLM provider's quota. The trade-off is accepting potential duplicates and increased latency, but these are mitigated through idempotent consumers and are acceptable given the alternative of either losing requests during bursts or constantly hitting rate limits. In our AWS context, this integrates naturally with CloudWatch for monitoring and Lambda/SQS consumers for scalable processing."