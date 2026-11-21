"""Shopify GraphQL Admin API 客户端。只在内存缓存短期令牌，不落库、不记录密钥。"""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import (SHOPIFY_API_VERSION, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET,
                     SHOPIFY_REQUEST_TIMEOUT_SECONDS)

_TOKENS: dict[str, tuple[str, float]] = {}


class ShopifyError(RuntimeError):
    pass


def normalize_domain(value: str) -> str:
    domain = str(value or "").strip().lower()
    domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
    if "/" in domain or not domain.endswith(".myshopify.com") or domain.count(".") < 2:
        raise ShopifyError("店铺域名格式应为 xxx.myshopify.com")
    return domain


def _request(url: str, body: bytes, headers: dict[str, str]) -> tuple[dict, dict]:
    try:
        with urlopen(Request(url, data=body, headers=headers, method="POST"),
                     timeout=SHOPIFY_REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8")), dict(response.headers)
    except HTTPError as e:
        raw = e.read().decode("utf-8", "replace")[:1000]
        raise ShopifyError(f"Shopify HTTP {e.code}：{raw}") from None
    except (URLError, TimeoutError, OSError) as e:
        raise ShopifyError(f"无法连接 Shopify：{e}") from None


def access_token(shop_domain: str) -> str:
    domain = normalize_domain(shop_domain)
    if not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
        raise ShopifyError("SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET 未配置")
    cached = _TOKENS.get(domain)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    payload, _ = _request(
        f"https://{domain}/admin/oauth/access_token",
        urlencode({"grant_type": "client_credentials", "client_id": SHOPIFY_CLIENT_ID,
                   "client_secret": SHOPIFY_CLIENT_SECRET}).encode(),
        {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    token = str(payload.get("access_token") or "")
    if not token:
        raise ShopifyError("Shopify 未返回访问令牌，请检查应用安装和凭据")
    expires = max(300, int(payload.get("expires_in") or 86400))
    _TOKENS[domain] = (token, time.time() + expires)
    return token


def graphql(shop_domain: str, query: str, variables: dict | None = None) -> tuple[dict, str]:
    domain = normalize_domain(shop_domain)
    payload, headers = _request(
        f"https://{domain}/admin/api/{SHOPIFY_API_VERSION}/graphql.json",
        json.dumps({"query": query, "variables": variables or {}}, ensure_ascii=False).encode("utf-8"),
        {"Content-Type": "application/json", "Accept": "application/json",
         "X-Shopify-Access-Token": access_token(domain)},
    )
    if payload.get("errors"):
        message = "；".join(str(e.get("message") or e) for e in payload["errors"][:5])
        raise ShopifyError(f"Shopify GraphQL：{message}")
    return payload.get("data") or {}, str(headers.get("X-Request-Id") or "")


CONNECTION_QUERY = """
query ConnectionInfo {
  shop { id name currencyCode myshopifyDomain }
  locations(first: 50) { nodes { id name isActive } }
  publications(first: 50) { nodes { id name } }
  currentAppInstallation { accessScopes { handle } }
}
"""
