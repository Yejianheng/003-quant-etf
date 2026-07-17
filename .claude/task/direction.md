# 执行指令

> 2026-07-17 | 操作列加入现金，完整展示资金流向

## 背景

操作列只显示 ETF 变化，但 combined_mult 加仓时现金同步减少，反之亦然。用户看不到资金从哪来/到哪去。

把现金作为第六个品种传入 `_format_action`，卖出/买入现金自动出现在操作文本中。

## 步骤 1 — `scripts/nav_chart.py` `_build_table_data`

在操作列计算区域（L316-335），old_weights 和 new_weights 都加入现金键：

```python
# old_weights 加入现金
old_weights = weights.copy()
old_cash = round(1.0 - sum(weights.values()), 4)
old_weights["现金"] = max(0.0, old_cash)

# new_weights 加入现金
n_today_active = len(today_active)
new_weights = {}
for name in etf_names:
    if cb_triggered or defense_count == 0:
        new_weights[name] = 0.0
    else:
        new_weights[name] = today_final_mult / n_today_active if name in today_active and n_today_active > 0 else 0.0
new_cash = round(1.0 - sum(new_weights.values()), 4)
new_weights["现金"] = max(0.0, new_cash)

action = _format_action(old_weights, new_weights, etf_names + ["现金"])
```

> `etf_names` 是 `["沪深300", "创业板", "纳指", "黄金", "国债ETF"]`，加上 `"现金"` 共 6 个。

## 步骤 2 — 验证

```bash
python scripts/nav_chart.py
```

预期：
| 日期 | 操作列 |
|------|--------|
| 7/13 | 卖出 现金(17.1%→16.1%)，买入 纳指(82.9%→83.9%) |
| 7/16 | 卖出 现金(14.2%→13.5%)，买入 纳指(85.8%→86.5%) |
| 7/10 | 卖出 创业板(38.9%→0.0%)、现金(22.3%→17.1%)，买入 纳指(38.9%→82.9%) |
