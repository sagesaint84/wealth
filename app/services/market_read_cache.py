"""Bounded process-memory cache for public market reads, never financial files."""
import asyncio
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from time import monotonic
from weakref import WeakValueDictionary


class MarketReadCache:
    def __init__(self, ttl, capacity=256):
        self.ttl, self.capacity = ttl, capacity
        self.values = OrderedDict()
        self.locks = WeakValueDictionary()

    async def get(self, key, loader):
        lock = self.locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self.locks[key] = lock
        async with lock:
            cached = self.values.get(key)
            if cached and monotonic() - cached[0] < self.ttl:
                return {**deepcopy(cached[1]), "cache_hit": True}
            attempted = datetime.now(timezone.utc).isoformat()
            try:
                value = await loader()
                result = {"value": value, "retrieved_at": attempted,
                          "last_attempt_at": attempted, "update_delayed": False,
                          "error": None, "cache_hit": False}
                self.values[key] = (monotonic(), deepcopy(result))
                self.values.move_to_end(key)
                while len(self.values) > self.capacity:
                    self.values.popitem(last=False)
                return result
            except Exception:
                # Short failure backoff prevents a broken source from being hit
                # by every render. Never advance the last successful fetch time.
                result = {**deepcopy(cached[1])} if cached else {
                    "value": None, "retrieved_at": None}
                result.update(last_attempt_at=attempted, update_delayed=True,
                              error="source_unavailable", cache_hit=False)
                self.values[key] = (monotonic() - self.ttl + min(60, self.ttl), deepcopy(result))
                self.values.move_to_end(key)
                while len(self.values) > self.capacity:
                    self.values.popitem(last=False)
                return result
