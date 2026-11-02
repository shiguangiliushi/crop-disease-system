@echo off
chcp 65001 >nul
cd /d "D:\新建文件夹\crop-disease-system\backend"
"C:\Users\zhx\anaconda3\envs\crop_env\python.exe" manage.py cleanup_media >> "D:\新建文件夹\crop-disease-system\deploy\schedule\logs\media-cleanup.log" 2>&1
