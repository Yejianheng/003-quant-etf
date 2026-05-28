"""
步骤 1：预过滤 + 名称映射（六步流水线第一步）
输入：fund_etf_category_sina 全量 ETF
输出：_mapped.csv（代码 + 名称 + 风险源 + 成交量）
"""
import os
import sys
import pandas as pd
import akshare as ak

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---- 预过滤关键词（名称包含即排除） ----

EXCLUDE_KEYWORDS = [
    # 债券/货币/QDII/商品/黄金/理财/逆回购
    "债", "货币", "QDII", "商品", "黄金", "理财", "逆回购",
    # 杠杆/反向
    "杠杆", "反向",
    # 联接/增强/LOF/定期开放/定开
    "联接", "增强", "LOF", "定期开放", "定开",
    # 宽基指数
    "沪深300", "中证500", "上证50", "科创50", "创业板", "中证1000",
    "中证2000", "中证100", "上证180", "上证380", "深证100", "深证300",
    "中证800", "沪深300", "中证全指", "恒生", "恒指", "H股",
    "标普500", "标普", "纳斯达克", "纳指", "道琼斯", "日经", "德国DAX",
    # 策略/主题
    "红利", "央企", "国企", "一带一路", "碳中和", "ESG", "央企创新",
    "国企改革", "央企改革", "民企", "区域", "长三角", "珠三角", "京津冀",
    "自贸", "PPP", "混改", "供给侧", "新基建",
    # 其他不适用
    "可转债", "转债",
]

# ---- 一级名称映射（→ 6 风险源） ----

RISK_SOURCE_KEYWORDS = {
    "消费": ["消费", "食品饮料", "酒", "家电", "农业", "养殖", "农牧", "畜牧", "旅游"],
    "医药": ["医药", "医疗", "药", "医械", "中药", "创新药", "生物医药"],
    "金融": ["证券", "券商", "银行", "金融", "保险", "非银"],
    "周期资源": ["煤炭", "有色", "钢铁", "化工", "材料", "能源", "石油", "稀土", "矿业", "资源"],
    "科技成长": [
        "芯片", "半导体", "科创", "电子", "通信", "计算机", "软件",
        "AI", "人工智能", "机器人", "5G", "信创", "信息技术", "数字经济",
    ],
    "军工": ["军工", "国防", "军民", "航空"],
}


def fetch_all_etfs():
    """获取全量 ETF 列表（新浪源）。"""
    df = ak.fund_etf_category_sina(symbol="ETF基金")
    code_col = df.columns[0]
    name_col = df.columns[1]
    amt_col = df.columns[12]  # 成交额
    df = df.rename(columns={code_col: "code", name_col: "name", amt_col: "amount"})
    # 去掉交易所前缀 sz/sh
    df["code"] = df["code"].str[2:]
    return df[["code", "name", "amount"]]


def pre_filter(df: pd.DataFrame) -> pd.DataFrame:
    """预过滤：排除不适用于动量策略的 ETF。"""
    mask = pd.Series(True, index=df.index)
    for kw in EXCLUDE_KEYWORDS:
        mask = mask & ~df["name"].str.contains(kw, na=False)
    return df[mask].copy()


def map_to_risk_source(name: str) -> str | None:
    """将 ETF 名称映射到风险源，无法映射返回 None。"""
    for source, keywords in RISK_SOURCE_KEYWORDS.items():
        for kw in keywords:
            if kw in name:
                return source
    return None


def main():
    print("=== 步骤 1：预过滤 + 名称映射 ===\n")
    print("[1/3] 获取全量 ETF...")
    df = fetch_all_etfs()
    print(f"  全量: {len(df)} 只")

    print("[2/3] 预过滤...")
    filtered = pre_filter(df)
    print(f"  过滤后: {len(filtered)} 只（排除 {len(df) - len(filtered)} 只）")

    print("[3/3] 名称映射到 6 风险源...")
    filtered["risk_source"] = filtered["name"].apply(map_to_risk_source)
    mapped = filtered[filtered["risk_source"].notna()].copy()
    unmapped = filtered[filtered["risk_source"].isna()].copy()

    print(f"  映射成功: {len(mapped)} 只")
    for src in ["消费", "医药", "金融", "周期资源", "科技成长", "军工"]:
        n = len(mapped[mapped["risk_source"] == src])
        print(f"    {src}: {n} 只")
    print(f"  未映射: {len(unmapped)} 只（策略/主题/宽基漏网）")

    out_path = os.path.join(os.path.dirname(__file__), "..", "_mapped.csv")
    cols = ["code", "name", "risk_source", "amount"]
    mapped[cols].to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n中间产物已写入: {out_path}")
    print(f"共 {len(mapped)} 条记录，覆盖 6 风险源")


if __name__ == "__main__":
    main()
