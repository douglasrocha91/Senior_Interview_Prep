# ADR-005: Per-Resource Circuit Breaker with Fallback Chain for LLM Providers

**Status:** Accepted  
**Context:** LLM pipeline integrating OpenAI and Anthropic APIs with variable reliability  
**Date:** 2026-04

## Context
Our RAG pipeline depends on external LLM providers (OpenAI GPT-4, Anthropic Claude) and an internal embedding service. These services exhibit different failure modes and SLAs:
- OpenAI: Frequent rate limits (429), occasional timeouts, rare model degradation
- Anthropic: Less frequent rate limits, higher latency variability, occasional service outages
- Internal embedding: Network issues, GPU failures, but more predictable SLAs

Without proper isolation, failures in one service consume resources (thread pools, connections) in dependent services, causing cascading failures. We need a circuit breaker strategy that respects each provider's characteristics while enabling graceful degradation.

## Decision
Implement per-resource circuit breakers (one for OpenAI, one for Anthropic, one for internal embedding) with fallback chains and degraded mode. Threshold: 50% error rate in 10s window or 5 consecutive failures. Recovery: half-open after 30s with limited test requests.

## Alternatives Considered

| Option | Description | Advantage | Disadvantage |
|--------|-------------|-----------|--------------|
| No Circuit Breaker | Direct calls with retry logic | Simplest implementation | Resource exhaustion during failures, cascading failures, poor user experience |
| Single Shared Circuit Breaker | One breaker for all LLM calls | Simple to manage | Masks provider-specific issues, inappropriate failover (e.g., tripping on Anthropic issues affects OpenAI calls) |
| Per-Endpoint Circuit Breaker | Breaker per API endpoint (e.g., /embeddings, /completions) | Fine-grained control | Operational overhead, misses correlated failures across endpoints for same provider |
| **Per-Resource Breaker with Fallback Chain (chosen)** | Separate breaker per provider + ordered fallback list | Aligns with provider SLAs, enables smart fallback, minimal overhead | Requires fallback chain design, slightly more complex monitoring |
| Adaptive Threshold Breaker | Threshold adjusts based on historical performance | Self-tuning, adapts to changing conditions | Complex to implement, may oscillate, harder to predict behavior |

## Consequences

**Positive:**
- Provider isolation: Failure in Anthropic doesn't affect OpenAI circuit breaker state
- Smart fallback: Ordered chain (OpenAI → Anthropic → cached → degraded) maintains availability
- Resource protection: Failing fast preserves thread pools and connections for other work
- Observable state: Circuit state metrics inform alerting and scaling decisions
- Aligns with SLAs: Different providers can have different threshold/timeout configurations

**Negative / Accepted Trade-offs:**
- Increased complexity: Managing multiple breakers and fallback logic (accepted given provider diversity)
- Fallback chain latency: Degraded responses may be suboptimal (accepted as better than failure)
- Configuration overhead: Need to tune thresholds per provider (accepted operational complexity)
- Half-open testing: Limited test requests may not represent real load (mitigated by gradual increase)

## Relationships
- Impacts: Queue design (breakers prevent queue overflow), Cache design (fallback chains use cached responses)
- Depends on: Idempotent retry logic, fallback response mechanisms, metrics collection for breaker state

## How to Defend in an Interview
"I chose per-resource circuit breakers with fallback chains for our LLM providers because each provider (OpenAI, Anthropic, internal embedding) has different failure modes and SLAs that require independent management. A single shared breaker would inappropriately tripped for all providers when one experiences issues, while per-endpoint breakers create unnecessary operational overhead. The per-resource approach allows us to tune thresholds and timeouts based on each provider's characteristics—for example, OpenAI might need faster rate limit detection while Anthropic might need more tolerance for latency variability. The fallback chain (try primary provider → secondary provider → cached response → degraded response) ensures we maintain availability even during provider outages. The trade-off is accepting increased complexity in breaker management and fallback logic, but this is essential for building resilient AI services that gracefully degrade rather than catastrophically fail when external dependencies experience issues."