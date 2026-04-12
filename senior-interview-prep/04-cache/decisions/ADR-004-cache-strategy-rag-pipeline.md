# ADR-004: Tiered Caching Strategy for RAG Pipeline Based on Data Mutability

**Status:** Accepted  
**Context:** RAG pipeline with embedding generation, retrieval, and LLM response generation  
**Date:** 2026-04

## Context
We need to design a caching strategy for our RAG pipeline that balances performance, cost, and consistency requirements. Different pipeline stages have distinct data characteristics:
- Embedding vectors: deterministic, expensive to compute (API call/GPU), rarely change if source static
- Prompt templates: deterministic when versioned, cheap to generate, but evolve over time
- LLM responses: non-deterministic (temperature > 0), may contain sensitive user data, expensive to generate
- Retrieval results: semi-deterministic, moderate cost, change when underlying documents update

We must also consider multitenancy requirements: cached data must not leak between tenants.

## Decision
Implement a tiered caching strategy:
- Aggressive caching for embedding vectors (TTL 7 days, DynamoDB, cache-aside)
- Version-based caching for prompt templates (TTL 1 hour or event-driven on version change)
- Conservative or disabled caching for LLM responses (TTL 60s for non-sensitive use cases, disabled for PII)
- Cache-aside pattern with tenant isolation (separate cache namespaces or encrypted entries)

## Alternatives Considered

| Option | Description | Advantage | Disadvantage |
|--------|-------------|-----------|--------------|
| Uniform TTL (1 hour) for all data | Simple, consistent caching approach | Easy to implement and manage | Over-caches sensitive LLM responses, under-caches expensive embeddings |
| No caching for LLM responses | Eliminates privacy and consistency risks | Safest approach for sensitive data | Misses performance opportunity for deterministic use cases |
| Event-driven invalidation everywhere | Strongest consistency guarantees | Minimizes stale data risk | Complex to implement, may cause cache never to warm for infrequently updated data |
| **Tiered strategy by data type (chosen)** | Match caching aggressiveness to data mutability and sensitivity | Optimal performance/cost trade-off per data type, addresses privacy concerns | Requires more complex cache management logic |

## Consequences

**Positive:**
- Cost optimization: Avoids expensive embedding API calls through aggressive caching (60-80% cost reduction)
- Privacy protection: Conservative LLM response caching prevents accidental PII leakage
- Performance improvement: Reduced latency for cache hits (embedding: 10ms vs 100ms API call)
- Multitenant safety: Tenant isolation prevents cross-tenant data leakage through cache
- Operational simplicity: Clear rules for what to cache and for how long

**Negative / Accepted Trade-offs:**
- Increased complexity: Different cache policies per data type require more sophisticated cache management
- Stale embedding risk: Embeddings may be stale for up to 7 days if source document changes (accepted as documents are infrequently updated)
- Cache warm-up delay: New prompt template versions incur cache miss penalty (mitigated by pre-warming during deployment)
- Inconsistency window: LLM responses may be stale for up to 60 seconds (accepted for non-sensitive use cases where slight staleness is tolerable)

## Relationships
- Impacts: Queue design (cache hits reduce queue pressure), Observability (cache hit ratio as key metric)
- Depends on: Tenant context propagation, cache library with namespace support, cache warming procedures

## How to Defend in an Interview
"I chose a tiered caching strategy that matches caching aggressiveness to the mutability and sensitivity of each data type in our RAG pipeline. For embedding vectors—which are deterministic, expensive to compute, and rarely change—I implemented aggressive caching with a 7-day TTL in DynamoDB using a cache-aside pattern. For prompt templates, I used version-based caching with event-driven invalidation when versions change. For LLM responses, I implemented conservative caching (60-second TTL) or disabled caching entirely for use cases involving sensitive data. The key trade-off is accepting potential staleness in exchange for significant cost and performance improvements, but this is carefully calibrated per data type: we tolerate embedding staleness because source documents change infrequently, and we limit LLM response caching to non-sensitive scenarios or very short TTLs. This approach reduces embedding costs by approximately 70% while maintaining privacy and consistency guarantees where they matter most."