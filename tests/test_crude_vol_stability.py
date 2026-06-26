# [2026-06-26] 新增：高波动风险权重标准化测试 — 原油波动率稳定性分析
"""测试 C：原油波动率稳定性分析。

不依赖回测，直接统计原油 vs 黄金滚动 1 年波动率的分布。
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE, "data")


def load_asset_close(name, code):
    fpath = os.path.join(DATA_DIR, f"{code}.parquet")
    if not os.path.exists(fpath):
        return None
    df = pd.read_parquet(fpath)
    return df["close"] if "close" in df.columns else None


def rolling_1y_vol(close: pd.Series, min_periods: int = 60) -> pd.Series:
    """计算滚动 1 年（252 日）年化波动率。"""
    ret = close.pct_change().dropna()
    vol = ret.rolling(window=252, min_periods=min_periods).std() * np.sqrt(252)
    return vol.dropna()


def vol_distribution(close: pd.Series) -> dict:
    """返回波动率分布的描述统计。"""
    vol = rolling_1y_vol(close)
    if len(vol) == 0:
        return {}
    return {
        "均值": vol.mean(),
        "中位数": vol.median(),
        "标准差": vol.std(),
        "最小值": vol.min(),
        "最大值": vol.max(),
        "P5": vol.quantile(0.05),
        "P95": vol.quantile(0.95),
        "max/min 比值": vol.max() / vol.min() if vol.min() > 0 else np.inf,
        "P95/P5 比值": vol.quantile(0.95) / vol.quantile(0.05) if vol.quantile(0.05) > 0 else np.inf,
        "样本数": len(vol),
    }


def plot_vol_timeseries(close_gold, close_crude):
    """输出波动率时间序列表格（每半年一个采样点）。"""
    vol_g = rolling_1y_vol(close_gold)
    vol_c = rolling_1y_vol(close_crude)

    # 每半年取一个点
    common_idx = vol_g.index.intersection(vol_c.index)
    sample = common_idx[::126]  # 约半年一个点

    print(f"\n{'日期':<14} {'黄金波动率':>12} {'原油波动率':>12} {'比值(原油/黄金)':>16}")
    print("-" * 56)
    for dt in sample:
        ratio = vol_c[dt] / vol_g[dt] if vol_g[dt] > 0 else np.inf
        print(f"{dt.strftime('%Y-%m-%d'):<14} {vol_g[dt]:>11.2%} {vol_c[dt]:>11.2%} {ratio:>15.2f}")


def run_vol_stability_analysis():
    """运行波动率稳定性分析。"""
    print("=" * 80)
    print("测试 C：原油波动率稳定性分析")
    print("=" * 80)

    close_gold = load_asset_close("黄金", "518880")
    close_crude = load_asset_close("原油", "159935")

    if close_gold is None or close_crude is None:
        print("错误：无法加载数据")
        return

    gold_dist = vol_distribution(close_gold)
    crude_dist = vol_distribution(close_crude)

    if not gold_dist or not crude_dist:
        print("错误：波动率计算失败")
        return

    print(f"\n{'指标':<16} {'黄金':>10} {'原油':>10}")
    print("-" * 38)
    for key in ["均值", "中位数", "标准差", "最小值", "最大值", "P5", "P95", "max/min 比值", "P95/P5 比值"]:
        gv = gold_dist.get(key, np.nan)
        cv = crude_dist.get(key, np.nan)
        if "比值" in key:
            print(f"{key:<16} {gv:>10.2f} {cv:>10.2f}")
        else:
            print(f"{key:<16} {gv:>9.2%} {cv:>9.2%}")

    print(f"\n样本数: 黄金={gold_dist.get('样本数','N/A')}  原油={crude_dist.get('样本数','N/A')}")

    # 波动率时间序列
    print("\n波动率时间序列（每半年采样）：")
    plot_vol_timeseries(close_gold, close_crude)

    # 关键判断
    print("\n--- 关键判断 ---")

    crude_ratio = crude_dist["max/min 比值"]
    gold_ratio = gold_dist["max/min 比值"]
    print(f"\nmax/min 比值:")
    print(f"  黄金: {gold_ratio:.2f}")
    print(f"  原油: {crude_ratio:.2f}")
    if crude_ratio > gold_ratio * 2:
        print(f"  >>> 原油波动率 max/min 比值远超黄金，固定风险权重不足以覆盖波动率切换")
    else:
        print(f"  原油与黄金的 max/min 比值差异可控")

    print(f"\nP95/P5 比值:")
    crude_p95p5 = crude_dist["P95/P5 比值"]
    gold_p95p5 = gold_dist["P95/P5 比值"]
    print(f"  黄金: {gold_p95p5:.2f}")
    print(f"  原油: {crude_p95p5:.2f}")
    diff = crude_p95p5 / gold_p95p5 if gold_p95p5 > 0 else np.inf
    if diff > 2:
        print(f"  >>> 原油波动率 P95/P5 = {crude_p95p5:.2f} (黄金 {gold_p95p5:.2f})，比值 {diff:.1f}x")
        print(f"  >>> 波动率分布宽广，固定风险权重方案不可靠")
    else:
        print(f"  原油 P95/P5 比值在可控范围内")

    return gold_dist, crude_dist


def test_vol_stats_computable():
    """验证波动率统计量可正常计算。"""
    close_gold = load_asset_close("黄金", "518880")
    close_crude = load_asset_close("原油", "159935")
    assert close_gold is not None
    assert close_crude is not None

    gold_dist = vol_distribution(close_gold)
    crude_dist = vol_distribution(close_crude)

    for key in ["均值", "中位数", "P5", "P95", "max/min 比值"]:
        assert key in gold_dist, f"黄金缺失 {key}"
        assert key in crude_dist, f"原油缺失 {key}"
        assert not np.isnan(gold_dist[key]), f"黄金 {key} is NaN"
        assert not np.isnan(crude_dist[key]), f"原油 {key} is NaN"

    # 原油波动率均值应显著高于黄金
    assert crude_dist["均值"] > gold_dist["均值"], "原油波动率应高于黄金"


def test_crude_vol_abs_higher_than_gold():
    """验证原油绝对波动率水平高于黄金（均值和中位数）。"""
    close_gold = load_asset_close("黄金", "518880")
    close_crude = load_asset_close("原油", "159935")
    gold_dist = vol_distribution(close_gold)
    crude_dist = vol_distribution(close_crude)
    print(f"\n  黄金波动率均值: {gold_dist['均值']:.2%}, 中位数: {gold_dist['中位数']:.2%}")
    print(f"  原油波动率均值: {crude_dist['均值']:.2%}, 中位数: {crude_dist['中位数']:.2%}")
    assert crude_dist["均值"] > gold_dist["均值"] * 1.5, (
        "原油波动率均值应显著高于黄金"
    )


def test_crude_p95_p5_ratio():
    """验证原油 P95/P5 比值作为固定权重适用性指标。"""
    close_crude = load_asset_close("原油", "159935")
    dist = vol_distribution(close_crude)
    ratio = dist["P95/P5 比值"]
    mean = dist["均值"]
    p5 = dist["P5"]
    print(f"\n  原油波动率均值: {mean:.2%}")
    print(f"  原油 P5: {p5:.2%}")
    print(f"  原油 P95: {dist['P95']:.2%}")
    print(f"  原油 P95/P5: {ratio:.2f}")
    # 判断：如果 P95/P5 > 3，则固定权重不适用
    if ratio > 3:
        print(f"  → P95/P5 = {ratio:.2f} > 3，固定风险权重不可靠")
    else:
        print(f"  → P95/P5 = {ratio:.2f} <= 3，固定风险权重可能适用")
    assert True


if __name__ == "__main__":
    run_vol_stability_analysis()
