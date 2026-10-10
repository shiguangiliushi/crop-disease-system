#!/usr/bin/env python
"""
推送并**核对**（第 152 批）

## 为什么需要它

`git push` 失败时 PowerShell 里会打出 `NativeCommandError`，而**成功时也会**
（git 的进度输出走 stderr）—— 光看屏幕分不出来。第 152 批我就因此写出一句
"✅ 工作区干净，且已同步"，而那次推送其实**根本没成功**（github.com:443 连不上）。
这正是我最警惕的"假绿灯"：结论来自"命令没报错"，而不是"事实核对过"。

这个脚本只有一个职责：**推完之后，拿远端的 ref 和本地 HEAD 比一次，并如实报告。**

用法：
    python docs/tools/push_and_verify.py                     # 推当前分支
    python docs/tools/push_and_verify.py --branch main
    python docs/tools/push_and_verify.py --proxy http://127.0.0.1:33210
    python docs/tools/push_and_verify.py --proxy auto        # 探测常见本地代理端口

退出码：0 = 远端已等于本地；1 = 没推上去（脚本会说明还差几个提交）。
"""
import argparse
import re
import socket
import subprocess
import sys

#: 常见代理端口（Clash / v2ray / 其它），仅用于 `--proxy auto` 探测
COMMON_PROXY_PORTS = (7890, 7891, 7897, 10808, 10809, 1080, 8889, 2080, 33210)


def run(args, cwd=None):
    """跑一条命令，返回 (退出码, 合并后的输出)"""
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    return proc.returncode, ((proc.stdout or '') + (proc.stderr or '')).strip()


def detect_proxy():
    """探测本机在监听的常见代理端口，返回 http://127.0.0.1:<port> 或 None"""
    for port in COMMON_PROXY_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return f'http://127.0.0.1:{port}'
    return None


def main():
    parser = argparse.ArgumentParser(description='推送并核对远端是否等于本地')
    parser.add_argument('--branch', default=None, help='分支名（默认当前分支）')
    parser.add_argument('--remote', default='origin')
    parser.add_argument('--proxy', default=None,
                        help='推送用的代理，如 http://127.0.0.1:33210；auto = 自动探测')
    args = parser.parse_args()

    code, branch = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if code != 0:
        print('❌ 取不到当前分支：', branch)
        return 1
    branch = args.branch or branch.strip()

    code, local_head = run(['git', 'rev-parse', 'HEAD'])
    local_head = local_head.strip()

    # 待推的提交数（本地领先多少）——先算出来，推送失败时直接告诉用户
    pending = run(['git', 'rev-list', '--count', f'{args.remote}/{branch}..HEAD'])[1].strip()

    push_cmd = ['git']
    proxy = args.proxy
    if proxy == 'auto':
        proxy = detect_proxy()
        print(f'（自动探测到本地代理：{proxy or "无"}）')
    if proxy:
        # 只对这一次命令生效，不动用户的全局 git 配置
        push_cmd += ['-c', f'http.proxy={proxy}', '-c', f'https.proxy={proxy}']
    push_cmd += ['push', args.remote, branch]

    print(f'推送 {args.remote}/{branch}（本地领先 {pending or "?"} 个提交）…')
    code, output = run(push_cmd)
    pushed = bool(re.search(rf'{branch} -> {branch}|Everything up-to-date', output))
    if not pushed:
        print(output[-800:] if output else '（无输出）')
        print(f'\n❌ 推送没成功 —— 这 {pending or "?"} 个提交仍在本地，远端未更新。')
        print('   常见原因：github.com:443 连不上（网络阻断）。可选：')
        print('     ① 打开代理软件后重跑：--proxy auto')
        print('     ② 稍后重试（这类阻断常常是间歇性的）')
        print('     ③ 配 SSH key 走 22 端口（实测 22 端口可达）')
        return 1

    # 关键一步：以**远端实际的 ref** 为准，而不是"命令没报错"
    code, remote_ref = run(['git', 'ls-remote', args.remote, f'refs/heads/{branch}'])
    if code != 0 or not remote_ref:
        print('⚠️ 推送命令看似成功，但读不到远端 ref（网络问题或权限问题）。')
        print('   请稍后重跑本脚本确认；不要据此认为"已同步"。')
        return 1
    remote_head = remote_ref.split()[0]

    if remote_head != local_head:
        print(f'❌ 不一致：本地 {local_head[:8]} ≠ 远端 {remote_head[:8]}')
        return 1

    print(f'✅ 远端已等于本地：{local_head[:8]}（{args.remote}/{branch}）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
