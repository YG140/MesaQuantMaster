from collections import deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable


@dataclass(frozen=True)
class LoginRateLimitDecision:
    allowed: bool
    retry_after: int | None = None


class LoginRateLimiter:
    def __init__(
        self,
        attempts: int,
        window_seconds: int,
        max_entries: int,
        clock: Callable[[], float] = monotonic,
    ):
        self.attempts = max(1, attempts)
        self.window_seconds = max(1, window_seconds)
        self.max_entries = max(1, max_entries)
        self.clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = Lock()

    @staticmethod
    def key(client_host: str | None, identifier: str) -> str:
        return f"{client_host or 'unknown'}:{identifier.strip().lower()}"

    def check(self, key: str) -> LoginRateLimitDecision:
        now = self.clock()
        with self._lock:
            self._cleanup(now)
            failures = self._failures.get(key)
            if not failures or len(failures) < self.attempts:
                return LoginRateLimitDecision(allowed=True)
            retry_after = max(1, int(self.window_seconds - (now - failures[0]) + 0.999))
            return LoginRateLimitDecision(False, retry_after)

    def record_failure(self, key: str) -> None:
        now = self.clock()
        with self._lock:
            self._cleanup(now)
            if key not in self._failures and len(self._failures) >= self.max_entries:
                oldest = min(self._failures, key=lambda item: self._failures[item][-1])
                del self._failures[oldest]
            self._failures.setdefault(key, deque()).append(now)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()

    def clear_key(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def _cleanup(self, now: float) -> None:
        cutoff = now - self.window_seconds
        expired = []
        for key, failures in self._failures.items():
            while failures and failures[0] <= cutoff:
                failures.popleft()
            if not failures:
                expired.append(key)
        for key in expired:
            del self._failures[key]
