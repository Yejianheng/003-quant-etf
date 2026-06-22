# [2026-06-22] 修复：exposure/repo_amount 优先从 positions_detail 计算
# [2026-05-30] 修改：record_daily 新增 positions_detail 可选参数 — Golden Dataset
# [2026-05-30] 修改：日记录新增 scaling_factor / predicted_vol — Vol Target 触发审计
# [2026-05-27] 新增：Recorder — 回测日记录器，记录每天组合状态和信号

import pandas as pd


def init_recorder() -> dict:
    """初始化空记录器。"""
    return {"records": [], "positions_detail": []}


def record_daily(
    recorder: dict,
    date: str,
    nav: float,
    signal: dict,
    positions: dict[str, float],
    positions_detail: dict[str, float] | None = None,
) -> None:
    """追加一条日记录到 recorder["records"]（in-place 修改）。"""
    if positions_detail:
        exposure = sum(positions_detail.values())
    else:
        exposure = sum(positions.values())
    repo_amount = nav - exposure

    offense_top = [item["name"] for item in signal["offense"]["rankings"]]
    position_names = list(positions.keys())

    record = {
        "date": date,
        "nav": nav,
        "exposure": exposure,
        "repo_amount": repo_amount,
        "final_multiplier": signal["execution"]["final_multiplier"],
        "circuit_breaker_triggered": signal["circuit_breaker"]["triggered"],
        "drawdown_level": signal["drawdown_stop"]["level"],
        "drawdown": signal["drawdown_stop"]["drawdown"],
        "n_positions": len(position_names),
        "position_names": ";".join(position_names),
        "defense_active": ";".join(signal["defense"]["active"]),
        "offense_top": ";".join(offense_top),
        "scaling_factor": signal["defense"]["scaling_factor"],
        "predicted_vol": signal["defense"].get("predicted_vol", 0.0),
        "defense_count": len(signal["defense"]["active"]),
    }
    recorder["records"].append(record)

    if positions_detail is not None:
        detail = {"date": date}
        detail.update(positions_detail)
        recorder["positions_detail"].append(detail)


def get_records_df(recorder: dict) -> pd.DataFrame:
    """将 records 列表转为 DataFrame，date 列设为 DatetimeIndex。"""
    df = pd.DataFrame(recorder["records"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")
