# [2026-06-11] 新增：2026 净值对比图表脚本 — 纯防御策略 vs 5 ETF 买入持有
"""
2026 净值对比图表生成脚本：拉取 5 ETF 数据 → 跑纯防御回测 → 生成 HTML 净值对比图。

用法：python scripts/nav_chart.py
输出：output/nav_2026.html
"""
import os
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest_engine import run_backtest
from src.signal_generator import DEFAULT_PARAMS, DEFENSE_NAMES
from src.etf_universe import ETF_UNIVERSE
from src.data_pipeline import load_from_parquet
from scripts.update_data import update_single_etf

START_DATE = "2026-01-01"

COLORS = {
    "纯防御策略": "#dc3912",
    "沪深300": "#3366cc",
    "创业板": "#ff9900",
    "纳指": "#109618",
    "黄金": "#ffd700",
    "国债ETF": "#990099",
}


def update_all_etfs(data_dir: str = "data") -> None:
    """
    更新全部 5 只防御 ETF 的 parquet 文件。
    任一 parquet 缺失 → FileNotFoundError。
    """
    for name in DEFENSE_NAMES:
        code = ETF_UNIVERSE[name]
        path = os.path.join(data_dir, f"{code}.parquet")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"parquet 文件缺失: {path}，请先运行 scripts/update_data.py"
            )
        update_single_etf(code, data_dir)


def load_prices(data_dir: str = "data") -> dict[str, pd.DataFrame]:
    """
    从 parquet 加载 5 只防御 ETF 的 OHLCV 数据。
    任一 parquet 缺失 → FileNotFoundError。
    """
    prices = {}
    for name in DEFENSE_NAMES:
        code = ETF_UNIVERSE[name]
        path = os.path.join(data_dir, f"{code}.parquet")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"parquet 文件缺失: {path}，请先运行 scripts/update_data.py"
            )
        prices[name] = load_from_parquet(path)
    return prices


def truncate_to_start(series: pd.Series, start_date: str) -> pd.Series:
    """截断 series 到 start_date 及之后，归一化到起点 1.0。"""
    mask = series.index >= pd.Timestamp(start_date)
    truncated = series[mask]
    if len(truncated) == 0:
        raise ValueError(f"无 {start_date} 及之后的数据")
    return truncated / truncated.iloc[0]


def compute_etf_navs(
    prices: dict[str, pd.DataFrame], start_date: str
) -> dict[str, pd.Series]:
    """计算每只 ETF 从 start_date 起的买入持有归一化净值。"""
    navs = {}
    for name in DEFENSE_NAMES:
        if name not in prices:
            continue
        close = prices[name]["close"]
        navs[name] = truncate_to_start(close, start_date)
    return navs


def _nav_to_json(series: pd.Series) -> list[float]:
    """净值 Series → JSON 可序列化的 float 列表（6 位有效数字）。"""
    return [round(float(v), 6) for v in series.values]


def _dates_to_labels(index: pd.DatetimeIndex) -> list[str]:
    """DatetimeIndex → YYYY-MM-DD 字符串列表。"""
    return [str(d.date()) for d in index]


def generate_html(
    strategy_nav: pd.Series,
    etf_navs: dict[str, pd.Series],
    output_path: str,
) -> None:
    """生成 Chart.js HTML 净值对比图（6 线 + 盈亏分界线）。"""

    # 统一 labels：使用策略 nav 的日期（已截断到 2026-01-01 之后）
    labels = _dates_to_labels(strategy_nav.index)
    label_json = json.dumps(labels, ensure_ascii=False)

    # 构建 datasets JSON
    datasets = []

    # 纯防御策略线（粗体突出）
    datasets.append({
        "label": "纯防御策略",
        "data": _nav_to_json(strategy_nav),
        "borderColor": COLORS["纯防御策略"],
        "backgroundColor": COLORS["纯防御策略"],
        "borderWidth": 3,
        "pointRadius": 0,
        "fill": False,
        "tension": 0,
    })

    # 5 ETF 线（细线半透明）
    for name in DEFENSE_NAMES:
        if name not in etf_navs:
            continue
        # ETF nav 使用自己的日期 labels，需对齐
        etf_data = _nav_to_json(etf_navs[name])
        datasets.append({
            "label": name,
            "data": etf_data,
            "borderColor": COLORS[name],
            "backgroundColor": COLORS[name],
            "borderWidth": 1,
            "pointRadius": 0,
            "fill": False,
            "tension": 0,
            "borderDash": [],
        })

    datasets_json = json.dumps(datasets, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>2026 净值对比 — 纯防御策略 vs 5 ETF</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js">
</script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 1100px; margin: 24px auto; padding: 0 16px; }}
  h2 {{ text-align: center; color: #333; }}
  .chart-container {{ position: relative; width: 100%; }}
</style>
</head>
<body>
<h2>2026 净值对比 — 纯防御策略 vs 5 ETF</h2>
<div class="chart-container">
  <canvas id="navChart"></canvas>
</div>
<script>
const labels = {label_json};

const datasets = {datasets_json};

const breakevenPlugin = {{
  id: 'breakevenLine',
  afterDraw(chart) {{
    const {{ ctx, scales: {{ y }} }} = chart;
    const yPos = y.getPixelForValue(1.0);
    if (yPos < chart.chartArea.top || yPos > chart.chartArea.bottom) return;
    ctx.save();
    ctx.setLineDash([6, 4]);
    ctx.strokeStyle = '#999999';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(chart.chartArea.left, yPos);
    ctx.lineTo(chart.chartArea.right, yPos);
    ctx.stroke();
    ctx.restore();
  }}
}};

new Chart(document.getElementById('navChart'), {{
  type: 'line',
  data: {{ labels, datasets }},
  options: {{
    responsive: true,
    maintainAspectRatio: true,
    scales: {{
      x: {{
        title: {{ display: true, text: '日期' }},
        ticks: {{ maxTicksLimit: 20, maxRotation: 45 }}
      }},
      y: {{
        title: {{ display: true, text: '净值 (2026-01-01 = 1.0)' }},
        beginAtZero: false
      }}
    }},
    plugins: {{
      legend: {{
        position: 'top',
        align: 'end',
        labels: {{ usePointStyle: true, boxWidth: 20, padding: 12 }}
      }}
    }}
  }},
  plugins: [breakevenPlugin]
}});
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def main(data_dir: str = "data", output_dir: str = "output") -> None:
    """
    主流程：
    1. 更新 5 ETF parquet
    2. 加载全量历史数据
    3. 跑纯防御回测
    4. 截断到 2026-01-01 + 归一化
    5. 生成 HTML
    """
    # Step 1: 更新数据
    update_all_etfs(data_dir)

    # Step 2: 加载全量历史
    prices = load_prices(data_dir)

    # Step 3: 跑纯防御回测
    result = run_backtest(prices, params=DEFAULT_PARAMS)
    strategy_nav_full = result["records_df"]["nav"]

    # Step 4: 截断到 2026-01-01 + 归一化
    strategy_nav = truncate_to_start(strategy_nav_full, START_DATE)
    etf_navs = compute_etf_navs(prices, START_DATE)

    # 对齐策略和 ETF 的日期标签：统一使用策略 nav 的 labels
    # ETF 数据截取与策略相同的日期范围
    strategy_dates = strategy_nav.index
    aligned_etf_navs = {}
    for name, nav in etf_navs.items():
        common_dates = nav.index.intersection(strategy_dates)
        if len(common_dates) > 0:
            aligned_etf_navs[name] = nav.loc[common_dates]

    # Step 5: 生成 HTML
    output_path = os.path.join(output_dir, "nav_2026.html")
    generate_html(strategy_nav, aligned_etf_navs, output_path)
    print(f"净值对比图已生成：{output_path}")


if __name__ == "__main__":
    main()
