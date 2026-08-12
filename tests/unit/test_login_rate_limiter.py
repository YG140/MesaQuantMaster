from app.services.login_rate_limiter import LoginRateLimiter


def test_limiter_recovers_after_window_and_cleans_expired_entries():
    now = [100.0]
    limiter = LoginRateLimiter(2, 10, 10, clock=lambda: now[0])
    key = limiter.key("127.0.0.1", " User@Example.com ")
    limiter.record_failure(key)
    limiter.record_failure(key)
    assert limiter.check(key).allowed is False
    now[0] = 111.0
    assert limiter.check(key).allowed is True
    assert limiter._failures == {}


def test_limiter_isolates_keys_and_bounds_storage():
    limiter = LoginRateLimiter(1, 60, 2, clock=lambda: 100.0)
    keys = [limiter.key("10.0.0.1", f"user{index}@example.com") for index in range(3)]
    for key in keys:
        limiter.record_failure(key)
    assert len(limiter._failures) == 2
    assert limiter.check(keys[-1]).allowed is False
