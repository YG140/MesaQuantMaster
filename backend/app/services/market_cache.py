from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Small in-process TTL cache for market data; replaceable by Redis later."""

    def __init__(self, clock: Callable[[], float] = monotonic):
        self._clock = clock
        self._items: dict[str, tuple[float, T]] = {}

    def get(self, key: str) -> T | None:
        item = self._items.get(key)
        if item is None:
            return None

        expires_at, value = item
        if expires_at <= self._clock():
            self._items.pop(key, None)
            return None

        return value

    def set(self, key: str, value: T, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        self._items[key] = (self._clock() + ttl_seconds, value)

    def clear(self) -> None:
        self._items.clear()
