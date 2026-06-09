@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\pythonw.exe" main.py
) else (
    pythonw main.py 2>nul || python main.py
)
