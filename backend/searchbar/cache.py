"""Bounded, process-local caches; only successful loads are reusable."""

import asyncio
import copy
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass
class Entry:
    value: Any
    expires_at: float
    generation: int


class AsyncCache:
    def __init__(self, ttl, capacity=128, clock=time.monotonic):
        self.ttl = ttl
        self.capacity = capacity
        self.clock = clock
        self.entries = OrderedDict()
        self.pending = {}
        self.generation = 0

    async def get(self, key, loader, *, expires_at=None):
        now = self.clock()
        for expired in [k for k, entry in self.entries.items() if entry.expires_at <= now]:
            del self.entries[expired]
        if self.ttl and key in self.entries:
            self.entries.move_to_end(key)
            return copy.deepcopy(self.entries[key])
        if not self.ttl:
            return Entry(await loader(), now, 0)
        if key not in self.pending:
            deadline = min(now + self.ttl, expires_at) if expires_at is not None else now + self.ttl
            task = asyncio.create_task(self._load(key, loader, deadline))
            self.pending[key] = task
            # Retrieve exceptions even if all waiting requests were cancelled.
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        return copy.deepcopy(await asyncio.shield(self.pending[key]))

    async def _load(self, key, loader, deadline):
        try:
            value = await loader()
            self.generation += 1
            entry = Entry(value, deadline, self.generation)
            if deadline > self.clock():
                self.entries[key] = entry
                while len(self.entries) > self.capacity:
                    self.entries.popitem(last=False)
            return entry
        finally:
            self.pending.pop(key, None)

    async def close(self):
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.entries.clear()
