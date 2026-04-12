# Scenario: JWT Validation for 50+ Microservices

**Topic:** auth  
**Level:** Senior  
**Estimated Time:** 15-20 minutes

## Context
You are designing authentication for a platform with 50+ microservices running on AWS EKS. The system includes:
- User-facing APIs via Application Load Balancer (ALB) -> API Gateway
- Internal service-to-service communication via AWS App Mesh
- A RAG pipeline where services need to access private customer documents
- Services written in Go, Java, and Kotlin
- Current auth approach uses a central auth service that all services call to validate tokens on every request

## Requirements / Constraints
- Functional requirement: Services must validate user identity and service identity
- SLA: 95th percentile latency < 100ms for service-to-service calls
- Scale: 50+ services, peak 10k req/s across the system
- Compliance: Audit trail required for all authentication events (for AI compliance)
- Cost: Minimize operational overhead and infrastructure costs

## Your Task
1. How would you redesign the authentication system to eliminate the central auth service bottleneck while maintaining security?
2. What trade-offs would you accept in your design, and why are they acceptable?
3. How would you handle token revocation in your proposed design?
4. How would your design scale if the system grew to 500+ services?

***
## Reference Answer

### Proposed Architecture
Adopt a hybrid authentication approach:
- API Gateway (or ALB with Cognito) handles initial user authentication and issues JWT tokens
- JWTs are signed with a gateway-held private key; public key distributed to all services
- Services verify JWT signatures locally using the public key and extract claims for authorization
- Service-to-service authentication uses AWS IAM Roles for Service Accounts (IRSA) or mutual TLS
- All initial authentication events are logged at the gateway for centralized audit trail
- Token expiration set to 15 minutes to balance security with revocation needs

### Key Decisions and Why
- **Local JWT verification**: Eliminates network hop for token validation, reducing latency from ~50ms to <2ms per service call. Trade-off: requires secure public key distribution (mitigated by infrastructure as code).
- **Short-lived tokens (15min)**: Limits exposure window if token is compromised. Trade-off: requires more frequent reauthentication, but acceptable given 90-second login SLA.
- **Gateway audit centralization**: Provides single source of truth for authn events without creating validation bottleneck. Trade-off: services don't see failed authn attempts (accepted as gateway logs are sufficient for compliance).
- **IRSA for service-to-service**: Leverages AWS IAM for automatic credential rotation and fine-grained permissions. Trade-off: AWS-specific, but aligns with job context requirements.

### What NOT to Do (and Why)
- **Don't use opaque tokens with introspection**: Would reintroduce the latency bottleneck we're trying to eliminate. Each service call would need to network-hop to auth service, destroying performance gains from microservices.
- **Don't distribute private signing key to services**: Would compromise token security if any service is breached. Private key must remain only at gateway.
- **Don't skip service-level authorization**: Just verifying identity isn't enough; each service must still check if the identity is authorized for the specific operation (e.g., can this user access document X?).

### How to Present in an Interview
"I would implement a hybrid authentication model where the API gateway handles initial authentication and signs JWT tokens, while services verify signatures locally. This eliminates the central auth service bottleneck while maintaining security through short token lifetimes and centralized audit at the gateway. For service-to-service communication, I'd use AWS IRSA for automatic credential rotation. The key trade-off is accepting short-lived tokens, which is worthwhile given the 50x reduction in service-to-service latency and elimination of the authentication single point of failure."