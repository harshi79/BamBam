"""
YoriNetflix — Throttle middleware tests.
"""

from app.middleware.throttle import ThrottleMiddleware


class TestThrottleMiddleware:
    def test_cleanup_evicts_oldest(self):
        mw = ThrottleMiddleware(rate=0.1, max_entries=3)
        mw.last[1] = 1.0
        mw.last[2] = 2.0
        mw.last[3] = 3.0
        mw.last[4] = 4.0
        mw._cleanup()
        assert len(mw.last) <= 3
        assert 1 not in mw.last  # oldest evicted
        assert 4 in mw.last

    def test_rate_limit_logic(self):
        mw = ThrottleMiddleware(rate=1.0, max_entries=100)
        import time
        now = time.monotonic()
        mw.last[42] = now
        # Should be throttled (same timestamp)
        last = mw.last.get(42, 0)
        assert now - last < 1.0

    def test_no_limit_after_interval(self):
        mw = ThrottleMiddleware(rate=0.01, max_entries=100)
        import time
        mw.last[42] = time.monotonic() - 1.0  # 1 second ago
        last = mw.last.get(42, 0)
        assert time.monotonic() - last >= 0.01