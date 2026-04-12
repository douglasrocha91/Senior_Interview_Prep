# Scenario: Saga Payment Rollback Without 2PC

**Topic:** decoupling  
**Level:** Senior  
**Estimated Time:** 15-20 minutes

## Context
You have a 5-step saga for processing payments in an e-commerce system: reserve_inventory → charge_card → generate_invoice → send_confirmation → update_analytics. Step 3 (generate_invoice) fails intermittently due to third-party service timeouts. You need to implement rollback without using distributed two-phase commit (2PC), which is prohibited due to scalability concerns.

## Requirements / Constraints
- Functional requirement: If any step fails, all previous steps must be compensated
- Scale: 500 req/s peak payment processing
- Consistency: Must maintain data consistency across services despite failures
- Latency: Compensation must complete within 5s for 95th percentile of failures
- Prohibition: Cannot use 2PC or any locking-based distributed transaction mechanism

## Your Task
1. How would you design the compensation transactions for each step?
2. What pattern would you use to coordinate the saga (orchestration vs choreography) and why?
3. How would you handle the case where a compensation transaction itself fails?
4. How would you ensure the saga doesn't hold resources indefinitely during failure scenarios?

***
## Reference Answer

### Proposed Architecture
Use orchestrator-based saga with idempotent compensating transactions:
- Each step publishes success/failure event to orchestrator (AWS Step Functions)
- Orchestrator maintains saga state and triggers compensations in reverse order
- Compensating transactions: uncharge_card → restock_inventory → cancel_invoice (send_confirmation and update_analytics are idempotent/no-op)
- All services implement idempotency keys to handle duplicate requests
- Compensation timeout set to 10s with exponential backoff retry

### Key Decisions and Why
- **Orchestration over Choreography**: Provides centralized visibility into saga state and simplifies compensation triggering. Trade-off: creates central orchestrator, but Step Functions is managed and highly available.
- **Idempotent Compensations**: Each compensation can be safely retried (e.g., uncharge_card is no-op if already refunded). Essential for handling network failures during compensation.
- **Reverse Order Execution**: Compensates in LIFO order to maintain semantic correctness (un charge before restock inventory).
- **State Persistence**: Orchestrator persists saga state to survive service restarts during long-running compensation.

### What NOT to Do (and Why)
- **Don't use 2PC**: Would lock resources (inventory, credit authorization) for duration of saga, destroying throughput and scalability.
- **Don't make compensations non-idempotent**: Would cause inconsistent states if compensation retries due to network issues.
- **Don't skip compensation for idempotent steps**: While send_confirmation and update_analytics might be safe to skip, explicit compensations make the saga logic clearer and more maintainable.
- **Don't compensate in parallel**: Could cause race conditions (e.g., charging card while trying to uncharge it).

### How to Present in an Interview
"I would implement an orchestrator-based saga using AWS Step Functions where each step publishes events and the orchestrator triggers compensating transactions in reverse order upon failure. Each service would implement idempotent operations using idempotency keys to handle retries safely. The key trade-off is accepting eventual consistency and the complexity of designing compensating transactions, but this avoids the resource locking and scalability issues of 2PC. For payment processing, this approach provides adequate consistency guarantees while maintaining 500 req/s throughput."