# [2026-06-18] 新增：因子归因模块 — 多因子 OLS 回归
import numpy as np
import pandas as pd


def factor_attribution(strategy_returns: pd.Series, factor_returns: pd.DataFrame) -> dict:
    """
    策略收益对因子收益做 OLS 多因子回归。

    R_strategy = α + Σ β_i × F_i + ε

    返回: {betas, alpha, r_squared, adj_r_squared, betas_se, t_values,
           factor_corr, n_obs, alpha_pvalue}
    """
    common_idx = strategy_returns.index.intersection(factor_returns.index)
    y = strategy_returns.loc[common_idx].dropna()
    X = factor_returns.loc[common_idx].dropna()

    common_idx = y.index.intersection(X.index)
    y = y.loc[common_idx].values
    X_mat = X.loc[common_idx].values
    factor_names = list(X.columns)
    n_obs = len(y)

    result = {
        "betas": {},
        "alpha": np.nan,
        "r_squared": np.nan,
        "adj_r_squared": np.nan,
        "betas_se": {},
        "t_values": {},
        "factor_corr": None,
        "n_obs": n_obs,
        "alpha_pvalue": np.nan,
    }

    if n_obs < len(factor_names) + 2:
        return result

    X_design = np.column_stack([np.ones(n_obs), X_mat])
    coeffs, residuals, rank, singular = np.linalg.lstsq(X_design, y, rcond=None)

    result["alpha"] = float(coeffs[0])
    for i, name in enumerate(factor_names):
        result["betas"][name] = float(coeffs[i + 1])

    y_pred = X_design @ coeffs
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))

    if ss_tot > 1e-15:
        result["r_squared"] = 1.0 - ss_res / ss_tot
        result["adj_r_squared"] = 1.0 - (1.0 - result["r_squared"]) * (n_obs - 1) / (n_obs - len(factor_names) - 1)
    else:
        result["r_squared"] = 0.0
        result["adj_r_squared"] = 0.0

    dof = n_obs - len(factor_names) - 1
    if dof > 0 and rank == len(factor_names) + 1:
        mse = ss_res / dof
        XtX_inv = np.linalg.inv(X_design.T @ X_design)
        se = np.sqrt(np.diag(XtX_inv) * mse)
        result["betas_se"]["alpha"] = float(se[0])
        t_alpha = coeffs[0] / se[0] if se[0] > 1e-15 else 0.0
        for i, name in enumerate(factor_names):
            s = float(se[i + 1])
            result["betas_se"][name] = s
            result["t_values"][name] = float(coeffs[i + 1] / s) if s > 1e-15 else 0.0

    result["factor_corr"] = X.corr()

    return result
