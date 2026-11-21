import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_URL = "mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4".format(
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"].replace("@", "%40"),
    host=os.environ["DB_HOST"],
    port=os.environ.get("DB_PORT", "3306"),
    name=os.environ["DB_NAME"],
)

SECRET_KEY = os.environ["SECRET_KEY"]

SHOPIFY_CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", "").strip()
SHOPIFY_CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()
SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2026-10").strip()
SHOPIFY_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("SHOPIFY_REQUEST_TIMEOUT_SECONDS", "30"))
SHOPIFY_MAX_RETRIES = int(os.environ.get("SHOPIFY_MAX_RETRIES", "3"))
SHOPIFY_WEBHOOK_BASE_URL = os.environ.get("SHOPIFY_WEBHOOK_BASE_URL", "").strip().rstrip("/")
SHOPIFY_ASSET_BASE_URL = os.environ.get(
    "SHOPIFY_ASSET_BASE_URL", SHOPIFY_WEBHOOK_BASE_URL
).strip().rstrip("/")

# 内置超级管理员：写在代码里，不入库，不出现在用户列表中
SUPER_ADMIN = {
    "id": 0,
    "username": "test.admin",
    "password": "TEST@2026@2026",
    "real_name": "超级管理员",
}
