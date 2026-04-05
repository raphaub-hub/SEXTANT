@echo off
cd /d "%~dp0"
echo.
echo  Starting Sextant — Backtest Engine...
echo  Your browser will open at http://localhost:8501
echo.
echo. | python -m streamlit run app.py
pause
