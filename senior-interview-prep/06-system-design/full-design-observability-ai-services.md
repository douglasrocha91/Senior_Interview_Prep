# Full Design: Observability for AI Services

## Three Pillars Applied to AI Services
**Metrics**: What is happening to the system (rates, ratios, aggregates)
**Logs**: What happened in a specific instance (discrete events with context)
**Traces**: How a request flowed through the system (causal pathway with timing)

## X-Ray Tracing in RAG Pipeline
```
[User Request] 
  → [API Gateway: trace_id injected] 
  → [Auth Service: validates token, adds tenant_id to trace] 
  → [Embedding Producer: publishes event with trace_id] 
  → [Embedding Consumer: extracts trace_id, processes, publishes] 
  → [Vector Store: extracts trace_id, adds document_ids to trace] 
  → [Retrieval Service: extracts trace_id, performs OPA check] 
  → [LLM Producer: publishes generate event with trace_id] 
  → [LLM Consumer: extracts trace_id, calls LLM API] 
  → [Response Cache: stores with trace_id] 
  → [Response Sender: includes trace_id in response headers]
```
Each service adds span attributes: operation type, duration, outcome, tenant_id, cache hit/miss, circuit state.

## AI-Specific Metrics to Collect
- **Latency per Stage**: embedding_publish_latency, retrieval_latency, llm_invoke_latency
- **Cache Performance**: embedding_cache_hit_ratio, prompt_cache_hit_ratio, llm_response_cache_hit_ratio
- **Circuit Breaker State**: openai_circuit_state (0=closed,1=open,2=half-open), anthropic_circuit_state
- **LLM Cost per Request**: input_tokens, output_tokens, estimated_cost_usd
- **Request Volume**: requests_per_second, tokens_per_second
- **Error Rates**: llm_api_error_rate, validation_error_rate, auth_failure_rate
- **Fallback Usage**: primary_provider_usage, fallback_provider_usage, cached_response_usage
- **Quality Signals**: user_feedback_score, retrieval_relevance_score, completion_length_variance

## Alerting Strategy: What Deserves PagerDuty vs Slack
**PagerDuty (Immediate Response Required)**:
- Circuit breaker open for >5 minutes on primary LLM provider
- Embedding cache hit ratio < 50% for 10-minute window (indicates cache storm or missing invalidation)
- Auth failure rate > 5% for 5-minute window (potential attack or misconfiguration)
- Vector store latency P99 > 1s for 5-minute window (index degradation)
- No traces arriving in X-Ray for 2-minute window (complete pipeline failure)

**Slack (Investigate Within Hour)**:
- LLM cost per request > 2x baseline for 30-minute window (prompt drift or inefficient usage)
- Fallback chain usage > 30% for 15-minute window (provider degradation)
- User feedback score < 3.0 for 10-minute sample (quality degradation)
- Retrieval relevance score dropping week-over-week (index freshness issue)
- DLQ depth > 100 messages for 10-minute window (processing issue needing attention)

**Silence (Log Only, No Alert)**:
- Individual cache misses (expected behavior)
- Single timeout or error (retries handle this)
- Normal latency fluctuations within SLA
- Expected traffic patterns (daily/weekly cycles)

## Anomaly Detection for Prompt Quality
1. **Baseline Establishment**: Compute rolling 7-day average for key metrics (latency, token usage, user feedback)
2. **Residual Calculation**: Actual minus baseline for each metric
3. **Multivariate Anomaly Score**: Weighted sum of standardized residuals
4. **Change Point Detection**: CUSUM algorithm to detect sustained shifts in metric means
5. **Trigger Conditions**: Anomaly score > 3 standard deviations for 10 consecutive minutes
6. **Root Cause Analysis**: Automatic drill-down to which metric(s) triggered anomaly
7. **Integration**: Feed into canary deployment evaluation loop for prompt rollback decisions

## Dashboard Design: On-Call View in < 30 Seconds
**Top Row (Critical Health)**:
- [🔴] Pipeline Health: Green if all circuits closed, Yellow if any open, Red if primary LLM open
- [⚡] Request Rate: Current req/s vs expected (sparkline)
- [💰] Cost per Request: Current USD vs baseline (sparkline)
- [🎯] Latency P95: Current ms vs SLA line (2000ms)

**Middle Row (Key Indicators)**:
- [📦] Cache Hit Ratios: Embedding/Prompt/LLM (three sparklines)
- [🔧] Fallback Usage: % requests using primary/secondary/cached/degraded
- [📉] Error Rates: Auth/LLM/Validation (stacked area)
- [👥] User Feedback: Rolling average (sparkline with threshold line)

**Bottom Row (Diagnostic Details)**:
- [🔍] Trace Sample: Latest request trace with timing breakdown
- [🚨] Active Alerts: List of firing alerts with severity and duration
- [📊] Resource Utilization: EKS CPU/Memory, SQS depth, DynamoDB throttling
- [📡] Recent Logs: Structured logs from pipeline services (filterable by trace_id)

**Interactive Features**:
- Click trace_id to see full X-Ray trace
- hover over sparkline to see exact values and timestamp
- click alert to see runbook and related metrics
- time-range selector: last 1h, 6h, 24h, 7d
- service filter: view metrics for specific pipeline stage
```
