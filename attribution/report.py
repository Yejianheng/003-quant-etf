# [2026-06-18] 新增：四张表 HTML 报表生成
import os
import numpy as np


def generate_four_tables_report(results: dict, output_path: str) -> str:
    """
    生成自包含 HTML 报表，内含四张表 + 简要解读。

    results: {"factor_return": {...}, "timing": {...}, "tail_risk": {...}, "stability": {...}}
    """
    fa = results.get("factor_return", {})
    td = results.get("timing", {})
    tr = results.get("tail_risk", {})
    sm = results.get("stability", {})

    html = _build_html(fa, td, tr, sm)

    d = os.path.dirname(output_path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def _fmt(v, decimals=4):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.{decimals}f}"
    return str(v)


def _build_html(fa, td, tr, sm):
    def _table1():
        rows = ""
        betas = fa.get("betas", {})
        ses = fa.get("betas_se", {})
        tvals = fa.get("t_values", {})
        for name in betas:
            rows += f"<tr><td>{name}</td><td>{_fmt(betas.get(name))}</td>"
            rows += f"<td>{_fmt(ses.get(name))}</td><td>{_fmt(tvals.get(name))}</td></tr>"

        alpha = _fmt(fa.get("alpha"))
        r2 = _fmt(fa.get("r_squared"))
        adj_r2 = _fmt(fa.get("adj_r_squared"))
        n = fa.get("n_obs", 0)

        return f"""
        <h3>表 1 — 因子归因</h3>
        <table><thead><tr><th>因子</th><th>β</th><th>SE</th><th>t</th></tr></thead><tbody>
        {rows}<tr class="sep"><td><strong>α (截距)</strong></td><td>{alpha}</td>
        <td>{_fmt(ses.get("alpha"))}</td><td>—</td></tr>
        </tbody></table>
        <p>R² = {r2} | 调整 R² = {adj_r2} | N = {n}</p>
        <p class="verdict">{_factor_verdict(fa)}</p>
        """

    def _table2():
        up = _fmt(td.get("up_month_excess"))
        down = _fmt(td.get("down_month_excess"))
        total = _fmt(td.get("total_excess_return"))
        wr = _fmt(td.get("monthly_win_rate"), 3)
        tc = _fmt(td.get("timing_coefficient"), 6)
        up_n = td.get("up_months_count", 0)
        down_n = td.get("down_months_count", 0)

        return f"""
        <h3>表 2 — 择时分解</h3>
        <table><thead><tr><th>指标</th><th>值</th></tr></thead><tbody>
        <tr><td>择时系数</td><td>{tc}</td></tr>
        <tr><td>上涨月超额（多赚）</td><td>{up}（{up_n} 个月）</td></tr>
        <tr><td>下跌月超额（少亏）</td><td>{down}（{down_n} 个月）</td></tr>
        <tr><td>月超额合计</td><td>{total}</td></tr>
        <tr><td>月胜率</td><td>{wr}</td></tr>
        </tbody></table>
        <p class="verdict">{_timing_verdict(td)}</p>
        """

    def _table3():
        skew = _fmt(tr.get("skewness"), 3)
        dd = _fmt(tr.get("max_drawdown"), 3)
        dur = tr.get("max_dd_duration_days", 0)
        warn = "⚠ 是" if tr.get("insurance_sell_warning") else "否"
        b_skew = _fmt(tr.get("benchmark_skewness"), 3)

        worst_rows = ""
        for w in tr.get("worst_5_months", []):
            worst_rows += f"<tr><td>{w.get('date','')}</td><td>{_fmt(w.get('return'),3)}</td></tr>"

        return f"""
        <h3>表 3 — 尾部审计</h3>
        <table><thead><tr><th>指标</th><th>策略</th><th>基准</th></tr></thead><tbody>
        <tr><td>偏度</td><td>{skew}</td><td>{b_skew}</td></tr>
        <tr><td>最大回撤</td><td>{dd}</td><td>—</td></tr>
        <tr><td>最大回撤持续（天）</td><td>{dur}</td><td>{tr.get("benchmark_max_dd_duration", 0)}</td></tr>
        <tr><td>卖保险警告</td><td colspan="2">{warn}</td></tr>
        </tbody></table>
        <h4>最差 5 个月</h4>
        <table><thead><tr><th>月份</th><th>收益</th></tr></thead><tbody>{worst_rows}</tbody></table>
        <p class="verdict">{_tail_verdict(tr)}</p>
        """

    def _table4():
        sens_rows = ""
        for s in sm.get("parameter_sensitivity", []):
            sens_rows += f"<tr><td>{s['param']}</td><td>{_fmt(s['delta_sharpe'])}</td>"
            sens_rows += f"<td>{_fmt(s['baseline_sharpe'])}</td></tr>"

        rs = sm.get("rolling_sharpe", {})
        rs_min = _fmt(rs.get("min"))
        rs_mean = _fmt(rs.get("mean"))
        rs_max = _fmt(rs.get("max"))
        min_period = rs.get("min_3yr_period", "") or ""

        ep_rows = ""
        for label, p in sm.get("extreme_periods", {}).items():
            ep_rows += f"<tr><td>{label}</td><td>{_fmt(p.get('total_return'),3)}</td>"
            ep_rows += f"<td>{_fmt(p.get('max_drawdown'),3)}</td><td>{p.get('n_days',0)} 天</td></tr>"

        return f"""
        <h3>表 4 — 稳定性矩阵</h3>
        <h4>参数敏感度</h4>
        <table><thead><tr><th>参数</th><th>ΔSharpe</th><th>基准 Sharpe</th></tr></thead>
        <tbody>{sens_rows}</tbody></table>
        <h4>滚动 3 年 Sharpe</h4>
        <table><thead><tr><th>最低</th><th>均值</th><th>最高</th><th>最差区间</th></tr></thead><tbody>
        <tr><td>{rs_min}</td><td>{rs_mean}</td><td>{rs_max}</td><td>{min_period}</td></tr>
        </tbody></table>
        <h4>极端行情</h4>
        <table><thead><tr><th>区间</th><th>总收益</th><th>最大回撤</th><th>天数</th></tr></thead>
        <tbody>{ep_rows}</tbody></table>
        """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>策略收益归因 — 四张表审计</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:960px;
margin:0 auto;padding:20px;background:#f8f9fa;color:#212529}}
h1{{text-align:center;color:#1a1a2e}}
h3{{margin-top:32px;border-bottom:2px solid #dee2e6;padding-bottom:8px;color:#1a1a2e}}
h4{{margin-top:16px;color:#495057}}
table{{width:100%;border-collapse:collapse;margin:8px 0 16px;background:#fff;
box-shadow:0 1px 3px rgba(0,0,0,.08)}}
th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid #e9ecef}}
th{{background:#f1f3f5;font-weight:600}}
tr.sep td{{border-top:2px solid #adb5bd}}
tr:hover{{background:#f8f9fa}}
.verdict{{padding:8px 16px;border-left:4px solid #228be6;background:#e7f5ff;
border-radius:4px;font-size:14px;line-height:1.6}}
</style>
</head>
<body>
<h1>策略收益归因 — 四张表审计</h1>
{_table1()}
{_table2()}
{_table3()}
{_table4()}
</body>
</html>"""


def _factor_verdict(fa):
    alpha = fa.get("alpha", np.nan)
    adj_r2 = fa.get("adj_r_squared", np.nan)
    a = ""
    if not np.isnan(alpha) and abs(alpha) < 0.0005:
        a = "α ≈ 0，收益全来源于因子暴露（β），无独立 alpha。"
    elif not np.isnan(alpha) and alpha > 0:
        a = "α > 0，存在超出因子补偿的剩余收益，需进一步排查来源。"
    r2 = f" 调整 R² = {adj_r2:.4f}。" if not np.isnan(adj_r2) else ""
    return a + r2


def _timing_verdict(td):
    tc = td.get("timing_coefficient", np.nan)
    if np.isnan(tc):
        return ""
    if tc > 0.0001:
        return f"择时系数 = {tc:.6f} > 0，仓位变动与未来收益正相关，择时有效。"
    elif tc < -0.0001:
        return f"择时系数 = {tc:.6f} < 0，仓位变动与未来收益负相关，择时反向。"
    else:
        return f"择时系数 ≈ 0，仓位变动与未来收益无相关性。"


def _tail_verdict(tr):
    skew = tr.get("skewness", np.nan)
    warn = tr.get("insurance_sell_warning", False)
    if warn:
        return f"偏度 = {skew:.3f}，负偏 + 高胜率 → 存在卖保险特征（小赚大赔）。"
    elif not np.isnan(skew) and skew > 0.1:
        return f"偏度 = {skew:.3f}，正偏 → 尾部保护有效。"
    elif not np.isnan(skew) and skew < -0.1:
        return f"偏度 = {skew:.3f}，负偏 → 注意极端负收益风险。"
    else:
        return "偏度 ≈ 0，收益分布近似对称。"
