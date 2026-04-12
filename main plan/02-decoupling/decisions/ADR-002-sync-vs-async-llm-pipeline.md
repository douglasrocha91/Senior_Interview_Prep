# ADR-002: Asynchronous Communication for LLM Pipeline Stages

**Status:** Accepted  
**Context:** RAG pipeline with embedding → retrieval → generation stages on AWS EKS  
**Date:** 2026-04

## Context
We need to design a RAG pipeline consisting of four stages: document extraction, embedding generation, document retrieval, and response generation. Each stage has different performance characteristics:
- Document extraction: 50-100ms (CPU-bound)
- Embedding generation: 100-200ms (GPU-bound or API call)
- Document retrieval: 20-50ms (memory-bound, vector search)
- Response generation: 2000-8000ms (LLM inference, highly variable)

The pipeline serves user requests with an SLA of <2s latency for 95th percentile. Currently implemented as synchronous HTTP calls between stages, causing thread blocking and poor resource utilization.

## Decision
Use asynchronous communication with AWS EventBridge to decouple pipeline stages. Each stage publishes events to EventBridge, and downstream stages consume events as they become available.

## Alternatives Considered

| Option | Description | Advantage | Disadvantage |
|--------|-------------|-----------|--------------|
| Synchronous HTTP/REST | Direct HTTP calls between stages with blocking wait | Simple to understand, immediate consistency, straightforward error handling | Thread blocking, poor resource utilization, head-of-line blocking, inability to scale stages independently |
| AWS SQS Queues | Each stage writes to SQS queue, next stage polls | Good decoupling, built-in retry, dead letter queue support | Polling latency, potential for empty receives, FIFO vs Standard trade-offs |
| **AWS EventBridge (chosen)** | Events published to EventBridge, routed to consumers via rules | Push-based (no polling), fan-out capabilities, schema validation, integrates with AWS services | Eventually consistent, requires idempotency, slightly more complex setup |
| gRPC Streaming | Long-lived connections with bidirectional streaming | Low latency, efficient for streaming data | Complex to manage connections, difficult to scale horizontally, tight coupling |

## Consequences

**Positive:**
- Eliminates thread blocking: services can process other requests while waiting for LLM completion
- Independent scaling: embedding stage can scale based on GPU availability, generation based on LLM tokens
- Resilience: failure in one stage doesn't block upstream stages (backpressure via queue depth)
- Fan-out capability: same embedding event can trigger multiple retrieval processes for different use cases
- Schema validation: EventBridge schema registry ensures contract compatibility

**Negative / Accepted Trade-offs:**
- Eventually consistency: stages may process events out of order or with delay (mitigated by event sequencing and idempotency)
- Increased complexity: requires handling duplicate events, out-of-order processing, and event versioning
- Latency overhead: event publishing adds ~5-10ms vs near-zero for direct calls (accepted given elimination of seconds-long blocking)

## Relationships
- Impacts: Queue design (events may buffer in EventBridge), Cache design (intermediate results may be cached), Observability (tracing across async boundaries)
- Depends on: Idempotency keys in events, schema versioning strategy, dead letter handling for failed events

## How to Defend in an Interview
"I chose asynchronous communication using AWS EventBridge for our LLM pipeline stages because the generation step has highly variable latency (2-8s) that would block threads in a synchronous design. With EventBridge, each stage publishes events and continues processing other requests, allowing independent scaling based on each stage's bottleneck. The trade-off is accepting eventual consistency and increased complexity around idempotency, but this is worthwhile given the 10x improvement in resource utilization and ability to handle LLM latency variations without affecting upstream stages. In an AWS/EKS context, EventBridge integrates naturally with our other services and provides built-in schema validation and monitoring."