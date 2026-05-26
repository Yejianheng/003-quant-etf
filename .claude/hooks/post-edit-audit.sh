#!/usr/bin/env bash
# 事后审计 PostToolUse Hook — 每次 Edit/Write 后检测违规
# 通用模板：硬编码凭证检测 + 单文件行数 + check_values.py 内容级校验
# 项目特定规则在下方标记处添加
set -euo pipefail
json=$(cat)
file=$(echo "$json" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path') or d.get('tool_response',{}).get('filePath') or '')" 2>/dev/null)
[ -z "$file" ] || [ ! -f "$file" ] && exit 0

v=""

# === 规则1: 禁硬编码凭证（通用）===
grep -qE '(sk-[a-zA-Z0-9]{20,}|sb_secret_[a-zA-Z0-9_-]{20,}|api_key\s*=\s*"[^"]{10,}")' "$file" 2>/dev/null && v="$v\n  [硬编码凭证] $file"

# === 规则2: 单文件行数限制（通用，可按项目调整阈值）===
# Python 默认 150，TypeScript 默认 250
LINE_LIMIT=250
case "$file" in
  *.py) LINE_LIMIT=150 ;;
  *.ts|*.tsx) LINE_LIMIT=250 ;;
esac
echo "$file" | grep -q "\.py$\|\.ts$\|\.tsx$" && [ "$(wc -l < "$file")" -gt "$LINE_LIMIT" ] && v="$v\n  [行数超限] $file: $(wc -l < "$file")行 (上限${LINE_LIMIT})"

# === 规则3: 内容级拦截 check_values.py（通用）===
CONTRACTS="protected-contracts.json"
if [ -f "$CONTRACTS" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] && v="$v\n$line"
  done < <(python check_values.py "$file" "$CONTRACTS" 2>/dev/null)
fi

# ═══════════════════════════════════════════════
# === 项目特定规则（在此处添加）===
# ═══════════════════════════════════════════════

# 示例 1: 禁止特定层直接调用数据库
# if echo "$file" | grep -qE "采集模块文件模式"; then
#   grep -q "database_direct_call" "$file" 2>/dev/null && v="$v\n  [分层越界] $file 直接调数据库"
# fi

# 示例 2: 禁止特定模块硬编码 Prompt
# echo "$file" | grep -q "llm_module" && grep -qE '(你是一位|请按照)' "$file" 2>/dev/null && v="$v\n  [Prompt硬编码] $file"

# ═══════════════════════════════════════════════

[ -n "$v" ] && echo -e "============================================\n[事后审计] 违规项：$v\n============================================"
exit 0
