# [2026-05-29] 重构：OFFENSE_POOL 主题去重——二级主题（芯片/半导体/酒/电池）排除，换宽基一级风险源 ETF
# [2026-05-29] 重构：OFFENSE_POOL 三层架构（风险源层 + ETF 候选层 + 代表 ETF），旧 10 只作废
# [2026-05-28] 新增：OFFENSE_POOL — 进攻层行业 ETF 候选池
# [2026-05-27] 新增：ETF 代码映射 — 防御层标的

# 防御层标的 → ETF 代码（上交所/深交所）
ETF_UNIVERSE = {
    "沪深300": "510300",
    "创业板": "159915",
    "纳指": "513100",
    "黄金": "518880",
    "国债ETF": "511010",
}

# 进攻层候选池 — 三层架构（方向性讨论 §二-进攻层-候选池）
# 风险源层：6 类经济驱动因子（架构级，长期不变）
# ETF 候选层：每类 1-3 只（实现层，ETF 退化可替换）
# 代表 ETF：每类 1 只（截面动量轮动使用，选流动性最佳者）
# 最终轮动：6 代表 ETF → 截面动量排名 → Top K 等权持仓
# 禁止：芯片/半导体/电池/AI/机器人/算力等二级主题 ETF 进入主轮动池
OFFENSE_POOL = {
    "消费": {
        "code": "159928",
        "name": "消费ETF汇添富",
        "candidates": [
            {"code": "159928", "name": "消费ETF汇添富"},
            {"code": "159865", "name": "养殖ETF国泰"},
        ],
    },
    "医药": {
        "code": "512010",
        "name": "医药ETF易方达",
        "candidates": [
            {"code": "512010", "name": "医药ETF易方达"},
            {"code": "512170", "name": "医疗ETF华宝"},
            {"code": "159992", "name": "创新药ETF银华"},
        ],
    },
    "金融": {
        "code": "512880",
        "name": "证券ETF国泰",
        "candidates": [
            {"code": "512880", "name": "证券ETF国泰"},
            {"code": "512000", "name": "券商ETF鹏华"},
            {"code": "512800", "name": "银行ETF鹏华"},
        ],
    },
    "周期资源": {
        "code": "512400",
        "name": "有色金属ETF南方",
        "candidates": [
            {"code": "512400", "name": "有色金属ETF南方"},
            {"code": "515220", "name": "煤炭ETF国泰"},
            {"code": "159870", "name": "化工ETF鹏华"},
        ],
    },
    "科技成长": {
        "code": "515000",
        "name": "科技ETF华夏",
        "candidates": [
            {"code": "515000", "name": "科技ETF华夏"},
            {"code": "515880", "name": "通信ETF国泰"},
        ],
    },
    "军工": {
        "code": "512660",
        "name": "军工ETF国泰",
        "candidates": [
            {"code": "512660", "name": "军工ETF国泰"},
            {"code": "512710", "name": "军工龙头ETF富国"},
            {"code": "512680", "name": "军工ETF广发"},
        ],
    },
}


def build_candidate_pool():
    """扫描全市场 ETF，返回行业候选池代码列表。
    网络不可达时返回空列表而非崩溃。
    """
    try:
        codes = []
        for entry in OFFENSE_POOL.values():
            codes.append(entry["code"])
        return codes
    except Exception:
        return []
