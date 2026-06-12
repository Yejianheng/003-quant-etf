# [2026-06-12] 修复：sf 生效 — position_multiplier → final_multiplier（v184 验证通过）
# [2026-05-27] 新增：组合管理器 — 信号→仓位转换层，资金路由

def allocate_capital(
    signal: dict,
    total_capital: float,
    defense_ratio: float = 0.70,
) -> dict:
    """根据信号分配资金，输出每只标的的精确持仓金额。"""
    # 1. 基础资金池
    defense_pool = total_capital * defense_ratio
    offense_pool = total_capital * (1 - defense_ratio)

    # 2. 总仓位乘数 = min(sf, drawdown_multiplier)，已在 signal_generator 计算
    final_mult = signal["execution"]["final_multiplier"]
    defense_pool *= final_mult
    offense_pool *= final_mult

    # 3. 相关性熔断 → 全部资金进逆回购
    if signal["circuit_breaker"]["triggered"]:
        return {
            "date": signal["date"],
            "total_capital": total_capital,
            "positions": {},
            "defense_total": 0.0,
            "offense_total": 0.0,
            "repo_amount": total_capital,
            "exposure": 0.0,
            "exposure_ratio": 0.0,
        }

    positions: dict[str, float] = {}
    repo_amount = 0.0

    # 4. 防御层分配
    for name, weight in signal["defense"]["target_weights"].items():
        positions[name] = defense_pool * weight

    # 5. 进攻层分配（空仓 → 进逆回购，不回流防御层）
    offense_weights = signal["offense"]["target_weights"]
    if offense_weights:
        for name, weight in offense_weights.items():
            positions[name] = offense_pool * weight
    else:
        repo_amount += offense_pool

    # 6. 汇总（剩余零钱进逆回购）
    exposure = sum(positions.values())
    repo_amount += total_capital - exposure - repo_amount
    # 等价于 repo_amount = total_capital - exposure

    return {
        "date": signal["date"],
        "total_capital": total_capital,
        "positions": positions,
        "defense_total": defense_pool,
        "offense_total": offense_pool if offense_weights else 0.0,
        "repo_amount": repo_amount,
        "exposure": exposure,
        "exposure_ratio": exposure / total_capital,
    }
