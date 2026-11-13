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

# 内置超级管理员：写在代码里，不入库，不出现在用户列表中
SUPER_ADMIN = {
    "id": 0,
    "username": "test.admin",
    "password": "TEST@2026@2026",
    "real_name": "超级管理员",
}
