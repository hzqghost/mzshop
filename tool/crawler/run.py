"""采集器入口（独立进程）。

用法（在 tool/crawler 目录下）：
    .venv/Scripts/python run.py            # 持续运行：处理定时 + 轮询领取 pending run
    .venv/Scripts/python run.py --once     # 只处理一次定时 + 领取并执行一个 pending run 后退出
    .venv/Scripts/python run.py --run-id 5 # 只领取并执行指定 run（调试）
    .venv/Scripts/python run.py --no-schedule  # 本次不处理定时任务
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import worker  # noqa: E402


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description="mzShop 采集器（独立进程，只通过数据库与 admin 通信）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true", help="处理一次定时 + 领取并执行一个 pending run 后退出")
    g.add_argument("--loop", action="store_true", help="持续运行（默认）")
    ap.add_argument("--run-id", type=int, help="只领取并执行指定 run（调试用）")
    ap.add_argument("--no-schedule", action="store_true", help="本次不处理定时任务")
    args = ap.parse_args()

    if args.run_id is not None:
        if worker.claim_run(args.run_id):
            worker.execute_run(args.run_id)
        else:
            logging.getLogger("crawler").warning("run %s 不是 pending，未领取", args.run_id)
        return 0
    if args.once:
        worker.run_once(no_schedule=args.no_schedule)
        return 0
    worker.run_forever(no_schedule=args.no_schedule)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n采集器已停止")
        raise SystemExit(0)