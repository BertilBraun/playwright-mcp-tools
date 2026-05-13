import time

import requests


class _RateLimitedSession(requests.Session):
    def __init__(self, min_interval: float) -> None:
        super().__init__()
        self._min_interval = min_interval
        self._last_request_time: float = 0.0
        self.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; personal-scraper/1.0)'})

    def request(self, method: str, url: str, **kwargs):  # type: ignore[override]
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        response = super().request(method, url, **kwargs)
        self._last_request_time = time.monotonic()
        return response


def make_session(min_interval: float = 0.8) -> _RateLimitedSession:
    return _RateLimitedSession(min_interval)
