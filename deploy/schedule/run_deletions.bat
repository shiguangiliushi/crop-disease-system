@echo off
chcp 65001 >nul
cd /d "D:\新建文件夹\crop-disease-system\backend"
"C:\Users\zhx\anaconda3\envs\crop_env\python.exe" manage.py process_deletions >> "D:\新建文件夹\crop-disease-system\deploy\schedule\logs\deletions.log" 2>&1
