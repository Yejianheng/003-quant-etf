# 执行指令

> 顾问写入。执行者只读、执行、写 outcome.md。

## 当前任务：每日数据更新脚本 + 一键运行串联

### 步骤 1：写数据更新脚本 → 红灯 → 绿灯

写 `tests/test_update_data.py`（3 场景）：

- parquet 存在 → 追加新数据 → 行数增加、无重复日期
- parquet 不存在 → 跳过不崩溃
- AKShare 返回空 → 跳过不崩溃

跑红后写 `scripts/update_data.py`：

```python
# 遍历 5 只 defense ETF parquet → fetch(最近10天) → 合并去重 → 存回
```

### 步骤 2：更新 run_daily.bat

```bat
@echo off
cd /d "d:\AI项目\003-quant-etf"
echo [1/2] 更新数据...
python scripts/update_data.py
echo.
echo [2/2] 生成信号...
python scripts/daily_signal.py
pause
```

### 验收

- `update_data.py` 3 测试全绿
- `run_daily.bat` 双击运行：先拉数据、再出信号
- 全量测试零回归

---

> 完成后写 outcome.md → 提示"请顾问窗口审查"。
