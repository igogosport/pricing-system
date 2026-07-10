@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "C:\Users\Eric\Desktop\Claude\pricing-system"
"C:\Users\Eric\AppData\Local\Python\pythoncore-3.14-64\python.exe" crawl_competitors.py >> "C:\Users\Eric\Desktop\Claude\pricing-system\cache\crawl_log.txt" 2>&1
