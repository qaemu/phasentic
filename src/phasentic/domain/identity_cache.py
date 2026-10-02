"""Bounded memo for pure functions of immutable objects, keyed by identity.

Hashing a ``ReferencePhase`` hashes every reflection, which is slower than
the work being memoized. These caches key on ``id(obj)`` plus the other
arguments and keep a strong reference to ``obj`` with the result, so an id
cannot be recycled while its entry is alive. A hit also checks identity.
Use only for pure functions of frozen inputs.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable, Hashable


class IdentityLRU:
    def __init__(self, maxsize: int) -> None:
        self.maxsize = int(maxsize)
        self._entries: OrderedDict[tuple[int, Hashable], tuple[Any, Any]] = OrderedDict()

    def get_or_compute(self, obj: Any, extra: Hashable, compute: Callable[[], Any]) -> Any:
        key = (id(obj), extra)
        entry = self._entries.get(key)
        if entry is not None and entry[0] is obj:
            self._entries.move_to_end(key)
            return entry[1]
        value = compute()
        self._entries[key] = (obj, value)
        if len(self._entries) > self.maxsize:
            self._entries.popitem(last=False)
        return value

    def clear(self) -> None:
        self._entries.clear()
