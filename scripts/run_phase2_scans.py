# [2026-05-28] 新增：阶段 2 参数扫描 — 12 项独立网格扫描
"""阶段 2 参数扫描 — 12 项独立网格扫描，结果写入 ./data/scan_2X.csv"""

import csv
import os
import sys
sys.path.insert(0, ".")

from src.data_pipeline import load_from_parquet
from src.backtest_engine import parameter_scan, run_backtest

CODES = {"510300": "沪深300", "159915": "创业板", "513100": "纳指", "518880": "黄金", "511010": "国债ETF"}

dd_groups = {
    "10_15_18": [(0.10, 1.0), (0.15, 0.5), (0.18, 0.0)],
    "12_15_18": [(0.12, 1.0), (0.15, 0.5), (0.18, 0.0)],
    "12_18_20": [(0.12, 1.0), (0.18, 0.5), (0.20, 0.0)],
}

# 构建 drawdown_thresholds 反向查找：str(list) → 组名
dd_reverse = {str(v): k for k, v in dd_groups.items()}

SCANS = [
    ("2.1", {"trend_window": [20, 40, 60, 80, 120]}),
    ("2.2", {"trend_threshold": [0.0, 1.0, 1.5, 2.0, 2.5, 3.0]}),
    # 2.3 单独手动循环处理（配对非笛卡尔积）
    ("2.4", {"offense_top_k": [2, 3, 4, 5]}),
    ("2.6", {"target_vol_beta": [0.08, 0.10, 0.12]}),
    ("2.7", {"target_vol_alpha": [0.15, 0.20, 0.25]}),
    ("2.8", {"vol_tolerance": [0.01, 0.015, 0.02]}),
    ("2.10", {"drawdown_thresholds": list(dd_groups.values())}),
    ("2.11", {"defense_ratio": [0.60, 0.70, 0.80]}),
    ("2.12", {"corr_window": [40, 60, 80]}),
    ("2.13", {"corr_threshold": [0.0, 0.1, 0.2]}),
    ("2.14", {"ewma_lambda": [0.90, 0.94, 0.97]}),
]

MOMENTUM_PAIRS = [(20, 60), (20, 80), (40, 120)]


def _compute_count(param_grid):
    """计算网格组合数。"""
    n = 1
    for v in param_grid.values():
        n *= len(v)
    return n


def _scan_2_3_manual(prices, min_days=120):
    """扫描 2.3：momentum_short + momentum_long 配对循环（3 组，非笛卡尔积）。"""
    path = "./data/scan_2_3.csv"
    print(f"\n{'='*50}")
    print(f"扫描 2.3: momentum_short × momentum_long 配对 → {path}")
    print(f"组合数: {len(MOMENTUM_PAIRS)}")

    # checkpoint：读取已完成组合
    completed = set()
    if os.path.exists(path):
        with open(path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                completed.add((row["momentum_short"], row["momentum_long"]))

    header_written = bool(completed)
    new_results = []

    for short, long in MOMENTUM_PAIRS:
        pair_key = (str(short), str(long))
        if pair_key in completed:
            continue

        params = {"momentum_short": short, "momentum_long": long}
        bt = run_backtest(prices, params=params, min_days=min_days)
        scalar = {k: v for k, v in bt.items() if k not in ("records_df", "benchmark_nav")}
        row = {"momentum_short": str(short), "momentum_long": str(long), **scalar}

        os.makedirs("data", exist_ok=True)
        mode = "a" if header_written else "w"
        with open(path, mode, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if not header_written:
                writer.writeheader()
                header_written = True
            writer.writerow(row)
        new_results.append(row)
        print(f"  完成: short={short}, long={long}, Sharpe={scalar.get('sharpe_ratio', 0):.4f}")

    # 汇总排序
    all_rows = []
    if os.path.exists(path):
        with open(path, "r", newline="") as f:
            all_rows = list(csv.DictReader(f))
    all_rows.sort(key=lambda r: float(r.get("sharpe_ratio", 0)), reverse=True)
    if all_rows:
        best = all_rows[0]
        print(f"最优: short={best['momentum_short']}, long={best['momentum_long']}, "
              f"Sharpe={float(best.get('sharpe_ratio', 0)):.4f}, "
              f"年化={float(best.get('annual_return', 0)):.4f}, "
              f"最大回撤={float(best.get('max_drawdown', 0)):.4f}")
    _sort_csv_by_sharpe(path)
    print(f"结果已保存: {path}")
    return all_rows


def _sort_csv_by_sharpe(path):
    """读取 CSV，按 sharpe_ratio 降序重写。"""
    if not os.path.exists(path):
        return
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not rows:
        return
    rows.sort(key=lambda r: float(r.get("sharpe_ratio", 0)), reverse=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _print_best(results, scan_id, extra_key=None):
    """打印最优参数行。extra_key 用于标注额外信息（如 2.10 组名）。"""
    if not results:
        print("  无结果")
        return
    best = results[0]
    parts = [f"Sharpe={float(best.get('sharpe_ratio', 0)):.4f}",
             f"年化={float(best.get('annual_return', 0)):.4f}",
             f"最大回撤={float(best.get('max_drawdown', 0)):.4f}"]
    if extra_key:
        parts.insert(0, f"{extra_key}={best.get(extra_key, '?')}")
    print(f"最优: {', '.join(parts)}")


def main():
    print("加载真实数据...")
    prices = {}
    for code, name in CODES.items():
        parquet_path = f"./data/{code}.parquet"
        if not os.path.exists(parquet_path):
            print(f"  [错误] 数据文件不存在: {parquet_path}，跳过")
            continue
        df = load_from_parquet(parquet_path)
        prices[name] = df
        print(f"  {name}: {len(df)} 行, {df.index[0].date()} ~ {df.index[-1].date()}")

    if not prices:
        print("[错误] 无可用数据，退出")
        return

    common = sorted(set.intersection(*[set(df.index) for df in prices.values()]))
    print(f"共同交易日: {len(common)}")

    # 2.3 单独处理
    _scan_2_3_manual(prices)

    # 其余扫描
    for scan_id, param_grid in SCANS:
        path = f"./data/scan_{scan_id.replace('.', '_')}.csv"
        n_combos = _compute_count(param_grid)
        print(f"\n{'='*50}")
        print(f"扫描 {scan_id}: {list(param_grid.keys())} → {path}")
        print(f"组合数: {n_combos}")

        results = parameter_scan(prices, param_grid, checkpoint_path=path)

        # 2.10 反查组名
        if scan_id == "2.10" and results:
            for r in results:
                raw = r.get("drawdown_thresholds", "")
                r["dd_group"] = dd_reverse.get(str(raw), "?")
            results.sort(key=lambda r: float(r.get("sharpe_ratio", 0)), reverse=True)
            _print_best(results, scan_id, extra_key="dd_group")
        elif results:
            _print_best(results, scan_id)
        else:
            print("  无新结果（全部来自 checkpoint）")
            if os.path.exists(path):
                with open(path, "r", newline="") as f:
                    cached = list(csv.DictReader(f))
                cached.sort(key=lambda r: float(r.get("sharpe_ratio", 0)), reverse=True)
                if cached:
                    _print_best(cached, scan_id)

        _sort_csv_by_sharpe(path)
        print(f"结果已保存: {path}")

    print("\n全部扫描完成。")


if __name__ == "__main__":
    main()
