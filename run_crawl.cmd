@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set PY=C:\Users\Eric\AppData\Local\Python\pythoncore-3.14-64\python.exe
if not exist "%PY%" set PY=python
"%PY%" crawl_competitors.py >> "%~dp0cache\crawl_log.txt" 2>&1
