# [2026-06-11] 修改：T+1 表格数据前移 + 操作列含权重变化（箭头格式）+ 表头改「今日调仓」
# [2026-06-11] 修改：净值归一化除以首日 + 底部分页增加页码跳转
# [2026-06-11] 修改：表格重做为持仓权重 + tooltip 移除自定义 callback 修复36行重复
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


def _format_action(old_weights, new_weights, etf_names):
    """格式化调仓操作文本：卖出 品种(旧%→新%), 买入 品种(旧%→新%)"""
    sold = []
    bought = []
    for name in etf_names:
        old_w = old_weights.get(name, 0.0)
        new_w = new_weights.get(name, 0.0)
        if new_w > old_w + 0.001:
            bought.append((name, old_w, new_w))
        elif old_w > new_w + 0.001:
            sold.append((name, old_w, new_w))

    if not sold and not bought:
        return "无需调仓"

    parts = []
    if sold:
        sold_str = '、'.join(f"{name}({old_w*100:.0f}%→{new_w*100:.0f}%)" for name, old_w, new_w in sold)
        parts.append(f"卖出 {sold_str}")
    if bought:
        bought_str = '、'.join(f"{name}({old_w*100:.0f}%→{new_w*100:.0f}%)" for name, old_w, new_w in bought)
        parts.append(f"买入 {bought_str}")

    return "，".join(parts)


def _build_table_data(records_df, etf_names):
    """T+1 前移：records_df[0] 为 2025 末锚点（不显示），records_df[1:] 为 2026 数据。
    X 日持仓来自 X-1 日 signal，操作比较 X-1 vs X-2 的 defense_active。"""
    first_nav = float(records_df.iloc[1]["nav"])
    rows = []

    for i, (_idx, row) in enumerate(records_df.iterrows()):
        if i == 0:
            continue  # anchor row, not displayed

        date_str = str(_idx.date()) if hasattr(_idx, "date") else str(_idx)[:10]

        # --- 持仓权重（T+1 前移：X 日持仓来自 X-1 日 signal） ---
        signal_row = records_df.iloc[i - 1]
        active_str = signal_row.get("defense_active", "")
        active = [n.strip() for n in active_str.split(";") if n.strip()] if active_str else []
        n_active = len(active)
        weights = {}
        for name in etf_names:
            weights[name] = 1.0 / n_active if name in active and n_active > 0 else 0.0

        total_weight = sum(weights.values())
        cash = 1.0 - total_weight

        # --- 操作列（T+1 前移） ---
        if i == 1:
            action = "建仓"
        else:
            new_weights = _defense_active_weights(records_df.iloc[i - 1], etf_names)
            old_weights = _defense_active_weights(records_df.iloc[i - 2], etf_names)
            action = _format_action(old_weights, new_weights, etf_names)

        # --- NAV（当日实际 NAV） ---
        nav = float(row["nav"]) / first_nav
        prev_nav = float(records_df.iloc[i - 1]["nav"]) / first_nav
        delta_nav = round((nav - prev_nav) / prev_nav * 100, 2) if prev_nav != 0 else None

        rows.append({
            "date": date_str,
            "nav": round(nav, 4),
            "weights": [round(weights.get(n, 0.0), 4) for n in etf_names],
            "cash": round(cash, 4),
            "action": action,
            "delta": delta_nav,
        })

    return rows


def _defense_active_weights(record_row, etf_names):
    """从 record 行的 defense_active 解析等权权重。"""
    active_str = record_row.get("defense_active", "")
    active = [n.strip() for n in active_str.split(";") if n.strip()] if active_str else []
    n_active = len(active)
    return {name: 1.0 / n_active if name in active and n_active > 0 else 0.0 for name in etf_names}


def generate_html(
    strategy_nav: pd.Series,
    etf_navs: dict[str, pd.Series],
    records_df: pd.DataFrame,
    output_path: str,
) -> None:
    """生成 Chart.js HTML 净值对比图（6 线 + 盈亏线 + 悬停浮窗 + 持仓权重表 + 翻页 + 日期搜索）。"""

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

    table_data = _build_table_data(records_df, DEFENSE_NAMES)
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
  td.action-cell {{ text-align: left; white-space: pre-wrap; max-width: 200px; }}
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
        <th>纯防御净值</th>
        <th>沪深300</th><th>创业板</th><th>纳指</th><th>黄金</th><th>国债ETF</th>
        <th>现金</th><th>今日调仓</th><th>Δ%</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>
</div>

<div class="pagination">
  <button id="prevBtn" onclick="changePage(-1)">上一页</button>
  <span class="page-info" id="pageInfo">第 1/{total_pages} 页</span>
  <span style="font-size:13px;color:#666;">到第</span>
  <input type="number" id="pageJumpInput" min="1" max="{total_pages}" value="1"
    style="width:50px;padding:4px 6px;border:1px solid #ccc;border-radius:4px;font-size:13px;text-align:center;">
  <span style="font-size:13px;color:#666;">页</span>
  <button onclick="jumpToPage()">跳转</button>
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
        boxPadding: 4
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
    html += '<td>' + row.nav.toFixed(4) + '</td>';
    for (let j = 0; j < 5; j++) {{
      const w = row.weights[j];
      html += '<td>' + (w > 0 ? (w * 100).toFixed(0) + '%' : '—') + '</td>';
    }}
    html += '<td>' + (row.cash > 0 ? (row.cash * 100).toFixed(0) + '%' : '—') + '</td>';
    html += '<td class="action-cell">' + row.action + '</td>';
    if (row.delta === null) {{
      html += '<td>—</td>';
    }} else if (row.delta >= 0) {{
      html += '<td class="pos">+' + row.delta.toFixed(2) + '%</td>';
    }} else {{
      html += '<td class="neg">' + row.delta.toFixed(2) + '%</td>';
    }}
    html += '</tr>';
  }}
  tbody.innerHTML = html;
  document.getElementById('pageInfo').textContent =
    '第 ' + currentPage + '/' + totalPages + ' 页';
  document.getElementById('prevBtn').disabled = currentPage <= 1;
  document.getElementById('nextBtn').disabled = currentPage >= totalPages;
  document.getElementById('pageJumpInput').value = currentPage;
}}

function changePage(delta) {{
  const newPage = currentPage + delta;
  if (newPage < 1 || newPage > totalPages) return;
  currentPage = newPage;
  renderTable();
  document.getElementById('navTable').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
}}

function jumpToPage() {{
  const input = document.getElementById('pageJumpInput');
  const page = parseInt(input.value);
  if (isNaN(page) || page < 1 || page > totalPages) {{
    input.value = currentPage;
    return;
  }}
  currentPage = page;
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
    result = run_backtest(prices, params=DEFAULT_PARAMS, execution_lag=1)
    records_df = result["records_df"]
    strategy_nav_full = records_df["nav"]

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
    # 包含 2025 末锚点行（T+1 前移需要前一交易日 signal）
    start_dt = pd.Timestamp(START_DATE)
    before = records_df[records_df.index < start_dt]
    if len(before) > 0:
        anchor = before.iloc[-1:]
        records_2026 = pd.concat([anchor, records_df.loc[strategy_nav.index]])
    else:
        records_2026 = records_df.loc[strategy_nav.index]
    generate_html(strategy_nav, aligned_etf_navs, records_2026, output_path)
    print(f"净值对比图已生成：{output_path}")


if __name__ == "__main__":
    main()
