from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.rate_limit import Limit, PerUserRateLimiter  # noqa: E402


def test_rate_limiter_uses_fake_clock() -> None:
    now = [100.0]
    limiter = PerUserRateLimiter(clock=lambda: now[0])
    limit = Limit(max_events=2, window_seconds=10)

    assert limiter.allow("alice", "message:send", limit) == (True, 0)
    assert limiter.allow("alice", "message:send", limit) == (True, 0)
    assert limiter.allow("alice", "message:send", limit)[0] is False

    now[0] = 110.1
    assert limiter.allow("alice", "message:send", limit) == (True, 0)
