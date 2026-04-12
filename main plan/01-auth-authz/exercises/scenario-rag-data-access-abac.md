# Scenario: RAG Data Access with ABAC

**Topic:** auth  
**Level:** Senior  
**Estimated Time:** 15-20 minutes

## Context
A new compliance requirement mandates that the LLM model in your RAG pipeline can only access data from the authenticated user's tenant. The system currently uses role-based access control (RBAC) where users have roles like "analyst" or "manager," but documents are not tagged with tenant information in a way that enables fine-grained control. You need to modify the authz system to enforce tenant-level document access without modifying each individual service in the pipeline.

## Requirements / Constraints
- Functional requirement: LLM can only retrieve and use documents belonging to the authenticated user's tenant
- Scale: 10,000+ tenants, 100k+ documents total
- Performance: Document retrieval must not add >50ms latency to RAG pipeline
- Compliance: Must satisfy data isolation requirements for multi-tenant SaaS
- Implementation constraint: Cannot modify embedding service or vector store services (owned by other teams)

## Your Task
1. How would you implement tenant-level data isolation in the RAG pipeline without modifying the embedding or vector store services?
2. What authz model would you choose (RBAC vs ABAC vs other) and why?
3. How would you propagate tenant information through the pipeline services?
4. How would you handle the case where a user tries to access documents from another tenant?

***
## Reference Answer

### Proposed Architecture
Implement Attribute-Based Access Control (ABAC) using Open Policy Agent (OPA) as a sidecar or shared service:
- Documents are tagged with tenant_id metadata during ingestion
- User JWT includes tenant_id claim (added during authentication)
- OPA policy evaluates: allow if user.tenant_id == document.tenant_id
- Vector store service queries OPA before returning search results to filtering service
- Embedding service remains unchanged as it only creates vectors, doesn't access tenant data
- Policy is updated in real-time as tenants are added/removed

### Key Decisions and Why
- **ABAC over RBAC**: RBAC cannot express "user can only access documents with matching tenant_id" without creating thousands of roles (one per tenant). ABAC uses attributes for dynamic, scalable policy.
- **OPA as decision point**: Centralizes policy logic while allowing local enforcement. Services query OPA via gRPC/http with user and resource attributes. Trade-off: adds network call, but mitigated by co-locating OPA as sidecar and caching decisions.
- **Tenant ID in JWT**: Propagates identity through stateless tokens. Trade-off: token size increases slightly, but JWT can handle reasonable claim sizes.
- **Filtering at retrieval**: Rather than modifying vector store, add a filtering service that calls vector store then filters results via OPA. This satisfies the constraint of not modifying existing services.

### What NOT to Do (and Why)
- **Don't rely on network segmentation**: Physically isolating tenants by network doesn't scale to 10k+ tenants and doesn't protect against compromised credentials within a tenant.
- **Don't use RBAC with role per tenant**: Would create operational nightmare managing 10k+ roles and require service restarts for each tenant change.
- **Don't filter at LLM level**: By the time data reaches LLM, compliance violation has already occurred (sensitive data accessed). Must enforce at retrieval step.
- **Don't store tenant ID in document content**: Would require scanning document text for tenant info, inefficient and error-prone.

### How to Present in an Interview
"I would implement ABAC using Open Policy Agent with tenant_id as the key attribute. Documents would be tagged with tenant_id during ingestion, and user JWTs would include tenant_id claims. The vector store service would query OPA (deployed as a sidecar for low latency) to verify tenant match before returning results. This approach satisfies the compliance requirement without modifying embedding or vector store services, scales to thousands of tenants through attribute-based policies, and enforces access control at the point of data retrieval where it matters for compliance."