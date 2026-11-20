<#
.SYNOPSIS
    注册本项目的五个定时任务（Windows 计划任务）。

.DESCRIPTION
    这五件事缺任何一件都是"安静的故障"（不会有人来报错，但备份/清理/注销到期都会悄悄失效）：
      1. backend_backup        每日备份数据库与 media
      2. backup_verify         每日校验最新备份可解压、可读
      3. health_snapshot       每日记录一条健康快照（管理端"14 天趋势"靠它）
      4. prune_media        每日清理孤儿图片
      5. purge_deletion_requests    每小时执行注销冷静期到期的账号

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
    @{ Name = 'media-cleanup';  Cmd = 'prune_media';           Schedule = 'DAILY'; At = '04:10' },
    @{ Name = 'deletions';      Cmd = 'purge_deletion_requests';       Schedule = 'HOURLY'; At = '' },
    @{ Name = 'restore-drill';  Cmd = 'restore-drill';           Schedule = 'DAILY'; At = '04:40' }
)

foreach ($job in $jobs) {
    $taskName = "$TaskPrefix-$($job.Name)"
    if ($Uninstall) {
        schtasks /Delete /TN $taskName /F 2>$null | Out-Null
        Write-Host "已删除任务 $taskName"
        continue
    }

    # 第 352 批：**改用 .bat 包装脚本**。
    # 原来把 `cmd /c cd /d ... ^&^& ...` 整条塞进 /TR，而 `^&^&` 是 cmd 交互式的转义，
    # schtasks 存进去后不按 cmd 规则解释 → 运行时报
    # "The filename, directory name, or volume label syntax is incorrect."，
    # 任务显示 Ready 却一次都没真正执行。现在 /TR 只指向 .bat，无 cd、无引号嵌套。
    $bat = Join-Path $PSScriptRoot ("run_{0}.bat" -f $job.Name)
    if (-not (Test-Path $bat)) {
        Write-Warning "缺少包装脚本：$bat（跳过 $taskName）"
        continue
    }
    $command = '"' + $bat + '"'

    if ($job.Schedule -eq 'HOURLY') {
        schtasks /Create /TN $taskName /TR $command /SC HOURLY /MO 1 /F | Out-Null
    } else {
        schtasks /Create /TN $taskName /TR $command /SC DAILY /ST $job.At /F | Out-Null
    }

    # 第 422 批：**这三个选项决定"任务会不会真的跑"**，schtasks 的默认值有一半是错的。
    #
    #   · `DisallowStartIfOnBatteries` 默认 **true** —— 笔记本拔了电源，到点直接不启动；
    #   · `StopIfGoingOnBatteries` 默认 true —— 跑到一半拔电源会被掐掉（备份写一半最糟）；
    #   · `StartWhenAvailable` 默认 **false** —— 机器关机错过的那次不会补跑。
    #
    # 实测事故：2026-11-15 之后连续 5 天没有备份，管理端健康检查报
    # "最新备份已 5.9 天前：定时任务可能没跑"，任务本身却一直显示 Ready。
    # `Last Result` 是 `0x80070520`（没有登录会话）—— 任务根本没被启动过。
    #
    # ⚠️ `Set-ScheduledTask` 需要**管理员**权限；本脚本本来就要管理员（注册任务就得要）。
    try {
        $taskSettings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        Set-ScheduledTask -TaskName $taskName -Settings $taskSettings -ErrorAction Stop | Out-Null
    } catch {
        Write-Warning "设置 $taskName 的电源/补跑选项失败：$($_.Exception.Message)"
    }
    Write-Host "已注册 $taskName"
}

Write-Host ''
Write-Host '查看任务： schtasks /Query /TN CropDisease-backup /V /FO LIST'
Write-Host '立即试跑： schtasks /Run /TN CropDisease-backup'
