# Senior Engineer Interview Preparation Repository

This repository is designed for interview preparation targeting a **Senior Engineer** role focused on distributed microservices architecture with integrated AI (LLM/RAG). It contains conceptual notes, ADRs (Architecture Decision Records), and scenario exercises focused on **architectural decision-making and trade-offs**, not code implementation.

## Job Context
- Microservices architecture on **AWS (EKS, SQS, SNS, DynamoDB, EC2, EventBridge)**
- Integration of **LLM (OpenAI, Anthropic), RAG, MCP, and embedding-based search**
- **Zero-downtime deployments, canary releases, feature flags**
- **Observability**: metrics, tracing, alerting (X-Ray, CloudWatch, Prometheus)
- **Infrastructure as Code**, Docker, Helm, Kubernetes
- Languages: Golang, Java, Kotlin, .Net
- Compliance with **privacy and fairness in AI**

## Directory Structure
```
senior-interview-prep/
├── README.md
├── 01-auth-authz/
│   ├── notes.md
│   ├── decisions/
│   │   └── ADR-001-api-gateway-vs-distributed-auth.md
│   └── exercises/
│       ├── scenario-jwt-validation-50-services.md
│       └── scenario-rag-data-access-abac.md
├── 02-decoupling/
│   ├── notes.md
│   ├── decisions/
│   │   └── ADR-002-sync-vs-async-llm-pipeline.md
│   └── exercises/
│       ├── scenario-llm-pipeline-4-stages.md
│       └── scenario-saga-payment-rollback.md
├── 03-queues/
│   ├── notes.md
│   ├── decisions/
│   │   └── ADR-003-queue-strategy-llm-rate-limit.md
│   └── exercises/
│       └── scenario-10k-rps-llm-throttle.md
├── 04-cache/
│   ├── notes.md
│   ├── decisions/
│   │   └── ADR-004-cache-strategy-rag-pipeline.md
│   └── exercises/
│       └── scenario-cache-embeddings-privacy.md
├── 05-circuit-breaker/
│   ├── notes.md
│   ├── decisions/
│   │   └── ADR-005-circuit-breaker-per-resource-llm.md
│   └── exercises/
│       └── scenario-llm-provider-fallback-chain.md
├── 06-system-design/
│   ├── full-design-rag-assistant-end-to-end.md
│   ├── full-design-canary-deployment-prompts.md
│   └── full-design-observability-ai-services.md
└── 07-interview-qa/
    ├── expected-questions-and-answers.md
    └── trade-offs-cheatsheet.md
```

## How to Use This Repository
1. **Start with notes.md** in each topic to understand the core concepts
2. **Review the ADR** to see concrete architectural decisions with trade-offs
3. **Practice with scenarios** to apply your decision-making skills
4. **Study interview Q&A** to prepare for real interviews
5. **Reference the trade-offs cheatsheet** for quick review

## Philosophy
**Decision-making > implementation**: This repository focuses on the "why" behind architectural choices, not the "how" of coding. Each file is self-contained and written for senior engineers who need to evaluate trade-offs in distributed AI systems.

All examples are contextualized to AWS, EKS, LLM, RAG, and the specific constraints mentioned in the job description.