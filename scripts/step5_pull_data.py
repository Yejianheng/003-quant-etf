"""
步骤 5：拉取候选 ETF 全量历史数据（新浪源，≥3s 间隔）
输出：./data/{code}.parquet
"""
import os
import sys
import time
import pandas as pd
import akshare as ak

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 所有需要数据的 ETF（防御 5 + 进攻 18）
ALL_CODES = {
    # 防御层（已有数据，跳过）
    "510300": "沪深300",
    "159915": "创业板",
    "513100": "纳指",
    "518880": "黄金",
    "511010": "国债ETF",
    # 进攻层代表（6 只）
    "512690": "酒ETF鹏华",
    "159992": "创新药ETF银华",
    "512880": "证券ETF国泰",
    "512400": "有色金属ETF南方",
    "512480": "半导体ETF华夏",
    "512660": "军工ETF国泰",
    # 进攻层候选（12 只）
    "159928": "消费ETF汇添富",
    "159865": "养殖ETF国泰",
    "512170": "医疗ETF华宝",
    "512010": "医药ETF易方达",
    "512000": "券商ETF鹏华",
    "512800": "银行ETF鹏华",
    "515220": "煤炭ETF国泰",
    "159870": "化工ETF鹏华",
    "515880": "通信ETF国泰",
    "159995": "芯片ETF华夏",
    "512710": "军工龙头ETF富国",
    "512680": "军工ETF广发",
}


def code_to_sina_symbol(code: str) -> str:
    if code.startswith("5"):
        return f"sh{code}"
    return f"sz{code}"


def fetch_and_save_sina(code: str, data_dir: str) -> pd.DataFrame:
    """新浪源拉取 ETF 全量历史数据 → parquet。"""
    out_path = os.path.join(data_dir, f"{code}.parquet")

    # 已存在则跳过
    if os.path.exists(out_path):
        existing = pd.read_parquet(out_path)
        print(f"  {code} 已存在 ({len(existing)} 行)，跳过")
        return existing

    symbol = code_to_sina_symbol(code)
    df = ak.fund_etf_hist_sina(symbol=symbol)
    if df is None or df.empty:
        print(f"  {code} 无数据")
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df.sort_index()

    os.makedirs(data_dir, exist_ok=True)
    df.to_parquet(out_path, index=True)
    print(f"  {code} 拉取完成 ({len(df)} 行, {df.index[0].date()} ~ {df.index[-1].date()})")
    return df


def main():
    base = os.path.join(os.path.dirname(__file__), "..")
    data_dir = os.path.join(base, "data")

    to_pull = []
    for code, name in ALL_CODES.items():
        fpath = os.path.join(data_dir, f"{code}.parquet")
        if not os.path.exists(fpath):
            to_pull.append((code, name))

    print(f"=== 步骤 5：拉取历史数据 ===\n")
    print(f"总计: {len(ALL_CODES)} 只, 已有: {len(ALL_CODES) - len(to_pull)} 只, 需拉取: {len(to_pull)} 只\n")

    if not to_pull:
        print("所有数据已就绪，无需拉取。")
        return

    for i, (code, name) in enumerate(to_pull):
        print(f"[{i+1}/{len(to_pull)}] {code} {name}")
        try:
            fetch_and_save_sina(code, data_dir)
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(3.5)

    print("\n数据拉取完成。")


if __name__ == "__main__":
    main()
