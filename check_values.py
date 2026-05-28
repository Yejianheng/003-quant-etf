"""
模块归属：工具层 / 内容级防篡改校验
职责：读取 protected-contracts.json，校验目标文件是否保留已确认常量、不含禁止模式
用法：python check_values.py <target_file> <contracts_json>
退出码：0=合规, 1=违规
依赖：protected-contracts.json
"""
import json
import re
import ast
import sys
import os


def load_contracts(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_values(target: str, contracts: dict) -> list[str]:
    basename = os.path.basename(target)
    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
    violations = []
    for entry in contracts.get("values", []):
        if os.path.basename(entry.get("file", "")) != basename:
            continue
        expected = entry.get("value", "")
        if expected not in content:
            violations.append(
                f"[常量篡改] {basename}: {entry.get('key', '?')}"
                f" 预期值 '{expected[:60]}' 丢失"
                f" — {entry.get('reason', '')[:80]}"
            )
    return violations


def check_patterns(target: str, contracts: dict) -> list[str]:
    basename = os.path.basename(target)
    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
    violations = []
    for entry in contracts.get("patterns", []):
        pattern = entry.get("pattern", "")
        try:
            if re.search(pattern, content):
                violations.append(
                    f"[禁止模式] {basename}: {pattern[:60]}"
                    f" — {entry.get('reason', '')[:80]}"
                )
        except re.error:
            violations.append(f"[模式错误] 正则无效: {pattern[:60]}")
    return violations


def check_offense_pool(target: str, contracts: dict) -> list[str]:
    """校验 src/etf_universe.py 的 OFFENSE_POOL 符合方向性讨论三层架构硬约束"""
    pool_cfg = contracts.get("offense_pool", {})
    target_file = pool_cfg.get("file", "")
    if os.path.basename(target) != os.path.basename(target_file):
        return []
    try:
        with open(target, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except SyntaxError:
        return ["[AST错误] 无法解析 etf_universe.py"]
    violations = []

    # 查找 OFFENSE_POOL 和 ETF_UNIVERSE 的 AST 节点
    offense_assign = None
    defense_assign = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "OFFENSE_POOL":
                    offense_assign = node
                if isinstance(t, ast.Name) and t.id == pool_cfg.get("defensive_var", "ETF_UNIVERSE"):
                    defense_assign = node

    if offense_assign is None:
        return ["[OFFENSE_POOL] 在 etf_universe.py 中未找到"]

    # 提取 OFFENSE_POOL 字典
    try:
        pool = ast.literal_eval(offense_assign.value)
    except (ValueError, TypeError):
        return ["[OFFENSE_POOL] 无法解析为静态字典，禁止使用变量拼接"]

    if not isinstance(pool, dict):
        return [f"[OFFENSE_POOL] 必须为 dict，实际为 {type(pool).__name__}"]

    required = pool_cfg.get("required_sources", [])
    min_c = pool_cfg.get("min_candidates", 1)
    max_c = pool_cfg.get("max_candidates", 3)

    # 检查风险源名称完全匹配
    actual_sources = set(pool.keys())
    expected_sources = set(required)
    if actual_sources != expected_sources:
        missing = expected_sources - actual_sources
        extra = actual_sources - expected_sources
        if missing:
            violations.append(f"[OFFENSE_POOL] 缺少风险源: {missing}")
        if extra:
            violations.append(f"[OFFENSE_POOL] 多余风险源: {extra}")

    # 检查每风险源结构
    all_offense_codes = set()
    for source_name in actual_sources:
        entry = pool.get(source_name, {})
        if not isinstance(entry, dict):
            violations.append(f"[OFFENSE_POOL] {source_name}: 值必须为 dict，实际 {type(entry).__name__}")
            continue
        code = entry.get("code", "")
        candidates = entry.get("candidates", [])
        if not isinstance(code, str) or not code.isdigit():
            violations.append(f"[OFFENSE_POOL] {source_name}: code 必须为纯数字字符串")
        if not isinstance(candidates, list):
            violations.append(f"[OFFENSE_POOL] {source_name}: candidates 必须为 list")
        else:
            n = len(candidates)
            if n < min_c or n > max_c:
                violations.append(f"[OFFENSE_POOL] {source_name}: candidates 数量 {n}，要求 {min_c}-{max_c}")
            for c in candidates:
                if isinstance(c, str) and c.isdigit():
                    all_offense_codes.add(c)

    # 检查与防御层重叠
    if defense_assign is not None:
        try:
            defense = ast.literal_eval(defense_assign.value)
            if isinstance(defense, dict):
                defense_codes = set(v for v in defense.values() if isinstance(v, str) and v.isdigit())
                overlap = all_offense_codes & defense_codes
                if overlap:
                    violations.append(f"[OFFENSE_POOL] 候选 ETF 代码与 ETF_UNIVERSE 重叠: {overlap}")
        except (ValueError, TypeError):
            pass

    return violations


def check_ast_constants(target: str, contracts: dict) -> list[str]:
    basename = os.path.basename(target)
    if not basename.endswith(".py"):
        return []
    try:
        with open(target, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except SyntaxError:
        return []
    const_assigns = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    try:
                        val = ast.literal_eval(node.value)
                        const_assigns[t.id] = str(val)
                    except (ValueError, TypeError):
                        pass
    violations = []
    for entry in contracts.get("values", []):
        if os.path.basename(entry.get("file", "")) != basename:
            continue
        key = entry.get("key", "")
        var_name = key.split(".", 1)[0]
        if var_name in const_assigns:
            expected = entry.get("value", "")
            if expected not in const_assigns[var_name]:
                violations.append(
                    f"[AST篡改] {basename}:{var_name}"
                    f" 预期含'{expected}'"
                    f" — {entry.get('reason', '')[:80]}"
                )
    return violations


def main():
    if len(sys.argv) < 2:
        print("用法: python check_values.py <target_file> [contracts_json]")
        sys.exit(0)
    target = sys.argv[1]
    contracts_path = sys.argv[2] if len(sys.argv) > 2 else "protected-contracts.json"
    if not os.path.exists(target) or not os.path.exists(contracts_path):
        sys.exit(0)
    contracts = load_contracts(contracts_path)
    violations = []
    violations.extend(check_values(target, contracts))
    violations.extend(check_patterns(target, contracts))
    violations.extend(check_ast_constants(target, contracts))
    violations.extend(check_offense_pool(target, contracts))
    if violations:
        for v in violations:
            print(v)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
