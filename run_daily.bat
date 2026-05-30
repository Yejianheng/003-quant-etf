@echo off
cd /d "d:\AI项目\003-quant-etf"
echo [1/2] 更新数据...
python scripts/update_data.py
echo.
echo [2/2] 生成信号...
python scripts/daily_signal.py
pause
