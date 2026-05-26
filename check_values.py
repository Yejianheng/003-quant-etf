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
    if violations:
        for v in violations:
            print(v)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
