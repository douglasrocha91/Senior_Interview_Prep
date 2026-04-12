# ADR-001: Hybrid API Gateway and Distributed Authentication for Microservices

**Status:** Accepted  
**Context:** Platform with 50+ microservices including RAG service accessing private customer documents on AWS EKS  
**Date:** 2026-04

## Context
We need to authenticate users and service-to-service calls across 50+ microservices running on AWS EKS. The system includes a RAG pipeline that must access private customer documents based on user authentication. Requirements include:
- No single point of failure in authentication path
- Low latency for service-to-service calls (particularly in LLM pipeline stages)
- Centralized audit trail for compliance (who accessed what data for AI model context)
- Ability to revoke credentials when needed
- Integration with AWS IAM for EKS workload identity
- Support for both user-facing APIs and internal service communication

## Decision
Adopt a hybrid approach: API Gateway handles initial authentication and issues JWT tokens signed with a gateway-held key; individual services verify JWT signatures locally using the public key and perform authorization checks.

## Alternatives Considered

| Option | Description | Advantage | Disadvantage |
|--------|-------------|-----------|--------------|
| Centralized Auth Service | All services call a central auth service to validate tokens on every request | Simple credential management, unified audit trail, easy revocation | Creates latency bottleneck, single point of failure, doesn't scale with service count |
| Distributed AuthN (Shared Secret) | Each service validates credentials using a shared secret or public key infrastructure | No SPOF, low latency per service, scales well | Complex credential rotation, no centralized audit trail, harder to implement revocation |
| **Hybrid Approach (chosen)** | API Gateway authenticates and signs JWT; services verify signatures locally and enforce authz | No SPOF for validation, low latency, centralized audit at gateway, services can make local authz decisions | Requires secure key management for gateway signing key, services must trust gateway's public key distribution |

## Consequences

**Positive:**
- Eliminates authentication SPOF: if gateway is down, services can still validate existing tokens until expiration
- Low latency for service-to-service calls: no network hop to auth service for validation
- Centralized audit at gateway: all initial authn events logged in one place for compliance
- Services can make fine-grained authz decisions locally using JWT claims
- Compatible with AWS IAM Roles for Service Accounts (IRSA) on EKS for service-to-service auth

**Negative / Accepted Trade-offs:**
- Token revocation requires short expiration times or distributed revocation list (accepted complexity)
- Gateway becomes a trusted entity for signing (mitigated by strict key management and rotation)
- Services must implement signature verification logic (standard library support available in all target languages)

## Relationships
- Impacts: AuthZ decisions (services use JWT claims for local policy enforcement)
- Depends on: Secure key management infrastructure, JWT library availability in Go/Java/Kotlin/.Net

## How to Defend in an Interview
"I chose a hybrid authentication approach where the API gateway handles initial authentication and signs JWT tokens, while individual services verify signatures locally. This eliminates the single point of failure and latency bottleneck of a centralized auth service while maintaining a centralized audit trail at the gateway. For our specific context of 50+ microservices with LLM pipelines requiring low-latency service-to-service communication, this approach scales well. The trade-off is accepting short token lifetimes or implementing a revocation list, which is worthwhile given the performance and resilience benefits. In an AWS/EKS context, this integrates naturally with IRSA for service-to-service authentication and ALB/API Gateway for edge authentication."