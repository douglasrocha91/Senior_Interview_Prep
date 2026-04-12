# Scenario: Decoupling LLM Pipeline with 4 Stages

**Topic:** decoupling  
**Level:** Senior  
**Estimated Time:** 15-20 minutes

## Context
You are designing a RAG pipeline with four stages: document_extract → embed → retrieve → generate. Each stage has different performance and scaling characteristics:
- document_extract: CPU-intensive, scales with number of cores
- embed: GPU-intensive or expensive API call, scales with GPU availability or rate limits
- retrieve: memory-intensive, scales with memory bandwidth
- generate: LLM inference, highly variable latency (2-8s), scales with token throughput

The pipeline must serve user requests with <2s latency for 95th percentile. Currently implemented as synchronous HTTP calls, causing thread pooling issues when the generate stage is slow.

## Requirements / Constraints
- Functional requirement: Pipeline must process documents through all four stages in order
- SLA: 95th percentile end-to-end latency < 2s
- Scale: Peak 1k req/s, with generate stage being the bottleneck
- Resilience: Failure in one stage should not cause backpressure to overflow upstream queues
- Observability: Must maintain end-to-end traceability despite decoupling

## Your Task
1. How would you decouple these stages to allow independent scaling and prevent thread blocking?
2. What messaging pattern would you choose (queues, topics, event bridge) and why?
3. How would you maintain end-to-end traceability across asynchronous boundaries?
4. How would you handle the case where the generate stage falls behind and queues start to back up?

***
## Reference Answer

### Proposed Architecture
Use AWS EventBridge with idempotency keys and trace headers:
- Each stage processes incoming events, performs its function, and publishes a completion event
- Events include: trace_id (from request), stage_id, timestamp, input/output references
- Intermediate results stored in S3 with references passed in events (to avoid large event payloads)
- Generate stage uses async invocation: publishes event immediately, processes in background
- Client polls for completion via separate status endpoint or uses WebSocket callback

### Key Decisions and Why
- **EventBridge over SQS**: Push-based delivery eliminates polling latency; built-in schema validation and replay capabilities. Trade-off: slightly higher cost per event, but acceptable given reduced compute waste from polling.
- **Idempotency keys**: Each event includes a unique identifier based on trace_id and stage, allowing services to safely retry without duplicate processing. Essential for handling at-least-once delivery guarantees.
- **Trace context propagation**: Uses AWS X-Ray trace header embedded in events to maintain end-to-end tracing across asynchronous boundaries. All services extract and propagate trace context.
- **Backpressure handling**: Generate stage includes circuit breaker that trips when queue depth exceeds threshold, returning degraded response (cached or error) rather than allowing unlimited backlog.

### What NOT to Do (and Why)
- **Don't use synchronous HTTP**: Would cause thread blocking in upstream services when generate stage is slow, exhausting thread pools and causing cascading failures.
- **Don't pass large payloads in events**: Events should contain only references to data stored in S3/DynamoDB to avoid hitting event size limits and reducing costs.
- **Don't ignore out-of-order processing**: Must design stages to handle events arriving out of sequence (e.g., using sequence numbers or ignoring stale events).
- **Don't rely on retry alone for backpressure**: Unbounded retries during generate stage slowness would worsen the problem; need active load shedding.

### How to Present in an Interview
"I would decouple the pipeline stages using AWS EventBridge with idempotency keys and trace context propagation. Each stage publishes completion events, allowing independent scaling based on each stage's bottleneck. To maintain traceability, I'd embed AWS X-Ray trace headers in all events. For backpressure, I'd implement circuit breaking in the generate stage that returns degraded responses when queue depth exceeds thresholds, preventing upstream queue overflow. The trade-off is accepting eventual consistency and increased complexity around idempotency, but this eliminates thread blocking and allows each stage to scale independently based on its specific resource constraints."