#!/usr/bin/env bash
# @claude-override-approved
# Stop Hook: 会话结束时清除 .claude/role.json，强制新会话从 step 0 开始
ROLE_FILE="$(dirname "$0")/../role.json"
rm -f "$ROLE_FILE"
