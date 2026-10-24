from services.rate_limit import AttemptLimiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_blocks_after_the_limit_and_frees_after_the_window():
    clock = Clock()
    limiter = AttemptLimiter(3, 60, clock=clock)
    for _ in range(3):
        assert limiter.retry_after("a@x.example") == 0
        limiter.record("a@x.example")
    wait = limiter.retry_after("a@x.example")
    assert 1 <= wait <= 61
    clock.now += 30
    assert 1 <= limiter.retry_after("a@x.example") <= 31
    clock.now += 31
    assert limiter.retry_after("a@x.example") == 0


def test_keys_are_independent_and_reset_clears_one():
    limiter = AttemptLimiter(1, 60, clock=Clock())
    limiter.record("a")
    assert limiter.retry_after("a") > 0 and limiter.retry_after("b") == 0
    limiter.reset("a")
    assert limiter.retry_after("a") == 0


def test_memory_is_bounded():
    clock = Clock()
    limiter = AttemptLimiter(5, 60, max_keys=10, clock=clock)
    for i in range(100):
        limiter.record(f"k{i}")
    assert len(limiter._hits) <= 10
