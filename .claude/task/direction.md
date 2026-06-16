# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务：项目日志 + 提交 + 推送 + Release + README

### 背景

v186→v188 完整链路收束：
- v184：发现 sf 空转（79%交易日未生效）
- v185：修复 sf 生效，target_vol_beta 0.10→0.08
- v186：决策 50/50 A/B 组合，但代码未落地（仅文档+图表）
- 外审：发现公式不一致
- v188：50/50 公式落地 signal_generator.py + nav_chart.py 修正 + golden 重生成

### 步骤 1：写项目日志

创建 `项目日志/2026-06-16.md`，内容：

```markdown
## 2026-06-16 全天记录

### 1. 跨模型审计

外审提示（Qwen3-Max）：`signal_generator.py:141` 的 `final_multiplier = min(sf, dd_mult)` 与文档 3-core-mechanism.md 声称的 `(dd_mult + min(sf, dd_mult)) / 2` 不一致。

### 2. 公式验证

`tests/test_verify_50_50_formula.py` monkey-patch 对比：

| 指标 | 纯B（当前代码） | 50/50（文档） | Δ |
|------|:---------:|:---------:|:---------:|
| Sharpe | 1.205 | 1.113 | -0.092 |
| 总收益 | 177.8% | 223.7% | +46.0pp |
| 最大回撤 | -7.45% | -9.93% | -2.48pp |

50/50 年化 +1.41pp，回撤 -2.48pp。用额外回撤换取更高绝对收益。

### 3. 前因后果排查

`git log` 追溯 v184→v186：
- v185：signal_generator.py 落地 `final_multiplier = min(sf, dd_mult)`（纯B）
- v186：改 README + nav_chart.py + 3-core-mechanism.md，但 `git diff v185..v186 -- src/` 为空
- v186 commit message 写的是 50/50，代码从未改过
- nav_chart.py 的 50/50 线是外部手动平均（`0.5 * nav_a + 0.5 * nav_b`），不是生产逻辑

v186决策确定选50/50，项目日志#5记录了完整对比表（0/100→50/50→100/0），但公式从未写进 signal_generator.py。

### 4. 代码落地

- `signal_generator.py:142`：`min(sf, dd_mult)` → `(dd_mult + min(sf, dd_mult)) / 2`
- `.claude/rules/3-core-mechanism.md`：绩效数据同步 50/50 实测值
- `scripts/nav_chart.py`：去手动平均、去 A/B 参考线，只留 50/50 生产策略
- `output/golden_*.csv`：重生成（公式变更后必然偏移）
- `跨模型审计/公式验证报告.md`：完整验证记录+决策

### 5. 验证

- 全量 pytest：334 passed, 2 failed（既有）
- `nav_2026.html`：1 策略线 + 5 ETF，真实生产数据

### 教训

- commit message ≠ 代码变更，`git diff` 是唯一事实源
- 审计模型（异构）交叉验证有效：发现了人+主模型都忽略的不一致
- 等效单策略公式数学上严格等价于跑两个账户，不需要分别维护
```

### 步骤 2：Git 提交

```bash
git add -A
git commit -m "v188-20260616: 修复 — 50/50 A/B 公式落地（v186决策，代码遗漏4版本）

v186决策选50/50组合但公式从未写入src/，持续纯B运行4个版本。
外审模型发现公式与文档不一致，追溯git log确认v185→v186 src/零改动。

变更：
- signal_generator.py:142 纯B→50/50公式（保护区，audit通过）
- nav_chart.py 去手动平均+去A/B参考线，只留生产策略
- 3-core-mechanism.md 绩效同步50/50实测值
- golden dataset重生成
- 新增 test_verify_50_50_formula.py 验证脚本

绩效（2014-2026 T+1）：
- Sharpe 1.113，年化 10.35%，回撤 -9.93%
- vs纯B：年化+1.41pp，回撤-2.48pp，Sharpe-0.092
- 策略选择：用额外回撤换更高绝对收益"
```

### 步骤 3：推送

```bash
git push origin master
```

### 步骤 4：创建 Release

```bash
gh release create v188-20260616 \
  --title "v188 — 50/50 A/B 公式落地" \
  --notes "## v188-20260616：50/50 A/B 公式落地

### 问题起源
v186 (2026-06-12) 决策确立 50/50 A/B 组合策略（50%无sf满仓 + 50%sf缩仓），但公式仅写入文档和图表，src/signal_generator.py 始终是纯B公式。
外部模型审计（Qwen3-Max）发现该不一致。

### 修复内容
- **signal_generator.py**: \`final_multiplier = min(sf, dd_mult)\` → \`(dd_mult + min(sf, dd_mult)) / 2\`
- **nav_chart.py**: 去手动平均，生产策略线直出
- **3-core-mechanism.md**: 绩效数据同步
- **golden dataset**: 重生成
- **新增验证**: \`test_verify_50_50_formula.py\`

### 策略绩效（2014-2026，T+1）

| 指标 | v188 50/50 | 旧纯B | Δ |
|------|:---:|:---:|:---:|
| Sharpe | 1.113 | 1.205 | -0.092 |
| 年化收益 | 10.35% | 8.94% | +1.41pp |
| 最大回撤 | -9.93% | -7.45% | -2.48pp |
| 总收益 | 223.7% | 177.8% | +46.0pp |

**策略选择：用额外回撤换取更高绝对收益。** 低波动时满仓享受beta，高波动时半仓保护。

### 同期基准

| 指标 | 策略 | 沪深300 | 创业板 | 纳指 |
|------|:---:|:-----:|:-----:|:---:|
| Sharpe | 1.113 | 0.16 | 0.30 | 0.78 |
| 年化 | 10.35% | 2.1% | 6.7% | 10.0% |
| 回撤 | -9.93% | -46.7% | -71.5% | -35.6% |

### v186→v188 完整链路

v184(发现sf空转) → v185(sf生效+参数优化) → v186(50/50决策，代码未落地) → 外审(发现公式不一致) → v188(代码落地+图表修正)
"
```

### 步骤 5：更新 README.md

README 中 v188 部分：

```markdown
## v188 — 50/50 A/B 策略落地（2026-06-16）

### 策略机制

50/50 A/B 组合：A端满仓（不受波动率缩放）+ B端缩仓（sf+0.08），等效单策略乘数：

```
final_multiplier = (dd_mult + min(sf, dd_mult)) / 2
```

- 低波动（sf ≥ dd_mult）：= dd_mult，满仓运行
- 高波动（sf < dd_mult）：= (dd_mult + sf) / 2，半保护

### 六步决策链

1. 趋势过滤（trend_strength > 0）→ active ETF 池
2. 等权分配
3. EWMA 波动率缩放（target_vol_beta=0.08）
4. 股债相关性熔断（corr_threshold=0.0，>0全线清仓）
5. 回撤硬止损（三级：8%/12%/18%）
6. 资金路由（50/50乘数 × 等权权重）

### 策略选择理由

纯B Sharpe 1.205 更高但牛市被sf拖累收益。50/50在低波动时不受sf限制（等于纯A满仓），高波动时获得一半保护。不是数学最优，是实用最优。
```

### 验收

- [ ] 项目日志已写
- [ ] git commit 已创建
- [ ] git push 成功
- [ ] Release 已创建（输出 URL）
- [ ] README 已更新
