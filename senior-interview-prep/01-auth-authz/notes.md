# Auth and Authorization — Conceptual Notes

## Core Concept
Authentication (AuthN) and Authorization (AuthZ) are distinct but complementary security concerns in distributed systems. AuthN verifies "who you are" through credentials (passwords, tokens, certificates), while AuthZ determines "what you can do" based on identity, roles, attributes, and policies. In microservices, this separation becomes critical because services must independently validate identity and enforce access decisions without creating bottlenecks or single points of failure. Modern approaches decouple identity verification from policy enforcement using signed tokens (like JWT) and external policy engines (like OPA), allowing services to make authz decisions locally while trusting centrally issued identity assertions.

## Why It Matters in Distributed Microservices
Without proper authn/authz patterns, microservices architectures suffer from several critical issues: every service becomes a potential entry point for attackers (expanding attack surface), latency increases due to round-trips to central auth services, and operational complexity explodes when trying to maintain consistent policies across dozens of services. In AI/LLM systems specifically, inadequate authz can lead to data leakage where one tenant accesses another's documents through RAG pipelines, violating compliance requirements like GDPR or CCPA. Conversely, overly restrictive authn can create performance bottlenecks that negate the scalability benefits of microservices, particularly when LLM inference already introduces significant latency.

## Patterns and Variations
- **Centralized AuthN**: All authentication handled by a single service (e.g., OAuth2 Authorization Server). Simple to manage but creates SPOF and latency.
- **Distributed AuthN**: Each service validates credentials independently (e.g., shared secret for HMAC). Eliminates SPOF but complicates credential rotation and audit trails.
- **Hybrid Approach**: Gateway handles initial AuthN and token signing; services verify signatures locally. Balances security, performance, and operational simplicity.
- **RBAC**: Role-Based Access Control. Assigns permissions to roles, then roles to users. Simple but coarse-grained.
- **ABAC**: Attribute-Based Access Control. Uses attributes (user, resource, environment) to make dynamic decisions. Flexible but complex to implement and audit.
- **Policy as Code**: External policy engine (OPA) evaluates policies defined in Rego. Enables consistent, version-controlled authz across services.

## In the AI/LLM Context (relevant to the role)
In RAG pipelines, authz is particularly challenging because the LLM needs access to specific documents based on the user's identity and permissions. Simply authenticating the user isn't sufficient; the system must ensure the retrieval component only returns documents the user is authorized to see. This requires propagating user identity or tokens through the pipeline (embedding service → vector store → LLM) and enforcing document-level access controls at retrieval time. Additionally, audit trails must capture which user data influenced which LLM outputs for AI compliance and fairness monitoring. Service-to-service authentication (mTLS) becomes important when embedding services or vector stores are managed by different teams or have different trust boundaries.

## Key Trade-offs
| Decision | Advantage | Disadvantage | When to Choose |
|----------|-----------|--------------|----------------|
| Centralized vs Distributed AuthN | Centralized: simpler credential management, unified audit. Distributed: no SPOF, lower latency per service. | Centralized: latency bottleneck, SPOF risk. Distributed: complex credential rotation, inconsistent policies. | Choose distributed/hybrid when scale > 20 services or latency-sensitive paths exist. Choose centralized for < 10 services with simple requirements. |
| JWT vs Opaque Tokens | JWT: stateless verification, contains claims for local authz. Opaque: revocable, no size limits. | JWT: difficult to revoke, size limits, signature verification overhead. Opaque: requires introspection call, stateful. | Choose JWT for service-to-service or short-lived user sessions. Choose opaque for long-lived sessions requiring revocation. |
| RBAC vs ABAC | RBAC: simple to understand and administer. ABAC: fine-grained, context-aware decisions. | RBAC: role explosion, coarse-grained. ABAC: policy complexity, performance overhead, harder to audit. | Choose RBAC for static role-based access (e.g., admin/user). Choose ABAC for dynamic contexts like multi-tenant RAG with document-level permissions. |
| API Gateway Auth vs Service-Level Auth | Gateway: single point of enforcement, reduces service complexity. Service-level: defense in depth, no trust in network. | Gateway: SPOF, adds latency, services must trust network. Service-level: duplicated logic, increased service complexity. | Choose gateway for North-South traffic with standard policies. Choose service-level for East-West traffic or zero-trust architectures. |

## Common Interview Questions on This Topic
- How would you implement authentication for 50+ microservices without creating a single point of failure?
- What's the difference between authentication and authorization, and why does it matter in a RAG pipeline?
- How do you prevent a user from accessing another tenant's documents in a multitenant RAG system?
- When would you choose JWT over opaque tokens for service-to-service communication?
- How would you implement audit logging for AI compliance to track which user data influenced model outputs?

## Connections to Other Topics
AuthZ decisions directly impact cache design (what can be cached and shared), decoupling patterns (how identity flows between services), and observability (tracing user context across services). For example, aggressive caching of embeddings requires careful consideration of authz boundaries to prevent cross-tenant data leakage. Similarly, async LLM pipelines need to propagate user identity through event messages to ensure proper authorization at each stage. Circuit breaker patterns must also consider auth service failures—should a failing auth service trigger circuit breakers for dependent services, or should services fail closed/open based on cached tokens?