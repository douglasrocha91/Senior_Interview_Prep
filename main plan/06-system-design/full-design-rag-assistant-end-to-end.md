# Full Design: RAG Assistant End-to-End

## End-to-End Data Flow
```
[User Request] 
        → [API Gateway (AuthN)] 
        → [Request Validation & Rate Limiting] 
        → [Embedding Service (Async via EventBridge)] 
        → [Vector Store (with Tenant-Aware Cache)] 
        → [Retrieval Service (OPA-enforced)] 
        → [LLM Service (Circuit Breaker + Fallback Chain)] 
        → [Response Cache (Conservative TTL)] 
        → [API Gateway (Response)] 
        → [User]
```

## Integrated Patterns
1. **AuthN/AuthZ**: 
   - API Gateway validates JWT and passes tenant_id/claims
   - OPA sidecar enforces tenant-level document access in retrieval service
   - Service-to-service via IRSA/mTLS where applicable

2. **Decoupling**:
   - Async pipeline via EventBridge: extract → embed → retrieve → generate
   - Each stage publishes completion events with trace context
   - Idempotency keys prevent duplicate processing

3. **Queues**:
   - SQS Standard with token bucket consumers for LLM rate limiting
   - Batching consumers for embedding calls (20:1 batch ratio)
   - DLQ for poisonous messages

4. **Cache**:
   - Embedding: DynamoDB cache-aside, tenant:doc_hash keys, TTL 7d
   - Prompt templates: Version-based, TTL 1h or event-driven
   - LLM responses: Disabled for PII use cases, TTL 60s otherwise

5. **Circuit Breaker**:
   - Per-resource breakers (OpenAI, Anthropic, Embedding)
   - Fallback chain: Primary → Secondary → Cached → Degraded
   - Threshold: 50% error rate in 10s or 5 consecutive failures

## AWS Service Decisions
- **Compute**: EKS Fargate for stateless services (automatic scaling)
- **Queueing**: SQS Standard + EventBridge (push-based, no polling)
- **Cache**: DynamoDB (tenant isolation via partition key design)
- **Vector Store**: OpenSearch Service with tenant_id filtering
- **Orchestration**: Step Functions for payment saga (not RAG pipeline)
- **API Layer**: API Gateway with Cognito/User Pools for AuthN
- **Monitoring**: CloudWatch + X-Ray for distributed tracing

## SLA Budget Distribution (2s Total)
- API Gateway & AuthN: 100ms
- Embedding Service (cache hit): 20ms / (miss): 120ms
- Vector Store Retrieval: 50ms
- LLM Generation (cached/prompt): 800ms / (uncached): 1800ms
- Response Formatting & Cache: 100ms
- Network/Serialization: 130ms buffer

## Scaling Strategy
- Embedding Service: Scale based on GPU utilization or API rate limits
- Vector Store: Scale based on query latency and memory usage
- LLM Service: Scale based on token throughput and concurrent requests
- Autonomous scaling via HPA with custom metrics (queue depth, latency)

## Privacy Compliance
- Tenant isolation at every layer: auth tokens, cache keys, vector store queries
- Audit trail: AuthN events at gateway, data access logs in vector store
- No cross-tenant caching: tenant_id embedded in all cache keys
- Data minimization: Only essential claims passed between services

## Cost Model
- Primary cost: LLM API calls (60-70% of total)
- Secondary: Embedding API calls (20-30%)
- Tertiary: Compute, storage, networking
- Savings: 
  - Embedding cache reduces API calls by 65%
  - Request batching reduces embedding API overhead by 80%
  - Circuit breaker fallback reduces wasted retries