# [2026-05-30] 新增：补 trend_window=30/50 回测，追加到 scan_2_1.csv
"""一次性脚本：补测 trend_window=30 和 50，结果追加到 ./data/scan_2_1.csv"""
import sys
sys.path.insert(0, ".")

from src.data_pipeline import load_from_parquet
from src.backtest_engine import parameter_scan

CODES = {"510300": "沪深300", "159915": "创业板", "513100": "纳指", "518880": "黄金", "511010": "国债ETF"}


def main():
    print("加载数据...")
    prices = {}
    for code, name in CODES.items():
        df = load_from_parquet(f"./data/{code}.parquet")
        prices[name] = df
        print(f"  {name}: {len(df)} 行, {df.index[0].date()} ~ {df.index[-1].date()}")

    common = sorted(set.intersection(*[set(df.index) for df in prices.values()]))
    print(f"共同交易日: {len(common)}")

    print("\n补测 trend_window=30, 50...")
    results = parameter_scan(
        prices,
        {"trend_window": [30, 50]},
        checkpoint_path="./data/scan_2_1.csv",
    )

    for r in results:
        print(f"  trend_window={r['trend_window']}: "
              f"Sharpe={float(r['sharpe_ratio']):.4f}, "
              f"年化={float(r['annual_return']):.4f}, "
              f"最大回撤={float(r['max_drawdown']):.4f}")

    print("\n完成。")


if __name__ == "__main__":
    main()
