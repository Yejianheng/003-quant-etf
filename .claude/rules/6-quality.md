# 质量保证与测试

## 测试要求

- 核心逻辑修改需同步更新/新增测试用例。
- 测试框架：[Jest / PyTest / 其他]

## 构建要求

- 提交代码前，必须确保本地运行构建/类型检查零报错。
- 构建命令：`[npm run build / npx tsc --noEmit / 其他]`
- Lint 命令：`[eslint / ruff / 其他]`

## AI 质量门禁

- LLM 输出失败降级策略：[重试次数 + temperature 调整]
- 人工介入条件：[何时标记 status=review]
