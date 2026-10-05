import os
import shutil

# 定义日志目录
log_dir = os.path.join(os.path.dirname(__file__), 'logs')

# 确保日志目录存在
if not os.path.exists(log_dir):
    print(f"日志目录 {log_dir} 不存在，无需删除日志文件")
    exit(0)

# 要删除的日志文件
log_files = ['django.log', 'error.log']

# 删除日志文件
for log_file in log_files:
    file_path = os.path.join(log_dir, log_file)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"已删除日志文件: {file_path}")
        else:
            print(f"日志文件不存在: {file_path}")
    except Exception as e:
        print(f"删除日志文件 {file_path} 时出错: {e}")

print("日志清理完成")
