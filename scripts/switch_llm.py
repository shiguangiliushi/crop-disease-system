"""LLM 模型切换与连通性检查（第 359 批）

## 为什么需要这个脚本

`api/assistant/llm.py` 是纯 OpenAI 兼容实现（`requests.post` 打 `/chat/completions`），
换模型只要改 4 个环境变量。**但改完后最常见的问题不是"报错"，而是"静默降级"**：

配置写错（模型名不对 / 额度用完 / URL 少了 `/v1`）时，助手不会 500，
而是**降级成词条原文**——界面上只是引用变少、回答变短，用户和开发者都很难察觉。

所以这个脚本除了切配置，还负责**发一条最小请求真实验证**。

## 用法

    # 看当前配置是否可用（会真的打一次 API）
    python scripts/switch_llm.py --check

    # 切到智谱 GLM-4-Flash（免费额度）
    python scripts/switch_llm.py --provider zhipu --key <你的key>

    # 只打印将写入的内容，不动文件、不发请求
    python scripts/switch_llm.py --provider qwen --dry-run

    # 临时覆盖模型/地址
    python scripts/switch_llm.py --provider deepseek --model deepseek-reasoner

## 写到哪里

`backend/.env`（该文件已在 .gitignore 中）。已存在的同名键会**原地替换**，
不会重复追加，也不会动其他配置。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / 'backend' / '.env'

#: 已知的 OpenAI 兼容服务。`model` 是可用的默认值；豆包需要用户自己创建接入点。
PROVIDERS = {
    'deepseek': {
        'url': 'https://api.deepseek.com/v1',
        'model': 'deepseek-chat',
        'note': '当前方案；deepseek-chat 便宜、中文好',
    },
    'zhipu': {
        'url': 'https://open.bigmodel.cn/api/paas/v4',
        'model': 'glm-4-flash',
        'note': 'glm-4-flash 免费额度，国内访问快',
    },
    'qwen': {
        'url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'model': 'qwen-plus',
        'note': '通义千问；qwen-turbo 更便宜',
    },
    'kimi': {
        'url': 'https://api.moonshot.cn/v1',
        'model': 'moonshot-v1-8k',
        'note': '长上下文',
    },
    'openrouter': {
        'url': 'https://openrouter.ai/api/v1',
        'model': 'deepseek/deepseek-chat',
        'note': '一个 key 调多家模型（模型名要写全路径）',
    },
    'ollama': {
        'url': 'http://127.0.0.1:11434/v1',
        'model': 'qwen2.5:7b',
        'note': '本地推理：免费、数据不出机器；需先 ollama serve',
    },
}


def read_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if not ENV_PATH.exists():
        return data
    for line in ENV_PATH.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        data[key.strip()] = value.strip()
    return data


def write_env(updates: dict[str, str], dry_run: bool = False) -> None:
    """原地更新 .env 的指定键；保留其他行与注释。"""
    lines = ENV_PATH.read_text(encoding='utf-8').splitlines() if ENV_PATH.exists() else []
    remaining = dict(updates)
    out = []
    for line in lines:
        stripped = line.strip()
        if '=' in stripped and not stripped.startswith('#'):
            key = stripped.split('=', 1)[0].strip()
            if key in remaining:
                out.append(f'{key}={remaining.pop(key)}')
                continue
        out.append(line)
    if remaining:
        out.append('')
        out.append('# ── LLM（由 scripts/switch_llm.py 写入）──')
        out.extend(f'{k}={v}' for k, v in remaining.items())

    content = '\n'.join(out).rstrip('\n') + '\n'
    if dry_run:
        print('--- 将写入 backend/.env（未落盘）---')
        for key, value in updates.items():
            shown = value if key != 'LLM_API_KEY' else (value[:6] + '***' if value else '(空)')
            print(f'  {key}={shown}')
        return
    ENV_PATH.write_text(content, encoding='utf-8')
    print(f'已写入 {ENV_PATH}')


def check(url: str, key: str, model: str, timeout: float = 20.0) -> bool:
    """发一条最小请求验证连通性。成功返回 True。"""
    endpoint = url.rstrip('/') + '/chat/completions'
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': '回复"ok"两个字即可'}],
        'max_tokens': 8,
        'stream': False,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'},
        method='POST',
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', 'replace')[:300]
        print(f'  ✗ HTTP {exc.code}：{detail}')
        return False
    except Exception as exc:  # noqa: BLE001
        print(f'  ✗ 请求失败：{exc}')
        return False

    elapsed = (time.perf_counter() - started) * 1000
    actual = (body.get('model') or model)
    usage = body.get('usage') or {}
    print(f'  ✓ 可用 | 实际模型: {actual} | 耗时 {elapsed:.0f}ms | usage: {usage or "未返回"}')
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description='切换 / 检查 LLM 配置（OpenAI 兼容服务）')
    parser.add_argument('--provider', choices=sorted(PROVIDERS), help='预设服务商')
    parser.add_argument('--key', help='API Key（写入 LLM_API_KEY）')
    parser.add_argument('--model', help='覆盖模型名')
    parser.add_argument('--url', help='覆盖 API 地址')
    parser.add_argument('--max-tokens', type=int, default=2000,
                        help='LLM_MAX_TOKENS（默认 2000：本项目回答常 1400+ 字）')
    parser.add_argument('--check', action='store_true', help='只验证当前配置是否可用')
    parser.add_argument('--dry-run', action='store_true', help='只打印，不写文件、不发请求')
    parser.add_argument('--list', action='store_true', help='列出所有预设服务商')
    args = parser.parse_args()

    if args.list:
        for name, meta in PROVIDERS.items():
            print(f'{name:11} {meta["url"]:52} {meta["model"]:26} {meta["note"]}')
        return 0

    current = read_env()
    env_url = os.environ.get('LLM_API_URL') or current.get('LLM_API_URL', '')
    env_key = os.environ.get('LLM_API_KEY') or current.get('LLM_API_KEY', '')
    env_model = os.environ.get('LLM_MODEL') or current.get('LLM_MODEL', '')

    if args.check:
        print('检查当前配置…')
        print(f'  LLM_API_URL = {env_url or "(未设置)"}')
        print(f'  LLM_MODEL   = {env_model or "(未设置)"}')
        print(f'  LLM_API_KEY = {"(已设置)" if env_key else "(未设置)"}')
        if not (env_url and env_key and env_model):
            print('  ✗ 配置不完整（缺 URL / KEY / MODEL），助手会一直走降级')
            return 1
        return 0 if check(env_url, env_key, env_model) else 1

    if not args.provider:
        parser.error('需要 --provider 或 --check（用 --list 看可用服务商）')

    preset = PROVIDERS[args.provider]
    updates = {
        'LLM_ENABLED': 'True',
        'LLM_API_URL': args.url or preset['url'],
        'LLM_MODEL': args.model or preset['model'],
        'LLM_MAX_TOKENS': str(args.max_tokens),
    }
    if args.key:
        updates['LLM_API_KEY'] = args.key
    elif env_key:
        updates['LLM_API_KEY'] = env_key
    else:
        print('⚠️ 没有提供 --key，也没有现成的 LLM_API_KEY；切换后助手将无法调用模型')
        updates['LLM_API_KEY'] = env_key

    print(f'切换到 {args.provider}（{preset["note"]}）')
    write_env(updates, dry_run=args.dry_run)

    if args.dry_run:
        print('（--dry-run：未发请求）')
        return 0

    if not updates['LLM_API_KEY']:
        print('⚠️ 缺少 API Key，跳过连通性检查')
        return 0

    print('验证连通性（发一条 8 token 的最小请求）…')
    ok = check(updates['LLM_API_URL'], updates['LLM_API_KEY'], updates['LLM_MODEL'])
    print()
    if ok:
        print('完成。重启后端即生效：python manage.py runserver')
    else:
        print('写入已完成，但**连通性检查失败** —— 现在换回原配置或检查 key/模型名。')
        print('注意：配置不对时助手不会报错，只会静默降级成词条原文。')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
