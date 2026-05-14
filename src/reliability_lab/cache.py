from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any


PRIVACY_PATTERNS = re.compile(
    r"\b(balance|password|credit.card|ssn|social.security|user.\d+|account.\d+)\b",
    re.IGNORECASE,
)


def _is_uncacheable(query: str) -> bool:
    return bool(PRIVACY_PATTERNS.search(query))


def _looks_like_false_hit(query: str, cached_key: str) -> bool:
    nums_q = set(re.findall(r"\b\d{4}\b", query))
    nums_c = set(re.findall(r"\b\d{4}\b", cached_key))
    return bool(nums_q and nums_c and nums_q != nums_c)


@dataclass(slots=True)
class CacheEntry:
    key: str
    value: str
    created_at: float
    metadata: dict[str, str]


class ResponseCache:
    def __init__(self, ttl_seconds: int, similarity_threshold: float):
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self._entries: list[CacheEntry] = []

    def get(self, query: str) -> tuple[str | None, float]:
        if _is_uncacheable(query):
            return None, 0.0

        best_value: str | None = None
        best_score = 0.0

        now = time.time()

        self._entries = [
            e for e in self._entries
            if now - e.created_at <= self.ttl_seconds
        ]

        for entry in self._entries:
            score = self.similarity(query, entry.key)

            if score > best_score:
                best_score = score
                best_value = entry.value
                best_key = entry.key

        if best_score >= self.similarity_threshold:
            if _looks_like_false_hit(query, best_key):
                return None, best_score

            return best_value, best_score

        return None, best_score

    def set(
        self,
        query: str,
        value: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        if _is_uncacheable(query):
            return

        self._entries.append(
            CacheEntry(
                query,
                value,
                time.time(),
                metadata or {},
            )
        )

    @staticmethod
    def similarity(a: str, b: str) -> float:
        a = a.lower().strip()
        b = b.lower().strip()

        if a == b:
            return 1.0

        left = set(re.findall(r"\w+", a))
        right = set(re.findall(r"\w+", b))

        if not left or not right:
            return 0.0

        overlap = len(left & right)
        union = len(left | right)

        token_score = overlap / union

        years_a = set(re.findall(r"\b\d{4}\b", a))
        years_b = set(re.findall(r"\b\d{4}\b", b))

        if years_a and years_b and years_a != years_b:
            token_score *= 0.5

        return token_score


class SharedRedisCache:
    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int,
        similarity_threshold: float,
        prefix: str = "rl:cache:",
    ):
        import redis as redis_lib

        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self.prefix = prefix
        self.false_hit_log: list[dict[str, object]] = []

        self._redis: Any = redis_lib.Redis.from_url(
            redis_url,
            decode_responses=True,
        )

    def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except Exception:
            return False

    def get(self, query: str) -> tuple[str | None, float]:
        if _is_uncacheable(query):
            return None, 0.0

        try:
            exact_key = f"{self.prefix}{self._query_hash(query)}"

            exact_response = self._redis.hget(exact_key, "response")

            if exact_response:
                return exact_response, 1.0

            best_score = 0.0
            best_value: str | None = None
            best_query: str | None = None

            for key in self._redis.scan_iter(f"{self.prefix}*"):
                cached_query = self._redis.hget(key, "query")
                cached_response = self._redis.hget(key, "response")

                if not cached_query or not cached_response:
                    continue

                score = ResponseCache.similarity(query, cached_query)

                if score > best_score:
                    best_score = score
                    best_value = cached_response
                    best_query = cached_query

            if best_score >= self.similarity_threshold:
                if best_query and _looks_like_false_hit(query, best_query):
                    self.false_hit_log.append(
                        {
                            "query": query,
                            "cached_query": best_query,
                            "score": best_score,
                        }
                    )
                    return None, best_score

                return best_value, best_score

            return None, best_score

        except Exception:
            return None, 0.0

    def set(
        self,
        query: str,
        value: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        if _is_uncacheable(query):
            return

        try:
            key = f"{self.prefix}{self._query_hash(query)}"

            self._redis.hset(
                key,
                mapping={
                    "query": query,
                    "response": value,
                },
            )

            self._redis.expire(key, self.ttl_seconds)

        except Exception:
            return

    def flush(self) -> None:
        for key in self._redis.scan_iter(f"{self.prefix}*"):
            self._redis.delete(key)

    def close(self) -> None:
        if self._redis is not None:
            self._redis.close()

    @staticmethod
    def _query_hash(query: str) -> str:
        return hashlib.md5(
            query.lower().strip().encode()
        ).hexdigest()[:12]