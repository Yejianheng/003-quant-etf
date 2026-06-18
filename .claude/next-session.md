# 下一会话

> 顾问每次会话结束前更新。新会话顾问读取此文件恢复上下文。

## 当前阶段

策略审计与基准完善。四张表系统已交付（`attribution/`），发现三项缺口。

## 本次结论

1. **策略本质确认**：α≈0，择时系数≈0，偏度≈0。纯风险预算器，不做方向预测。
2. **逆回购不可见**：图表代码已补（repo 背景带+净值线），但 HTML 未重跑。
3. **基准不够**：缺 5 ETF 等权和全期 60/40。全天候未定义。
4. **成本一刀切**：滑点统一 bp，应 per-ETF 按流动性质分档。
5. **2008 测不了**：五只 ETF 最早 2011 年上市，需合成数据。

## 已完成

- [x] 四张表收益归因系统（`attribution/` 目录，7 模块 + 7 测试文件）
- [x] `four_tables_report.html` 首次生成（R²=0.46, α≈0, 偏度≈-0.05, 不卖保险）
- [x] 逆回购可视化代码（`nav_chart.py` + `report.py`）
- [x] `attribution/gap_audit.md` 缺口审计文件

## 待处理

- [ ] 执行窗口完成 `direction.md`（等权+60/40 基准 + per-ETF 价差 + 换手统计）
- [ ] 执行完成后重写 `attribution/gap_audit.md`（关闭已修复缺口）

## 重要上下文

### 四张表关键发现
- 因子归因: R²=0.46, α=0.0002（日频）→ 收益全来自 β
- 择时分解: 月胜率 41.3%, 上涨月跑输 1.26, 下跌月跑赢 0.85 → 纯防守策略
- 尾部审计: 偏度 -0.05 vs 基准 -0.41 → 不卖保险
- 稳定性: 滚动 3y Sharpe min=-0.69, mean=0.71

### 核心文件
- `attribution/gap_audit.md` — 缺口审计（G1-G6）
- `attribution/report.py` — HTML 报表，`generate_four_tables_report()`
- `scripts/four_tables.py` — 入口，`python scripts/four_tables.py`
- `scripts/nav_chart.py` — 2026 图表，`python scripts/nav_chart.py`
- `output/four_tables_report.html` — 最新报表
- `output/nav_2026.html` — 2026 净值图表（待重跑）

### 资产池数据范围
- 510300: 2012-05-28 ~ now
- 159915: 2011-12-09 ~ now
- 513100: 2013-07-31 ~ now
- 518880: 2013-07-29 ~ now
- 511010: 2013-04-09 ~ now
- 共同覆盖: 2013-07-31 起（回测始于 2014-01 考虑 120 天最小历史）
