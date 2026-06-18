# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务：系统审计文件入必读 + 封存发布

### 背景

`attribution/system_audit.md` 是策略系统的完整技术文档，覆盖规则、决策链、绩效、仓位轨迹、压力测试、参数敏感度、成本、熔断鲁棒性、宏观经济分解。需设为新窗口必读文件。

### 步骤 1：CLAUDE.md 增加必读引用

修改 `CLAUDE.md`，在 "AI 核心指令" 段落中添加 `attribution/system_audit.md`：

```markdown
> **AI 核心指令**：任何新会话启动时，必须优先完整阅读本文件、`方向性讨论.md`、`attribution/system_audit.md` 及 `.claude/rules/` 下所有规则文件（按编号顺序加载）。本文件拥有最高解释权。
```

### 步骤 2：打 release tag

当前 HEAD 为 0.15 生产版本，含完整的四张表/缺口审计/系统审计/熔断扫描/宏观分解。打 tag：

```bash
git tag -a v0.15-release f8abc9e~1..HEAD -m "
【执行封闭版本】v0.15-release — 2026-06-18

策略配置：
  target_vol_beta=0.15（约束下收益最优），vol_tolerance=0.0225
  50/50 A/B 公式，defense_ratio=1.00
  备份参数: target_vol_beta=0.08（v0.08-canonical tag，Sharpe 最大化）

绩效 (2014-2026, T+1):
  年化 13.1%, 回撤 -13.1%, Sharpe 1.23

交付物：
  attribution/system_audit.md — 系统审计（规则/决策链/绩效/仓位轨迹/压力/敏感度/熔断鲁棒性/宏观分解）
  attribution/gap_audit.md — 缺口审计（7项关闭5项）
  attribution/ — 四张表收益归因系统（7模块+7测试）
  scripts/four_tables.py — 全量审计入口
  scripts/nav_chart.py — 2026净值可视化（等权/60/40/repo/换手/成本）
  scripts/corr_robustness_scan.py — 熔断三维扫描
  scripts/macro_corr_decomposition.py — 股债相关性宏观分解
  项目日志/2026-06-18.md — 全天记录

封存说明：
  本版本为执行封闭版本。策略逻辑完整，所有核心参数经过扫描验证。
  后续改动应基于本版本的审计文件（system_audit.md）作为事实源。
"
```

注意：tag 命令如果范围语法不支持，直接 `git tag -a v0.15-release HEAD -m "..."`。

### 步骤 3：推送

```bash
git push origin master
git push origin v0.15-release
```

### 验收

- [ ] CLAUDE.md 含 `attribution/system_audit.md` 引用
- [ ] `v0.15-release` tag 存在且已推送
- [ ] master 已推送
- [ ] `git tag -l` 可见 `v0.08-canonical` + `v0.15-release` 两个 tag
- [ ] 工作区干净
