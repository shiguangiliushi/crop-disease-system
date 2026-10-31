# 定时任务安装（第 291 批）

这五件事**缺任何一件都是"安静的故障"**：不会有人来报错，但备份、校验、健康趋势、
孤儿图片清理、注销到期执行都会悄悄失效。

| 任务 | 频率 | 作用 |
|---|---|---|
| `backend_backup` | 每日 02:30 | 备份数据库与 media |
| `backup_verify` | 每日 03:10 | 校验最新备份可解压、可读（备份没验证过 = 没备份） |
| `health_snapshot` | 每日 03:40 | 记一条健康快照，管理端「14 天趋势」靠它；缺的那天会画灰格 |
| `cleanup_media` | 每日 04:10 | 清理孤儿图片 |
| `process_deletions` | 每小时 | 执行注销冷静期到期的账号 |

## Windows

```powershell
# 管理员身份
powershell -ExecutionPolicy Bypass -File deploy\schedule\install_tasks.ps1
# 卸载
powershell -ExecutionPolicy Bypass -File deploy\schedule\install_tasks.ps1 -Uninstall
```

- 默认使用 `C:\Users\zhx\anaconda3\envs\crop_env\python.exe`，可用 `-Python` 覆盖；
- 日志写到 `deploy/schedule/logs/*.log`；
- 立即试跑：`schtasks /Run /TN CropDisease-backup`。

## Linux

```bash
crontab -e          # 粘贴 crontab.example 内容，按实际路径改 PY / APP / LOG
crontab -l          # 确认
```

## 验证是否真的在执行

```powershell
# 1) 任务是否存在
schtasks /Query /TN CropDisease-backup /V /FO LIST

# 2) 今天有没有留下产物
cd backend && python manage.py backup_verify   # 应报告"最新备份可读"

# 3) 健康趋势是否在长
#    管理端 → 系统健康 → 14 天趋势：有绿点说明快照任务在跑
```
