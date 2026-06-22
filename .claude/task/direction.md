# 执行指令

> 2026-06-22 | 巡检 — 跑数据校验，确认管线健康

## 操作

依次执行，输出贴到 outcome。

### 1. 数据校验

```bash
python scripts/verify_data.py
```

### 2. 增量更新 + 校验

```bash
python scripts/update_data.py
```

### 3. 抽查 parquet 元信息

```bash
python -c "
import os, pandas as pd
from src.etf_universe import ETF_UNIVERSE
from src.data_pipeline import load_from_parquet
for name, code in ETF_UNIVERSE.items():
    path = os.path.join('data', f'{code}.parquet')
    if os.path.exists(path):
        df = load_from_parquet(path)
        print(f'{name} ({code}): {len(df)} 行, {df.index.min().date()} ~ {df.index.max().date()}, NaN={df.close.isna().sum()}')
    else:
        print(f'{name} ({code}): 文件缺失')
"
```

## 输出要求

outcome.md 贴三段命令的原始输出，不做分析。如全部通过则写"管线健康"，有告警则标注。
