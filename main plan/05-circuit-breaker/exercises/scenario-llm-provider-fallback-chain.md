# Scenario: LLM Provider Fallback Chain Design

**Topic:** circuit-breaker  
**Level:** Senior  
**Estimated Time:** 15-20 minutes

## Context
OpenAI starts showing degraded performance: P95 latency increased from 800ms to 8s, error rate increased from 1% to 15%. Your circuit breaker must be responsive enough to catch this degradation without being so sensitive that it flaps (opens/closes rapidly) during normal brief latency spikes. You need to define appropriate thresholds, timeouts, and fallback strategy.

## Requirements / Constraints
- Functional requirement: System must maintain availability during provider degradation
- Sensitivity: Must distinguish between brief latency spikes and sustained degradation
- Recovery: Should allow provider to recover without manual intervention
- Fallback: Have alternatives available (Anthropic API, cached responses, degraded mode)
- Metrics: Use available signals (latency, error rate, timeout rate)

## Your Task
1. What specific circuit breaker thresholds (error rate, latency, timeout) would you set for this scenario?
2. What timeout duration would you choose for the open state before trying half-open?
3. What fallback chain would you implement and in what order?
4. How would you prevent flapping during brief latency spikes?

***
## Reference Answer

### Proposed Architecture
Adaptive circuit breaker with multi-dimensional thresholds:
- **Error rate threshold**: 15% errors in 30s window (trips at current degradation level)
- **Latency threshold**: P95 latency > 3s for 30 consecutive seconds (catches the 8s degradation)
- **Timeout rate threshold**: 10% timeouts in 30s window
- **Circuit open duration**: 60 seconds before attempting half-open
- **Half-open behavior**: Allow 5 test requests per half-open period
- **Fallback chain**: 
  1. Try Anthropic (if healthy)
  2. Serve cached response (if available and < 60s old)
  3. Serve degraded response (generic template or last known good)
  4. Return error with retry-after header
- **Flapping prevention**: Require threshold breach for 30s continuously; hysteresis with different open/close thresholds

### Key Decisions and Why
- **30s Evaluation Window**: Smooths out brief spikes while catching sustained degradation. Trade-off: slower reaction to sudden outages, but acceptable given our 5s latency SLA.
- **Multi-dimensional Thresholds**: Uses error rate, latency, and timeouts to catch different failure modes. Trade-off: more complex configuration, but more accurate failure detection.
- **60s Open Duration**: Provides adequate recovery time for provider issues while limiting user impact. Trade-off: longer degradation period, but prevents premature retries that could worsen provider load.
- **Limited Half-Open Requests**: Prevents overwhelming recovering service while testing viability. Trade-off: slower recovery confirmation, but protects against flapping.
- **Fallback Chain Order**: Prioritizes alternative provider over cached responses to maintain freshness, then cached, then degraded. Trade-off: may serve slightly stale data, but better than failure.

### What NOT to Do (and Why)
- **Don't use static thresholds based on historical averages**: Would be too sensitive during normal fluctuations or too insensitive during actual degradation.
- **Don't open circuit on single timeout or error**: Would cause excessive flapping during normal operation.
- **Don't use immediate retry in half-open**: Would likely fail if service still degraded, wasting the test opportunity.
- **Don't skip latency thresholds**: Error rate alone misses slow failures that still consume resources and degrade user experience.

### How to Present in an Interview
"I would configure a circuit breaker with multi-dimensional thresholds (error rate >15%, P95 latency >3s, timeout rate >10% over 30s windows) to detect sustained degradation while filtering out brief spikes. The circuit would remain open for 60 seconds before allowing limited test requests in half-open state. For fallback, I'd implement a chain: try Anthropic first, then cached responses (<60s old), then degraded responses, finally erroring with retry-after. The key trade-off is accepting slightly slower failure detection in exchange for stability against flapping, but this is appropriate given our latency SLA and the need to distinguish between transient spikes and genuine degradation requiring fallback."