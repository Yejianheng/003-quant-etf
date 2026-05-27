# [2026-05-27] 新增：Recorder — 回测日记录器，记录每天组合状态和信号

import pandas as pd


def init_recorder() -> dict:
    """初始化空记录器。"""
    return {"records": []}


def record_daily(
    recorder: dict,
    date: str,
    nav: float,
    signal: dict,
    positions: dict[str, float],
) -> None:
    """追加一条日记录到 recorder["records"]（in-place 修改）。"""
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
    }
    recorder["records"].append(record)


def get_records_df(recorder: dict) -> pd.DataFrame:
    """将 records 列表转为 DataFrame，date 列设为 DatetimeIndex。"""
    df = pd.DataFrame(recorder["records"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")
