# AGENT INSTRUCTIONS — Senior Engineer Interview Prep Repository

## Objective
Create an interview preparation repository for a **Senior Engineer** role focused on distributed microservices architecture with integrated AI (LLM/RAG). The repository must contain conceptual notes, ADRs (Architecture Decision Records), and scenario exercises focused on **architectural decision-making and trade-offs**, not code implementation.

---

## Directory Structure to Create
senior-interview-prep/
├── README.md
├── 01-auth-authz/
│ ├── notes.md
│ ├── decisions/
│ │ └── ADR-001-api-gateway-vs-distributed-auth.md
│ └── exercises/
│ ├── scenario-jwt-validation-50-services.md
│ └── scenario-rag-data-access-abac.md
├── 02-decoupling/
│ ├── notes.md
│ ├── decisions/
│ │ └── ADR-002-sync-vs-async-llm-pipeline.md
│ └── exercises/
│ ├── scenario-llm-pipeline-4-stages.md
│ └── scenario-saga-payment-rollback.md
├── 03-queues/
│ ├── notes.md
│ ├── decisions/
│ │ └── ADR-003-queue-strategy-llm-rate-limit.md
│ └── exercises/
│ └── scenario-10k-rps-llm-throttle.md
├── 04-cache/
│ ├── notes.md
│ ├── decisions/
│ │ └── ADR-004-cache-strategy-rag-pipeline.md
│ └── exercises/
│ └── scenario-cache-embeddings-privacy.md
├── 05-circuit-breaker/
│ ├── notes.md
│ ├── decisions/
│ │ └── ADR-005-circuit-breaker-per-resource-llm.md
│ └── exercises/
│ └── scenario-llm-provider-fallback-chain.md
├── 06-system-design/
│ ├── full-design-rag-assistant-end-to-end.md
│ ├── full-design-canary-deployment-prompts.md
│ └── full-design-observability-ai-services.md
└── 07-interview-qa/
├── expected-questions-and-answers.md
└── trade-offs-cheatsheet.md


---

## Job Context (reference in all files)

The role is **Senior Engineer** focused on:
- Microservices architecture on **AWS (EKS, SQS, SNS, DynamoDB, EC2, EventBridge)**
- Integration of **LLM (OpenAI, Anthropic), RAG, MCP, and embedding-based search**
- **Zero-downtime deployments, canary releases, feature flags**
- **Observability**: metrics, tracing, alerting (X-Ray, CloudWatch, Prometheus)
- **Infrastructure as Code**, Docker, Helm, Kubernetes
- Languages: Golang, Java, Kotlin, .Net
- Compliance with **privacy and fairness in AI**

---

## Quality Rules for All Files

1. **Focus on trade-offs**, not on code. Every decision must answer "why this and not that?"
2. **Direct and technical language** — no basic explanations; the reader is senior-level
3. **Contextualized examples** referencing the job (LLM, RAG, AWS, EKS)
4. **Each file must be self-contained** — readable in isolation
5. **Consistent format** — use the templates below for each file type

---

## Content Templates

### Template: `notes.md` (per topic)

```markdown
# [Topic] — Conceptual Notes

## Core Concept
[2-3 paragraphs explaining the concept with depth, without being basic]

## Why It Matters in Distributed Microservices
[Direct context: what breaks without it, what improves with it]

## Patterns and Variations
[List of patterns with one line on when to use each]

## In the AI/LLM Context (relevant to the role)
[How this concept applies specifically to AI pipelines, RAG, LLM serving]

## Key Trade-offs
| Decision | Advantage | Disadvantage | When to Choose |
|----------|-----------|--------------|----------------|
| ...      | ...       | ...          | ...            |

## Common Interview Questions on This Topic
[3-5 questions as bullet points]

## Connections to Other Topics
[How this topic interacts with the other topics in the repository]
```

---

### Template: `ADR-XXX-name.md`

```markdown
# ADR-XXX: [Decision Title]

**Status:** Accepted  
**Context:** [System/scenario from the job description]  
**Date:** 2026-04

## Context
[Describes the specific architectural problem that motivated the decision.
Includes constraints: scale, SLA, compliance, cost, operational overhead.]

## Decision
[The chosen decision in 1-2 direct sentences.]

## Alternatives Considered

| Option | Description | Advantage | Disadvantage |
|--------|-------------|-----------|--------------|
| Option A | ... | ... | ... |
| **Option B (chosen)** | ... | ... | ... |
| Option C | ... | ... | ... |

## Consequences

**Positive:**
- [list]

**Negative / Accepted Trade-offs:**
- [list]

## Relationships
- Impacts: [other ADRs or topics]
- Depends on: [prerequisites]

## How to Defend in an Interview
[1 direct paragraph: how to articulate this decision verbally, including the trade-off reasoning]
```

---

### Template: `scenario-name.md`

```markdown
# Scenario: [Scenario Title]

**Topic:** [auth/decoupling/queues/cache/circuit-breaker]  
**Level:** Senior  
**Estimated Time:** 15-20 minutes

## Context
[Describes the system, constraints, and current situation]

## Requirements / Constraints
- Functional requirement: [...]
- SLA: [latency, availability]
- Scale: [req/s, users, data volume]
- Compliance: [privacy, audit, fairness]
- Cost: [budget concern if relevant]

## Your Task
1. [Specific design question]
2. [Trade-off to justify]
3. [Hypothetical failure: what happens if X fails?]
4. [Evolution: how does it scale to 10x volume?]

***

## Reference Answer

### Proposed Architecture
[Textual diagram or description of the solution]

### Key Decisions and Why
[Bullet points with each decision and its trade-off justification]

### What NOT to Do (and Why)
[Anti-patterns specific to this scenario]

### How to Present in an Interview
[3-5 sentence script to open the answer with a clear structure]
```

---

## Specific Content per File

### `README.md`
- Repository objective
- Job context (summary)
- Navigable index for all topics
- How to use: "read notes.md → review ADR → practice scenarios"
- Philosophy: "decision-making > implementation"

---

### `01-auth-authz/notes.md`
Cover in depth:
- Auth vs authz distinction and why it matters in distributed systems
- JWT anatomy: header, payload, signature — what validates where
- OAuth 2.0 flows: Authorization Code, Client Credentials (service-to-service)
- RBAC vs ABAC: when RBAC is not enough (e.g., RAG with per-user documents)
- Centralized vs distributed: API Gateway vs each service validates
- **Special focus**: authentication in RAG pipelines — how to control which documents a user can use as LLM context
- AWS IAM as identity provider in the context of EKS
- Open Policy Agent (OPA) as a distributed policy engine
- Audit trail for AI compliance (who accessed what data that fed the model)
- mTLS for service-to-service authentication

**ADR-001:** Decision between centralized API Gateway vs distributed per-service auth vs hybrid (gateway signs, services verify signature). Choice: hybrid. Justification: no SPOF, no extra latency per call, centralized audit trail.

**Scenario 1:** Design auth for a platform with 50+ microservices where RAG service accesses private customer documents.  
**Scenario 2:** A new compliance requirement mandates the LLM model can only access data from the authenticated user's tenant. How do you implement this without modifying each service individually?

---

### `02-decoupling/notes.md`
Cover in depth:
- The three levels of coupling: direct contract, event schema, semantic via saga
- Event-driven vs choreography vs orchestration: when each applies
- Saga pattern: compensating transactions, why not to use distributed 2PC
- Event schema versioning: backward/forward compatibility
- **Special focus**: LLM pipelines are inherently async — embedding → retrieval → generation are independent steps that scale separately
- AWS EventBridge vs SQS vs SNS: conceptual differences and when to use each
- Canary of prompt templates via event versioning
- Strangler Fig Pattern for gradual migration

**ADR-002:** Sync vs async for LLM pipeline. Choice: async with EventBridge. Justification: LLM inference takes 2-8s, clients should not block threads; each step (embedding, retrieval, generation) has different SLA and scales independently.

**Scenario 1:** Design a RAG pipeline with 4 stages: document_extract → embed → retrieve → generate. How to decouple without losing end-to-end traceability?  
**Scenario 2:** Payment fails at step 3 of a 5-step saga. Describe rollback without 2PC.

---

### `03-queues/notes.md`
Cover in depth:
- Queues as pressure regulators (not just resilience)
- Backpressure: what happens without it (memory explosion, cascade failure)
- Dead Letter Queue: philosophy of "accept that failure exists and isolate it"
- Priority queues: when and how
- **Special focus**: LLM rate limiting — OpenAI/Anthropic have per-minute quotas; queues are economic flow control, not just technical
- Token bucket vs leaky bucket for rate limiting
- Batch processing via queue to reduce cost per LLM call
- AWS SQS FIFO vs Standard: ordering vs throughput trade-offs
- Visibility timeout and consumer idempotency

**ADR-003:** Queue strategy for LLM calls with 1000 rpm rate limit. Choice: SQS Standard with token bucket consumer + DLQ. Justification: decouples production from consumption, respects quota, isolates failures, enables batching to reduce cost.

**Scenario:** System receives 10k req/s, LLM quota is 1000 rpm. Maximum acceptable latency: 5s for 95th percentile. Budget constraint: minimize cost per request. Design the architecture.

---

### `04-cache/notes.md`
Cover in depth:
- Cache as a consistency trade-off, not a performance optimization
- Read-through vs cache-aside vs write-through: when each applies
- TTL-based vs event-driven invalidation: simplicity vs correctness
- **Special focus**: embedding vectors are deterministic and expensive — aggressive caching makes sense; LLM responses are non-deterministic and may expose sensitive data — conservative caching
- Cost impact: cache hit on embedding = avoiding an expensive API call
- Privacy concern: cached embeddings may expose sensitive data from other users (multitenancy)
- ElastiCache vs DynamoDB for distributed cache in AWS context
- Cache stampede: thundering herd problem and how to mitigate
- Semantic caching for LLM: similar queries return the same result

**ADR-004:** Cache strategy for RAG pipeline. Choice: aggressive embedding cache (TTL 7 days, DynamoDB), prompt template cache by version (immutable), conservative LLM response cache (TTL 60s or disabled for critical data). Justification: each type has a different mutability profile and privacy risk.

**Scenario:** Multitenant RAG pipeline where Tenant A must not receive Tenant B's document embeddings from cache. How do you implement secure cache with tenant isolation?

---

### `05-circuit-breaker/notes.md`
Cover in depth:
- The three states: closed, open, half-open — transitions and thresholds
- Why circuit breaker does not prevent failures: it prepares for them
- Failure cascades: how one slow service takes down the entire system (thread pool exhaustion)
- **Special focus**: LLM providers fail regularly (rate limit, timeout, model degradation) — circuit breaker per resource, not per endpoint
- Fallback chain: try OpenAI → try Anthropic → serve cached response → serve degraded response
- Bulkhead pattern: isolate LLM failures from business logic failures
- Timeout vs circuit breaker: complementary, not alternatives
- Metrics for observability: circuit state as a health indicator
- AWS: using CloudWatch to detect and alert on circuit states
- Retry policy with exponential backoff + jitter: why jitter is critical (avoid retry storms)

**ADR-005:** Circuit breaker per resource (OpenAI, Anthropic, internal embedding service) with fallback chain and degraded mode. Threshold: 50% error rate in a 10s window or 5 consecutive failures. Recovery: half-open after 30s. Justification: LLM providers have distinct SLAs; fallback chain avoids degraded user experience.

**Scenario:** OpenAI starts showing P95 latency of 8s instead of the normal 800ms. The circuit breaker must be responsive without being oversensitive (flapping). Define threshold, timeout, and fallback strategy.

---

### `06-system-design/full-design-rag-assistant-end-to-end.md`
Full design of a RAG assistant covering:
- End-to-end data flow with detailed textual diagram
- All 5 patterns integrated: where auth, decoupling, queue, cache, and circuit breaker appear
- AWS service decisions: which service for each role and why
- SLA budget: how to distribute 2s total latency across the pipeline stages
- Scaling strategy: embedding service vs generation service have different profiles
- Privacy compliance: how to ensure one tenant's data does not leak to another
- Cost model: where money is spent and where cache/batch saves

### `06-system-design/full-design-canary-deployment-prompts.md`
Design of canary deployment for prompt templates covering:
- Why prompt templates need canary (changes can silently degrade quality)
- Event versioning: how to route traffic by template version
- Quality metrics: what to measure to decide on rollback (latency, user satisfaction, accuracy)
- Automated evaluation loop: how to automate the rollback decision
- Feature flags for prompt version control
- Rollback in < 30s: how to guarantee it

### `06-system-design/full-design-observability-ai-services.md`
Observability design for AI services covering:
- The three pillars: metrics, logs, traces — what each one answers
- X-Ray tracing in RAG pipeline: how to trace a request end-to-end
- AI-specific metrics: latency per stage, cache hit rate, circuit state, LLM cost per request
- Alerting strategy: what deserves PagerDuty vs Slack vs silence
- Anomaly detection: how to automatically detect prompt quality degradation
- Dashboard design: what an on-call engineer needs to see in < 30 seconds

---

### `07-interview-qa/expected-questions-and-answers.md`
Include likely real interview questions with a response structure for each:

1. Design a RAG assistant that scales to 10k req/s with latency < 2s
2. An LLM model has degraded in quality. How do you detect and mitigate it?
3. How do you protect sensitive data in a multitenant RAG pipeline?
4. What is your deployment strategy for a new prompt template in production?
5. How would you implement auth for 50+ microservices without a SPOF?
6. A dependent service is slow and degrading the entire platform. What do you do?
7. What is the difference between orchestration and choreography in saga? When to use each?
8. How would you reduce LLM cost by 60% without degrading the user experience?
9. Explain backpressure and how you would implement it in an SQS consumer
10. How would you implement observability for an AI pipeline in production?

**Response format for each:**
- Structured opening (1 sentence)
- Core decision + trade-off justification
- What you would NOT do and why
- How it scales or evolves

---

### `07-interview-qa/trade-offs-cheatsheet.md`
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

---

## Final Instructions for the Agent

1. **Create all files** listed in the structure above
2. **Use the provided templates** for each file type (notes, ADR, scenario)
3. **Deep and technical content** — no basic explanations, no unnecessary code snippets
4. **Consistent context** — all examples referencing AWS, EKS, LLM, RAG as in the job description
5. **ADRs must have a "How to Defend in an Interview" section** — verbal articulation script
6. **Scenarios must have a "Reference Answer"** — do not leave blank
7. **trade-offs-cheatsheet.md must be scannable in < 2 minutes** — dense table, no prose
8. **README.md must be the entry point** — must guide study in logical sequence
9. **Do not create code files** — this is an architecture and decision repository, not implementation
10. **Consistent tone**: direct, technical, trade-off-oriented — as a senior would speak to another senior