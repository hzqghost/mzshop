"""限速与退避（契约 §5）：同一域名请求间隔下限 >=2 秒，单进程串行；指数退避，次数有上限。"""
import time
from urllib.parse import urlparse

import config


class RateLimiter:
    def __init__(self, min_interval: float | None = None):
        self.min_interval = config.MIN_REQUEST_INTERVAL if min_interval is None else min_interval
        self._last: dict[str, float] = {}

    def wait(self, url_or_domain: str) -> None:
        domain = urlparse(url_or_domain).netloc or url_or_domain
        last = self._last.get(domain)
        if last is not None:
            delta = time.monotonic() - last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
        self._last[domain] = time.monotonic()


def backoff_sleep(attempt: int) -> None:
    delay = min(config.BACKOFF_MAX, config.BACKOFF_BASE * (2 ** max(0, attempt)))
    time.sleep(delay)