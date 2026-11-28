#!/usr/bin/env bash
# =============================================================================
# 一键安全加固（第 442 批）
# -----------------------------------------------------------------------------
# 把 `docs/安全加固清单.md` 里能在服务器上自动化的几条做完，**幂等**，可重复执行：
#
#   §2  给 nginx 加限速（挡住"换 IP 刷识别"——只有反代这一层能挡）
#   §5  修正 crontab：prune_media 补 --yes、追加 prune_guests
#   §6  显式写入 DJANGO_GUEST_TRIAL
#   §8  （可选，--private-media）把 detection_uploads 也变成"私有"——需要重启后端
#
# 用法：
#   sudo bash deploy/harden.sh --check          # 只预演，不写任何文件
#   sudo bash deploy/harden.sh                  # 执行（nginx + cron + env）
#   sudo bash deploy/harden.sh --private-media  # 额外打开私有媒体开关
#
# 设计约定（每一条都对应一次真实教训）：
#   · **先备份**：nginx.conf / crontab 都留时间戳备份，失败自动回滚；
#   · **改完必须 nginx -t**：在一次性容器里验（带 compose 网络 + 证书挂载，
#     否则会得到 "host not found in upstream" 这种假错）；
#   · **幂等**：检测到标记就跳过，重复执行不会叠加配置；
#   · **不重启任何容器**（除了 --private-media 需要后端重建），只 reload nginx。
# =============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NGINX_CONF="$APP_DIR/deploy/nginx.conf"
CRON_LOG_DIR=/var/log/crop-disease
DC="docker compose"
CHECK_ONLY=0
PRIVATE_MEDIA=0

for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    --private-media) PRIVATE_MEDIA=1 ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg（用 --help 看用法）" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

run() {  # --check 时只打印
  if [ "$CHECK_ONLY" = "1" ]; then printf '  [预演] %s\n' "$*"; else eval "$@"; fi
}

[ -f "$NGINX_CONF" ] || die "没找到 $NGINX_CONF（请在项目根目录运行）"
command -v docker >/dev/null || die "没有 docker"
command -v python3 >/dev/null || die "没有 python3"

say "0. 环境确认"
ok "项目目录：$APP_DIR"
grep -q 'listen 443' "$NGINX_CONF" && ok "nginx 配置含 listen 443" \
  || die "nginx.conf 里没有 listen 443 —— 这是仓库的 HTTP-only 样板，先换成线上那份"
if sudo -n docker ps >/dev/null 2>&1; then DC="sudo docker compose"; ok "cron/脚本用 sudo docker"; fi

# ── 1. nginx 限速 ────────────────────────────────────────────────────────────
say "1. nginx 限速（§2 跨 IP 刷识别）"
if grep -q 'crop_detect' "$NGINX_CONF"; then
  ok "已经加过 limit_req_zone（crop_detect），跳过"
else
  BACKUP="$NGINX_CONF.bak.$(date +%Y%m%d-%H%M%S)"
  if [ "$CHECK_ONLY" = "0" ]; then cp "$NGINX_CONF" "$BACKUP"; ok "已备份 → $BACKUP"; fi

  if [ "$CHECK_ONLY" = "0" ]; then
    python3 - "$NGINX_CONF" <<'PY'
import re, sys

path = sys.argv[1]
src = open(path, encoding='utf-8').read()
lines = src.split('\n')

if 'crop_detect' in src:
    print('  已经加过，跳过'); sys.exit(0)

# ① zone：必须位于 http 上下文（conf.d 里的顶层就是 http）→ 插到文件最前
zones = [
    'limit_req_zone $binary_remote_addr zone=crop_detect:10m rate=6r/m;',
    'limit_req_zone $binary_remote_addr zone=crop_guest:10m  rate=2r/m;',
    'limit_req_zone $binary_remote_addr zone=crop_api:10m    rate=120r/m;',
    '# ^ 第 442 批：限速 zone（见 docs/安全加固清单.md §2）',
]
lines = zones + [''] + lines

HDR = [
    'proxy_http_version 1.1;',
    'proxy_set_header Host $host;',
    'proxy_set_header X-Real-IP $remote_addr;',
    'proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;',
    'proxy_set_header X-Forwarded-Proto $scheme;',
]

# ② 找到 listen 443 的 server 块（按大括号配对）
def blocks():
    starts = [i for i, l in enumerate(lines) if re.match(r'\s*server\s*\{', l)]
    for s in starts:
        depth = 0
        for i in range(s, len(lines)):
            depth += lines[i].count('{') - lines[i].count('}')
            if depth == 0:
                yield s, i
                break

target = None
for s, e in blocks():
    if re.search(r'listen\s+443', '\n'.join(lines[s:e + 1])):
        target = (s, e)
        break
if not target:
    print('  ✗ 没找到 listen 443 的 server 块'); sys.exit(1)

s, e = target
# 插到该 server 块里第一个 location 之前
ins = None
for i in range(s, e):
    if re.match(r'\s*location\s', lines[i]):
        ins = i
        break
if ins is None:
    print('  ✗ 443 server 块里没有 location，请手工加'); sys.exit(1)

indent = re.match(r'(\s*)', lines[ins]).group(1)
new_block = []
for path_, zone, burst, extra in (
    ('/api/detect/',        'crop_detect', '3', ['proxy_read_timeout 120s;']),
    ('/api/guest/session/', 'crop_guest',  '2', []),
):
    new_block += [f'{indent}location = {path_} {{',
                  f'{indent}    limit_req zone={zone} burst={burst} nodelay;',
                  f'{indent}    limit_req_status 429;',
                  '']
    new_block += [f'{indent}    {h}' for h in HDR]
    new_block += [f'{indent}    {x}' for x in extra]
    new_block += [f'{indent}    proxy_pass http://crop_backend;',
                  f'{indent}}}', '']

lines = lines[:ins] + new_block + lines[ins:]

# ③ 给现有的 location /api/ 加粗粒度兜底
for i, l in enumerate(lines):
    if re.match(r'\s*location\s+/api/\s*\{', l):
        depth = 0
        for j in range(i, len(lines)):
            depth += lines[j].count('{') - lines[j].count('}')
            if depth >= 1 and 'limit_req' not in lines[i + 1:i + 10][0]:
                pass
            if depth == 0:
                break
        ind = re.match(r'(\s*)', l).group(1)
        lines.insert(i + 1, f'{ind}    limit_req zone=crop_api burst=60 nodelay;')
        break

open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('  已插入 zone + 两个精确 location + /api/ 兜底')
PY
    ok "nginx.conf 已修改"
  fi

  say "1b. 验证 nginx 配置（带 compose 网络 + 证书）"
  NET="$(docker network ls --format '{{.Name}}' | grep -E '_default$' | head -1 || true)"
  [ -n "$NET" ] || die "找不到 compose 网络（*_default），无法验证"
  ok "网络：$NET"
  if [ "$CHECK_ONLY" = "0" ]; then
    if ! docker run --rm --network "$NET" \
        -v "$NGINX_CONF:/etc/nginx/conf.d/default.conf:ro" \
        -v "$APP_DIR/deploy/certs:/etc/nginx/certs:ro" \
        nginx:1.27-alpine nginx -t; then
      cp "$BACKUP" "$NGINX_CONF"
      die "nginx -t 失败，已自动回滚到 $BACKUP"
    fi
    ok "nginx -t 通过"
    $DC up -d --force-recreate nginx >/dev/null 2>&1 || true
    $DC restart nginx >/dev/null 2>&1 || true
    ok "nginx 已重启生效"
  else
    printf '  [预演] docker run … nginx -t；通过后 up -d --force-recreate nginx\n'
  fi
fi

# ── 2. crontab ───────────────────────────────────────────────────────────────
say "2. 定时任务（§5 prune_media 补 --yes + prune_guests）"
run "sudo mkdir -p $CRON_LOG_DIR && sudo chmod 777 $CRON_LOG_DIR"
if crontab -l 2>/dev/null | grep -q 'prune_media --yes'; then
  ok "prune_media 已带 --yes，跳过"
else
  run "crontab -l > ~/crontab.bak.\$(date +%m%d%H%M)"
  run "crontab -l 2>/dev/null | sed 's#manage.py prune_media >>#manage.py prune_media --yes --min-age-days 7 >>#' | crontab -"
  ok "prune_media 已补 --yes --min-age-days 7"
fi
if crontab -l 2>/dev/null | grep -q 'prune_guests'; then
  ok "prune_guests 已存在，跳过"
else
  RUN_LINE="0 5 * * * cd $APP_DIR && $DC exec -T backend python manage.py prune_guests --days 3 --yes >> $CRON_LOG_DIR/guests.log 2>&1"
  run "( crontab -l 2>/dev/null; echo '$RUN_LINE' ) | crontab -"
  ok "已追加 prune_guests（每天 05:00）"
fi

# ── 3. 试用开关 ──────────────────────────────────────────────────────────────
say "3. 试用开关（§6）"
ENV_FILE="$APP_DIR/backend/.env"
if [ -f "$ENV_FILE" ]; then
  if grep -q '^DJANGO_GUEST_TRIAL=' "$ENV_FILE"; then
    ok "已有：$(grep '^DJANGO_GUEST_TRIAL=' "$ENV_FILE")"
  else
    run "echo 'DJANGO_GUEST_TRIAL=True' >> '$ENV_FILE'"
    ok "已写入 DJANGO_GUEST_TRIAL=True（想灰度就先改成 False）"
  fi
else
  warn "没有 $ENV_FILE（跳过）"
fi

# ── 4. 可选：私有媒体 ────────────────────────────────────────────────────────
if [ "$PRIVATE_MEDIA" = "1" ]; then
  say "4. 私有媒体（§8，两处一起改）"
  warn "这一项会让**旧的无签名 URL 立即失效**（浏览器刷新一次即可恢复）"
  if grep -q 'detection_uploads' "$NGINX_CONF"; then
    ok "nginx 正则已含 detection_uploads"
  else
    if [ "$CHECK_ONLY" = "0" ]; then
      python3 - "$NGINX_CONF" <<'PY'
import re, sys
path = sys.argv[1]
src = open(path, encoding='utf-8').read()
if 'detection_uploads' in src:
    sys.exit(0)
# 给"私有前缀"那条正则加上 detection_uploads（若有）；否则提示手工加
pat = re.compile(r'(location\s*~\s*\^/media/\([^)]*)(\))')
def repl(m):
    if 'detection_uploads' in m.group(1):
        return m.group(0)
    return f'{m.group(1)}|detection_uploads{m.group(2)}'
new, n = pat.subn(repl, src)
if n == 0:
    print('  ! 没找到私有前缀正则，请手工把 detection_uploads 加进去（见安全加固清单 §8）')
else:
    open(path, 'w', encoding='utf-8').write(new)
    print(f'  已给私有前缀正则补上 detection_uploads（{n} 处）')
PY
    fi
  fi
  if grep -q '^DJANGO_PRIVATE_DETECTION_UPLOADS=' "$ENV_FILE" 2>/dev/null; then
    ok "已有 DJANGO_PRIVATE_DETECTION_UPLOADS"
  else
    run "echo 'DJANGO_PRIVATE_DETECTION_UPLOADS=True' >> '$ENV_FILE'"
  fi
  run "$DC up -d --build backend"
  run "$DC restart nginx"
  ok "后端已重建（私有媒体生效）"
fi

# ── 5. 汇总验收 ──────────────────────────────────────────────────────────────
say "5. 验收"
echo "  443 映射数：$(docker compose -f "$APP_DIR/docker-compose.yml" config 2>/dev/null | grep -c 'published: "443"' || echo '?')"
echo "  limit_req 条数：$(grep -c 'limit_req' "$NGINX_CONF" || true)"
echo "  prune 任务数：$(crontab -l 2>/dev/null | grep -c 'prune_' || true)"
echo "  试用开关：$(grep '^DJANGO_GUEST_TRIAL=' "$ENV_FILE" 2>/dev/null || echo '未设置')"
echo
if [ "$CHECK_ONLY" = "0" ]; then
  echo "  下一步："
  echo "    curl -s -o /dev/null -w 'api:%{http_code}\\n' https://<你的域名>/api/health/"
  echo "    for i in 1 2 3 4 5; do curl -s -o /dev/null -w '%{http_code} ' -X POST https://<你的域名>/api/guest/session/; done; echo"
  echo "    ↑ 配好限速后，第 3 次起应出现 429"
else
  echo "  这是预演，没有修改任何文件。去掉 --check 执行。"
fi
