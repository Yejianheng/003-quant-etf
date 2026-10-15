# [2026-10-15] 修复：写入目标改为「原始行情层」data/raw/，写完重算「研究行情层」data/
#            修复门禁比对未对齐日期（此前取各源最后一行，某源当日未出即误报分歧）
#            新增「基准漂移复检」：库内末日各源取值必须一致，否则阻断
# [2026-07-24] 重写：三源交叉验证 — 腾讯/东方财富/新浪独立拉取，一致则自动入库（v214）
# [2026-07-15] 重写：时间门禁 + 拉取不入库 — Web 核验通过后才写入 parquet
# [2026-07-15] 修改：双源独立拉取 + 交叉验证 — 腾讯/东方财富 close 偏差 >0.3% 阻断入库
# [2026-06-23] 修改：数据源优先级调整为腾讯 > 东方财富 > 新浪
# [2026-06-18] 修复：单日增量 fence-post bug（>= → >），start==end 时不再错误跳过
# [2026-06-18] 修改：更新完成后调用 trim_isolated_dates 剔除跨 ETF 不一致日
# [2026-05-30] 新增：每日数据更新脚本 — 增量拉取 AKShare 数据追加到 parquet
"""
每日数据更新脚本：遍历防御层 ETF parquet → 时间门禁 → 三源交叉验证 → 自动入库/待核验。

用法：
  python scripts/update_data.py    # 自动入库（三源/两源一致），分歧则输出核验清单
"""
import os
import sys
import time
from datetime import date, datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data_pipeline import (
    fetch_etf_daily, fetch_etf_daily_tx, fetch_etf_daily_em, fetch_etf_daily_sina,
    load_from_parquet, save_to_parquet, raw_data_path, rebuild_adjusted,
)
from src.etf_universe import ETF_UNIVERSE


def _write_parquet_incremental(code: str, new_data: pd.DataFrame, data_dir: str) -> None:
    """追加新数据 → 原始行情层 data/raw/{code}.parquet，随后重算研究行情层 data/{code}.parquet。

    原始行情层只增不改（去重 keep='last'、按日期排序），是唯一被管线写入的一层；
    研究行情层由「原始行情 + 除权因子」派生，不手工维护。
    """
    path = raw_data_path(code, data_dir)
    existing = load_from_parquet(path)
    combined = pd.concat([existing, new_data])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()
    save_to_parquet(combined, path)
    rebuild_adjusted(code, data_dir)


def _name_from_code(code: str) -> str:
    for name, c in ETF_UNIVERSE.items():
        if c == code:
            return name
    return code


def update_single_etf(code: str, data_dir: str = "data") -> dict:
    """
    三源交叉验证：独立拉取腾讯/东方财富/新浪，收盘价一致则自动入库。

    返回 dict:
      三源/两源一致自动通过: {"ok": True, "needs_verify": False,
                           "source_used": "tx"|"em"|"sina", "agreed_sources": 2|3,
                           "new_data": DataFrame, ...}
      已是最新:              {"ok": True, "needs_verify": False, "reason": "up_to_date"}
      仅一源有数据/各源分歧:  {"ok": True, "needs_verify": True, "source": "...",
                           "new_data": DataFrame, ...}
      零源阻断:              {"ok": False, "reason": "no_data"}
    """
    name = _name_from_code(code)
    path = raw_data_path(code, data_dir)   # 原始行情层才是增量基准
    if not os.path.exists(path):
        return {"ok": False, "name": name, "code": code, "reason": "no_parquet"}

    existing = load_from_parquet(path)
    last_date = existing.index.max().date()

    # 时间门禁：15:00 前不拉当日（盘中日线不完整）
    today = date.today()
    end_date = today
    if datetime.now().hour < 15:
        end_date = today - timedelta(days=1)

    start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
    end = end_date.strftime("%Y-%m-%d")

    if start > end:
        return {"ok": True, "needs_verify": False, "name": name, "code": code, "reason": "up_to_date"}

    # 取数窗口自库内末日（含）起：多取一天用于「基准漂移复检」
    fetch_start = last_date.strftime("%Y-%m-%d")
    time.sleep(3); df_tx = fetch_etf_daily_tx(code, fetch_start, end)
    time.sleep(3); df_em = fetch_etf_daily_em(code, fetch_start, end)
    time.sleep(3); df_sina = fetch_etf_daily_sina(code, fetch_start, end)

    sources = {"tx": df_tx, "em": df_em, "sina": df_sina}

    # 基准漂移复检（2026-10-15 新增）：库内已存在的最后一行，各源必须仍报同一价格。
    # 报不一致说明该源的价格基准（复权口径）变了，此时追加必然造出接缝 —— 直接阻断。
    # 注意：last_date 是 datetime.date，各源 index 是 DatetimeIndex，
    # 直接 `date in DatetimeIndex` 恒为 False（会让复检静默失效），必须转 Timestamp。
    last_ts = pd.Timestamp(last_date)
    wanted = round(float(existing["close"].iloc[-1]), 4)
    drift = []
    for src, df in sources.items():
        if df is None or df.empty or last_ts not in df.index:
            continue
        got = round(float(df.at[last_ts, "close"]), 4)
        if got != wanted:
            drift.append(f"{src}:库内{wanted:.4f}/源报{got:.4f}")
    if drift:
        print(f"  [{code}] 基准漂移告警（{last_date}）—— {'；'.join(drift)}")
        return {"ok": False, "name": name, "code": code, "reason": "basis_drift"}

    # 门禁比对对齐到「各源共有的最新交易日」（2026-10-15 修复）：
    # 此前取各源自己的最后一行，当某源当日数据未出时，比的是今天的与昨天的，必然误报分歧。
    common_dates = None
    for df in sources.values():
        if df is None or df.empty:
            continue
        dates = set(df.index)
        common_dates = dates if common_dates is None else (common_dates & dates)
    compare_date = max(common_dates) if common_dates else None

    def _close_on(df):
        """该源在共同比对日的收盘价；无该日 → None。"""
        if df is None or compare_date is None or compare_date not in df.index:
            return None
        return round(float(df.at[compare_date, "close"]), 4)

    closes = {src: (_close_on(df), df) for src, df in sources.items()}
    available = {k: v for k, v in closes.items() if v[0] is not None}
    n_avail = len(available)

    if n_avail == 0:
        print(f"  [{code}] 三源均无新数据（{start}~{end}）")
        return {"ok": False, "name": name, "code": code, "reason": "no_data"}

    def _new_rows(df):
        """只保留库内末日之后的行，避免重复写入已存在日期。"""
        if df is None or df.empty:
            return pd.DataFrame()
        return df[df.index > pd.Timestamp(last_date)]

    # 按收盘价分组，找一致组
    groups: dict[float, list[str]] = {}
    for src, (close_val, _) in available.items():
        groups.setdefault(close_val, []).append(src)

    max_group = max(groups.values(), key=len)

    if len(max_group) >= 2:
        # 两源/三源一致 → 自动通过
        agreed_close = next(c for c, srcs in groups.items() if len(srcs) == len(max_group))
        preferred = next(s for s in ["tx", "em", "sina"] if s in max_group)
        new_data = _new_rows(closes[preferred][1])
        if new_data.empty:
            return {"ok": True, "needs_verify": False, "name": name, "code": code, "reason": "up_to_date"}
        print(f"  [{code}] {len(max_group)}源一致（{'+'.join(max_group)}={agreed_close:.4f}@{compare_date.date()}，取{preferred}）")
        return {
            "ok": True, "needs_verify": False,
            "name": name, "code": code,
            "source_used": preferred, "agreed_sources": len(max_group),
            "new_data": new_data,
            "latest_close": agreed_close, "latest_date": str(new_data.index[-1].date()),
        }
    else:
        # 各源数据都不同 → 待核验（取首个有数据的源）
        src_name = list(available.keys())[0]
        close_val, _ = available[src_name]
        new_data = _new_rows(closes[src_name][1])
        close_strs = [f"{s}={c[0]:.4f}" for s, c in sorted(closes.items()) if c[0] is not None]
        print(f"  [{code}] 各源分歧（比 {compare_date.date()}）：{', '.join(close_strs)}，待核验（用{src_name}={close_val:.4f}）")
        return {
            "ok": True, "needs_verify": True,
            "name": name, "code": code,
            "source": src_name, "new_data": new_data,
            "latest_close": close_val, "latest_date": str(compare_date.date()),
        }


def main(data_dir: str = "data") -> None:
    """遍历全部防御层 ETF，三源交叉验证 → 自动入库或待核验。"""
    codes = list(ETF_UNIVERSE.values())
    results = []
    for code in codes:
        results.append(update_single_etf(code, data_dir))

    # 自动通过（两源/三源一致）→ 入库
    passed = [r for r in results if r["ok"] and not r.get("needs_verify") and "new_data" in r]
    for r in passed:
        _write_parquet_incremental(r["code"], r["new_data"], data_dir)
        print(f"  [{r['code']}] 入库（{r['agreed_sources']}源一致，用{r['source_used']}）")

    needs_verify = [r for r in results if r.get("needs_verify")]
    failures = [r for r in results if not r["ok"]]

    if not needs_verify and not failures:
        if not passed:
            print("所有 ETF 已是最新，无需更新。")
        else:
            print("所有 ETF 更新完成。")
        return

    if needs_verify:
        print(f"\n[待核验] {len(needs_verify)} 只需要 Web 核验")
        for r in needs_verify:
            print(f"  {r['name']}({r['code']}) {r['source']} close={r['latest_close']:.4f}")
        print("---")
        print("请执行窗口 AI WebSearch 核验以上收盘价：")
        print("  https://q.stock.sohu.com/cn/{code}/lshq.shtml")
        print("核验通过后运行入库脚本。")
        sys.exit(0)

    for r in failures:
        print(f"  [{r['code']}] {r['reason']}")
    sys.exit(1)


if __name__ == "__main__":
    main()
