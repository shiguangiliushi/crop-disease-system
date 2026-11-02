@echo off
chcp 65001 >nul
cd /d "D:\新建文件夹\crop-disease-system"
"C:\Users\zhx\anaconda3\envs\crop_env\python.exe" scripts\restore_drill.py >> "D:\新建文件夹\crop-disease-system\deploy\schedule\logs\restore-drill.log" 2>&1
