# 执行指令

> 2026-07-28 | 必读条目 + 提交 + 清理

## 步骤 1 — 添加必读到 core-mechanism

`.claude/rules/3-core-mechanism.md` 末尾追加：

```markdown
---

## 常见陷阱：final_multiplier 在全空仓时的语义

**规则**：当 `defense_active=[]`（趋势过滤剔除全部 ETF）时，`final_multiplier` 默认 = 1.0。这个 1.0 的含义是"100% 资金已路由到 repo"，**不是**"100% 买了 ETF"。

**陷阱**：任何用 `1.0 - final_multiplier` 反推现金比例的代码，在全空仓时会得到 0%（错误）。

**正确做法**：
- 显示现金比例 → 用 `1.0 - sum(weights.values())`
- 判断是否空仓 → 用 `defense_count == 0` 或 `sum(weights) == 0`
- 策略计算中 `final_multiplier * weights` 不受影响（weights 全 0 时乘积正确）

**历史**：v214 全面核查发现 nav_chart.py 全现金期间 cash 列显示 0%（#2026-07-28 日志）。
```

> 该文件在保护区，修改前需走 validate→audit 流程。

## 步骤 2 — 提交

```bash
git add scripts/nav_chart.py .claude/task/outcome.md .claude/task/recommendation.md .claude/task/direction.md .claude/next-session.md 项目日志/2026-07-28.md
# 如果步骤1完成了才加 rules 文件：
# git add .claude/rules/3-core-mechanism.md
git commit -m "v214-20260728-1: 修复图表全现金时段cash列显示0%→100%，根因为final_multiplier全空仓语义陷阱"
```

## 步骤 3 — 清理

确认 `git status --porcelain` 无残留。

## 约束

- 步骤 1 的 3-core-mechanism.md 是保护区文件，必须 validate→audit 通过才能改
- 如果 audit 受阻，先跳过步骤 1，完成步骤 2-3，outcome 里记录阻塞
