@echo off
chcp 65001 >nul
cd /d "D:\新建文件夹\crop-disease-system\backend"
"C:\Users\zhx\anaconda3\envs\crop_env\python.exe" manage.py backup_verify >> "D:\新建文件夹\crop-disease-system\deploy\schedule\logs\verify.log" 2>&1
