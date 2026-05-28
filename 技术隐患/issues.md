@claude-override-approved
# 待解决隐患

> 按重要性降序。

| # | 隐患 | 状态 |
|---|------|:--:|
| 1 | Hook 东方财富限流参数过松——`pre_bash.js` 最低间隔 5s，实际 WAF 要求 ≥5min，差距 60 倍，一次密集调用可能封 IP | 已解决 |
| 2 | API 字段探查未做——`fund_etf_category_sina` 返回字段未实测，若不返回基金类型列则粗筛无法进行，需回退到东方财富源 `fund_etf_fund_info_em`（字段全但限流严重），选型决定粗筛效率 | 已解决 |
| 3 | 进攻层候选池强制流动性门槛——行业 ETF 流动性分化大，筛选时须严格执行日均成交额底线，避免低流动性标的进入进攻层导致滑点吃掉 Alpha | 已解决 |
| 4 | fetch_etf_daily 异常静默吞没 | 已解决 |
| 5 | 无日志/可观测性机制 | 已解决 |
| 6 | save_to_parquet 不创建目录 | 已解决 |
| 7 | AKShare fund_etf_hist_em 返回空 | 已解决 |
