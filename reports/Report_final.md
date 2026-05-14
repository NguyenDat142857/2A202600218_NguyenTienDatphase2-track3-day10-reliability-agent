# Day 10 Reliability Final Report

## Student Information

| Field | Value |
|---|---|
| Student Name | Nguyen Tien Dat |
| Student ID | 2A202600218 |
| Repository | 2A202600218_NguyenTienDatphase2-track3-day10-reliability-agent-main |
| Subject | Reliability Engineering for Production Agents |
| Lab | Day 10 Reliability Agent |
| Environment | Python + Redis + Docker |
| Operating System | Windows 11 |
| IDE | VSCode |

---

# 1. Architecture Summary

This project implements a production-style reliability layer for an LLM gateway system.  
The system improves reliability through:

- Circuit breaker protection
- Automatic fallback routing
- Cache optimization
- Redis shared cache
- Chaos testing
- Metrics collection

The gateway first checks whether a cached response exists.  
If there is no cache hit, the request is routed through provider-specific circuit breakers.

If the primary provider fails or becomes unstable, the system automatically routes traffic to the backup provider.  
If all providers fail, the gateway returns a static fallback response instead of crashing.

This design improves:

- Availability
- Fault tolerance
- Recovery behavior
- Cost optimization
- Response latency

---

## Architecture Flow

```text
                    +-------------------+
                    |       User        |
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    |      Gateway      |
                    +---------+---------+
                              |
                    +---------+---------+
                    |   Cache Check     |
                    +---------+---------+
                              |
                +-------------+-------------+
                |                           |
                v                           v
        Cache Hit                    Cache Miss
                |                           |
                v                           v
      Cached Response           Circuit Breaker Layer
                                            |
                    +-----------------------+-----------------------+
                    |                                               |
                    v                                               v
          Primary Provider                               Backup Provider
                    |                                               |
             Success / Fail                                 Success / Fail
                    |                                               |
                    +-----------------------+-----------------------+
                                            |
                                            v
                                   Static Fallback
```

---

# 2. Reliability Features

## 2.1 Circuit Breaker

The circuit breaker protects the system from continuously sending requests to failing providers.

Three states were implemented:

| State | Description |
|---|---|
| CLOSED | Normal operation, requests allowed |
| OPEN | Provider considered unhealthy, requests blocked |
| HALF_OPEN | Recovery probe state |

### Circuit Breaker Behavior

- Failures are counted while the circuit is CLOSED
- After reaching the failure threshold, the circuit transitions to OPEN
- OPEN circuits fail fast without retry storms
- After timeout expiration, the breaker enters HALF_OPEN
- Successful probes close the circuit
- Failed probes immediately reopen the circuit

### Benefits

- Prevents cascading failures
- Reduces unnecessary retries
- Improves recovery handling
- Protects unstable providers

---

## 2.2 Fallback Routing

When the primary provider fails:

1. The circuit breaker opens
2. Traffic automatically routes to the backup provider
3. Users still receive responses
4. Availability remains high

If all providers fail:

- The system returns a static fallback message
- The gateway never crashes completely

Example routes:

```text
primary:primary
fallback:backup
cache_hit:1.00
static_fallback
```

---

## 2.3 Cache System

Two cache systems were implemented:

| Cache Type | Description |
|---|---|
| ResponseCache | In-memory cache |
| SharedRedisCache | Redis-based shared cache |

### Cache Features

- TTL expiration
- Similarity-based lookup
- Exact match lookup
- False-hit detection
- Privacy guardrails

### Privacy Protection

Sensitive queries are never cached.

Examples:

```text
balance
password
account
credit card
user IDs
```

### False-Hit Protection

The cache prevents incorrect matches between queries containing different years.

Example:

```text
refund policy 2024
refund policy 2026
```

These queries should NOT match.

---

# 3. Configuration

| Setting | Value | Reason |
|---|---:|---|
| failure_threshold | 3 | Opens after repeated failures while avoiding overly sensitive triggering |
| reset_timeout_seconds | 2.0 | Fast recovery checks during chaos testing |
| success_threshold | 1 | Single successful HALF_OPEN probe closes the circuit |
| cache TTL | 300 | Five-minute cache lifetime balances freshness and performance |
| similarity_threshold | 0.92 | Prevents date-sensitive false cache hits |
| cache backend | redis | Enables multi-instance shared cache |
| load_test requests | 100 | Generates stable reproducible metrics |

---

# 4. SLO Definitions

The following SLOs were defined to evaluate system reliability.

| SLI | Target | Actual Value | Status |
|---|---|---:|---|
| Availability | >= 99% | 1.0 | PASS |
| Error Rate | < 5% | 0.0 | PASS |
| P95 Latency | < 2500 ms | 320.51 | PASS |
| Cache Hit Rate | >= 10% | 0.7775 | PASS |
| Recovery Time | < 5000 ms | 2292.38 | PASS |
| Fallback Success Rate | >= 95% | 1.0 | PASS |

---

# 5. Metrics Summary

## Final Metrics

| Metric | Value |
|---|---:|
| total_requests | 400 |
| availability | 1.0 |
| error_rate | 0.0 |
| latency_p50_ms | 0.35 |
| latency_p95_ms | 320.51 |
| latency_p99_ms | 525.59 |
| fallback_success_rate | 1.0 |
| cache_hit_rate | 0.7775 |
| circuit_open_count | 5 |
| recovery_time_ms | 2292.38 |
| estimated_cost | 0.041494 |
| estimated_cost_saved | 0.311 |

---

## Metric Analysis

### Availability

The system maintained 100% availability during chaos testing.  
Even when providers failed, fallback routing ensured continued service.

### Latency

P50 latency became extremely low because most requests were served directly from cache.

P95 and P99 latency remained stable even during provider failures.

### Cost Savings

The cache significantly reduced provider usage cost.

Estimated cost savings:

```text
0.311
```

This demonstrates the value of aggressive cache reuse.

### Circuit Recovery

The circuit breaker successfully recovered providers after failures.

Average recovery time:

```text
2292.38 ms
```

---

# 6. Cache Comparison

## Without Cache vs With Cache

| Metric | Without Cache | With Cache | Improvement |
|---|---:|---:|---|
| latency_p50_ms | 237.6 | 0.35 | -99.9% |
| latency_p95_ms | 510.01 | 320.51 | -37.1% |
| estimated_cost | 0.185782 | 0.041494 | -77.7% |
| cache_hit_rate | 0.0 | 0.7775 | +0.7775 |

---

## Cache Analysis

The cache dramatically improved:

- Response speed
- Cost efficiency
- System scalability

A high cache hit rate reduced repeated provider calls.

False-hit protection prevented incorrect semantic matches between unrelated queries.

---

# 7. Redis Shared Cache

## Why Shared Cache Matters

In-memory cache only exists inside one process.

This becomes a problem in distributed deployments because:

- Each instance has isolated cache state
- Duplicate provider calls increase cost
- Cache hit consistency decreases

Redis solves this by providing centralized shared cache storage.

---

## Redis Implementation

The `SharedRedisCache` implementation supports:

- Exact-match lookup
- Similarity-based lookup
- TTL expiration
- Shared cache state
- Privacy protection
- False-hit detection

Redis keys:

```text
rl:cache:<query_hash>
```

Stored fields:

```text
query
response
```

---

## Shared Cache Evidence

Two separate cache instances successfully reused the same Redis entry.

Example:

```text
peer.get(...) returned 'shared cache evidence response' with score 1.00
```

---

## Redis CLI Verification

```bash
docker compose exec redis redis-cli KEYS "rl:cache:*"

rl:cache:4918eb19ce89
```

---

# 8. Chaos Testing

Several chaos scenarios were implemented to validate reliability behavior.

---

## Scenario 1 — primary_timeout_100

### Goal

Force the primary provider to fail completely.

### Expected Behavior

- Circuit breaker opens
- Requests route to backup provider
- Availability remains high

### Observed Result

- Circuit opened correctly
- Backup provider handled traffic successfully
- System remained available

### Result

```text
PASS
```

---

## Scenario 2 — primary_flaky_50

### Goal

Simulate unstable provider behavior.

### Expected Behavior

- Circuit oscillates between OPEN and CLOSED
- Some requests fallback successfully

### Observed Result

- Circuit transitions worked correctly
- Backup routing prevented downtime

### Result

```text
PASS
```

---

## Scenario 3 — all_healthy

### Goal

Measure baseline system behavior.

### Expected Behavior

- Stable provider routing
- High cache hit rate
- Low latency

### Observed Result

- Metrics remained stable
- Latency stayed low
- Cache performed well

### Result

```text
PASS
```

---

## Scenario 4 — cache_stale_candidate

### Goal

Test false-hit protection.

### Expected Behavior

- Similar but different queries should not match incorrectly

### Observed Result

- Guardrails prevented invalid cache matches
- Privacy-sensitive queries bypassed cache

### Result

```text
PASS
```

---

# 9. Test Results

## Pytest Result

```bash
11 passed, 1 xpassed, 1 warning in 2.02s
```

All required tests passed successfully.

Redis shared cache tests also passed.

---

# 10. Failure Analysis

One remaining weakness is that circuit breaker state is currently process-local.

In distributed production deployments:

- Different gateway replicas may disagree about provider health
- Some instances may continue sending traffic to unhealthy providers

Potential improvements:

- Move circuit breaker state into Redis
- Add distributed synchronization
- Add provider-level rate limiting
- Add async concurrency handling

---

# 11. Future Improvements

Future improvements for this project include:

1. Concurrent load testing using ThreadPoolExecutor
2. Distributed Redis-backed circuit breaker state
3. Prometheus monitoring integration
4. Cost-aware provider routing
5. Async provider execution
6. Dynamic provider prioritization
7. Advanced semantic similarity models
8. Request-level rate limiting
9. Grafana monitoring dashboards
10. Production-scale stress testing

---

# 12. Conclusion

This project successfully implemented a production-style reliability layer for LLM gateways.

Key achievements:

- Circuit breaker implementation
- Automatic fallback routing
- Redis shared caching
- Cache safety protection
- Chaos testing
- Reliability metrics
- Cost optimization
- Recovery handling

The final system achieved:

- 100% availability
- Strong fallback reliability
- Low latency
- Significant provider cost reduction

The project demonstrates how reliability engineering techniques can improve production AI systems under unstable conditions.
