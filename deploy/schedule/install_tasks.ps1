<#
.SYNOPSIS
    注册本项目的五个定时任务（Windows 计划任务）。

.DESCRIPTION
    这五件事缺任何一件都是"安静的故障"（不会有人来报错，但备份/清理/注销到期都会悄悄失效）：
      1. backend_backup        每日备份数据库与 media
      2. backup_verify         每日校验最新备份可解压、可读
      3. health_snapshot       每日记录一条健康快照（管理端"14 天趋势"靠它）
      4. cleanup_media        每日清理孤儿图片
      5. process_deletions    每小时执行注销冷静期到期的账号

.USAGE
    # 以【管理员身份】运行（注册计划任务需要）
    powershell -ExecutionPolicy Bypass -File deploy\schedule\install_tasks.ps1
    powershell -ExecutionPolicy Bypass -File deploy\schedule\install_tasks.ps1 -Uninstall

.NOTES
    · 脚本用**绝对路径**注册，工作目录固定为 backend/（Django 命令依赖 cwd）；
    · 日志写到 deploy/schedule/logs/，出问题先看那里；
    · 默认用当前 conda 解释器（可用 -Python 指定）。
#>
param(
    [string]$Python = 'C:\Users\zhx\anaconda3\envs\crop_env\python.exe',
    [string]$TaskPrefix = 'CropDisease',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$backendDir = Join-Path $repoRoot 'backend'
$logDir = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$jobs = @(
    @{ Name = 'backup';         Cmd = 'backend_backup';          Schedule = 'DAILY'; At = '02:30' },
    @{ Name = 'verify';         Cmd = 'backup_verify';           Schedule = 'DAILY'; At = '03:10' },
    @{ Name = 'health';         Cmd = 'health_snapshot';         Schedule = 'DAILY'; At = '03:40' },
    @{ Name = 'media-cleanup';  Cmd = 'cleanup_media';           Schedule = 'DAILY'; At = '04:10' },
    @{ Name = 'deletions';      Cmd = 'process_deletions';       Schedule = 'HOURLY'; At = '' }
)

foreach ($job in $jobs) {
    $taskName = "$TaskPrefix-$($job.Name)"
    if ($Uninstall) {
        schtasks /Delete /TN $taskName /F 2>$null | Out-Null
        Write-Host "已删除任务 $taskName"
        continue
    }

    $logFile = Join-Path $logDir "$($job.Name).log"
    # 用 cmd /c 串起来：切目录 → 跑命令 → 追加日志（PowerShell 直接写会让引号转义很麻烦）
    $command = "cmd /c cd /d `"$backendDir`" ^&^& `"$Python`" manage.py $($job.Cmd) >> `"$logFile`" 2>&1"

    if ($job.Schedule -eq 'HOURLY') {
        schtasks /Create /TN $taskName /TR $command /SC HOURLY /MO 1 /F | Out-Null
    } else {
        schtasks /Create /TN $taskName /TR $command /SC DAILY /ST $job.At /F | Out-Null
    }
    Write-Host "已注册 $taskName（$($job.Schedule) $($job.At)）→ $logFile"
}

Write-Host ''
Write-Host '查看任务： schtasks /Query /TN CropDisease-backup /V /FO LIST'
Write-Host '立即试跑： schtasks /Run /TN CropDisease-backup'
