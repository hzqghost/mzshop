"""采集器配置：从本模块 .env 读取数据库连接与运行参数。独立进程，不复用 admin 代码。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DB_URL = "mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4".format(
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"].replace("@", "%40"),
    host=os.environ["DB_HOST"],
    port=os.environ.get("DB_PORT", "3306"),
    name=os.environ["DB_NAME"],
)


def _float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, "") or default)
    except ValueError:
        return default


def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, "") or default)
    except ValueError:
        return default


def _bool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# 契约 §5：真实可识别 User-Agent，Chrome 156.0.8078.80
USER_AGENT = os.environ.get("CRAWLER_USER_AGENT") or (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.8078.80 Safari/537.36"
)
MIN_REQUEST_INTERVAL = max(2.0, _float("CRAWLER_MIN_INTERVAL", 2.0))  # 契约下限 >=2 秒
MAX_RETRIES = _int("CRAWLER_MAX_RETRIES", 3)
BACKOFF_BASE = _float("CRAWLER_BACKOFF_BASE", 2.0)
BACKOFF_MAX = _float("CRAWLER_BACKOFF_MAX", 60.0)
REQUEST_TIMEOUT = _float("CRAWLER_TIMEOUT", 30.0)
HEADLESS = _bool("CRAWLER_HEADLESS", True)
# 使用已安装的浏览器通道（chrome/msedge），避免下载 chromium；留空则用 playwright install 的 chromium
BROWSER_CHANNEL = os.environ.get("CRAWLER_BROWSER_CHANNEL", "chrome")
# 可选：连接用户已正常启动的 Chrome（--remote-debugging-port=9222），复用真实浏览器会话；留空则自行 launch
CDP_URL = (os.environ.get("CRAWLER_CDP_URL") or "").strip()
POLL_INTERVAL = _float("CRAWLER_POLL_INTERVAL", 5.0)
LOCALE = "en-US"

# 与 admin MAX_PAGES_LIMIT 一致的防御性硬上限：即使库里被改大也只取 10 页
MAX_PAGES = 10
EBAY_BASE = (os.environ.get("CRAWLER_EBAY_BASE") or "https://www.ebay.com").rstrip("/")
# 可选代理（如 http://127.0.0.1:8118）；留空直连。忽略系统环境中可能损坏的代理变量。
PROXY = (os.environ.get("CRAWLER_PROXY") or "").strip()