"""
步骤 2：每风险源代表选择（修正版——排除港股/跨境，优先 A 股长历史 ETF）
数据源：新浪（≥3s）
输入：_mapped.csv
输出：_risk_sources.csv
"""
import os
import sys
import time
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MAX_PER_SOURCE = 3
RISK_SOURCE_ORDER = ["消费", "医药", "金融", "周期资源", "科技成长", "军工"]

# 额外排除：港股/跨境 ETF（名称包含这些关键词的，虽是 A 股交易但跟踪境外资产）
EXCLUDE_CROSS_BORDER = [
    "港股", "香港", "恒生", "沪港通", "深港通", "港股通",
    "中韩", "中日", "沪伦", "跨境", "全球",
    "标普", "纳斯达克", "纳指", "道琼斯", "MSCI", "富时",
]


def code_to_sina_symbol(code: str) -> str:
    code = str(code)
    if code.startswith("5"):
        return f"sh{code}"
    else:
        return f"sz{code}"


def get_listing_date_sina(code: str) -> pd.Timestamp | None:
    import akshare as ak
    symbol = code_to_sina_symbol(code)
    try:
        df = ak.fund_etf_hist_sina(symbol=symbol)
        if df is not None and not df.empty:
            return pd.to_datetime(df["date"].min())
    except Exception:
        pass
    return None


def main():
    import akshare as ak

    base = os.path.join(os.path.dirname(__file__), "..")
    mapped_path = os.path.join(base, "_mapped.csv")
    df = pd.read_csv(mapped_path, dtype={"code": str})
    print(f"=== 步骤 2：代表选择（修正版）===\n")
    print(f"输入: {len(df)} 只已映射 ETF")

    # 排除港股/跨境
    mask = pd.Series(True, index=df.index)
    for kw in EXCLUDE_CROSS_BORDER:
        mask = mask & ~df["name"].str.contains(kw, na=False)
    a_share = df[mask].copy()
    print(f"A 股纯境内: {len(a_share)} 只（排除跨境 {len(df) - len(a_share)} 只）\n")

    results = []
    for source in RISK_SOURCE_ORDER:
        group = a_share[a_share["risk_source"] == source].copy()
        # 成交量降序
        group = group.sort_values("amount", ascending=False)
        print(f"[{source}] {len(group)} 只境内候选")

        selected = group.head(MAX_PER_SOURCE)
        for i, (_, row) in enumerate(selected.iterrows()):
            code = row["code"]
            name = row["name"]
            print(f"  {i+1}. {code} {name}  成交额: {row['amount']:,.0f}")

            list_date = get_listing_date_sina(code)
            years = (pd.Timestamp.now() - list_date).days / 365 if list_date else 0
            print(f"     上市: {list_date}  (~{years:.1f}年)")
            time.sleep(3.5)

            results.append({
                "risk_source": source,
                "code": code,
                "name": name,
                "amount": row["amount"],
                "list_date": list_date,
                "years": round(years, 1),
            })
        print()

    out = pd.DataFrame(results)
    out_path = os.path.join(base, "_risk_sources.csv")
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"中间产物已写入: {out_path}")
    print(f"共 {len(out)} 只代表 ETF\n")

    # 找出最晚上市日期
    latest = out["list_date"].max()
    print(f"最晚上市: {latest}")
    years_window = (pd.Timestamp.now() - latest).days / 365
    print(f"共同回测窗口: ~{years_window:.1f} 年")
    if years_window < 5:
        print("⚠ 不足 5 年！需要替换最晚的 ETF 或接受短窗口。")

    for source in RISK_SOURCE_ORDER:
        subset = out[out["risk_source"] == source]
        items = ", ".join(f"{r['code']}({r['name']}, {r['years']}年)"
                         for _, r in subset.iterrows())
        print(f"  {source}: {items}")


if __name__ == "__main__":
    main()
