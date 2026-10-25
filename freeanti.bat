@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
    python "%~dp0freeanti.py" serve
) else (
    python "%~dp0freeanti.py" %*
)
