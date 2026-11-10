"""Injectable time sources so limits and quotas can be tested deterministically."""

import time
from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]
Monotonic = Callable[[], float]


def utc_now() -> datetime:
    return datetime.now(UTC)


monotonic: Monotonic = time.monotonic
