# [2026-06-11] 修改：输出路径改项目根 + 鼠标悬停6线净值 + 数据表格 + 日期搜索
# [2026-06-11] 新增：2026 净值对比图表脚本 — 纯防御策略 vs 5 ETF 买入持有
"""
2026 净值对比图表生成脚本：拉取 5 ETF 数据 → 跑纯防御回测 → 生成 HTML 净值对比图。

用法：python scripts/nav_chart.py
输出：nav_2026.html
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
PAGE_SIZE = 20

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


def _build_table_data(strategy_nav, etf_navs, names):
    """构建表格行数据（净值 + 日环比 Δ%），对齐到策略净值日期。"""
    dates = strategy_nav.index
    rows = []
    prev = None
    for i, d in enumerate(dates):
        navs = [float(strategy_nav.iloc[i])]
        for name in names:
            s = etf_navs.get(name)
            if s is not None and d in s.index:
                navs.append(float(s.loc[d]))
            else:
                navs.append(None)
        if prev is None:
            deltas = [None] * 6
        else:
            deltas = [
                round((navs[j] - prev[j]) / prev[j] * 100, 2)
                if (navs[j] is not None and prev[j] is not None and prev[j] != 0)
                else None
                for j in range(6)
            ]
        rows.append({
            "date": str(d.date()),
            "navs": [round(v, 4) if v is not None else None for v in navs],
            "deltas": deltas,
        })
        prev = navs
    return rows


def generate_html(
    strategy_nav: pd.Series,
    etf_navs: dict[str, pd.Series],
    output_path: str,
) -> None:
    """生成 Chart.js HTML 净值对比图（6 线 + 盈亏线 + 悬停浮窗 + 数据表 + 翻页 + 日期搜索）。"""

    labels = _dates_to_labels(strategy_nav.index)
    label_json = json.dumps(labels, ensure_ascii=False)

    datasets = []

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

    for name in DEFENSE_NAMES:
        if name not in etf_navs:
            continue
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

    table_data = _build_table_data(strategy_nav, etf_navs, DEFENSE_NAMES)
    table_data_json = json.dumps(table_data, ensure_ascii=False)
    total_pages = max(1, (len(table_data) + PAGE_SIZE - 1) // PAGE_SIZE)

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
         max-width: 1200px; margin: 24px auto; padding: 0 16px; }}
  h2 {{ text-align: center; color: #333; }}
  .chart-container {{ position: relative; width: 100%; margin-bottom: 32px; }}
  .table-toolbar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }}
  .table-toolbar input[type="date"] {{ padding: 4px 8px; border: 1px solid #ccc;
      border-radius: 4px; font-size: 13px; }}
  .table-toolbar button {{ padding: 4px 14px; border: 1px solid #999; border-radius: 4px;
      background: #f5f5f5; cursor: pointer; font-size: 13px; }}
  .table-toolbar button:hover {{ background: #e0e0e0; }}
  .table-wrapper {{ overflow-x: auto; max-width: 100%; border: 1px solid #e0e0e0;
      border-radius: 4px; }}
  table {{ border-collapse: collapse; font-size: 13px; white-space: nowrap; width: 100%; }}
  th, td {{ padding: 5px 10px; border-right: 1px solid #e8e8e8;
      border-bottom: 1px solid #e8e8e8; text-align: right; }}
  th {{ background: #f5f5f5; position: sticky; top: 0; z-index: 2; font-weight: 600; }}
  th:first-child, td:first-child {{ position: sticky; left: 0; z-index: 1;
      text-align: left; background: #fff; font-weight: 600; }}
  th:first-child {{ z-index: 3; background: #f5f5f5; }}
  thead tr:first-child th {{ border-top: none; }}
  tbody tr:hover td {{ background: #fafafa; }}
  tbody tr:hover td:first-child {{ background: #fafafa; }}
  .pos {{ color: #d32f2f; }}
  .neg {{ color: #2e7d32; }}
  .pagination {{ display: flex; align-items: center; justify-content: center; gap: 16px;
      margin-top: 16px; margin-bottom: 24px; }}
  .pagination button {{ padding: 6px 18px; border: 1px solid #aaa; border-radius: 4px;
      background: #fff; cursor: pointer; font-size: 13px; }}
  .pagination button:hover {{ background: #f0f0f0; }}
  .pagination button:disabled {{ opacity: 0.35; cursor: default; }}
  .page-info {{ font-size: 13px; color: #666; min-width: 80px; text-align: center; }}
</style>
</head>
<body>
<h2>2026 净值对比 — 纯防御策略 vs 5 ETF</h2>
<div class="chart-container">
  <canvas id="navChart"></canvas>
</div>

<div class="table-toolbar">
  <label for="dateSearch" style="font-size:13px;">日期定位：</label>
  <input type="date" id="dateSearch">
  <button onclick="jumpToDate()">跳转</button>
  <span id="searchMsg" style="font-size:12px;color:#e53935;margin-left:8px;"></span>
</div>

<div class="table-wrapper">
  <table id="navTable">
    <thead>
      <tr>
        <th>日期</th>
        <th>纯防御策略</th><th>沪深300</th><th>创业板</th><th>纳指</th><th>黄金</th><th>国债ETF</th>
        <th>纯防御Δ%</th><th>沪深300Δ%</th><th>创业板Δ%</th><th>纳指Δ%</th><th>黄金Δ%</th><th>国债ETFΔ%</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>
</div>

<div class="pagination">
  <button id="prevBtn" onclick="changePage(-1)">上一页</button>
  <span class="page-info" id="pageInfo">第 1/{total_pages} 页</span>
  <button id="nextBtn" onclick="changePage(1)">下一页</button>
</div>

<script>
const tableData = {table_data_json};
const PAGE_SIZE = {PAGE_SIZE};
const totalPages = {total_pages};
let currentPage = 1;

// ===== Chart =====
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
    interaction: {{
      mode: 'index',
      intersect: false,
    }},
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
      }},
      tooltip: {{
        usePointStyle: true,
        boxPadding: 4,
        callbacks: {{
          label: function(ctx) {{
            const di = ctx.dataIndex;
            const colNames = ['纯防御策略','沪深300','创业板','纳指','黄金','国债ETF'];
            const lines = [];
            for (let j = 0; j < datasets.length && j < 6; j++) {{
              const v = datasets[j].data[di];
              if (v !== undefined && v !== null) {{
                lines.push(colNames[j] + '  ' + v.toFixed(4));
              }}
            }}
            return lines;
          }}
        }}
      }}
    }}
  }},
  plugins: [breakevenPlugin]
}});

// ===== Table =====
function renderTable() {{
  const start = (currentPage - 1) * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, tableData.length);
  const tbody = document.querySelector('#navTable tbody');
  let html = '';
  for (let i = start; i < end; i++) {{
    const row = tableData[i];
    html += '<tr>';
    html += '<td>' + row.date + '</td>';
    for (let j = 0; j < 6; j++) {{
      const v = row.navs[j];
      html += '<td>' + (v !== null ? v.toFixed(4) : '—') + '</td>';
    }}
    for (let j = 0; j < 6; j++) {{
      const d = row.deltas[j];
      if (d === null) {{
        html += '<td>—</td>';
      }} else if (d >= 0) {{
        html += '<td class="pos">+' + d.toFixed(2) + '%</td>';
      }} else {{
        html += '<td class="neg">' + d.toFixed(2) + '%</td>';
      }}
    }}
    html += '</tr>';
  }}
  tbody.innerHTML = html;
  document.getElementById('pageInfo').textContent =
    '第 ' + currentPage + '/' + totalPages + ' 页';
  document.getElementById('prevBtn').disabled = currentPage <= 1;
  document.getElementById('nextBtn').disabled = currentPage >= totalPages;
}}

function changePage(delta) {{
  const newPage = currentPage + delta;
  if (newPage < 1 || newPage > totalPages) return;
  currentPage = newPage;
  renderTable();
  document.getElementById('navTable').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
}}

function jumpToDate() {{
  const input = document.getElementById('dateSearch');
  const msg = document.getElementById('searchMsg');
  msg.textContent = '';
  if (!input.value) {{
    msg.textContent = '请选择日期';
    return;
  }}
  let found = -1;
  for (let i = 0; i < tableData.length; i++) {{
    if (tableData[i].date >= input.value) {{
      found = i;
      break;
    }}
  }}
  if (found === -1) {{
    msg.textContent = '未找到该日期之后的数据';
    return;
  }}
  currentPage = Math.floor(found / PAGE_SIZE) + 1;
  renderTable();
  document.getElementById('navTable').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
}}

renderTable();
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def main(data_dir: str = "data", output_path: str = "nav_2026.html") -> None:
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
    strategy_dates = strategy_nav.index
    aligned_etf_navs = {}
    for name, nav in etf_navs.items():
        common_dates = nav.index.intersection(strategy_dates)
        if len(common_dates) > 0:
            aligned_etf_navs[name] = nav.loc[common_dates]

    # Step 5: 生成 HTML
    generate_html(strategy_nav, aligned_etf_navs, output_path)
    print(f"净值对比图已生成：{output_path}")


if __name__ == "__main__":
    main()
