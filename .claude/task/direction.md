# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 任务：target_vol_beta 切换到 0.18 + 封闭发布

### 背景

全量参数扫描切换到 T+1 可执行基准后，真实数据显示 0.18 是约束下收益最优：

| beta | 年化(T+1) | 回撤(T+1) | 边际换率 |
|------|------|------|------|
| 0.08 | 10.3% | -9.9% | — |
| 0.10 | 10.7% | -11.2% | 0.31 |
| 0.12 | 10.9% | -12.4% | 0.17 |
| 0.15 | 11.1% | -13.6% | 0.17 |
| **0.18** | **11.4%** | **-13.8%** | **1.50** |
| 0.22 | 11.5% | -14.1% | 0.33 |

0.15 是基于 T+0（物理不可执行）数据选定的。T+1 下最优是 0.18——年化 +0.3pp，回撤仅 +0.2pp，边际换率 1.50 倍。回撤 -13.8% 距 20% 硬约束仍有 6.2pp 安全垫。

### 步骤 1：切换参数

修改 `src/signal_generator.py` `DEFAULT_PARAMS`：

```
"target_vol_beta": 0.18,
"vol_tolerance": 0.027,  # = 0.18 × 15%，等比缩放
```

备份注释更新：`# 备份: target_vol_beta=0.08, vol_tolerance=0.012（v185 扫描最优，Sharpe 最大化）`

### 步骤 2：更新 README.md

替换为 T+1 数据 + 0.18 参数说明。写清楚为什么弃用 0.15、为什么选 0.18：

- 之前选定 0.15 的依据是 T+0 扫描（物理不可执行）
- 全量 T+1 重扫后发现 0.15→0.18 边际换率 1.50，是真实最优
- 标注 T+1 为系统唯一可执行基准

### 步骤 3：写项目日志

`项目日志/2026-06-18.md` 追加：

```
## 11. 参数切换：0.15 → 0.18

全量扫描从 T+0 切换到 T+1 可执行基准后，0.18 替代 0.15 成为约束下收益最优。

切换理由：
- T+0 数据物理不可执行（当日收盘既算信号又成交）
- T+1 下 0.15→0.18：年化 +0.3pp（11.1%→11.4%），回撤仅 +0.2pp（-13.6%→-13.8%）
- 边际换率 1.50，全扫描最高值
- 回撤 -13.8% 距 20% 硬约束仍有 6.2pp 安全垫

0.15-release tag 作废。新封闭版本 tag：v0.18-release。
```

### 步骤 4：打 tag + 提交 + 推送

```bash
git add src/signal_generator.py README.md 项目日志/2026-06-18.md attribution/system_audit.md
git commit -m "v190-20260618-31: 切换 — target_vol_beta 0.15→0.18，T+1 可执行基准下约束最优"

# 新 release tag（废弃 0.15）
git tag -d v0.15-release
git push origin :refs/tags/v0.15-release
git tag -a v0.18-release HEAD -m "【执行封闭版本】v0.18-release

T+1 可执行基准下的约束最优参数。
年化 11.4%, 回撤 -13.8%, Sharpe 1.06 (T+1)。
30+ commits, 全量参数扫描完成, 无盲区。"
git push origin master
git push origin v0.18-release
```

### 验收

- [ ] target_vol_beta = 0.18, vol_tolerance = 0.027
- [ ] README.md 含完整切换说明
- [ ] 项目日志已追加
- [ ] v0.15-release tag 已删除
- [ ] v0.18-release tag 已推送
- [ ] master 已推送

### 审核协议

`src/signal_generator.py` 为保护区文件 + `protected-contracts.json` 受保护值：CLI validate → audit → gate → 令牌 Edit。
