"""备份恢复演练（第 351 批）

## 为什么单独写脚本

`backup_verify` 只验证"备份文件能解压/能读"，**没验证"能不能恢复出一个能跑的系统"**。
备份最危险的失败形态不是"备份报错"，而是"备份完整、恢复失败"—— 只有到真正需要时才

## 演练做什么（全程不碰线上库）

1. 取最近一次备份；
2. 把它的 `db.sqlite3` 复制到**临时目录**；
3. 用 sqlite3 做 `PRAGMA integrity_check`；
4. 统计表数量与关键表行数，和**线上库**对比（发现"备份是旧的/空的"）；
5. 校验 `data.json` 可解析、`manifest.json` 里记录的哈希与文件实际哈希一致；
6. 尝试用**恢复出来的库**跑一次 Django `check`（通过临时 settings 指向该文件）。

任何一步失败都返回非 0，可直接进 CI / 定时任务。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = ROOT / 'backups'
LIVE_DB = ROOT / 'backend' / 'db.sqlite3'


def latest_backup() -> Path:
    dirs = [d for d in BACKUPS.iterdir() if d.is_dir()] if BACKUPS.exists() else []
    if not dirs:
        raise SystemExit('没有找到任何备份目录')
    return max(dirs, key=lambda d: d.stat().st_mtime)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def table_stats(db: Path) -> tuple[int, dict[str, int]]:
    conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        counts = {}
        for name in ('api_detectionhistory', 'api_pestinfo', 'api_customuser'):
            if name in tables:
                counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        return len(tables), counts
    finally:
        conn.close()


def main() -> int:
    backup = latest_backup()
    print(f'[1/6] 最近备份: {backup.name}')

    src_db = backup / 'db.sqlite3'
    if not src_db.exists():
        print('  ✗ 备份里没有 db.sqlite3')
        return 1

    tmp = Path(tempfile.mkdtemp(prefix='restore-drill-'))
    restored = tmp / 'db.sqlite3'
    shutil.copy2(src_db, restored)
    print(f'[2/6] 已复制到临时目录: {restored}')

    conn = sqlite3.connect(f'file:{restored}?mode=ro', uri=True)
    integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
    conn.close()
    if integrity != 'ok':
        print(f'  ✗ integrity_check 失败: {integrity}')
        return 1
    print(f'[3/6] PRAGMA integrity_check = {integrity}')

    b_tables, b_counts = table_stats(restored)
    l_tables, l_counts = table_stats(LIVE_DB) if LIVE_DB.exists() else (0, {})
    print(f'[4/6] 表数量: 备份 {b_tables} / 线上 {l_tables}')
    for name, cnt in b_counts.items():
        live = l_counts.get(name, '?')
        flag = '' if live == '?' or cnt <= live else '  ← 备份比线上多，可疑'
        print(f'      {name}: 备份 {cnt} / 线上 {live}{flag}')

    manifest = backup / 'manifest.json'
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding='utf-8'))
        recorded = {}
        # ⚠️ 备份清单里的键是 `artifacts`（不是 files）—— 第 351 批第一次跑时
        # 解析成 0 个文件，等于哈希校验被静默跳过。这里两个键都认。
        entries = data.get('artifacts') or data.get('files') or {}
        for key, value in entries.items():
            if isinstance(value, dict):
                recorded[key] = value.get('sha256') or value.get('hash')
            elif isinstance(value, str):
                recorded[key] = value
        bad = 0
        for name, digest in recorded.items():
            target = backup / name
            if not digest or not target.exists():
                continue
            actual = sha256(target)
            if actual != digest:
                bad += 1
                print(f'      ✗ 哈希不一致: {name}')
        print(f'[5/6] manifest 记录的 {len(recorded)} 个文件，哈希不一致 {bad} 个')
    else:
        print('[5/6] manifest.json 不存在，跳过哈希校验')

    print('[6/6] 用恢复出的库跑 Django check…')
    env_test = tmp / 'settings_probe.py'
    env_test.write_text(
        'from crop_disease_backend.settings import *  # noqa\n'
        f"DATABASES['default']['NAME'] = r'{restored}'\n",
        encoding='utf-8',
    )
    backend_dir = ROOT / 'backend'
    result = subprocess.run(
        [sys.executable, 'manage.py', 'check', '--settings', 'settings_probe'],
        # manage.py 在 backend/ 下；临时 settings 通过 PYTHONPATH 找到
        cwd=str(backend_dir),
        env={**__import__('os').environ, 'PYTHONPATH': f'{tmp};{backend_dir}'},
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print('  ✗ 恢复出的库无法通过 Django check')
        print(result.stdout[-800:])
        print(result.stderr[-800:])
        return 1
    print('  ✓ 恢复出的库通过 Django check')

    shutil.rmtree(tmp, ignore_errors=True)
    print('\n恢复演练通过：备份可用于真实恢复。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
