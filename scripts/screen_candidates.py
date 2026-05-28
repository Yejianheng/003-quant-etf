# [2026-05-28] 新增：进攻层候选池筛选工具
# 不修改业务代码，输出候选清单供人工确认后写入 etf_universe.py。
import sys
sys.stdout.reconfigure(encoding='utf-8')

import time
import pandas as pd
import akshare as ak

MIN_AUM_YI = 5
MIN_TURNOVER_WAN = 1000
DEFENSE_CODES = {"510300", "159915", "513100", "518880", "511010"}

EXCLUDE_NAME_KW = [
    "债", "货币", "短融", "城投", "公司债", "可转债", "转债", "信用债",
    "地方债", "政金债", "金融债", "利率债", "国债",
    "QDII", "纳指", "标普", "恒生", "港股", "日经", "德国", "法国", "印度", "越南",
    "黄金", "豆粕", "能源化工", "原油", "白银",
    "增强", "联接", "LOF", "定期", "理财", "定开", "申赎",
]

EXCLUDE_BROAD_KW = [
    "沪深300", "中证500", "中证1000", "中证2000", "中证A50", "中证A500",
    "上证50", "上证180", "科创50", "科创100", "科创200",
    "创业板", "创业板指", "创业板综", "深证100", "深证300",
    "中证红利", "红利低波", "红利质量",
    "碳中和", "一带一路", "国企改革", "央企", "民企",
    "ESG", "可持续发展",
]

INDUSTRY_KW = [
    "芯片", "半导体", "集成电路",
    "医药", "医疗", "创新药", "生物医药", "中药", "疫苗", "器械",
    "证券", "券商", "银行", "保险", "金融",
    "军工", "国防",
    "消费", "食品", "饮料", "酒", "家电", "汽车", "新能源车",
    "新能源", "光伏", "电池", "锂电", "储能",
    "煤炭", "钢铁", "有色", "稀土", "化工",
    "房地产", "基建", "建材", "建筑",
    "电力", "公用事业",
    "农业", "畜牧", "养殖",
    "传媒", "游戏", "影视",
    "通信", "5G", "计算机", "软件", "云计算", "大数据",
    "人工智能", "机器人", "工业母机", "高端装备",
    "电子", "消费电子",
    "旅游", "物流", "交通运输",
]

FUND_COMPANY_SUFFIXES = [
    "华夏", "国泰", "天弘", "易方达", "南方", "广发", "富国",
    "招商", "博时", "华安", "嘉实", "工银", "鹏华", "银华",
    "汇添富", "景顺", "华泰柏瑞", "万家", "中欧", "兴全",
    "建信", "平安", "方正富邦", "弘毅远方", "国联",
]

INDUSTRY_MAP = {
    "半导体": "科技", "芯片": "科技", "集成电路": "科技",
    "电子": "科技", "计算机": "科技", "软件": "科技",
    "通信": "科技", "5G": "科技", "云计算": "科技", "大数据": "科技",
    "人工智能": "科技", "机器人": "科技",
    "医药": "医药", "医疗": "医药", "创新药": "医药", "生物医药": "医药",
    "中药": "医药", "疫苗": "医药", "器械": "医药",
    "证券": "金融", "券商": "金融", "银行": "金融", "保险": "金融",
    "军工": "制造", "国防": "制造", "工业母机": "制造", "高端装备": "制造",
    "消费": "消费", "食品": "消费", "饮料": "消费", "酒": "消费",
    "家电": "消费", "汽车": "消费", "新能源车": "消费", "旅游": "消费",
    "新能源": "能源", "光伏": "能源", "电池": "能源", "锂电": "能源",
    "储能": "能源", "电力": "能源", "煤炭": "能源",
    "钢铁": "材料", "有色": "材料", "稀土": "材料", "化工": "材料", "建材": "材料",
    "房地产": "地产基建", "基建": "地产基建", "建筑": "地产基建",
    "农业": "农业", "畜牧": "农业", "养殖": "农业",
    "传媒": "传媒", "游戏": "传媒", "影视": "传媒",
    "物流": "交通", "交通运输": "交通",
}


def classify_industry(name):
    for kw, industry in INDUSTRY_MAP.items():
        if kw in name:
            return industry
    return "其他"


def extract_index_name(name):
    for suffix in FUND_COMPANY_SUFFIXES:
        name = name.replace(suffix, "")
    return name


def main():
    print("Step 1: 获取全量 ETF 列表...")
    df_sina = ak.fund_etf_category_sina(symbol="ETF基金")
    print(f"  新浪源: {len(df_sina)} 只")
    time.sleep(3)

    print("Step 1b: 东方财富 spot (规模/流动性)...")
    df_em = ak.fund_etf_spot_em()
    print(f"  东方财富 spot: {len(df_em)} 只")

    df_sina["code_digit"] = df_sina["代码"].str.extract(r"(\d{6})", expand=False)
    df_em["code_digit"] = df_em["代码"].astype(str)
    merged = df_sina.merge(
        df_em[["code_digit", "成交量", "成交额", "最新份额", "流通市值", "总市值"]],
        on="code_digit", how="inner", suffixes=("_sina", "_em"),
    )
    print(f"  合并后: {len(merged)} 只")

    print("\nStep 1.5: 粗筛过滤...")
    before = len(merged)
    merged = merged[~merged["code_digit"].isin(DEFENSE_CODES)]
    print(f"  排除防御层 {before - len(merged)} 只 -> {len(merged)} 只")

    for kw in EXCLUDE_NAME_KW:
        before = len(merged)
        merged = merged[~merged["名称"].str.contains(kw, na=False)]
        if before != len(merged):
            print(f"  排除 [{kw}]: {before - len(merged)} 只")

    before = len(merged)
    merged = merged[~merged["名称"].str.contains("|".join(EXCLUDE_BROAD_KW), na=False)]
    print(f"  排除宽基/策略/主题: {before - len(merged)} 只 -> {len(merged)} 只")

    print("\nStep 2: 精细筛选...")
    merged["aum_yi"] = merged["总市值_em"] / 1e8
    before = len(merged)
    merged = merged[merged["aum_yi"] >= MIN_AUM_YI]
    print(f"  规模 >= {MIN_AUM_YI}亿: 排除 {before - len(merged)} 只 -> {len(merged)} 只")

    merged["turnover_wan"] = merged["成交额_em"] / 1e4
    before = len(merged)
    merged = merged[merged["turnover_wan"] >= MIN_TURNOVER_WAN]
    print(f"  成交额 >= {MIN_TURNOVER_WAN}万: 排除 {before - len(merged)} 只 -> {len(merged)} 只")

    print("\nStep 3: 行业匹配...")
    industry_pattern = "|".join(INDUSTRY_KW)
    candidates = merged[merged["名称"].str.contains(industry_pattern, na=False)].copy()
    print(f"  行业匹配后: {len(candidates)} 只")

    candidates["industry"] = candidates["名称"].apply(classify_industry)
    candidates["index_name"] = candidates["名称"].apply(extract_index_name)
    candidates = candidates.sort_values("aum_yi", ascending=False)
    candidates = candidates.drop_duplicates(subset="index_name", keep="first")
    print(f"  去重后: {len(candidates)} 只")

    print("\n行业分布:")
    for ind, grp in candidates.groupby("industry"):
        print(f"  {ind}: {len(grp)} 只")

    print("\nStep 4: 行业均衡 (每行业 <=3 只)...")
    final = []
    industry_count = {}
    for _, row in candidates.iterrows():
        ind = row["industry"]
        cnt = industry_count.get(ind, 0)
        if cnt < 3:
            final.append(row)
            industry_count[ind] = cnt + 1

    final_df = pd.DataFrame(final)
    n = len(final_df)

    print(f"\n最终候选池 {n} 只:")
    for _, row in final_df.iterrows():
        print(f"  {row['code_digit']}  {row['名称']:<30s}  "
              f"AUM={row['aum_yi']:5.1f}亿  成交={row['turnover_wan']:7.0f}万  [{row['industry']}]")

    print("\nOFFENSE_POOL = {")
    for _, row in final_df.iterrows():
        print(f"    \"{row['名称']}\": \"{row['code_digit']}\",")
    print("}")

    final_df[["code_digit", "名称", "aum_yi", "turnover_wan", "industry"]].to_csv(
        "_industry_candidates.csv", index=False, encoding="utf-8-sig"
    )
    print(f"\n导出 _industry_candidates.csv")

    if 10 <= n <= 15:
        print(f"OK 候选池 {n} 只在目标范围 10-15 内")
    else:
        print(f"候选池 {n} 只 (目标 10-15)")


if __name__ == "__main__":
    main()
