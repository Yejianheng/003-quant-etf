# [2026-07-15] 重写：时间门禁 + 拉取不入库 — Web 核验通过后才写入 parquet
# [2026-07-15] 修改：双源独立拉取 + 交叉验证 — 腾讯/东方财富 close 偏差 >0.3% 阻断入库
# [2026-06-23] 修改：数据源优先级调整为腾讯 > 东方财富 > 新浪
# [2026-06-18] 修复：单日增量 fence-post bug（>= → >），start==end 时不再错误跳过
# [2026-06-18] 修改：更新完成后调用 trim_isolated_dates 剔除跨 ETF 不一致日
# [2026-05-30] 新增：每日数据更新脚本 — 增量拉取 AKShare 数据追加到 parquet
"""
每日数据更新脚本：遍历防御层 ETF parquet → 时间门禁 → 拉取（不入库）→ Web 核验 → 入库。

用法：
  python scripts/update_data.py    # 拉取 + 输出核验清单
  # → Web 核验完成后重新运行（此时已是最新，跳过拉取）
"""
import os
import sys
import time
from datetime import date, datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data_pipeline import fetch_etf_daily, fetch_etf_daily_tx, load_from_parquet, save_to_parquet
from src.etf_universe import ETF_UNIVERSE


def _name_from_code(code: str) -> str:
    for name, c in ETF_UNIVERSE.items():
        if c == code:
            return name
    return code


def update_single_etf(code: str, data_dir: str = "data") -> dict:
    """
    单只 ETF 拉取（不入库），返回核验状态。

    返回 dict:
      拉到数据待核验: {"ok": True, "needs_verify": True, "name": str, "code": str,
                        "source": "tx"|"em", "new_data": DataFrame,
                        "latest_close": float, "latest_date": str}
      已是最新:       {"ok": True, "needs_verify": False, "name": str, "code": str,
                        "reason": "up_to_date"}
      两源均空阻断:   {"ok": False, "name": str, "code": str, "reason": "no_data"}
    """
    name = _name_from_code(code)
    path = os.path.join(data_dir, f"{code}.parquet")
    if not os.path.exists(path):
        return {"ok": False, "name": name, "code": code, "reason": "no_data"}

    existing = load_from_parquet(path)
    last_date = existing.index.max().date()

    # 时间门禁：15:00 前不拉当日
    today = date.today()
    end_date = today
    if datetime.now().hour < 15:
        end_date = today - timedelta(days=1)

    start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
    end = end_date.strftime("%Y-%m-%d")

    if start > end:
        return {"ok": True, "needs_verify": False, "name": name, "code": code, "reason": "up_to_date"}

    # 数据源优先级：腾讯 > 东方财富（含新浪 fallback）
    time.sleep(3)
    new_data = fetch_etf_daily_tx(code, start, end)
    source = "tx"

    if new_data is None or new_data.empty:
        new_data = fetch_etf_daily(code, start, end)
        source = "em"

    if new_data is None or new_data.empty:
        print(f"  [{code}] 两源均无新数据（{start}~{end}）")
        return {"ok": False, "name": name, "code": code, "reason": "no_data"}

    # 拉到数据，不入库，返回待核验
    latest_close = float(new_data["close"].iloc[-1])
    latest_date = str(new_data.index[-1].date())
    print(f"  [{code}] {source} 返回 {len(new_data)} 行，最新={latest_date} close={latest_close:.3f}")
    return {
        "ok": True,
        "needs_verify": True,
        "name": name,
        "code": code,
        "source": source,
        "new_data": new_data,
        "latest_close": round(latest_close, 4),
        "latest_date": latest_date,
    }


def main(data_dir: str = "data") -> None:
    """遍历全部防御层 ETF，拉取数据并输出核验清单。"""
    codes = list(ETF_UNIVERSE.values())
    results = []
    for code in codes:
        results.append(update_single_etf(code, data_dir))

    needs_verify = [r for r in results if r.get("needs_verify")]
    failures = [r for r in results if not r["ok"]]

    if not needs_verify and not failures:
        print("所有 ETF 已是最新，无需更新。")
        return

    if needs_verify:
        print(f"\n[待核验] {len(needs_verify)} 只需要 Web 核验")
        for r in needs_verify:
            print(f"  {r['name']}({r['code']}) {r['source']} close={r['latest_close']:.3f}")
        print("---")
        print("请执行窗口 AI WebFetch 核验以上收盘价：")
        print("  https://q.stock.sohu.com/cn/{code}/lshq.shtml")
        print("核验通过后运行入库脚本，然后重新执行命令。")
        print("核验失败则等待数据源更新后重试。")
        sys.exit(0)

    # 有失败且无待核验 → 阻断
    for r in failures:
        print(f"  [{r['code']}] {r['reason']}")
    sys.exit(1)


if __name__ == "__main__":
    main()
