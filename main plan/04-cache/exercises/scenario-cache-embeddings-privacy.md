# Scenario: Cache Embeddings with Tenant Privacy

**Topic:** cache  
**Level:** Senior  
**Estimated Time:** 15-20 minutes

## Context
You are designing a multitenant RAG pipeline where Tenant A must not receive Tenant B's document embeddings from cache. The system uses an embedding service (either self-hosted or API-based) that is expensive to call, making caching desirable for performance and cost reasons. However, naively caching embeddings by document content hash creates a privacy risk: if two tenants have identical document content, caching by hash would allow one tenant to access another's embeddings through the cache.

## Requirements / Constraints
- Functional requirement: Embedding cache must provide tenant isolation; no cross-tenant leakage
- Scale: 1000+ tenants, 1M+ documents total
- Performance: Cache hit should reduce embedding latency from 100ms to <10ms
- Cost: Minimize embedding API calls (primary cost driver)
- Implementation: Using AWS ElastiCache Redis or DynamoDB for distributed cache

## Your Task
1. How would you design the embedding cache to prevent cross-tenant data leakage?
2. What cache key strategy would you use to ensure tenant isolation?
3. How would you handle cache invalidation when tenant documents are updated or deleted?
4. What metrics would you monitor to detect potential privacy breaches in the cache?

***
## Reference Answer

### Proposed Architecture
Tenant-aware cache keys with namespace isolation:
- Cache key format: `tenant:{tenant_id}:doc:{document_hash}:v:{version}`
- Document hash computed from normalized content (whitespace, case-insensitive if appropriate)
- Version field for manual invalidation when needed
- Cache stored in AWS DynamoDB with tenant_id as partition key prefix
- Cache-aside pattern: application checks cache before calling embedding service
- On document update/delete: invalidate specific cache keys via version increment or direct deletion

### Key Decisions and Why
- **Tenant ID in Cache Key**: Ensures mathematical separation of cache entries between tenants. Even identical document hashes produce different keys due to tenant_id prefix.
- **Document Hash Normalization**: Prevents cache misses due to insignificant formatting differences while maintaining security (hash doesn't reveal content).
- **Version Field**: Allows bulk invalidation without knowing all document hashes (e.g., when changing embedding model).
- **DynamoDB over ElastiCache**: Better fits the access pattern (tenant_id prefix queries) and provides fine-grained IAM policies per tenant.
- **Cache-aside Pattern**: Gives application control over cache population and invalidation logic.

### What NOT to Do (and Why)
- **Don't cache by document hash only**: Would allow cross-tenant access when documents have identical content (e.g., standard contracts, public filings).
- **Don't use global cache flush for tenant deletion**: Inefficient and impacts other tenants; use targeted invalidation instead.
- **Don't encrypt cache values as sole protection**: Encryption prevents casual inspection but doesn't stop a compromised service from decrypting and leaking data; tenant isolation in keys is stronger.
- **Don't ignore cache stampede**: Use probabilistic early expiration or mutex to prevent thundering herd when popular documents expire.

### How to Present in an Interview
"I would implement tenant-aware cache keys that include the tenant_id as a prefix, ensuring mathematical isolation between tenants even when document content is identical. The cache key would be structured as `tenant:{tenant_id}:doc:{document_hash}:v:{version}` stored in DynamoDB with appropriate IAM policies. For cache invalidation, I'd use version increments for bulk changes or direct deletion for individual document updates. The key trade-off is slightly more complex cache key management, but this is essential for preventing cross-tenant data leakage in a multitenant system. I'd monitor cache hit rates per tenant and set alerts for anomalous patterns that might indicate privacy breaches, such as one tenant suddenly accessing another tenant's usual documents."