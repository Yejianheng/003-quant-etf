# [2026-05-27] 修复：回撤图去掉 reverse:true（负值应向下）
# [2026-05-27] 修复：benchmark 同起点归一化
# [2026-05-27] 修复：NAV 归一化 + benchmark 日期对齐 + Calmar 格式
# [2026-05-27] 新增：HTML 回测可视化报告 — Chart.js CDN + 内嵌 JSON

import json
import os
import numpy as np
import pandas as pd


def generate_report(result: dict, output_path: str = "./reports/backtest_report.html") -> str:
    """生成独立 HTML 回测可视化报告。result: run_backtest() 返回值。"""

    records_df = result.get("records_df", pd.DataFrame())
    benchmark_nav = result.get("benchmark_nav", pd.Series(dtype=float))

    has_data = len(records_df) > 0

    # 提取日期和净值序列
    if has_data:
        dates = [str(d.date()) for d in records_df.index]
        nav_raw = records_df["nav"].values
        # Bug1 修复：归一化到起点 1.0，与基准同比例尺
        nav_list = (nav_raw / nav_raw[0]).tolist()
        running_max = np.maximum.accumulate(nav_raw)
        drawdown_list = ((nav_raw - running_max) / running_max * 100).tolist()
        # Bug2 修复：benchmark 对齐到 records_df 日期范围，并归一化到同一起点
        bench_aligned = benchmark_nav.reindex(records_df.index)
        if bench_aligned.isna().any():
            bench_aligned = bench_aligned.ffill()
        bench_list = (bench_aligned / bench_aligned.iloc[0]).tolist()
    else:
        dates, nav_list, drawdown_list = [], [], []
        bench_list = []

    # 标量指标
    def pct(v):
        return f"{v * 100:.2f}%" if isinstance(v, (int, float)) else v

    annual_return = result.get("annual_return", 0)
    calmar = result.get("calmar_ratio", 0)
    # Bug3 修复：年化收益为负时 Calmar 无参考意义，显示 N/A
    if annual_return < 0:
        calmar_str = "N/A"
    else:
        calmar_str = f"{calmar:.3f}"

    metrics = {
        "总收益": pct(result.get("total_return", 0)),
        "年化收益": pct(annual_return),
        "年化波动": pct(result.get("annual_volatility", 0)),
        "Sharpe": f"{result.get('sharpe_ratio', 0):.2f}",
        "最大回撤": pct(result.get("max_drawdown", 0)),
        "Calmar": calmar_str,
    }

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF 动量轮动 — 回测报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js">
</script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #f5f5f5; color: #333; padding: 24px; }}
h1 {{ text-align: center; margin-bottom: 24px; font-size: 22px; }}
.cards {{ display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; margin-bottom: 32px; }}
.card {{ background: #fff; border-radius: 8px; padding: 16px 24px; min-width: 140px;
         text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
.card .value {{ font-size: 24px; font-weight: 700; color: #1a1a2e; }}
.card .label {{ font-size: 12px; color: #888; margin-top: 4px; }}
.chart-container {{ max-width: 960px; margin: 0 auto 32px; background: #fff;
                    border-radius: 8px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
.chart-container h2 {{ font-size: 16px; margin-bottom: 12px; color: #555; }}
.empty-notice {{ text-align: center; color: #999; padding: 60px 0; }}
</style>
</head>
<body>
<h1>ETF 动量轮动 — 回测报告</h1>

<div class="cards">
{"".join(f'<div class="card"><div class="value">{v}</div><div class="label">{k}</div></div>' for k, v in metrics.items())}
</div>

{"<div class=\"empty-notice\">无回测数据</div>" if not has_data else f"""
<div class="chart-container">
  <h2>净值曲线（策略 vs 基准）</h2>
  <canvas id="navChart"></canvas>
</div>
<div class="chart-container">
  <h2>回撤曲线</h2>
  <canvas id="ddChart"></canvas>
</div>
"""}

<script>
const dates = {json.dumps(dates)};
const navData = {json.dumps(nav_list)};
const benchData = {json.dumps(bench_list)};
const ddData = {json.dumps(drawdown_list)};

const blue = '#3366cc';
const orange = '#ff6600';
const red = '#dc3912';

if (dates.length > 0) {{
  // NAV 叠加图
  new Chart(document.getElementById('navChart'), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [
        {{
          label: '策略净值',
          data: navData,
          borderColor: blue,
          backgroundColor: 'rgba(51,102,204,0.05)',
          borderWidth: 2,
          pointRadius: 0,
          fill: true,
          tension: 0.1,
        }},
        {{
          label: '基准净值',
          data: benchData,
          borderColor: orange,
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
          tension: 0.1,
          borderDash: [5, 3],
        }},
      ],
    }},
    options: {{
      responsive: true,
      animation: false,
      plugins: {{ legend: {{ position: 'top' }} }},
      scales: {{
        x: {{ display: true, ticks: {{ maxTicksLimit: 12 }} }},
        y: {{ display: true, ticks: {{ callback: v => v.toFixed(2) }} }},
      }},
    }},
  }});

  // 回撤图
  new Chart(document.getElementById('ddChart'), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [{{
        label: '回撤 (%)',
        data: ddData,
        borderColor: red,
        backgroundColor: 'rgba(220,57,18,0.08)',
        borderWidth: 2,
        pointRadius: 0,
        fill: true,
        tension: 0.1,
      }}],
    }},
    options: {{
      responsive: true,
      animation: false,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ display: true, ticks: {{ maxTicksLimit: 12 }} }},
        y: {{
          display: true,
          ticks: {{ callback: v => v + '%' }},
          max: 0,
        }},
      }},
    }},
  }});
}}
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path
