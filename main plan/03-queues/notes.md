# Queues in Distributed Systems — Conceptual Notes

## Core Concept
Queues in distributed systems serve as pressure regulators and flow control mechanisms, not just resilience tools. They decouple producers from consumers in time, allowing services to operate at their natural rates rather than being forced to match the slowest consumer. Beyond simple buffering, queues provide backpressure signals (through queue depth), enable batching for efficiency, isolate failures through dead letter queues, and support priority-based processing. The philosophical shift is from viewing queues as "band-aids for slow services" to seeing them as essential flow control infrastructure that enables sustainable system operation under variable load.

## Why It Matters in Distributed Microservices
Without proper queue usage, microservices suffer from cascading failures during load spikes: producers overwhelm consumers, exhausting memory or thread pools and causing system-wide collapse. In AI/LLM systems specifically, queues are economic flow control mechanisms—LLM providers impose strict rate limits (e.g., 1000 requests/minute), and queues allow smoothing bursty traffic to stay within quotas while minimizing cost per request through batching. Without queues, systems either waste money by over-provisioning for peak loads or suffer from frequent rate limit errors and poor user experience. Additionally, queues enable patterns like the circuit breaker to work effectively by providing a buffer where failed requests can be isolated and retried separately.

## Patterns and Variations
- **Backpressure**: Signal sent upstream when queue depth exceeds threshold, telling producers to slow down. Essential for preventing resource exhaustion.
- **Dead Letter Queue (DLQ)**: Isolates repeatedly failing messages for inspection rather than clogging main queue. Embodies philosophy of "accept that failure exists."
- **Priority Queues**: Multiple queues or priority levels within a queue for service level differentiation (e.g., premium vs free users).
- **Batch Consumption**: Process multiple messages per API call to reduce per-message overhead (critical for LLM API cost optimization).
- **Visibility Timeout**: Time during which a message is invisible after being consumed; prevents other consumers from processing it. Must be longer than expected processing time.
- **Idempotency Requirement**: Queue consumers must be idempotent due to at-least-once delivery guarantees.
- **FIFO vs Standard Queues**: FIFO guarantees ordering and exactly-once processing but lower throughput; Standard offers higher throughput but at-least-once and potential duplicates.
- **Delay Queues**: Postpone message availability for a set time, useful for retry scheduling or scheduled workflows.

## In the AI/LLM Context (relevant to the role)
LLM rate limiting is fundamentally an economic constraint, not just a technical one. Providers like OpenAI and Anthropic charge per token and enforce strict RPM/TPM limits. Queues enable smoothing bursty user traffic to stay within these limits while maximizing throughput. For example, a system receiving 10k req/s with a 1000 RPM LLM quota needs queues to buffer 90% of requests and allow the LLM stage to work at its sustainable rate. Additionally, batching multiple embedding or generation requests into single API calls can reduce cost by 60-80% due to fixed overhead per HTTP request. Queues also enable graceful degradation: when LLM services are slow or failing, the system can return cached responses or generic answers while keeping the queue processing at a sustainable rate.

## Key Trade-offs
| Decision | Advantage | Disadvantage | When to Choose |
|----------|-----------|--------------|----------------|
| Queue Depth Threshold | High threshold: better resource utilization, smoother bursts. Low threshold: faster backpressure, prevents overflow. | High: risk of memory explosion, slow backpressure. Low: underutilization, excessive backpressure signals. | Choose based on consumer processing time variance and memory constraints. Monitor queue depth vs processing time. |
| Standard vs FIFO Queue | Standard: high throughput, good for most use cases. FIFO: guaranteed ordering, exactly-once processing. | Standard: potential duplicates, no ordering guarantee. FIFO: ~300 msg/s limit per queue, higher cost. | Choose FIFO for workflows requiring strict ordering (e.g., financial transactions). Choose Standard for high-throughput event processing where ordering is less critical. |
| Immediate vs Batch Processing | Immediate: lowest latency per message. Batch: better throughput, lower cost per message (especially for LLM APIs). | Immediate: higher per-message overhead, poor batching efficiency. Batch: increased latency, complexity in handling partial batches. | Choose batch for LLM API calls or other expensive operations where fixed cost per request dominates. Choose immediate for low-latency user-facing notifications. |
| DLQ: Process Immediately vs Batch | Immediate: quick visibility into failures. Batch: efficient handling of recurring failure patterns. | Immediate: poor resource utilization for repetitive failures. Batch: delayed failure detection, potential backlog. | Choose batch processing for DLQ when failure patterns are predictable and repetitive. Choose immediate for novel or critical failures requiring urgent attention. |

## Common Interview Questions on This Topic
- How would you design a queue system to handle 10k req/s when your LLM provider only allows 1000 rpm?
- What is backpressure and how would you implement it in an SQS consumer?
- When would you choose SQS FIFO over Standard queues?
- How do you prevent queue consumers from processing stale messages or causing message loss?
- What is the philosophy behind dead letter queues and how would you use them in an AI/LLM pipeline?

## Connections to Other Topics
Queue design deeply interacts with cache patterns (queues can buffer requests for cache warming), circuit breakers (queues provide the buffer where circuit breaker isolation works), and decoupling (queues enable asynchronous communication). For example, in an LLM pipeline, queues sit between the API gateway and embedding service to provide rate limiting and backpressure. Cache hit rates may be affected by queue-induced delays, requiring careful TTL tuning. Circuit breaker states can be inferred from queue depth and DLQ growth, providing valuable observability signals.