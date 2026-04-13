# Expected Questions and Answers

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

## 1. Design a RAG assistant that scales to 10k req/s with latency < 2s

**Structured opening:** I would design an asynchronous, decoupled RAG pipeline with aggressive caching strategies and proper load distribution across specialized services.

**Core decision + trade-off justification:** Use AWS EventBridge for decoupling pipeline stages (extract → embed → retrieve → generate), with aggressive embedding caching (TTL 7 days in DynamoDB) and conservative LLM response caching (TTL 60s). Implement asynchronous processing to handle the variable LLM latency (2-8s) without blocking threads. Trade-off: Accept eventual consistency for improved throughput and resource utilization.

**What you would NOT do and why:** I would NOT use synchronous HTTP calls between stages because LLM inference latency would block threads, causing poor resource utilization and inability to handle traffic spikes. Synchronous design would require over-provisioning to handle peak LLM latency, increasing costs significantly.

**How it scales or evolves:** Each pipeline stage scales independently based on its bottleneck (embedding stage scales with GPU/API limits, generation with LLM token throughput). As traffic grows, we can add more consumers to EventBridge routes and adjust cache TTLs based on observed hit rates. The design evolves to incorporate semantic caching and prompt versioning for further optimization.

---

## 2. An LLM model has degraded in quality. How do you detect and mitigate it?

**Structured opening:** I would implement automated quality metrics and a fallback chain to detect degradation and route traffic to better-performing models.

**Core decision + trade-off justification:** Monitor key quality metrics (BLEU/ROUGE scores, user satisfaction signals, task completion rates) and implement automated alerts when quality drops below thresholds. Use a circuit breaker per LLM provider with fallback chain: degraded primary model → secondary provider → cached response → degraded response. Trade-off: Increased complexity vs. maintaining user experience during model transitions.

**What you would NOT do and why:** I would NOT rely solely on latency or error rate metrics because model degradation can occur without performance changes (e.g., biased outputs, factual inaccuracies). Pure performance monitoring would miss silent quality degradation that affects user trust.

**How it scales or evolves:** The detection system evolves to include A/B testing frameworks for comparing model versions and automated rollback procedures. As we add more LLM providers, the fallback chain extends naturally, and we can implement model-specific quality thresholds based on use case requirements.

---

## 3. How do you protect sensitive data in a multitenant RAG pipeline?

**Structured opening:** I would implement strict tenant isolation at the data and retrieval layers, ensuring users only access their authorized documents.

**Core decision + trade-off justification:** Use tenant-specific vector stores or namespaces within a shared vector database, enforcing tenant ID validation at retrieval time. Combine with ABAC policies that check document ownership and user permissions before returning context to the LLM. Trade-off: Slightly increased retrieval complexity vs. strong tenant isolation.

**What you would NOT do and why:** I would NOT rely solely on post-retrieval filtering or prompt engineering to prevent cross-tenant data leakage because these approaches are brittle and can be bypassed. Security must be enforced at the retrieval layer where we have guaranteed control over data access.

**How it scales or evolves:** The isolation mechanism scales to support thousands of tenants through efficient vector database partitioning and caching strategies. As compliance requirements evolve (e.g., GDPR right to be forgotten), we can implement tenant-specific data deletion pipelines without affecting other tenants.

---

## 4. What is your deployment strategy for a new prompt template in production?

**Structured opening:** I would use canary deployment with automated quality metrics and rapid rollback capability to safely introduce new prompt templates.

**Core decision + trade-off justification:** Deploy new prompt templates via feature flags, routing small percentages of traffic (5-10%) to the new version while monitoring quality metrics (latency, user engagement, task success). Use EventBridge rules for traffic splitting based on prompt version. Trade-off: Increased monitoring complexity vs. zero-risk production validation.

**What you would NOT do and why:** I would NOT use blue-green deployments for prompt templates because quality degradation is often subtle and gradual, requiring real-user traffic to detect. Blue-green would expose all users to potential quality issues simultaneously.

**How it scales or evolves:** The strategy evolves to include automated evaluation loops that compare new prompts against golden datasets and trigger rollbacks when quality degrades. As we manage more prompt variations, we implement prompt versioning systems and template inheritance to reduce duplication.

---

## 5. How would you implement auth for 50+ microservices without a SPOF?

**Structured opening:** I would implement a hybrid authentication approach where the API gateway handles initial authentication and services verify tokens locally.

**Core decision + trade-off justification:** Use API Gateway for initial user authentication and JWT signing, then have each microservice verify JWT signatures locally using the public key. Services perform authorization checks based on JWT claims. Trade-off: Accept short token lifetimes or revocation list complexity vs. eliminating authentication SPOF and latency bottlenecks.

**What you would NOT do and why:** I would NOT use centralized authentication service calls for every request because this creates a latency bottleneck and single point of failure that doesn't scale with service count, particularly problematic for LLM pipelines with already high latency.

**How it scales or evolves:** The system scales to hundreds of services because verification is local and stateless. As security requirements evolve, we can integrate with AWS IAM Roles for Service Accounts (IRSA) for service-to-service authentication and implement distributed revocation lists using services like Redis or DynamoDB.

---

## 6. A dependent service is slow and degrading the entire platform. What do you do?

**Structured opening:** I would implement circuit breakers and bulkhead patterns to isolate the slow service and prevent failure cascades.

**Core decision + trade-off justification:** Deploy circuit breakers per dependent service with appropriate failure thresholds (error rate, timeout) and bulkheads to isolate thread/connection pools. Use fallback responses or degraded functionality when circuits are open. Trade-off: Increased complexity vs. system resilience and preventing total platform outages.

**What you would NOT do and why:** I would NOT simply increase timeouts or thread pools because this delays the inevitable and can worsen resource exhaustion. Without proper isolation, a slow service will consume all available resources and take down dependent services.

**How it scales or evolves:** The isolation strategy evolves to include adaptive thresholds based on historical performance and predictive scaling based on anticipated load. As we add more dependencies, we implement service mesh solutions (like Istio or AWS App Mesh) for fine-grained traffic control and observability.

---

## 7. What is the difference between orchestration and choreography in saga? When to use each?

**Structured opening:** Orchestration uses a central coordinator to manage saga steps, while choreography relies on services communicating through events without central control.

**Core decision + trade-off justification:** Choose orchestration when you need centralized visibility, complex error handling, or when services have existing transactional dependencies. Choose choreography when you want low coupling, independent service evolution, and can handle eventual consistency. Trade-off: Orchestration provides better visibility but creates a central point of failure and coupling; choreography reduces coupling but makes tracking and error handling more complex.

**What you would NOT do and why:** I would NOT use distributed two-phase commit (2PC) for long-running sagas because it creates blocking resources, doesn't scale well, and is prone to coordinator failures. 2PC assumes short-lived transactions and homogeneous systems, which doesn't match microservices realities.

**How it scales or evolves:** The saga pattern evolves to include hybrid approaches where simple sagas use choreography and complex business transactions use orchestration. As systems grow, we implement saga execution engines with built-in monitoring, compensation triggers, and dead letter handling for failed compensations.

---

## 8. How would you reduce LLM cost by 60% without degrading the user experience?

**Structured opening:** I would implement aggressive caching, batch processing, and intelligent routing to reduce redundant LLM calls while maintaining quality.

**Core decision + trade-off justification:** Cache embedding vectors aggressively (TTL 7 days), implement prompt template caching, batch similar LLM requests, and route simple queries to smaller/cheaper models. Use semantic caching to catch similar queries. Trade-off: Increased system complexity vs. significant cost reduction with minimal quality impact.

**What you would NOT do and why:** I would NOT simply reduce model parameters or use lower-quality models universally because this degrades experience for all users, including those needing advanced capabilities. Blind cost reduction ignores the varying complexity of user queries.

**How it scales or evolves:** The optimization strategy evolves to include dynamic model selection based on query complexity prediction and continuous fine-tuning of smaller models on domain-specific data. As usage patterns change, we adjust cache TTLs, batch sizes, and routing rules based on observed cost/quality trade-offs.

---

## 9. Explain backpressure and how you would implement it in an SQS consumer

**Structured opening:** Backpressure is the practice of propagating overload signals upstream to prevent system overload and resource exhaustion.

**Core decision + trade-off justification:** In SQS consumers, implement backpressure by monitoring queue depth and processing latency, then throttling message consumption when systems are overloaded. Use dynamic scaling based on CloudWatch alarms and implement dead letter queues for poison messages. Trade-off: Reduced throughput during peak load vs. system stability and preventing cascade failures.

**What you would NOT do and why:** I would NOT simply increase consumer count or batch size without limits because this can overwhelm downstream services and cause resource exhaustion. Uncontrolled scaling treats symptoms rather than addressing root causes of overload.

**How it scales or evolves:** The backpressure mechanism evolves to include predictive scaling based on historical patterns and adaptive rate smoothing to prevent thundering herd problems. As systems become more complex, we implement service-level objectives (SLOs) that automatically adjust consumption rates based on error budgets and latency targets.

---

## 10. How would you implement observability for an AI pipeline in production?

**Structured opening:** I would implement end-to-end tracing, AI-specific metrics, and alerting focused on user-impacting issues.

**Core decision + trade-off justification:** Use AWS X-Ray for distributed tracing across pipeline stages, collect AI-specific metrics (cache hit rates per type, LLM cost per request, circuit states, prompt version usage), and implement intelligent alerting that distinguishes between degradation and transient issues. Trade-off: Increased instrumentation overhead vs. faster diagnosis and proactive issue detection.

**What you would NOT do and why:** I would NOT focus solely on infrastructure metrics (CPU, memory, disk) because AI pipeline issues often manifest in quality degradation or incorrect outputs that don't correlate with resource usage. Infrastructure-only monitoring misses the user impact of model drift or prompt ineffectiveness.

**How it scales or evolves:** The observability platform evolves to include automated anomaly detection for quality metrics, predictive alerting based on seasonal patterns, and integration with feedback loops for continuous improvement. As we add more AI capabilities, we expand metric coverage to include fairness indicators, bias detection, and explanation quality measures.