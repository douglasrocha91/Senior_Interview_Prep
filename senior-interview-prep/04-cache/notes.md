# Caching in Distributed Systems — Conceptual Notes

## Core Concept
Caching is a consistency trade-off, not merely a performance optimization. Every cache introduces a window of inconsistency where cached data may differ from the source of truth. The fundamental decision in caching is determining how much inconsistency is acceptable for a given performance gain. Effective caching requires understanding the mutability profile of data: how frequently it changes, the cost of obtaining fresh data, and the consequences of serving stale data. Rather than asking "can we cache this?", the senior engineer asks "what level of staleness is acceptable, and what mechanisms exist to detect or mitigate inconsistency?"

## Why It Matters in Distributed Microservices
In microservices architectures, caching decisions amplify across service boundaries. A poorly chosen cache strategy in one service can create inconsistency cascades that affect downstream services. In AI/LLM systems specifically, caching presents unique challenges: embedding vectors are deterministic and expensive to compute, making aggressive caching highly beneficial; however, LLM responses are non-deterministic (temperature > 0) and may contain sensitive user data, requiring conservative caching approaches. Additionally, multitenant systems must ensure cached data doesn't leak between tenants, turning cache isolation into a security and compliance concern rather than just a performance consideration.

## Patterns and Variations
- **Read-through**: Cache sits in the data path; on miss, reads from store and populates cache. Simplifies client logic but increases latency on miss.
- **Cache-aside**: Application manages cache population; on miss, loads from store and updates cache. Most flexible but requires application-level cache management.
- **Write-through**: Writes go to cache and store simultaneously. Ensures cache freshness but increases write latency.
- **Write-behind**: Writes go to cache first, asynchronously persisted to store. Improves write performance but risks data loss on crash.
- **TTL-based Invalidation**: Entries expire after fixed time. Simple to implement but may cause thundering herd or serve stale data.
- **Event-driven Invalidation**: Cache cleared or updated when source data changes. More complex but provides stronger consistency guarantees.
- **Cache Stampede Protection**: Mechanisms (like probabilistic early expiration or mutex) to prevent thundering herd on cache miss.
- **Semantic Caching**: Cache based on query meaning rather than exact string match (e.g., similar SQL queries). Particularly valuable for LLM prompts.
- **Multitenant Cache Isolation**: Separate cache namespaces or encrypted entries to prevent cross-tenant data leakage.

## In the AI/LLM Context (relevant to the role)
Different components of an AI pipeline have vastly different caching characteristics:
- **Embedding Vectors**: Highly deterministic (same input → same output), expensive to compute (API call or GPU time), rarely change if source document static → Aggressive caching (TTL days/weeks) with cache-aside pattern.
- **Prompt Templates**: Deterministic if versioned, cheap to generate, but may evolve → Cache by version with short TTL or event-driven invalidation when version changes.
- **LLM Responses**: Non-deterministic (even with same prompt due to temperature/randomness), may contain PII/sensitive data → Very conservative caching (TTL seconds or disabled) or cache only for deterministic use cases (fact extraction).
- **Retrieval Results**: Semi-deterministic (same query → same top-k results if index static), moderate cost → Medium TTL caching with invalidation on document updates.
- **Tokenization Output**: Deterministic, cheap → Aggressive caching beneficial.

## Key Trade-offs
| Decision | Advantage | Disadvantage | When to Choose |
|----------|-----------|--------------|----------------|
| Cache-aside vs Read-through | Cache-aside: flexible, cache logic in app. Read-through: simpler client, consistent cache population. | Cache-aside: cache pollution risk, complex invalidation. Read-through: increased miss latency, cache coupling to data store. | Choose cache-aside for application-controlled caching (embeddings). Choose read-through for simple, cache-friendly data access layers. |
| TTL-based vs Event-driven | TTL: simple, predictable memory usage. Event-driven: stronger consistency, reduces stale data. | TTL: serves stale data until expiry, thundering herd risk. Event-driven: complex invalidation logic, potential for cache never warming. | Choose TTL for deterministic, infrequently changing data (embeddings). Choose event-driven for frequently changing data where staleness is unacceptable (user profiles). |
| Aggressive vs Conservative TTL | Aggressive: higher hit rate, lower latency, lower cost. Conservative: fresher data, reduced inconsistency risk. | Aggressive: serves stale data, potential security/privacy issues. Conservative: lower hit rate, higher backend load. | Choose aggressive for deterministic, non-sensitive data (embeddings). Choose conservative for sensitive, non-deterministic data (LLM responses with PII). |
| Local vs Distributed Cache | Local: lowest latency, no network hop. Distributed: shared state, survives service restarts. | Local: memory duplication, cache incoherence between instances. Distributed: network latency, single point of failure (if not clustered). | Choose local for read-heavy, latency-sensitive workloads with tolerant inconsistency (embedding lookup). Choose distributed for shared state requirements or when local memory insufficient. |

## Common Interview Questions on This Topic
- How would you design a caching strategy for embedding vectors in a multitenant RAG system?
- When would you choose TTL-based invalidation over event-driven invalidation in an AI pipeline?
- What is cache stampede and how would you mitigate it in a high-traffic LLM service?
- How does caching impact consistency in microservices, and what trade-offs do you consider?
- When would you avoid caching LLM responses entirely, and what alternatives would you consider?

## Connections to Other Topics
Cache design interacts closely with queue patterns (cached results can reduce queue pressure), decoupling (caching intermediate results enables async processing), and observability (cache hit ratio is a key performance metric). For example, aggressive embedding caching reduces the load on embedding services, decreasing queue depth and improving pipeline latency. Cache hit/miss ratios provide valuable signals for auto-scaling decisions. In decoupled systems, caches must be placed carefully to avoid creating new consistency boundaries—e.g., caching retrieval results before the LLM stage requires ensuring the cache is invalidated when underlying documents change.