"""商品分类树与属性继承。

属性的「适用分类」可多选且是继承的：选了「香水」，它下面所有级别的子分类（女士香水、中性香水……）都适用该属性；
适用分类为空表示所有分类通用。同名属性在多级都定义时，离商品分类最近的一级生效。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ShopAttribute, ShopCategory


def ancestor_ids(db: Session, category_id: int) -> list[int]:
    """[自己, 父级, 祖父级, ...]；分类 0 / 不存在返回空列表。带环保护。"""
    parents = dict(db.execute(select(ShopCategory.id, ShopCategory.parent_id)).all())
    out, seen = [], set()
    while category_id and category_id in parents and category_id not in seen:
        out.append(category_id)
        seen.add(category_id)
        category_id = parents[category_id]
    return out


def applicable_attributes(db: Session, category_id: int) -> list[ShopAttribute]:
    """某分类下的商品适用的启用属性：通用 + 本级 + 所有上级；同名取最近一级；按 sort_order、id 排。"""
    chain = ancestor_ids(db, category_id)
    depth = {cid: i for i, cid in enumerate(chain)}
    depth[0] = len(chain)  # 通用属性离得最远
    rows = db.scalars(select(ShopAttribute).where(ShopAttribute.status == 1))
    best: dict[str, tuple[int, ShopAttribute]] = {}
    for a in rows:
        hits = [depth[c] for c in (a.category_ids or [0]) if c in depth]  # 空数组 = 通用
        if not hits:
            continue
        d = min(hits)
        cur = best.get(a.name)
        if cur is None or d < cur[0]:
            best[a.name] = (d, a)
    return sorted((a for _, a in best.values()), key=lambda a: (a.sort_order, a.id))


def is_leaf(db: Session, category_id: int) -> bool:
    return db.scalar(select(ShopCategory.id).where(ShopCategory.parent_id == category_id).limit(1)) is None
