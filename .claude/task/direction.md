# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务：文档双更新 + 日志 + 提交 + 推送 + 图表

### 步骤 1：更新 `.claude/rules/5-infrastructure.md`（保护区）

替换文件内容为：

```markdown
# 基建与环境约束

## 数据库

- 所有表结构变更必须通过 Migration 脚本执行，严禁直接 `ALTER TABLE`。
- 禁止在业务代码中拼接 SQL 字符串。
- [其他数据库约束]

## 数据管线

- 主数据源：AKShare → 东方财富（`ak.fund_etf_hist_em`），数据最全但 WAF 不稳定
- 备用数据源：AKShare → 新浪（`ak.fund_etf_hist_sina`），已跨源验证（2026-05-28，相关性 0.999）
- 失败策略：东方财富重试 3 次（2s→4s→8s 指数退避）→ 自动切换新浪
- 拆分检测：任一源返回后统一走跌幅 >50% 自动前复权修正
- 分时限流：Hook pre_bash.js — 东方财富 `_em` 5min 间隔 / 新浪 `_sina` 3s 间隔

## 第三方服务

- 调用外部 API 必须包裹在 `try-catch` 中。
- 必须统一使用 [指定的请求库/代理模块]。
- [其他第三方约束]

## 环境变量

- 新增环境变量必须同步在 `.env.example` 中记录。
- 禁止在非配置文件中硬编码凭证。
- [其他环境约束]
```

### 步骤 2：更新 `.claude/rules/3-core-mechanism.md`（保护区）

关键文件表新增一行：

```markdown
| `src/data_pipeline.py` | 数据管线（东方财富 + 新浪 fallback） |
```

### 步骤 3：写项目日志

创建 `项目日志/2026-06-16.md`：

```markdown
## 2026-06-16 全天记录

### 1. 多源数据管线 fallback

**现象**：data_pipeline.py 只有东方财富单一源，不可达时重试 3 次后返回空，不会切换备用源。

**背景**：5·27-5·29 已约定多源分级（东方财富主 + 新浪备），Hook 分时限流已就位，但 fetch_etf_daily() 的 fallback 代码从未落地。

**修复**：东方财富 3 次重试失败 → 自动切 `ak.fund_etf_hist_sina()`。新增 `_to_sina_symbol()` 辅助函数，双源共享数据归一化逻辑。

**教训**：协议层设计 ≠ 代码落地。Hook 限流分级配置完整，但业务代码只调了一个源。跨文件设计需逐一验证每个环节。

### 2. 50/50 A/B 公式落地（v188）

（见前次记录——外审发现公式不一致 → 追溯 v184→v186 git log → 确认 v186 从未改 src/ → 公式落地 signal_generator.py:142）
```

### 步骤 4：提交

```bash
git add -A
git commit -m "v189-20260616-1: 修复 — data_pipeline 新增新浪 fallback + 文档双更新

data_pipeline.py: fetch_etf_daily() 东方财富3次重试失败→自动切新浪源。
5-infrastructure.md: 新增数据管线段落（双源+限流+拆分检测）。
3-core-mechanism.md: 关键文件表补 data_pipeline.py。
项目日志: 2026-06-16 全天记录。"
```

### 步骤 5：推送

```bash
git push origin master
```

### 步骤 6：重跑图表

```bash
python scripts/nav_chart.py
```

### 审核协议

3-core-mechanism.md 和 5-infrastructure.md 为保护区文件：
1. 先跑 CLI validate
2. 再跑 CLI audit
3. 写 outcome → 等人批 → gate → 令牌 Edit

### 验收

- [ ] 5-infrastructure.md 含数据管线段落
- [ ] 3-core-mechanism.md 关键文件表含 data_pipeline.py
- [ ] 项目日志已写
- [ ] git commit + push 成功
- [ ] nav_2026.html 已更新
