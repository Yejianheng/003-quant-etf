# [2026-05-29] 新增：步骤3 — 基于步骤1-2发现设计条件性激活规则

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(BASE, "output")


def load_features() -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, "regime_features.csv")
    return pd.read_csv(path)


def find_best_threshold(
    feature: pd.Series,
    labels: pd.Series,
    direction: str = "gt",
    n_steps: int = 50,
) -> dict:
    valid = feature.dropna()
    common = valid.index.intersection(labels.index)
    feature = feature.loc[common]
    labels = labels.loc[common]

    if len(feature) < 4:
        return {"best_threshold": 0.0, "best_accuracy": 0.5, "direction": direction}

    lo, hi = feature.min(), feature.max()
    if hi - lo < 1e-8:
        return {"best_threshold": float(lo), "best_accuracy": 0.5, "direction": direction}

    best_acc = 0.0
    best_thresh = float(lo)
    thresholds = np.linspace(lo, hi, n_steps)

    for t in thresholds:
        if direction == "gt":
            pred_out = feature > t
        else:
            pred_out = feature < t
        pred = pred_out.map({True: "outperform", False: "underperform"})
        acc = (pred == labels).mean()
        if acc > best_acc:
            best_acc = acc
            best_thresh = float(t)

    return {"best_threshold": best_thresh, "best_accuracy": float(best_acc), "direction": direction}


def evaluate_rule(
    feature_map: dict[str, pd.Series],
    labels: pd.Series,
    rule: dict[str, tuple],
) -> dict:
    mask = pd.Series(True, index=labels.index)
    for name, (op, thresh) in rule.items():
        if name not in feature_map:
            continue
        f = feature_map[name]
        if op == ">":
            mask = mask & (f > thresh)
        elif op == "<":
            mask = mask & (f < thresh)

    mask = mask & labels.notna()
    if mask.sum() == 0:
        return {"accuracy": 0.0, "coverage": 0.0, "true_pos": 0, "false_pos": 0, "total": len(labels)}

    pred = pd.Series("underperform", index=labels.index)
    pred[mask] = "outperform"
    common = labels.index.intersection(pred.index)
    acc = float((pred.loc[common] == labels.loc[common]).mean())
    coverage = float(mask.sum() / len(mask))

    tp = int(((pred == "outperform") & (labels == "outperform")).sum())
    fp = int(((pred == "outperform") & (labels == "underperform")).sum())
    return {"accuracy": acc, "coverage": coverage, "true_pos": tp, "false_pos": fp, "total": len(labels)}


def main():
    print("=== Step 3: Activation Rule Design ===\n")
    ft = load_features()

    labels_full = pd.Series(ft["regime"].values, index=range(len(ft)))
    features = {}
    for col in ["trend_mean", "volatility_mean", "offense_count_mean", "avg_correlation_mean"]:
        features[col] = pd.Series(ft[col].values, index=range(len(ft)))

    # 1. Single-feature threshold scan
    print("[1/3] Single-feature threshold scan:")
    directions = {
        "trend_mean": "gt",
        "volatility_mean": "lt",
        "offense_count_mean": "lt",
        "avg_correlation_mean": "lt",
    }
    best = {}
    for col, direction in directions.items():
        result = find_best_threshold(features[col], labels_full, direction=direction)
        best[col] = result
        short = col.replace("_mean", "")
        print(f"  {short:<22}: {direction} {result['best_threshold']:>8.4f}  acc={result['best_accuracy']:.2%}")

    # 2. Two-condition combinations
    print("\n[2/3] Two-condition rule combinations:")
    combos = [
        ("trend_mean > T AND offense_count_mean < T", {
            "trend_mean": (">", best["trend_mean"]["best_threshold"]),
            "offense_count_mean": ("<", best["offense_count_mean"]["best_threshold"]),
        }),
        ("offense_count_mean < T AND volatility_mean < T", {
            "offense_count_mean": ("<", best["offense_count_mean"]["best_threshold"]),
            "volatility_mean": ("<", best["volatility_mean"]["best_threshold"]),
        }),
        ("trend_mean > T AND avg_correlation_mean < T", {
            "trend_mean": (">", best["trend_mean"]["best_threshold"]),
            "avg_correlation_mean": ("<", best["avg_correlation_mean"]["best_threshold"]),
        }),
    ]
    for desc, rule in combos:
        result = evaluate_rule(features, labels_full, rule)
        print(f"  {desc:<55}: acc={result['accuracy']:.2%} cover={result['coverage']:.2%} "
              f"TP={result['true_pos']} FP={result['false_pos']}/{result['total']}")

    # 3. Recommended rule
    print("\n[3/3] Recommended rule:")
    rule_desc = (
        "if offense_count <= 2 and trend > 0: activate 30% offense\n"
        "else: 100% defense"
    )
    print(f"\n  {rule_desc}")
    rule = {
        "trend_mean": (">", best["trend_mean"]["best_threshold"]),
        "offense_count_mean": ("<", best["offense_count_mean"]["best_threshold"]),
    }
    result = evaluate_rule(features, labels_full, rule)
    print(f"  On regime labels: acc={result['accuracy']:.0%} cover={result['coverage']:.0%} "
          f"TP={result['true_pos']} FP={result['false_pos']}/{result['total']}")

    # Simple heuristic: offense_count <= 2
    simple_rule = {"offense_count_mean": ("<", 2.5)}
    sr = evaluate_rule(features, labels_full, simple_rule)
    print(f"  offense_count <= 2 only: acc={sr['accuracy']:.0%} cover={sr['coverage']:.0%} "
          f"TP={sr['true_pos']} FP={sr['false_pos']}/{sr['total']}")

    rules_path = os.path.join(OUTPUT_DIR, "activation_rules.json")
    import json
    rules_config = {
        "offense_count_threshold": int(round(best["offense_count_mean"]["best_threshold"])),
        "trend_threshold": round(float(best["trend_mean"]["best_threshold"]), 4),
        "offense_allocation": 0.3,
        "rule": "offense_count <= 2 AND trend > 0 -> 30% offense",
        "accuracy_on_regimes": result["accuracy"],
    }
    with open(rules_path, "w") as f:
        json.dump(rules_config, f, indent=2, ensure_ascii=False)
    print(f"\n  Rules saved to {rules_path}")
    print("\n=== Step 3 Complete ===")


if __name__ == "__main__":
    main()
