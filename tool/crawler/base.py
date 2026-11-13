"""平台采集器统一接口与异常。每个平台一个采集器，放 tool/crawler/<platform>/。"""
from abc import ABC, abstractmethod


class CollectError(Exception):
    """采集过程中的可预期错误（解析失败、缺少字段等），单元据此标记失败。"""


class BlockedError(CollectError):
    """遇到 403/429/验证码等访问受阻：退避后标记单元失败，不绕过、不破解。"""


class BaseCollector(ABC):
    """统一接口（契约 §3）。输出统一商品字典：键名即 product 列名 + attributes/search_attrs。

    采集器负责限速与退避；worker 负责领取 run、展开单元、落库、回写进度。
    用上下文管理生命周期（如启动/关闭浏览器）。
    """

    platform: str = ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        pass

    @abstractmethod
    def list_attr_values(self, task, category: str) -> list[str]:
        """读取搜索页左侧 task.attr_name 的可选属性值；attr_name 为空时返回 ['']（每分类一个单元）。"""

    @abstractmethod
    def search(self, task, category: str, attr_value: str, page: int) -> list[dict]:
        """返回该页商品 stub 列表（至少含 item_id、product_url）；无结果返回 []。"""

    @abstractmethod
    def parse_item(self, stub: dict, task, category: str, attr_value: str) -> dict:
        """抓详情并解析为统一 product 字典（含 platform、item_id、category_name、search_attrs、attributes）。"""

    @abstractmethod
    def fetch_reviews(self, item: dict) -> list[dict]:
        """返回评价字典列表（review_type/review_key/reviewer_name/rating/title/content/reviewed_at/...）。"""