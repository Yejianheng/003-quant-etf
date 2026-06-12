# [2026-06-12] 新增：sf 修复后的理论地板重算
"""计算策略理论地板（最坏年化 Sharpe）—— 不含 sf vs 含 sf。

方法：
1. 复现原版地板推导（涨跌停 + T+1 + 18%止损 → -25%/年, Sharpe -2.5）
2. 叠加 sf 约束，重新计算最坏年收益
3. 用实际 14 年回测数据做滚动 12 月最差值做交叉验证
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from src.portfolio_manager import allocate_capital as _original_allocate
from src.backtest_engine import run_backtest

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ETF_CODE_MAP = {
    "沪深300": "510300", "创业板": "159915", "纳指": "513100",
    "黄金": "518880", "国债ETF": "511010",
}

# ============================================================
# Part 1: 理论推导 —— 原版地板 -2.5
# ============================================================

def derive_original_floor():
    """复现原版地板推导每一步。"""
    print("=" * 70)
    print("Part 1: 原版地板推导（不含 sf）")
    print("=" * 70)

    # 1. 单日最坏组合收益
    # 5 ETF 等权, 涨跌停: 510300/513100/518880/511010=10%, 159915=20%
    worst_daily = 0.2 * (-0.10) * 4 + 0.2 * (-0.20)
    print(f"\n1. 单日最坏组合收益（5 ETF 等权，全部跌停）:")
    print(f"   = 0.2×(-10%)×4 + 0.2×(-20%) = {worst_daily*100:.0f}%")

    # 2. T+1 延迟 → 第一日按昨日信号执行，无预警
    print(f"\n2. T+1 执行延迟：第一日无预警，满仓吃满 {worst_daily*100:.0f}%")

    # 3. 回撤止损三级
    print(f"\n3. 回撤止损: <8%=1.0x, 8-12%=1.0x, 12-18%=0.5x, ≥18%=0.0x")
    print(f"   第一日 -12% → 直接进入 halve (12-18%)")

    # 4. 最坏年模型：多次假突破 → 反复入场亏损
    print(f"\n4. 最坏年模型：趋势假突破 → 入场 → 止损 → 恢复 → 再次假突破")
    print(f"   每次 cycle: 趋势误判入场(1.0x) → 跌 3-5% → 趋势翻转出场")
    print(f"   每次损失: ~3-5% NAV")
    print(f"   若 5-8 次/年: 累积 -20% ~ -30%")

    # 5. 封顶机制
    print(f"\n5. 三重封顶:")
    print(f"   - 涨跌停: 单日 ≤ 12%")
    print(f"   - 回撤止损: DD≥18% 清盘")
    print(f"   - T+1 + 趋势延迟: 趋势需 ~40 天确认转向，不会一日清盘")
    print(f"   结论: 最坏年化收益 ≈ -25%, 年化波动 ≈ 10%, Sharpe ≈ -2.5")

    return worst_daily


# ============================================================
# Part 2: 叠加 sf 后的理论地板
# ============================================================

def derive_sf_floor(worst_daily):
    """叠加 sf 约束，重算地板。"""
    print("\n" + "=" * 70)
    print("Part 2: sf 生效后的地板推导")
    print("=" * 70)

    # sf = 0.10 / predicted_vol
    # final_multiplier = min(sf, dd_mult)
    # sf < 1 时缩仓，sf ≥ 1 时被 dd_mult 截断（不加仓）

    print("\n--- 场景分析：什么年最坏？ ---")
    print("sf 缩仓 = 高波动时降低敞口。地板最坏年 = sf 帮不上忙的年。")
    print("即：波动率始终中等偏低，sf ≈ 1.0，但反复假突破亏钱。")
    print()

    # 关键问题：波动率低 + 趋势反复假突破，是否矛盾？
    # trend_strength = ann_return / ann_vol
    # 趋势假突破 = ann_return 短暂 > 0（反弹），然后恢复下跌
    # 反弹产生波动 → 如果有足够多的假突破来亏损 25%，波动率会不会被迫升高？

    print("--- 假突破的波动率代价 ---")
    # 一次假突破: 价格涨 d%（触发入场），然后跌 d'%（触发出场）
    # 这个 V 形走势产生的波动率:
    #   假设 d=3%, d'=5%, 跨度 20 天
    #   日收益: +0.15%, +0.15%, ..., -0.25%, -0.25%, ...
    #   日 std ≈ 0.2% → 年化 ≈ 3.2%
    #   sf = 0.10 / 0.032 > 1.0 → 被截断 → 无保护

    # 但 5-8 次假突破意味着多次 V 形 → 累计波动率更高
    # 8 次 × 20 天 V 形 = 160 天波动 → 年化 vol 可能 5-8%

    n_cycles = [3, 5, 8, 12]  # 每年假突破次数
    loss_per_cycle = 0.04  # 每次损失 4% NAV

    print(f"\n假突破场景（每次损失 {loss_per_cycle*100:.0f}%）:")
    print(f"{'次数':<6} {'年损失':<10} {'估算年化vol':<14} {'sf值':<10} {'sf后损失':<10}")
    print("-" * 55)

    for n in n_cycles:
        annual_loss = 1 - (1 - loss_per_cycle) ** n
        # 每次 V 形：涨 3%、跌 4.17%（回到原点再跌 4%）
        # 20 天 V 形: 日收益 std ≈ (3+4.17)/20/2 ≈ 0.18%
        # n 次 V 形: 有效波动天数 ≈ n×20, 日 std ≈ 0.18%
        # 年化 vol ≈ 0.0018 × sqrt(252) ≈ 2.86%
        # 但波动叠加: n 次 V 形 → 日 std ≈ sqrt(n×20/252) × 单次日 std
        vol_daily = 0.0025  # 单次日 std（含 V 形波动）
        effective_days = n * 15  # 每次 V 形约 15 个有效波动日
        ann_vol = vol_daily * np.sqrt(min(effective_days, 252))

        if ann_vol > 0:
            sf_val = min(0.10 / ann_vol, 1.0)  # capped at 1.0
        else:
            sf_val = 1.0

        # sf 后的有效损失: 每次 V 形中，上涨阶段满仓，下跌阶段 sf 缩减
        # 简化：V 形中一半在涨（sf≈1），一半在跌（sf 生效）
        # 实际上涨阶段波动低 sf≈1，跌阶段如果有波动 sf<1
        # 这里做最坏假设：sf 只在下半段生效
        effective_loss_per_cycle = loss_per_cycle * (0.5 + 0.5 * sf_val)
        annual_loss_sf = 1 - (1 - effective_loss_per_cycle) ** n

        print(f"{n:<6} {-annual_loss*100:>7.1f}%    {ann_vol*100:>6.1f}%         "
              f"{sf_val:>6.2f}      {-annual_loss_sf*100:>7.1f}%")

    # 关键结论
    print(f"\n--- 关键发现 ---")
    print("最坏年 = 假突破频繁 + 波动率中等偏低 + sf 基本不缩仓")
    print("= 市场反复震荡阴跌，波动率 3-8%，sf≈1.0（被截断）")
    print("= 与原版地板接近，因为 sf 在这种场景下帮不上忙。")

    # 但 sf 在另一种坏年（高波动暴跌）提供保护
    print(f"\n--- 对比：高波动暴跌年（如 2020）---")
    print("波动率 20-40% → sf=0.25~0.5 → 暴露减半以上 → 损失大幅缩减")
    print("这种年在原版模型中 ≈ 贡献 -15%，sf 后 ≈ 贡献 -5% ~ -8%")

    print(f"\n--- 结论 ---")
    print("sf 地板的改善取决于最坏年的波动率构成:")
    print("  纯低波动阴跌（sf 无效）: 地板几乎不变, ≈ -2.3 ~ -2.5")
    print("  混有高波动暴跌（sf 有效）: 地板改善, ≈ -1.5 ~ -2.0")
    print("  实际市场是混合型 → 地板在 -1.8 ~ -2.2 之间")


# ============================================================
# Part 3: 实际数据验证 —— 滚动 12 月最差 Sharpe
# ============================================================

def rolling_worst_sharpe():
    """用实际回测数据，找滚动 12 月最差 Sharpe（含/不含 sf）。"""
    print("\n" + "=" * 70)
    print("Part 3: 实际数据滚动 12 月最差 Sharpe")
    print("=" * 70)

    prices = {}
    for name, code in ETF_CODE_MAP.items():
        fpath = os.path.join(DATA_DIR, f"{code}.parquet")
        if os.path.exists(fpath):
            df = pd.read_parquet(fpath)
            if "close" in df.columns:
                prices[name] = df

    if len(prices) < 5:
        print("ERROR: 数据不完整")
        return

    # --- 不含 sf ---
    bt_no = run_backtest(prices, params={"defense_ratio": 1.00}, execution_lag=1)
    nav_no = bt_no["records_df"]["nav"]

    # --- 含 sf（猴子补丁） ---
    import src.backtest_engine as be

    def allocate_fixed(signal, total_capital, defense_ratio=0.70):
        """修复版：使用 final_multiplier"""
        defense_pool = total_capital * defense_ratio
        offense_pool = total_capital * (1 - defense_ratio)
        final_mult = signal["execution"]["final_multiplier"]
        defense_pool *= final_mult
        offense_pool *= final_mult
        if signal["circuit_breaker"]["triggered"]:
            return {"date": signal["date"], "total_capital": total_capital,
                    "positions": {}, "defense_total": 0.0, "offense_total": 0.0,
                    "repo_amount": total_capital, "exposure": 0.0, "exposure_ratio": 0.0}
        positions = {}
        for name, weight in signal["defense"]["target_weights"].items():
            positions[name] = defense_pool * weight
        offense_weights = signal["offense"]["target_weights"]
        if offense_weights:
            for name, weight in offense_weights.items():
                positions[name] = offense_pool * weight
            repo_amount = 0.0
        else:
            repo_amount = offense_pool
        exposure = sum(positions.values())
        repo_amount += total_capital - exposure - repo_amount
        return {"date": signal["date"], "total_capital": total_capital,
                "positions": positions, "defense_total": defense_pool,
                "offense_total": offense_pool if offense_weights else 0.0,
                "repo_amount": repo_amount, "exposure": exposure,
                "exposure_ratio": exposure / total_capital}

    be.allocate_capital = allocate_fixed
    bt_yes = run_backtest(prices, params={"defense_ratio": 1.00}, execution_lag=1)
    be.allocate_capital = _original_allocate
    nav_yes = bt_yes["records_df"]["nav"]

    # --- 滚动 12 月 ---
    def rolling_12m_sharpe(nav_series):
        """计算所有滚动 252 个交易日的年化 Sharpe，返回最小值。"""
        daily_ret = nav_series.pct_change().dropna()
        if len(daily_ret) < 252:
            return None, None, None
        rolling_sharpe = daily_ret.rolling(252).apply(
            lambda x: (x.mean() * 252) / (x.std() * np.sqrt(252)) if x.std() > 0 else 0
        )
        min_idx = rolling_sharpe.idxmin()
        return rolling_sharpe.min(), min_idx, rolling_sharpe

    min_sharpe_no, worst_date_no, _ = rolling_12m_sharpe(nav_no)
    min_sharpe_yes, worst_date_yes, _ = rolling_12m_sharpe(nav_yes)

    print(f"\n滚动 12 月最差 Sharpe:")
    print(f"  不含 sf: {min_sharpe_no:.3f} (窗口截止: {str(worst_date_no)[:10]})")
    print(f"  含 sf:   {min_sharpe_yes:.3f} (窗口截止: {str(worst_date_yes)[:10]})")
    print(f"  改善:    {min_sharpe_yes - min_sharpe_no:+.3f}")

    # 对应期间的收益和回撤
    def window_metrics(nav_series, end_date):
        """计算以 end_date 结尾的 252 日窗口的收益和回撤。"""
        end_loc = nav_series.index.get_loc(end_date)
        start_loc = max(0, end_loc - 251)
        window = nav_series.iloc[start_loc:end_loc + 1]
        total_ret = (window.iloc[-1] / window.iloc[0]) - 1
        running_max = window.cummax()
        dd = (window - running_max) / running_max
        return total_ret, dd.min()

    ret_no, dd_no = window_metrics(nav_no, worst_date_no)
    ret_yes, dd_yes = window_metrics(nav_yes, worst_date_yes)

    print(f"\n最差 12 月窗口详情:")
    print(f"  {'':<12} {'不含 sf':>12} {'含 sf':>12}")
    print(f"  {'Sharpe':<12} {min_sharpe_no:>12.3f} {min_sharpe_yes:>12.3f}")
    print(f"  {'收益':<12} {ret_no*100:>11.1f}% {ret_yes*100:>11.1f}%")
    print(f"  {'回撤':<12} {dd_no*100:>11.1f}% {dd_yes*100:>11.1f}%")

    print(f"\n--- 结论 ---")
    delta = min_sharpe_yes - min_sharpe_no
    if delta > 0.3:
        print(f"实际最差滚动年改善 {delta:+.2f}，地板显著抬升")
    elif delta > 0.1:
        print(f"实际最差滚动年改善 {delta:+.2f}，地板有限抬升")
    else:
        print(f"实际最差滚动年改善 {delta:+.2f}，地板变化不大")

    return min_sharpe_no, min_sharpe_yes


if __name__ == "__main__":
    worst_daily = derive_original_floor()
    derive_sf_floor(worst_daily)
    empirical = rolling_worst_sharpe()
