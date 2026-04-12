# Full Design: Canary Deployment for Prompt Templates

## Why Prompt Templates Need Canary
Prompt templates in AI systems can silently degrade output quality without causing errors or latency changes. A small wording change might:
- Trigger different model behaviors (reasoning vs factual)
- Activate unsafe completion paths
- Reduce relevance of retrieved context
- Increase token consumption without improving quality
Unlike traditional code, prompt changes don't fail tests or increase latency—they change the semantic output in ways that are difficult to detect with conventional monitoring.

## Event Versioning for Traffic Routing
- Each prompt template version gets a unique identifier (semantic version or hash)
- Events published to EventBridge include prompt_version in metadata
- Retrieval and LLM services extract prompt_version from events
- Router service examines prompt_version and routes to appropriate processing flow
- Canary percentage configured via Dynamic Configuration (Feature Flag service)
- Traffic splitting: 95% stable version → 5% canary version
- Router uses consistent hashing on request_id to ensure same user sees same version

## Quality Metrics for Rollback Decisions
- **Latency**: P95 response time (should not degrade >10%)
- **Error Rate**: HTTP 5xx or service exceptions (should not increase)
- **User Feedback**: Explicit thumbs-up/down or regret signals (if available)
- **Retrieval Relevance**: Click-through rate on cited sources (if tracked)
- **Completion Length**: Abnormal changes in output length
- **Token Consumption**: Input/output token count (cost proxy)
- **Semantic Similarity**: Embedding distance between canary and stable outputs (sampled)
- **Safety Triggers**: Detection of harmful content in outputs

## Automated Evaluation Loop
1. Deploy new prompt version to canary group (5% traffic)
2. Collect metrics for 10-minute evaluation window
3. Compare against stable version baseline using statistical significance test
4. If all metrics pass threshold: promote to 100%
5. If any metric fails: rollback to previous version and alert
6. Loop repeats for each new prompt version commit
7. Manual override available for emergency rollbacks

## Feature Flags for Prompt Version Control
- LaunchDarkly-style feature flag service integrated with CI/CD
- Flag key: `prompt_version:{template_name}`
- Flag value: percentage rollout (0-100) or specific version string
- Flags evaluated at router service with <1ms latency
- Flag changes propagate via pub/sub (sub-second propagation)
- Audit trail: all flag changes logged with user and timestamp
- Kill switch: ability to immediately route 100% to last known good version

## Rollback in < 30 Seconds
- Router service loads flag configuration from local cache (updated via pub/sub)
- Changing flag to 0% canary takes effect immediately for new requests
- In-flight requests complete with current version (acceptable)
- No service restart or redeployment needed
- Fallback: if flag service unavailable, router defaults to stable version
- Monitoring: dashboard shows current rollout percentage and version distribution