# 003-quant-etf

ETF 多资产动量轮动量化系统。AI 辅助纪律执行和标的筛选，不追求全自动交易。

## 策略概要

**双引擎结构**：防御层（70% 资金，多资产趋势跟踪 + 目标波动率控制）+ 进攻层（30% 资金，行业截面动量排名）。

完整策略规格见 [方向性讨论.md](方向性讨论.md)。

## 架构

```
src/
├── config.py                       # 配置入口
├── data_pipeline.py                # Step 1  AKShare → Parquet
├── etf_universe.py                 # Step 1  防御层 ETF 代码映射
├── trend_strength.py               # Step 2  年化收益率 / 年化波动率
├── logging_config.py               # Step 2  统一日志
├── cross_sectional_momentum.py     # Step 3  20+60 日 z-score 截面排名
├── target_volatility.py            # Step 4  EWMA 协方差 + 容忍带
├── correlation_circuit_breaker.py  # Step 5  股债相关 + SMA 熔断
├── drawdown_stop.py                # Step 6  8/12/18 三层回撤止损
├── signal_generator.py             # Step 7  编排 Step 2-6
├── portfolio_manager.py            # Step 8  仓位计算 + 资金路由
├── recorder.py                     # Step 9  日记录器
├── benchmark.py                    # Step 9  基准计算
└── backtest_engine.py              # Step 10 回测主循环 + 参数扫描
```

## 快速开始

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## 运行回测

```python
from src.backtest_engine import run_backtest
from src.data_pipeline import fetch_etf_daily

# 拉取数据
prices = {name: fetch_etf_daily(code, "2020-01-01", "2025-12-31")
          for name, code in [("沪深300", "510300"), ...]}

# 运行回测
result = run_backtest(prices, initial_capital=1_000_000)
print(f"年化收益: {result['annual_return']:.2%}")
print(f"夏普比率: {result['sharpe_ratio']:.2f}")
print(f"最大回撤: {result['max_drawdown']:.2%}")
```

## 技术栈

Python 3.12 / AKShare / pandas / numpy / scipy / pytest

## 测试状态

61 passed / 1 failed (AKShare 外部依赖) / 1 skipped

## 版本

### v1.0.0 — 回测引擎端到端可运行（2026-05-27）

- 10 步回测开发计划全部完成
- 五模块决策链：趋势强度 → 截面动量 → 目标波动率 → 相关性熔断 → 回撤止损
- 日循环回测引擎 + 参数扫描入口
- 架构防火墙三层 Hook 就位
- 13 源文件，12 测试文件，~777 行业务代码

### v1-20260527：项目初始化

- 基础文件骨架 + 依赖清单
- 策略方向性讨论完成，架构冻结
- 三角色模型分配就位
