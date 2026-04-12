# Scenario: Handling 10k RPS with 1000 RPM LLM Limit

**Topic:** queues  
**Level:** Senior  
**Estimated Time:** 15-20 minutes

## Context
Your system receives 10,000 requests per second from users requiring LLM processing (embedding or generation). However, your LLM provider (Anthropic) imposes a strict limit of 1000 requests per minute. Maximum acceptable latency is 5s for 95th percentile of requests. You have a budget constraint to minimize cost per request.

## Requirements / Constraints
- Functional requirement: System must process LLM requests while staying within provider rate limits
- Scale: 10k req/s peak, 1000 rpm LLM quota
- Latency: 95th percentile < 5s end-to-end
- Cost: Minimize cost per request (provider charges per token)
- Compliance: No data loss; every request must eventually be processed or return an error

## Your Task
1. How would you design the queueing system to smooth bursty traffic and respect the LLM rate limit?
2. What specific queue configuration and consumer strategy would you use?
3. How would you handle cost optimization through batching?
4. What metrics would you monitor to ensure the system is working correctly?

***
## Reference Answer

### Proposed Architecture
Two-tier queue system with batching consumers:
- Tier 1: API Gateway → SQS Standard queue (unlimited throughput) for request buffering
- Tier 2: Batch consumers that pull messages, accumulate up to 20 requests, then call LLM API as single batch
- Consumer uses token bucket algorithm: accumulates 1000 tokens per minute, spends 1 token per batch request
- Batch size optimized for provider API: 20 requests per LLM call (embedding) or 1 request per LLM call (generation)
- DLQ for messages exceeding visibility timeout or failing after retries
- Results returned via async callback or polling endpoint

### Key Decisions and Why
- **SQS Standard over FIFO**: Need 10k msg/s throughput; FIFO limited to 300 msg/s. Ordering not critical for LLM requests.
- **Batching Consumers**: Reduces LLM API call overhead by 95% (fixed cost per HTTP request amortized over 20 embeddings). Trade-off: increased latency for individual requests waiting in batch.
- **Token Bucket at Consumer Level**: Allows natural bursting (use accumulated tokens during spikes) while maintaining long-term rate limit. Trade-off: requires state management in consumers.
- **20-Request Batch Size**: Optimized for embedding API where per-request overhead dominates. For generation, batch size=1 due to sequential token generation.
- **Async Result Delivery**: Clients poll or use webhook for results, freeing up HTTP connections immediately.

### What NOT to Do (and Why)
- **Don't use synchronous rate limiting at API gateway**: Would return 429 errors for 99% of requests during peak, destroying user experience and losing traffic.
- **Don't process messages one-by-one**: Would incur massive overhead from HTTP connection costs; batching reduces cost per embedding by ~80%.
- **Don't use fixed window rate limiting**: Would cause bursts at window edges and inefficient quota usage (e.g., idle for 50s then burst 1000 requests).
- **Don't ignore DLQ**: Would lose visibility into poisonous messages that clog the queue and waste processing capacity.

### How to Present in an Interview
"I would implement a two-tier queue system with SQS Standard for request buffering and batching consumers that use token bucket algorithm to throttle LLM API calls. The batching consumers would accumulate up to 20 embedding requests per LLM API call to amortize the fixed HTTP overhead, reducing cost per request by approximately 80%. For rate limiting, I'd implement token bucket at the consumer level to allow natural bursting while maintaining the 1000 RPM long-term average. The trade-off is accepting increased latency for individual requests waiting in batches, but this is worthwhile given the massive cost reduction and ability to handle 10k RPS traffic within a 1000 RPM quota. I'd monitor queue depth, batch size, and token bucket utilization to ensure the system stays within limits while maximizing throughput."