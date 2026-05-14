# Day 10 Reliability Final Report

## Student Information

| Field | Value |
|---|---|
| Student Name | Nguyen Tien Dat |
| Student ID | 2A202600218 |
| Repository | 2A202600218_NguyenTienDatphase2-track3-day10-reliability-agent-main |

---

# 1. Architecture Summary

The reliability gateway first checks the cache before routing requests through provider-specific circuit breakers. If the primary provider fails or its circuit is open, traffic automatically falls back to the backup provider. If all providers fail, the system returns a static fallback response.

```text
User
  |
  v
Gateway
  |
  +--> Cache Check
  |       |
  |       +--> Cache Hit
  |
  +--> Circuit Breaker (Primary)
  |       |
  |       +--> Primary Provider
  |
  +--> Circuit Breaker (Backup)
  |       |
  |       +--> Backup Provider
  |
  +--> Static Fallback
```

---

# 2. Configuration

| Setting | Value | Reason |
|---|---:|---|
| failure_threshold | 3 | Detect failures quickly without opening the circuit too aggressively |
| reset_timeout_seconds | 2.0 | Allows fast recovery checks during chaos testing |
| success_threshold | 1 | One successful HALF_OPEN probe closes the circuit |
| cache TTL | 300 | Balances freshness and cache hit efficiency |
| similarity_threshold | 0.92 | Prevents false hits between date-sensitive queries |
| cache backend | redis | Enables shared cache across multiple instances |
| load_test requests | 100 | Provides enough traffic for reproducible metrics |

---

# 3. SLO Definitions

| SLI | SLO Target | Actual Value | Status |
|---|---|---:|---|
| Availability | >= 99% | 1.0 | PASS |
| Latency P95 | < 2500 ms | 320.51 | PASS |
| Fallback Success Rate | >= 95% | 1.0 | PASS |
| Cache Hit Rate | >= 10% | 0.7775 | PASS |
| Recovery Time | < 5000 ms | 2292.38 | PASS |

---

# 4. Metrics Summary

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

# 5. Cache Comparison

| Metric | Without Cache | With Cache | Delta |
|---|---:|---:|---|
| latency_p50_ms | 237.6 | 0.35 | -99.9% |
| latency_p95_ms | 510.01 | 320.51 | -37.1% |
| estimated_cost | 0.185782 | 0.041494 | -77.7% |
| cache_hit_rate | 0.0 | 0.7775 | +0.7775 |

The cache significantly reduced provider calls and improved response latency.  
False-hit protection successfully prevented incorrect matches between queries with different years.

---

# 6. Redis Shared Cache

The project uses `SharedRedisCache` to support multi-instance deployments.  
Unlike in-memory cache, Redis allows multiple gateway instances to share the same cache state.

## Shared Cache Evidence

```text
peer.get(...) returned 'shared cache evidence response' with score 1.00
```

## Redis CLI Output

```bash
docker compose exec redis redis-cli KEYS "rl:cache:*"

rl:cache:4918eb19ce89
```

Benefits of shared Redis cache:

- Shared cache state across instances
- Reduced repeated provider requests
- Better horizontal scalability
- Consistent cache hit behavior

---

# 7. Chaos Scenarios

| Scenario | Expected Behavior | Observed Behavior | Result |
|---|---|---|---|
| primary_timeout_100 | Primary fails completely and backup serves traffic | Circuit opened and fallback routing worked correctly | PASS |
| primary_flaky_50 | Circuit oscillates between OPEN and CLOSED | Backup provider handled unstable traffic successfully | PASS |
| all_healthy | Low latency and stable provider routing | Requests completed successfully with low errors | PASS |
| cache_stale_candidate | Prevent false cache hits on similar queries | Guardrails blocked incorrect cache matches | PASS |

---

# 8. Failure Analysis

One remaining weakness is that the circuit breaker state is currently process-local.  
In a distributed deployment, multiple gateway replicas may not share the same provider health state.

Potential production improvements:

- Store circuit breaker state in Redis
- Add provider-level rate limiting
- Improve concurrency handling
- Add async request execution

---

# 9. Next Steps

1. Add concurrent load testing using ThreadPoolExecutor
2. Store circuit breaker state in Redis
3. Add Prometheus monitoring metrics
4. Implement distributed rate limiting
5. Add cost-aware provider routing

---

# 10. Conclusion

The reliability gateway successfully implemented:

- Circuit breaker protection
- Automatic fallback routing
- Redis shared caching
- Cache safety guardrails
- Chaos testing scenarios
- Latency and cost metrics

The system maintained 100% availability during testing while significantly reducing latency and estimated provider cost through caching.