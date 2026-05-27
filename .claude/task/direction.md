# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。每步完成后顾问审核提交后方可进行下一步。

## 总体规划（10 步）

```
Step 1  数据管线      AKShare → Parquet                ✅ 已完成
Step 2  趋势强度      年化收益率 / 年化波动率            ✅ 已完成
Step 3  截面动量      20+60 日 z-score 合成排名          ✅ 已完成
Step 4  目标波动率    EWMA 协方差矩阵 + 容忍带            ✅ 已完成
Step 5  相关性熔断    股债 60 日相关性 5 日 SMA            ✅ 已完成
Step 6  回撤硬止损    8/12/18 三层                        ✅ 已完成
Step 7  信号生成器    编排 Step 2-6                        ✅ 已完成
Step 8  组合管理器    仓位计算 + 资金路由                  ← 当前
Step 9  Recorder      日志记录 + 基准计算
Step 10 回测主循环    日循环 + 参数扫描入口
```

## 当前步骤：Step 8 — 组合管理器

### 背景

组合管理器是信号→仓位的转换层。接收 Step 7 的 Signal dict 和总资金，输出每只标的的精确持仓金额和资金路由路径。

```
Signal dict + total_capital
    │
    ├─ 回撤止损乘数 → 缩减总风险敞口
    ├─ 相关性熔断 → 全部资金进逆回购
    ├─ 防御层权重 × 70% × 总资金 × final_multiplier
    ├─ 进攻层权重 × 30% × 总资金 × final_multiplier
    └─ 进攻层空仓 → 30% 进逆回购（不回流防御层！）
    │
输出：{"positions": {...}, "repo_amount": ..., "cash": ...}
```

### 关键约束

**进攻层空仓时，30% 资金进逆回购，不回流防御层。** 这是系统最珍贵的职责分离结构——Beta 70% / Alpha 30% 的风险预算不可污染。如果回流，Beta 变成 100%，双引擎重新耦合，防御层的风险预算完全失效。

### 任务

`src/portfolio_manager.py` — 一个函数：

```python
allocate_capital(
    signal: dict,
    total_capital: float,
    defense_ratio: float = 0.70,
) -> dict
"""
根据信号分配资金。

signal: Step 7 generate_signal 的输出。
total_capital: 组合总资金（元）。
defense_ratio: 防御层资金比例，默认 0.70（进攻层 = 1 - defense_ratio = 0.30）。

返回: {
    "date": str,
    "total_capital": float,           # 输入总资金
    "positions": {name: float},       # 每只标的持仓金额（元）
    "defense_total": float,           # 防御层总金额
    "offense_total": float,           # 进攻层总金额
    "repo_amount": float,             # 逆回购金额
    "exposure": float,                # 总风险敞口（非逆回购部分）
    "exposure_ratio": float,          # 风险敞口 / 总资金
}

计算逻辑：
1. 基础资金池：
   defense_pool = total_capital * defense_ratio
   offense_pool = total_capital * (1 - defense_ratio)

2. 回撤止损覆盖：
   defense_pool *= signal["drawdown_stop"]["position_multiplier"]
   offense_pool *= signal["drawdown_stop"]["position_multiplier"]
   （multiplier=0.5 时两池各减半，multiplier=0 时全清）

3. 相关性熔断检查：
   if signal["circuit_breaker"]["triggered"]:
       → 全部资金进逆回购
       → positions = {}, repo = total_capital
       → 跳过步骤 4-5

4. 防御层分配：
   for name, weight in signal["defense"]["target_weights"]:
       positions[name] = defense_pool * weight

5. 进攻层分配：
   if signal["offense"]["target_weights"] 非空:
       for name, weight in signal["offense"]["target_weights"]:
           positions[name] = offense_pool * weight
   else:
       → repo_amount += offense_pool  （不回流防御层！）

6. 汇总：
   repo_amount += total_capital - sum(positions) - 已计入的 repo
   （剩余零钱也进逆回购）
   exposure = sum(positions.values())
   exposure_ratio = exposure / total_capital
"""
```

### 测试（先写，必须红灯）

`tests/test_portfolio_manager.py` — 5 个场景：

1. **全绿正常分配**：构造全绿 signal（5 标的 active，无熔断，normal 止损）。total_capital=1,000,000。验证 defense_total=700,000，offense 空 → repo=300,000，exposure_ratio=0.70。

2. **进攻层持仓**：signal 含进攻层 3 标的 target_weights。验证 offense_total=300,000，3 标的等权分配（各 100,000），defense_total=700,000。

3. **熔断全进逆回购**：signal 熔断触发。验证 positions 为空，repo_amount=1,000,000，exposure=0。

4. **回撤减半**：signal drawdown_stop level="halve", multiplier=0.5。验证 defense_total=350,000（700k×0.5），offense 空 → repo=650,000（300k + 350k 被砍部分）。

5. **进攻层空仓不回流**：signal defense.active 含 5 标的但 offense.target_weights 为空。验证 offense_pool=300,000 全部进 repo，defense_total 仍为 700,000（非 1,000,000）。这是本模块最关键的测试。

### 约束

- 不写 Recorder、回测主循环等后续模块代码
- 资金计算使用浮点数，不处理整数股数（Step 10 回测主循环中再处理取整）
- 权重字典的 value 之和可能不为 1（如趋势过滤后只剩部分标的），直接用给定权重不做内部归一化（权重归一化由 signal_generator 保证）
- `defense_ratio` 默认 0.70

### 验收标准

- [ ] `python -m pytest tests/test_portfolio_manager.py -v` — 5/5 绿
- [ ] `python -m pytest tests/test_signal_generator.py -v` — 旧测试不红
- [ ] `python -c "from src.portfolio_manager import allocate_capital; print('OK')"` — 无报错

---

> 完成本步后：写 outcome.md → 提示"请顾问窗口审查 Step 8"。
> 顾问审核通过并 commit 后，更新本文 Step 9。
> 禁止跳过步骤，禁止一次完成多步。
