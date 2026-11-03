"""线程安全的 LRU 缓存（按 FEN + 深度缓存局面分析，避免重复搜索）。"""

import threading
from collections import OrderedDict
from typing import Any, Optional


class LRUCache:
    def __init__(self, maxsize: int = 256):
        self._maxsize = max(1, int(maxsize))
        self._data: "OrderedDict[Any, Any]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: Any) -> Optional[Any]:
        with self._lock:
            if key not in self._data:
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return self._data[key]

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._data),
                "maxsize": self._maxsize,
                "hits": self.hits,
                "misses": self.misses,
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
