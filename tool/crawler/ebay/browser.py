"""抓取会话：httpx 快路径 + Playwright 浏览器兜底。

契约 §5：真实 Chrome 156 UA、同域 >=2 秒限速、指数退避重试（次数有上限）。
遇 403/429/验证码退避后抛 BlockedError，由 worker 标记单元失败——不绕过、不破解、不做隐身规避。
"""
import logging

import httpx
from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

import config
from base import BlockedError, CollectError
from ratelimit import RateLimiter, backoff_sleep

log = logging.getLogger("crawler.ebay.browser")

_CAPTCHA_MARKERS = (
    "Pardon Our Interruption", "captcha", "Are you a human", "robot check",
    "Access Denied", "Please verify you are a human", "distil networks",
)


def _has_captcha(html: str) -> bool:
    low = (html or "").lower()
    return any(m.lower() in low for m in _CAPTCHA_MARKERS)


def _valid_html(html: str) -> bool:
    return bool(html) and len(html) > 2000 and not _has_captcha(html)


class FetchSession:
    def __init__(self):
        self._rl = RateLimiter()
        self._http = httpx.Client(
            headers={
                "User-Agent": config.USER_AGENT,
                "Accept-Language": f"{config.LOCALE},en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=config.REQUEST_TIMEOUT,
            follow_redirects=True,
            trust_env=False,  # 忽略环境中可能损坏的代理变量
            proxy=config.PROXY or None,
        )
        self._pw = None
        self._browser = None
        self._page = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def _ensure_browser(self):
        if self._page is not None:
            return
        self._pw = sync_playwright().start()
        if config.CDP_URL:
            # 连接用户已启动的 Chrome（--remote-debugging-port=9222），复用真实会话；
            # 不覆盖其 UA/代理/视口，否则就失去复用真实浏览器指纹的意义
            self._browser = self._pw.chromium.connect_over_cdp(config.CDP_URL)
            ctx = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
            self._page = ctx.new_page()
        else:
            kwargs = {"headless": config.HEADLESS}
            if config.BROWSER_CHANNEL:
                kwargs["channel"] = config.BROWSER_CHANNEL
            if config.PROXY:
                kwargs["proxy"] = {"server": config.PROXY}
            else:
                kwargs["args"] = ["--no-proxy-server"]  # 直连，避开系统代理
            self._browser = self._pw.chromium.launch(**kwargs)
            ctx = self._browser.new_context(
                user_agent=config.USER_AGENT,
                locale=config.LOCALE,
                viewport={"width": 1366, "height": 900},
            )
            self._page = ctx.new_page()
        self._page.set_default_timeout(int(config.REQUEST_TIMEOUT * 1000))

    def fetch_html(self, url: str, wait_selector: str | None = None) -> str:
        # httpx 快路径（eBay 常对无 JS 客户端返回 403，失败则转浏览器）
        self._rl.wait(url)
        try:
            r = self._http.get(url)
            if r.status_code == 200 and _valid_html(r.text):
                return r.text
            last_err = f"httpx HTTP {r.status_code}"
        except Exception as e:  # 任何 httpx 失败（含 InvalidURL/重定向异常）都转浏览器兜底
            last_err = f"httpx {type(e).__name__}"

        # Playwright 兜底 + 指数退避重试
        try:
            self._ensure_browser()
        except PWError as e:
            raise CollectError(f"浏览器启动失败（先运行 playwright install chromium）: {e}") from e

        for attempt in range(config.MAX_RETRIES + 1):
            self._rl.wait(url)
            try:
                resp = self._page.goto(url, wait_until="domcontentloaded")
                status = resp.status if resp else 0
                if wait_selector:
                    try:
                        self._page.wait_for_selector(wait_selector, timeout=6000)
                    except PWTimeout:
                        pass
                html = self._page.content()
                if status == 200 and _valid_html(html):
                    return html
                last_err = f"HTTP {status}" + (" / 验证码" if _has_captcha(html) else "")
                if status in (403, 429) or _has_captcha(html):
                    if attempt < config.MAX_RETRIES:
                        backoff_sleep(attempt)
                        continue
                    raise BlockedError(last_err)
            except PWTimeout:
                last_err = "页面超时"
            except BlockedError:
                raise
            except PWError as e:
                last_err = f"浏览器错误: {e}"
            if attempt < config.MAX_RETRIES:
                backoff_sleep(attempt)
        raise BlockedError(f"多次重试仍受阻: {last_err}")

    def close(self):
        for obj, meth in ((self._page, "close"), (self._browser, "close")):
            try:
                if obj is not None:
                    getattr(obj, meth)()
            except Exception:
                pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        try:
            self._http.close()
        except Exception:
            pass
        self._page = self._browser = self._pw = None