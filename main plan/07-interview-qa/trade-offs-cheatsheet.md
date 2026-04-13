# Trade-offs Cheatsheet

Quick reference table for pre-interview review:

| Pattern | Choice A | Choice B | Decision Criterion |
|---------|----------|----------|--------------------|
| Auth | Centralized Gateway | Distributed per service | Is SPOF acceptable? vs sync overhead |
| AuthZ | RBAC | ABAC | Is role-level control enough? vs per-attribute data control |
| Decoupling | Synchronous | Asynchronous | Immediate consistency required? vs throughput and resilience |
| Saga | Orchestration | Choreography | Centralized visibility vs zero coupling |
| Queue | SQS Standard | SQS FIFO | Maximum throughput vs guaranteed ordering |
| Cache | TTL-based | Event-driven invalidation | Simplicity vs correctness |
| Cache aggressiveness | High TTL | Low TTL | Deterministic data vs mutable/sensitive data |
| Circuit Breaker | Per endpoint | Per resource | Granularity vs operational overhead |
| LLM Fallback | Fail fast | Fallback chain | Availability SLA vs complexity |
| Deployment | Blue-green | Canary | Zero-risk vs gradual production validation |