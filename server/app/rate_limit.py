import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class Limit:
    max_events: int
    window_seconds: float


class PerUserRateLimiter:
    """Small process-local sliding-window limiter for Socket.IO events."""

    def __init__(self, clock=time.monotonic) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._clock = clock

    def allow(self, username: str, event_name: str, limit: Limit) -> tuple[bool, int]:
        now = self._clock()
        key = (username, event_name)
        with self._lock:
            timestamps = self._events[key]
            cutoff = now - limit.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit.max_events:
                retry_after = max(1, int(timestamps[0] + limit.window_seconds - now))
                return False, retry_after
            timestamps.append(now)
            return True, 0