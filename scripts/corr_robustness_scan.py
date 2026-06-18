# [2026-06-18] 新增：股债相关性熔断鲁棒性扫描 — smoothed_corr 分布 + 三维参数敏感性
"""股债相关性熔断鲁棒性扫描。步骤 1-4 全部输出打印 + CSV。"""
import copy, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd

from src.backtest_engine import run_backtest
from src.signal_generator import DEFAULT_PARAMS
from src.correlation_circuit_breaker import stock_basket_returns, rolling_correlation

NAMES = ['沪深300', '创业板', '纳指', '黄金', '国债ETF']
CODES = ['510300', '159915', '513100', '518880', '511010']

os.makedirs('output', exist_ok=True)

# ── 加载数据 ──────────────────────────────────────────────
prices = {n: pd.read_parquet(f'data/{c}.parquet') for n, c in zip(NAMES, CODES)}
print(f"数据加载完成: {[(n, len(prices[n])) for n in NAMES]}")

# ═══════════════════════════════════════════════════════════
# Step 1: smoothed_corr 全期历史分布（独立计算，无需回测）
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 1: smoothed_corr 全期历史分布")
print("=" * 60)

stock_prices = {n: prices[n]['close'] for n in ['沪深300', '创业板', '纳指']}
bond_prices = prices['国债ETF']['close']

stock_rets = stock_basket_returns(stock_prices)
bond_rets = np.log(bond_prices / bond_prices.shift(1)).dropna()

common_idx = stock_rets.index.intersection(bond_rets.index)
stock_aligned = stock_rets.loc[common_idx]
bond_aligned = bond_rets.loc[common_idx]

corr_window = DEFAULT_PARAMS['corr_window']
sma_window = DEFAULT_PARAMS['corr_sma_window']

roll_corr = rolling_correlation(stock_aligned, bond_aligned, corr_window)
smoothed = roll_corr.rolling(sma_window).mean()
smoothed_corr = smoothed.dropna()

print(f"日期范围: {smoothed_corr.index[0].date()} ~ {smoothed_corr.index[-1].date()}")
print(f"样本数: {len(smoothed_corr)}")
print(f"均值: {smoothed_corr.mean():.4f}")
print(f"标准差: {smoothed_corr.std():.4f}")
print(f"Min: {smoothed_corr.min():.4f}")
print(f"Max: {smoothed_corr.max():.4f}")

print("\n分位数:")
for q in [0.50, 0.75, 0.90, 0.95, 0.99]:
    print(f"  {q:.0%}: {smoothed_corr.quantile(q):.4f}")

print("\n突破各阈值交易日数:")
total_days = len(smoothed_corr)
for thresh in [0.0, 0.05, 0.1, 0.15, 0.2, 0.3]:
    n = (smoothed_corr > thresh).sum()
    pct = n / total_days * 100
    print(f"  >{thresh:+.1f}: {n} 天 ({pct:.1f}%)")

csv_df = pd.DataFrame({'date': smoothed_corr.index, 'smoothed_corr': smoothed_corr.values})
csv_df.to_csv('output/smoothed_corr_history.csv', index=False)
print("\nsmoothed_corr 时序已保存到 output/smoothed_corr_history.csv")

# ═══════════════════════════════════════════════════════════
# 辅助函数：单参数扫描
# ═══════════════════════════════════════════════════════════
def scan_param(param_name, values):
    """扫描单个参数，返回 DataFrame。"""
    rows = []
    for val in values:
        params = copy.deepcopy(DEFAULT_PARAMS)
        params[param_name] = val
        bt = run_backtest(prices, 1_000_000, params=params, min_days=120)
        records = bt['records_df']
        cb_days = int(records['circuit_breaker_triggered'].sum())
        total_days = len(records)
        rows.append({
            param_name: val,
            'CB触发天数': cb_days,
            'CB触发%': round(cb_days / total_days * 100, 1),
            'Sharpe': round(bt['sharpe_ratio'], 3),
            '年化': round(bt['annual_return'] * 100, 1),
            '回撤': round(bt['max_drawdown'] * 100, 1),
        })
        print(f"  {param_name}={val} → Sharpe={bt['sharpe_ratio']:.3f} CB={cb_days}天")
    return pd.DataFrame(rows)

# ═══════════════════════════════════════════════════════════
# Step 2: corr_threshold 敏感性扫描
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 2: corr_threshold 敏感性扫描")
print("=" * 60)
df_threshold = scan_param('corr_threshold', [-0.1, -0.05, 0.0, 0.05, 0.10, 0.15])
print("\n", df_threshold.to_string(index=False))
df_threshold.to_csv('output/corr_threshold_scan.csv', index=False)

# ═══════════════════════════════════════════════════════════
# Step 3: corr_window 敏感性扫描
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 3: corr_window 敏感性扫描")
print("=" * 60)
df_window = scan_param('corr_window', [20, 40, 60, 90, 120])
print("\n", df_window.to_string(index=False))
df_window.to_csv('output/corr_window_scan.csv', index=False)

# ═══════════════════════════════════════════════════════════
# Step 4: corr_sma_window 敏感性扫描
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 4: corr_sma_window 敏感性扫描")
print("=" * 60)
df_sma = scan_param('corr_sma_window', [1, 3, 5, 10, 20])
print("\n", df_sma.to_string(index=False))
df_sma.to_csv('output/corr_sma_window_scan.csv', index=False)

print("\n" + "=" * 60)
print("全部扫描完成。输出文件:")
print("  output/smoothed_corr_history.csv")
print("  output/corr_threshold_scan.csv")
print("  output/corr_window_scan.csv")
print("  output/corr_sma_window_scan.csv")
print("=" * 60)
