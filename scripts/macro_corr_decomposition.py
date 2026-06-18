# [2026-06-18] 新增：股债相关性经济驱动力分解 — OLS 回归 + 分阶段分析
"""smoothed_corr 的宏观经济驱动力分解。步骤 1-4 全部输出打印。"""
import os, sys, warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

# ── 工具函数 ──────────────────────────────────────────────
def safe_fetch(fn, label):
    """安全拉取 akshare 数据，失败打印原因并重新抛出。"""
    try:
        import akshare as ak
        df = getattr(ak, fn)()
        print(f"  {label}: {fn}() → {df.shape[0]} 行, {df.shape[1]} 列")
        return df
    except Exception as e:
        print(f"  [ERROR] {fn} 拉取失败: {e}")
        raise

def ols_fit(X, y):
    """numpy lstsq 拟合，返回 coeffs, SE, t_stats, p_vals, R², adj_R²。"""
    n_samples = len(y)
    if X.size == 0:
        X_mat = np.ones((n_samples, 1))  # intercept only
    else:
        X_mat = np.column_stack([np.ones(n_samples), X])
    coeffs, residuals, rank, sv = np.linalg.lstsq(X_mat, y, rcond=None)
    resid = y - X_mat @ coeffs
    n, k = X_mat.shape
    dof = n - k
    if dof <= 0:
        # 饱和模型 → SE/t 无定义，返回 NaN
        se = np.full(k, np.nan)
        t_stats = np.full(k, np.nan)
        p_vals = np.full(k, np.nan)
    else:
        sigma2 = np.sum(resid**2) / dof
        try:
            cov = sigma2 * np.linalg.inv(X_mat.T @ X_mat)
        except np.linalg.LinAlgError:
            cov = sigma2 * np.linalg.pinv(X_mat.T @ X_mat)
        se = np.sqrt(np.abs(np.diag(cov)))
        t_stats = coeffs / se
        p_vals = 2 * (1 - scipy_stats.t.cdf(np.abs(t_stats), dof))
    ss_res = np.sum(resid**2)
    ss_tot = np.sum((y - y.mean())**2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    adj_r2 = 1 - (1 - r2) * (n - 1) / dof if dof > 0 else 0.0
    return coeffs, se, t_stats, p_vals, r2, adj_r2

# ═══════════════════════════════════════════════════════════
# Step 1: 拉取宏观数据
# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("Step 1: 拉取宏观数据")
print("=" * 60)

# 1a. 中国国债收益率（日频）
raw_yields = safe_fetch('bond_zh_us_rate', '中国国债收益率')
yields = raw_yields.copy()
yields['日期'] = pd.to_datetime(yields['日期'])
yields = yields.set_index('日期').sort_index()

yield_10y = yields['中国国债收益率10年'].dropna()
yield_2y = yields['中国国债收益率2年'].dropna()
yield_spread = yield_10y - yield_2y
us_10y = yields.get('美国国债收益率10年', pd.Series(dtype=float)).dropna()
if not us_10y.empty:
    us_cn_spread = us_10y - yield_10y
else:
    us_cn_spread = pd.Series(dtype=float)

print(f"  国债收益日期范围: {yields.index[0].date()} ~ {yields.index[-1].date()}")
print(f"  10Y-2Y spread 均值: {yield_spread.mean():.2f} bp")

# 1b. CPI 同比（月频）
raw_cpi = safe_fetch('macro_china_cpi_monthly', 'CPI 月同比')
cpi = raw_cpi.copy()
cpi['日期'] = pd.to_datetime(cpi['日期'])
cpi_monthly = cpi.set_index('日期')['今值'].sort_index()
cpi_monthly = pd.to_numeric(cpi_monthly, errors='coerce').dropna()

full_date_range = pd.date_range(cpi_monthly.index.min(), cpi_monthly.index.max(), freq='D')
cpi_daily = cpi_monthly.reindex(full_date_range).ffill()

print(f"  CPI 日期范围: {cpi_monthly.index[0].date()} ~ {cpi_monthly.index[-1].date()}")
print(f"  CPI 均值: {cpi_monthly.mean():.2f}%")

# 1c. 保存 parquet
macro_df = pd.DataFrame({
    'yield_10y': yield_10y,
    'yield_2y': yield_2y,
    'yield_spread': yield_spread,
    'cpi_yoy': cpi_daily,
})
if not us_cn_spread.empty:
    macro_df['us_cn_spread'] = us_cn_spread

os.makedirs('data', exist_ok=True)
macro_df.to_parquet('data/macro_indicators.parquet')
print(f"\n已保存: data/macro_indicators.parquet ({len(macro_df)} 行, {len(macro_df.columns)} 列)")

# ═══════════════════════════════════════════════════════════
# Step 2: 对齐 smoothed_corr 序列
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 2: 对齐 smoothed_corr 序列")
print("=" * 60)

corr = pd.read_csv('output/smoothed_corr_history.csv', parse_dates=['date'])
corr = corr.set_index('date').sort_index()
print(f"  smoothed_corr: {len(corr)} 行, {corr.index[0].date()} ~ {corr.index[-1].date()}")

X_dict = {
    'yield_10y': yield_10y,
    'yield_spread': yield_spread,
    'cpi_yoy': cpi_daily,
}
if not us_cn_spread.empty:
    X_dict['us_cn_spread'] = us_cn_spread

common = corr.index
for x_name, x_series in X_dict.items():
    common = common.intersection(x_series.dropna().index)
    print(f"  对齐 {x_name}: 交集 → {len(common)} 天")

if len(common) == 0:
    raise RuntimeError("X 和 y 日期无交集，无法回归。请检查数据时间范围。")

y = corr.loc[common, 'smoothed_corr'].copy()
X = pd.DataFrame({k: X_dict[k].loc[common] for k in X_dict.keys()})

print(f"  最终样本: {len(y)} 天")

print("\n特征相关性矩阵:")
print(X.corr().round(3).to_string())

# ═══════════════════════════════════════════════════════════
# Step 3: OLS 回归 + 分阶段分析
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 3: OLS 回归 + 分阶段分析")
print("=" * 60)

feat_names = list(X.columns)
feat_labels = {'yield_10y': 'CN 10Y', 'yield_spread': '10Y-2Y Spread',
               'cpi_yoy': 'CPI YoY', 'us_cn_spread': 'US-CN Spread'}
coeffs, se, t_stats, p_vals, r2, adj_r2 = ols_fit(X.values, y.values)

print("\n── 全期 OLS 回归 ──")
print(f"  样本: {len(y)}, 特征: {len(feat_names)}")
print(f"  R2 = {r2:.4f}, adj R2 = {adj_r2:.4f}")
print()
header = f"  {'因子':<20s} {'beta':>8s}  {'SE':>8s}  {'t':>8s}  {'p':>8s}  {'sig':>6s}"
print(header)
print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")

def _sig(p):
    if pd.isna(p):
        return ''
    if p < 0.001:
        return '***'
    elif p < 0.01:
        return '**'
    elif p < 0.05:
        return '*'
    return ''

print(f"  {'const':<20s} {coeffs[0]:>8.4f}  {se[0]:>8.4f}  {t_stats[0]:>8.2f}  {p_vals[0]:>8.4f}  {_sig(p_vals[0]):>6s}")

for i, name in enumerate(feat_names):
    label = feat_labels.get(name, name)
    sig = _sig(p_vals[i+1])
    print(f"  {label:<20s} {coeffs[i+1]:>8.4f}  {se[i+1]:>8.4f}  "
          f"{t_stats[i+1]:>8.2f}  {p_vals[i+1]:>8.4f}  {sig:>6s}")

# 因子贡献排序
contrib = []
for i, name in enumerate(feat_names):
    std_i = X[name].std() if X[name].std() > 0 else 1.0
    contrib.append((feat_labels.get(name, name), abs(coeffs[i+1]) * std_i))
contrib.sort(key=lambda x: x[1], reverse=True)
print("\n  因子贡献排序 (|beta| x std):")
for label, c in contrib:
    print(f"    {label}: {c:.4f}")

# 3b. 分年因子均值表
print("\n── 分年因子均值 + smoothed_corr 均值 ──")
y_by_year = y.groupby(y.index.year)
X_by_year = X.groupby(X.index.year)

line = f"  {'Year':>6s} {'N':>5s}  "
for name in feat_names:
    line += f"{feat_labels.get(name, name):>14s}  "
line += f"{'smoothed_corr':>14s}  {'CB触发%':>8s}"
print(line)
print(f"  {'-'*6} {'-'*5}  " + ' '.join([f"{'-'*14}" for _ in range(len(feat_names)+2)]))

for year in sorted(y_by_year.groups.keys()):
    y_i = y_by_year.get_group(year)
    n = len(y_i)
    cb_pct = (y_i > 0.0).sum() / n * 100 if n > 0 else 0.0
    print(f"  {year:>6d} {n:>5d}  ", end='')
    for name in feat_names:
        x_mean = X_by_year.get_group(year)[name].mean()
        print(f"{x_mean:>14.4f}  ", end='')
    print(f"{y_i.mean():>14.4f}  {cb_pct:>7.1f}%")

# 3c. CB 触发期 vs 非触发期
print("\n── CB 触发期 vs 非触发期因子均值对比 ──")
cb_on = y > 0.0
cb_off = ~cb_on

print(f"  {'因子':<20s} {'触发期均值':>12s}  {'非触发均值':>12s}  {'差值':>10s}  {'t-test p':>10s}")
print(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*10} {'-'*10}")
for name in feat_names:
    label = feat_labels.get(name, name)
    on_mean = X.loc[cb_on, name].mean()
    off_mean = X.loc[cb_off, name].mean()
    diff = on_mean - off_mean
    t, p = scipy_stats.ttest_ind(X.loc[cb_on, name].values, X.loc[cb_off, name].values)
    print(f"  {label:<20s} {on_mean:>12.4f}  {off_mean:>12.4f}  {diff:>+10.4f}  {p:>10.4f}")

# 3d. 2022 年专项
print("\n── 2022 年 vs 全样本对比 ──")
y2022 = y[y.index.year == 2022]
X2022 = X[X.index.isin(y2022.index)]
cb2022_pct = (y2022 > 0.0).sum() / len(y2022) * 100 if len(y2022) > 0 else 0.0

print(f"  2022 年: {len(y2022)} 天, smoothed_corr 均值 = {y2022.mean():.4f} (全期均值 = {y.mean():.4f})")
print(f"  2022 CB 触发%: {cb2022_pct:.1f}% (全期 = {(y > 0.0).sum()/len(y)*100:.1f}%)")
for name in feat_names:
    label = feat_labels.get(name, name)
    mean_2022 = X2022[name].mean()
    mean_all = X[name].mean()
    sigma_all = X[name].std()
    z_score = (mean_2022 - mean_all) / sigma_all if sigma_all > 0 else 0.0
    print(f"  {label}: 2022均值={mean_2022:+.4f}, 全期均值={mean_all:+.4f}, "
          f"偏离={mean_2022-mean_all:+.4f} ({z_score:+.2f} sigma)")

print("\n" + "=" * 60)
print("分析完成。因子贡献排序: " + " > ".join([f"{l}({c:.4f})" for l, c in contrib]))
print("=" * 60)
