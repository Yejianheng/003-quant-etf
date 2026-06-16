# [2026-06-16] 新增：50/50 A/B 公式验证 — 当前纯B vs 文档50/50 差异量化
"""验证 signal_generator.py:141 的 final_multiplier 公式是否匹配文档。

当前代码（纯B）: final_multiplier = min(sf, dd_mult)
文档声称（50/50）: final_multiplier = (dd_mult + min(sf, dd_mult)) / 2

通过 monkey-patch generate_signal 注入 50/50 公式，不修改 src/ 下任何文件。
"""
import json
import os
import sys
import unittest.mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.backtest_engine as be
from src.backtest_engine import run_backtest
from src.signal_generator import generate_signal as _original_generate_signal

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")
REPORT_DIR = os.path.join(BASE, "跨模型审计")
os.makedirs(REPORT_DIR, exist_ok=True)

ETF_CODE_MAP = {
    "沪深300": "510300",
    "创业板": "159915",
    "纳指": "513100",
    "黄金": "518880",
    "国债ETF": "511010",
}


def load_defense_prices():
    """加载 5 只防御 ETF 的 parquet 数据。"""
    prices = {}
    for name, code in ETF_CODE_MAP.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if "close" in df.columns:
                prices[name] = df
    return prices


def generate_signal_50_50(prices, portfolio_value, params=None):
    """50/50 A/B 组合版本的 generate_signal。

    与原始版本的唯一差异：当熔断未触发时，
    final_multiplier = (dd_mult + min(sf, dd_mult)) / 2
    （原始: min(sf, dd_mult)，即纯 B）
    """
    result = _original_generate_signal(prices, portfolio_value, params)

    if not result["circuit_breaker"]["triggered"]:
        sf = result["defense"]["scaling_factor"]
        dd_mult = result["drawdown_stop"]["position_multiplier"]
        result["execution"]["final_multiplier"] = (dd_mult + min(sf, dd_mult)) / 2.0
        result["execution"]["funds_to_repo"] = False

    return result


def patch_generate_signal(fifty_fifty=False):
    """替换 backtest_engine 模块中的 generate_signal 引用。"""
    if fifty_fifty:
        be.generate_signal = generate_signal_50_50
    else:
        be.generate_signal = _original_generate_signal


def compute_metrics(records_df):
    """从 records_df 计算绩效指标。"""
    nav = records_df["nav"].values
    final_nav = float(nav[-1])
    initial_nav = float(nav[0])
    total_return = (final_nav - initial_nav) / initial_nav

    n_trading_days = len(records_df)
    if n_trading_days >= 2:
        annual_return = (final_nav / initial_nav) ** (252 / n_trading_days) - 1
        daily_returns = np.diff(nav) / nav[:-1]
        annual_vol = float(np.std(daily_returns, ddof=1) * np.sqrt(252))
        sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0
    else:
        annual_return = 0.0
        annual_vol = 0.0
        sharpe = 0.0

    running_max = np.maximum.accumulate(nav)
    drawdowns = (nav - running_max) / running_max
    max_dd = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "final_nav": final_nav,
    }


def run_backtest_with(prices, fifty_fifty=False):
    """运行回测，fifty_fifty=True 时使用文档 50/50 公式。"""
    patch_generate_signal(fifty_fifty=fifty_fifty)
    result = run_backtest(
        prices,
        initial_capital=1_000_000,
        params={"defense_ratio": 1.00},
        execution_lag=1,
    )
    patch_generate_signal(fifty_fifty=False)
    return result


def format_pct(v):
    return f"{v * 100:.2f}%"


def print_metrics(label, m):
    print(f"  {label}:")
    print(f"    Sharpe:     {m['sharpe_ratio']:.3f}")
    print(f"    总收益:     {m['total_return'] * 100:.1f}%")
    print(f"    年化收益:   {m['annual_return'] * 100:.2f}%")
    print(f"    年化波动率: {m['annual_volatility'] * 100:.2f}%")
    print(f"    最大回撤:   {m['max_drawdown'] * 100:.2f}%")


def print_comparison_table(periods_data):
    """打印全量+逐年对比表。"""
    header = (
        f"{'Period':<12} {'公式':<10} {'Sharpe':>8} {'总收益':>9} "
        f"{'年化':>9} {'波动率':>9} {'回撤':>8}"
    )
    sep = "-" * len(header)
    print("\n" + sep)
    print(header)
    print(sep)

    for period_label, data in periods_data.items():
        for ver, key in [("纯B", "current"), ("50/50", "patched")]:
            if key not in data:
                continue
            m = data[key]
            print(
                f"{period_label:<12} {ver:<10} "
                f"{m['sharpe_ratio']:>8.3f} {m['total_return']:>8.1%} "
                f"{m['annual_return']:>8.2%} {m['annual_volatility']:>8.2%} "
                f"{m['max_drawdown']:>8.2%}"
            )
        if "current" in data and "patched" in data:
            mc = data["current"]
            mp = data["patched"]
            d_sharpe = mp["sharpe_ratio"] - mc["sharpe_ratio"]
            d_tot = mp["total_return"] - mc["total_return"]
            d_ann = mp["annual_return"] - mc["annual_return"]
            d_vol = mp["annual_volatility"] - mc["annual_volatility"]
            d_dd = mp["max_drawdown"] - mc["max_drawdown"]
            print(
                f"{'':>12} {'Δ':>10} "
                f"{d_sharpe:>+8.3f} {d_tot:>+8.1%} "
                f"{d_ann:>+8.2%} {d_vol:>+8.2%} "
                f"{d_dd:>+8.2%}"
            )
        print(sep)


def find_top_nav_diff_days(records_current, records_patched, n=10):
    """找出净值差异最大的 n 个交易日。"""
    common_index = records_current.index.intersection(records_patched.index)
    nav_c = records_current.loc[common_index, "nav"]
    nav_p = records_patched.loc[common_index, "nav"]
    diff = (nav_p - nav_c).abs()
    top = diff.nlargest(n)
    rows = []
    for date in top.index:
        rows.append({
            "date": str(date.date()),
            "nav_pure_b": float(nav_c[date]),
            "nav_50_50": float(nav_p[date]),
            "abs_diff": float(diff[date]),
            "pct_diff": float(diff[date] / nav_c[date] * 100),
        })
    return rows


def generate_comparison_chart(records_current, records_patched, output_path):
    """生成两条净值曲线叠加 + 差值曲线的 HTML 图表。"""
    common_index = records_current.index.intersection(records_patched.index)
    nav_c = records_current.loc[common_index, "nav"] / records_current.loc[common_index[0], "nav"]
    nav_p = records_patched.loc[common_index, "nav"] / records_patched.loc[common_index[0], "nav"]
    diff = nav_p - nav_c

    dates = [str(d.date()) for d in common_index]

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>50/50 A/B 公式验证 — 净值对比</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #f5f5f5; color: #333; padding: 24px; }}
h1 {{ text-align: center; margin-bottom: 8px; font-size: 20px; }}
.subtitle {{ text-align: center; color: #888; font-size: 13px; margin-bottom: 24px; }}
.chart-container {{ max-width: 1000px; margin: 0 auto 24px; background: #fff;
                    border-radius: 8px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
.chart-container h2 {{ font-size: 15px; margin-bottom: 12px; color: #555; }}
.legend {{ max-width: 1000px; margin: 0 auto 24px; background: #fff;
          border-radius: 8px; padding: 16px 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08);
          font-size: 13px; line-height: 1.8; }}
</style>
</head>
<body>
<h1>50/50 A/B 公式验证 — 净值曲线对比</h1>
<p class="subtitle">当前代码（纯B）vs 文档声称（50/50 A/B 组合）· execution_lag=1 · defense_ratio=1.00</p>

<div class="chart-container">
  <h2>净值曲线叠加</h2>
  <canvas id="navChart"></canvas>
</div>
<div class="chart-container">
  <h2>净值差异曲线（Δ NAV = 50/50 − 纯B）</h2>
  <canvas id="diffChart"></canvas>
</div>
<div class="legend">
  <strong>公式差异：</strong><br>
  当前代码（纯B）：<code>final_multiplier = min(sf, dd_mult)</code><br>
  文档 50/50：<code>final_multiplier = (dd_mult + min(sf, dd_mult)) / 2</code><br>
  含义：当前代码 B 端始终取 min(sf, dd_mult)；50/50 公式取 A 端（满仓 dd_mult）和 B 端（缩仓）的均值，等价于 50% 无sf + 50% sf。
</div>

<script>
const dates = {json.dumps(dates)};
const navPureB = {json.dumps(nav_c.tolist())};
const nav50_50 = {json.dumps(nav_p.tolist())};
const diffData = {json.dumps(diff.tolist())};

new Chart(document.getElementById('navChart'), {{
  type: 'line',
  data: {{
    labels: dates,
    datasets: [
      {{
        label: '当前代码（纯B）',
        data: navPureB,
        borderColor: '#3366cc',
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0.1,
      }},
      {{
        label: '文档 50/50',
        data: nav50_50,
        borderColor: '#ff6600',
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0.1,
      }},
    ],
  }},
  options: {{
    responsive: true,
    animation: false,
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
      x: {{ display: true, ticks: {{ maxTicksLimit: 12 }} }},
      y: {{ display: true, ticks: {{ callback: function(v) {{ return v.toFixed(2); }} }} }},
    }},
  }},
}});

new Chart(document.getElementById('diffChart'), {{
  type: 'line',
  data: {{
    labels: dates,
    datasets: [{{
      label: 'Δ NAV (50/50 − 纯B)',
      data: diffData,
      borderColor: '#dc3912',
      backgroundColor: 'rgba(220,57,18,0.08)',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: true,
      tension: 0.1,
    }}],
  }},
  options: {{
    responsive: true,
    animation: false,
    plugins: {{ legend: {{ display: true, position: 'top' }} }},
    scales: {{
      x: {{ display: true, ticks: {{ maxTicksLimit: 12 }} }},
      y: {{ display: true, ticks: {{ callback: function(v) {{ return v.toFixed(4); }} }} }},
    }},
  }},
}});
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def slice_prices_by_year(prices, year):
    """截取 prices 到指定年份。"""
    year_start = pd.Timestamp(f"{year}-01-01")
    year_end = pd.Timestamp(f"{year}-12-31")
    sliced = {}
    for name, df in prices.items():
        mask = (df.index >= year_start) & (df.index <= year_end)
        if mask.sum() > 0:
            sliced[name] = df[mask]
    return sliced


def run():
    """主入口：全量对比 + 逐年对比 + 图表生成。"""
    print("=" * 70)
    print("50/50 A/B 公式验证：当前纯B vs 文档 50/50")
    print("=" * 70)
    print("(T+1 执行, execution_lag=1, defense_ratio=1.00)")
    print()

    # 加载数据
    prices = load_defense_prices()
    if len(prices) < 5:
        print("ERROR: 防御 ETF 数据不完整，需要 5 只 parquet 文件")
        print(f"  已找到: {list(prices.keys())}")
        return 1

    print(f"数据加载完成: {list(prices.keys())}")
    for name, df in prices.items():
        print(f"  {name}: {str(df.index[0].date())} ~ {str(df.index[-1].date())} ({len(df)} 行)")

    # === 全量对比 ===
    print("\n" + "-" * 70)
    print("全量 2014-2026 回测")
    print("-" * 70)

    print("  跑当前公式（纯B）...")
    bt_current = run_backtest_with(prices, fifty_fifty=False)
    m_current = compute_metrics(bt_current["records_df"])
    print_metrics("当前代码（纯B）", m_current)

    print("  跑文档公式（50/50）...")
    bt_patched = run_backtest_with(prices, fifty_fifty=True)
    m_patched = compute_metrics(bt_patched["records_df"])
    print_metrics("文档 50/50", m_patched)

    # 自一致性检查
    print("\n  自一致性检查（补丁生效前两轮当前公式应一致）:")
    bt_current_2 = run_backtest_with(prices, fifty_fifty=False)
    m_current_2 = compute_metrics(bt_current_2["records_df"])
    assert abs(m_current["sharpe_ratio"] - m_current_2["sharpe_ratio"]) < 0.001, \
        "FAIL: 两次纯B回测结果不一致"
    print("  PASS: 纯B 两次回测 Sharpe 一致（补丁未泄漏）")

    # 红灯验证：差异确实存在
    assert abs(m_current["sharpe_ratio"] - m_patched["sharpe_ratio"]) > 0.001, \
        "FAIL: 纯B 与 50/50 回测结果相同，公式差异不存在"
    print("  PASS: 纯B 与 50/50 存在差异（红灯：差异确实存在）")

    # 全量对比表
    periods_data = {
        "2014-2026": {"current": m_current, "patched": m_patched},
    }

    # === 逐年对比 ===
    years = range(2014, 2027)
    for year in years:
        print(f"\n--- {year} 年 ---")
        prices_year = slice_prices_by_year(prices, year)
        available_count = sum(1 for df in prices_year.values() if len(df) >= 120)
        if available_count < 3:
            print(f"  {year} 年可用 ETF < 3（{available_count}），跳过")
            continue

        try:
            bt_y_c = run_backtest_with(prices_year, fifty_fifty=False)
            m_y_c = compute_metrics(bt_y_c["records_df"])

            bt_y_p = run_backtest_with(prices_year, fifty_fifty=True)
            m_y_p = compute_metrics(bt_y_p["records_df"])

            periods_data[str(year)] = {"current": m_y_c, "patched": m_y_p}

            d_sharpe = m_y_p["sharpe_ratio"] - m_y_c["sharpe_ratio"]
            d_return = m_y_p["total_return"] - m_y_c["total_return"]
            d_dd = m_y_p["max_drawdown"] - m_y_c["max_drawdown"]
            print(f"  ΔSharpe: {d_sharpe:+.3f}  Δ收益: {d_return * 100:+.1f}%  Δ回撤: {d_dd * 100:+.2f}%")
        except Exception as e:
            print(f"  {year} 年回测失败: {e}")

    # === 打印对比表 ===
    print_comparison_table(periods_data)

    # === 净值差异最大的 10 天 ===
    print("\n净值差异最大的 10 个交易日:")
    top_diffs = find_top_nav_diff_days(bt_current["records_df"], bt_patched["records_df"])
    print(f"{'日期':<12} {'纯B NAV':>12} {'50/50 NAV':>12} {'绝对差':>10} {'相对差':>8}")
    print("-" * 60)
    for row in top_diffs:
        print(f"{row['date']:<12} {row['nav_pure_b']:>12.0f} {row['nav_50_50']:>12.0f} "
              f"{row['abs_diff']:>10.0f} {row['pct_diff']:>7.2f}%")

    # === 生成图表 ===
    chart_path = os.path.join(DATA_DIR, "nav_compare_50_50.html")
    generate_comparison_chart(bt_current["records_df"], bt_patched["records_df"], chart_path)
    print(f"\n图表已生成: {chart_path}")

    # === 写 JSON 摘要 ===
    summary = {
        "config": {
            "execution_lag": 1,
            "defense_ratio": 1.00,
            "params": "DEFAULT_PARAMS unchanged",
        },
        "full_period": {
            "current_pure_b": {k: round(v, 6) if isinstance(v, float) else v
                              for k, v in m_current.items()},
            "docs_50_50": {k: round(v, 6) if isinstance(v, float) else v
                          for k, v in m_patched.items()},
            "delta_sharpe": round(m_patched["sharpe_ratio"] - m_current["sharpe_ratio"], 4),
            "delta_total_return": round(m_patched["total_return"] - m_current["total_return"], 4),
            "delta_annual_return": round(m_patched["annual_return"] - m_current["annual_return"], 4),
            "delta_annual_volatility": round(
                m_patched["annual_volatility"] - m_current["annual_volatility"], 4
            ),
            "delta_max_drawdown": round(m_patched["max_drawdown"] - m_current["max_drawdown"], 4),
        },
        "by_year": {},
        "top_10_nav_diffs": top_diffs,
    }
    for year_label, data in periods_data.items():
        if year_label == "2014-2026":
            continue
        summary["by_year"][year_label] = {
            "current_pure_b": {k: round(v, 6) if isinstance(v, float) else v
                              for k, v in data["current"].items()},
            "docs_50_50": {k: round(v, 6) if isinstance(v, float) else v
                          for k, v in data["patched"].items()},
            "delta_sharpe": round(
                data["patched"]["sharpe_ratio"] - data["current"]["sharpe_ratio"], 4
            ),
            "delta_total_return": round(
                data["patched"]["total_return"] - data["current"]["total_return"], 4
            ),
        }

    json_path = os.path.join(DATA_DIR, "verify_50_50_summary.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"JSON 摘要已保存: {json_path}")

    # === 最终结论 ===
    print("\n" + "=" * 70)
    print("结论")
    print("=" * 70)
    delta_sharpe = m_patched["sharpe_ratio"] - m_current["sharpe_ratio"]
    delta_return = m_patched["total_return"] - m_current["total_return"]
    delta_dd = m_patched["max_drawdown"] - m_current["max_drawdown"]
    print(f"  ΔSharpe:      {delta_sharpe:+.4f}")
    print(f"  Δ总收益:      {delta_return * 100:+.2f}%")
    print(f"  Δ年化收益:    {(m_patched['annual_return'] - m_current['annual_return']) * 100:+.2f}%")
    print(f"  Δ年化波动率:  {(m_patched['annual_volatility'] - m_current['annual_volatility']) * 100:+.2f}%")
    print(f"  Δ最大回撤:    {delta_dd * 100:+.2f}%")

    if abs(delta_sharpe) < 0.05:
        print(f"\n  -> DeltaSharpe {delta_sharpe:+.4f}，差异不显著（< 0.05），无需紧急修复。")
    else:
        print(f"\n  -> DeltaSharpe {delta_sharpe:+.4f}，差异显著（>= 0.05），建议修复。")

    return 0


if __name__ == "__main__":
    sys.exit(run())
