"""按最终前缀重置现有商品编码（数据修复，默认只预览）。

用途：按“品牌段 + 品类段 + 4 位流水”重排全部 shop_goods.goods_no。
影响：更新 shop_goods.goods_no；同步原本与商品同码的 shop_goods_sku.sku_code；重建 shop_goods_no_sequence。
兼容性：每个最终前缀按 shop_goods.id 升序从 0001 开始；品牌不参与时品牌段为 TH。
预览：python contracts/ddl/029_reset_goods_no.py
执行：python contracts/ddl/029_reset_goods_no.py --apply
回滚：使用执行时输出的 JSON 备份；人工审核后按其中 goods/skus/sequences 恢复。
注意：执行使用单事务和临时编码规避唯一索引换码冲突；运行期间不要同时编辑商品或生成编码。
"""
import argparse
import json
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "admin"))

from sqlalchemy import text

from app.db import engine


def load_plan(conn):
    rows = conn.execute(text("""
        SELECT g.id, g.goods_no, g.category_id, g.brand_id,
               TRIM(c.code) AS category_code, TRIM(b.code) AS brand_code,
               b.include_in_goods_no
          FROM shop_goods g
          JOIN shop_category c ON c.id = g.category_id
          JOIN brand b ON b.id = g.brand_id
         ORDER BY g.id
         FOR UPDATE
    """)).mappings().all()
    counters = defaultdict(int)
    plan = []
    for row in rows:
        category_code = row["category_code"] or ""
        brand_code = (row["brand_code"] or "") if row["include_in_goods_no"] else "TH"
        if not category_code:
            raise RuntimeError(f"商品 {row['id']} 的分类未设置品类编码")
        if not brand_code:
            raise RuntimeError(f"商品 {row['id']} 的品牌参与编码但未设置品牌编码")
        prefix = brand_code + category_code
        if len(prefix) > 60:
            raise RuntimeError(f"商品 {row['id']} 的最终前缀超过 60 个字符")
        counters[prefix] += 1
        if counters[prefix] > 9999:
            raise RuntimeError(f"前缀 {prefix} 超过四位流水容量")
        plan.append({"id": row["id"], "old": row["goods_no"],
                     "new": f"{prefix}{counters[prefix]:04d}", "prefix": prefix})
    new_codes = [row["new"] for row in plan]
    if len(new_codes) != len(set(new_codes)):
        raise RuntimeError("生成结果存在重复商品编码")
    return plan, dict(counters)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    backup_path = None
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            plan, counters = load_plan(conn)
            sku_rows = conn.execute(text("""
                SELECT s.id, s.goods_id, s.sku_code
                  FROM shop_goods_sku s
                  JOIN shop_goods g ON g.id = s.goods_id
                 ORDER BY s.id
                 FOR UPDATE
            """)).mappings().all()
            old_by_goods = {row["id"]: row["old"] for row in plan}
            new_by_goods = {row["id"]: row["new"] for row in plan}
            sku_plan = [{"id": row["id"], "goods_id": row["goods_id"], "old": row["sku_code"],
                         "new": new_by_goods[row["goods_id"]]}
                        for row in sku_rows if row["sku_code"] == old_by_goods[row["goods_id"]]]
            changing_sku_ids = {row["id"] for row in sku_plan}
            fixed_sku_codes = {row["sku_code"] for row in sku_rows if row["id"] not in changing_sku_ids}
            collisions = sorted({row["new"] for row in sku_plan} & fixed_sku_codes)
            if collisions:
                raise RuntimeError(f"新商品编码与不随商品改号的 SKU 编码冲突：{collisions[:5]}")
            sequences = [dict(row) for row in conn.execute(text(
                "SELECT prefix, current_seq FROM shop_goods_no_sequence ORDER BY prefix FOR UPDATE"
            )).mappings().all()]
            print(json.dumps({"goods": len(plan), "skus": len(sku_plan), "prefixes": counters,
                              "sample": plan[:10]}, ensure_ascii=False, indent=2))
            if not args.apply:
                tx.rollback()
                print("仅预览，未修改数据。加 --apply 执行。")
                return
            backup_dir = Path(tempfile.gettempdir()) / "mzshop-backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"029_goods_no_{datetime.now():%Y%m%d_%H%M%S}.json"
            backup_path.write_text(json.dumps({"goods": plan, "skus": sku_plan, "sequences": sequences},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
            token = uuid4().hex[:8]
            for row in plan:
                conn.execute(text("UPDATE shop_goods SET goods_no=:code WHERE id=:id"),
                             {"code": f"__MZG_{token}_{row['id']}__", "id": row["id"]})
            for row in sku_plan:
                conn.execute(text("UPDATE shop_goods_sku SET sku_code=:code WHERE id=:id"),
                             {"code": f"__MZS_{token}_{row['id']}__", "id": row["id"]})
            for row in plan:
                conn.execute(text("UPDATE shop_goods SET goods_no=:code WHERE id=:id"),
                             {"code": row["new"], "id": row["id"]})
            for row in sku_plan:
                conn.execute(text("UPDATE shop_goods_sku SET sku_code=:code WHERE id=:id"),
                             {"code": row["new"], "id": row["id"]})
            conn.execute(text("DELETE FROM shop_goods_no_sequence"))
            for prefix, current in counters.items():
                conn.execute(text("INSERT INTO shop_goods_no_sequence(prefix,current_seq) VALUES(:prefix,:current)"),
                             {"prefix": prefix, "current": current})
            tx.commit()
        except Exception:
            tx.rollback()
            raise
    print(f"执行完成；备份：{backup_path}")


if __name__ == "__main__":
    main()
