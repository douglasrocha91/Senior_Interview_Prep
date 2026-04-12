# Circuit Breaker in Distributed Systems — Conceptual Notes

## Core Concept
A circuit breaker is a resilience pattern that prevents repeated failed operations by temporarily stopping requests to a failing service, allowing it time to recover. It operates in three states: Closed (requests allowed), Open (requests blocked immediately), and Half-Open (limited test requests allowed). The pattern doesn't prevent failures but prepares for them by failing fast and providing fallback options. Beyond basic failure handling, circuit breakers provide valuable failure metrics, enable bulkhead patterns for resource isolation, and create observable failure domains that inform scaling and placement decisions.

## Why It Matters in Distributed Microservices
Without circuit breakers, microservices suffer from cascading failures where one slow or failing service exhausts thread pools, connection pools, or memory in callers, bringing down the entire system. In AI/LLM systems specifically, LLM providers are notoriously unreliable—experiencing rate limits, timeouts, model degradation, and intermittent outages. Without circuit breakers, a degraded LLM service can take down dependent services by consuming all available resources in synchronous calls. Circuit breakers enable graceful degradation: when the primary LLM fails, the system can fall back to cached responses, alternative providers, or degraded functionality while keeping core services available.

## Patterns and Variations
- **Failure Threshold**: Number of failures or failure rate that trips the circuit open (e.g., 50% errors in 10s window).
- **Timeout Duration**: Time circuit remains open before attempting half-open state.
- **Half-Open Behavior**: Limited requests allowed to test service recovery (often 1 request per timeout period).
- **Resource-specific vs Endpoint-specific**: Breaker per resource (e.g., OpenAI API) vs per endpoint (e.g., /embeddings vs /completions).
- **Fallback Chains**: Ordered list of alternatives (try primary → try secondary → serve cached → serve degraded).
- **Bulkhead Pattern**: Isolates critical resources (thread pools, connections) to prevent failure in one domain from exhausting shared resources.
- **Metrics-based Thresholds**: Using latency percentiles or error budgets instead of simple failure counts.
- **Jitter in Recovery**: Adding randomness to retry timing to prevent thundering herd on service recovery.
- **Manual Override**: Ability to force circuit open/closed for maintenance or testing.

## In the AI/LLM Context (relevant to the role)
LLM failure modes are diverse and provider-specific:
- **Rate Limits (429)**: Requires backing off and potentially switching providers
- **Timeouts (504)**: May indicate temporary overload or model loading issues
- **Model Degradation**: Service returns 200 but quality has deteriorated (requires separate detection)
- **Intermittent Outages**: Complete service unavailability for periods of time
- **Partial Failures**: Some models/features work while others don't

Effective LLM circuit breaking requires per-resource breakers (OpenAI vs Anthropic vs internal embedding) because each has different SLAs and failure characteristics. Fallback chains are particularly valuable: try OpenAI → try Anthropic → serve cached response → serve degraded response. Additionally, circuit breaker state itself becomes an important metric for observability and alerting—persistently open circuits indicate systemic issues requiring attention.

## Key Trade-offs
| Decision | Advantage | Disadvantage | When to Choose |
|----------|-----------|--------------|----------------|
| Per-Endpoint vs Per-Resource | Per-endpoint: fine-grained control. Per-resource: aligns with provider SLAs, less operational overhead. | Per-endpoint: higher overhead, may miss correlated failures. Per-resource: less granular, may mask endpoint-specific issues. | Choose per-resource for external APIs with unified SLAs (OpenAI). Choose per-endpoint for internal services with varying reliability. |
| Fast vs Slow Timeout | Fast: fails quickly, preserves resources. Slow: allows transient issues to resolve. | Fast: may trip on temporary blips. Slow: holds resources longer during actual failures. | Choose fast timeout for user-facing requests where latency matters. Choose slow for background tasks where completion is preferred over speed. |
| Fixed vs Adaptive Threshold | Fixed: simple to understand and configure. Adaptive: adjusts based on historical performance. | Fixed: may be too sensitive or insensitive as traffic patterns change. Adaptive: more complex, requires historical data. | Choose fixed for stable, predictable traffic. Choose adaptive for variable workloads where baseline error rate changes. |
| Simple Fallback vs Fallback Chain | Simple: one alternative. Chain: multiple fallback options. | Simple: limited degradation options. Chain: increased complexity, potential for confusing error handling. | Choose fallback chain for user-facing AI services where degradation steps exist. Choose simple for internal services with clear primary/secondary. |

## Common Interview Questions on This Topic
- How would you design circuit breakers for LLM providers with different failure modes and SLAs?
- What is the difference between circuit breaker and bulkhead patterns, and how do they complement each other?
- How would you set circuit breaker thresholds for an LLM service that experiences regular rate limiting?
- How does circuit breaker state inform observability and alerting decisions?
- When would you choose a half-open state that allows multiple test requests versus a single test request?

## Connections to Other Topics
Circuit breaker design interacts with queue patterns (queues provide buffering where circuit breakers isolate failures), cache strategies (fallback chains often include cached responses), and decoupling (async systems benefit from circuit breakers preventing producer overload). For example, in an LLM pipeline with queued requests, circuit breakers on the consumer side prevent queue overflow during provider outages. Cache hit rates may increase when circuit breakers are open as fallback chains serve cached responses. In decoupled systems, circuit breakers should be placed at service boundaries where external dependencies create failure risks.