# Django 配置
# ============================================================================
# **本文件按"环境变量优先"组织**：几乎所有可调项都能用环境变量覆盖，
# 模板见 `backend/.env.example`（每一项都写了取值理由与后果）。
#
# 小工具函数（本项目自研，不依赖 python-dotenv）：
#   · `_load_env_file()`  读 `.env`
#   · `_env_bool()`       读布尔环境变量（**认 1/true/yes/on**；
#                         第 106 批修过两处"只认字面量 true"导致开关静默失效的坑）
#   · `_file_handler()`   生成日志 handler（实现见 `api/log_handlers.py`）
#
# 几个"看起来可以改、其实不生效"的地方，改动前请读旁边的注释：
#   · `REST_FRAMEWORK['PAGE_SIZE']` —— DRF 只在用自带分页器时才读它，
#     本项目用 `api.pagination.CustomPagination`（类里自带 `page_size = 6`）；
#   · `AUTH_PASSWORD_VALIDATORS` —— **有意留空**，校验器在
#     `api/password_policy.py` 里显式实例化（那段注释解释了为什么）；
#   · 限流速率 `DEFAULT_THROTTLE_RATES` —— 少了某个 scope，
#     对应的 `ScopedRateThrottle` 会**静默放行**（第 35 批的教训）。
import os  # 导入操作系统接口模块
import warnings  # 第 97 批：生产未配共享缓存时给出可见警告
from pathlib import Path  # 导入路径处理模块

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent  # 获取项目根目录路径


# ============================================================================
# 环境变量加载（第 82 批 · P0）
# ----------------------------------------------------------------------------
# 背景：密钥、DEBUG、ALLOWED_HOSTS 此前**硬编码在文件里**：
#     SECRET_KEY = 'django-insecure-!your_secret_key_here!'
#     DEBUG = True
#     ALLOWED_HOSTS = ['*']
# 占位密钥进了版本库、生产也会默认开 DEBUG —— 这是本项目最需要先修的一处。
#
# 这里用**标准库**读 backend/.env（不引入 python-dotenv，避免为一个 15 行的功能
# 增加依赖）。规则：
#   · 已存在的真实环境变量优先（部署时用 `set`/`export` 传的值不会被文件覆盖）；
#   · .env 不存在就直接跳过（新克隆的仓库照旧能跑）；
#   · 只做最朴素的 KEY=VALUE 解析，支持 # 注释、可选的引号包裹。
# 模板见同目录 .env.example（该文件入库，.env 本身已在 .gitignore 里）。
# ============================================================================
def _load_env_file(path: Path) -> None:
    # 用 utf-8-sig 读：Windows 上用记事本/PowerShell 存出来的 .env 常带 UTF-8 BOM，
    # 若按 utf-8 读，BOM 会粘在**第一个键名**上（'\ufeffDJANGO_SECRET_KEY' ≠ 'DJANGO_SECRET_KEY'），
    # 结果是那一条被静默忽略、排查起来极费劲。utf-8-sig 会自动吃掉 BOM。
    try:
        content = path.read_text(encoding='utf-8-sig')
    except OSError:
        return
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(BASE_DIR / '.env')


def _env_bool(name: str, default: bool) -> bool:
    """
    读一个布尔环境变量。**接受的写法：`1` / `true` / `yes` / `on`**（大小写与空格无关）。

    ⚠️ 第 106 批补这段说明，因为踩过一个真实的坑：
    项目里有两处**自己写了一套解析**，只认字符串 `'true'`：

        POST_REQUIRE_REVIEW = os.environ.get('POST_REQUIRE_REVIEW', 'true').lower() == 'true'

    于是给 `POST_REQUIRE_REVIEW=1`（对本文件其它所有开关都有效）会**静默得到 False** ——
    也就是发帖审核被**关掉**。一个"内容安全开关"在拼写变体下失败开放，
    是这批审计里最不值得留的一类惊喜。现在两处都改用这个函数。

    ⚠️ 另外注意：**无法识别的值一律当作 False**（而不是报错）。
    所以 `XXX=flase` 这种拼写错误会静默变成"关"。真要确认开关状态，
    用 `manage.py check_env` 看它打出来的实际取值。
    """
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


# ----------------------------------------------------------------------------
# 是否正在跑单元测试（第 86 批）
# ----------------------------------------------------------------------------
# `manage.py test` 会把 settings.DEBUG 改成 False，但那是**运行期**的改动，
# 本文件里 `if DEBUG:` 分支在 import 时就已经决定了用哪个缓存后端。于是出现一个
# 隐蔽的坑：跑测试时用的其实是**磁盘上的 FileBasedCache**，后果有两个 ——
#   ① 测试之间、甚至两次 `manage.py test` 之间会互相污染（实测：翻译译文缓存把
#      上一次跑测试时桩函数写的假译文留在 backend/cache 里，下一次跑就"命中缓存"，
#      断言莫名其妙地失败）；
#   ② 测试里 `cache.clear()`（清限流计数是个常见操作）会把开发环境正在用的
#      限流计数一并清掉。
# 显式判断"是不是在跑测试"，把缓存切回进程内的 LocMemCache。
# ----------------------------------------------------------------------------
import sys as _sys  # noqa: E402  （与本文件风格保持一致：只做一次判断）

_IS_TESTING = 'test' in _sys.argv


# 安全设置（第 82 批改为环境变量驱动）
DEBUG = _env_bool('DJANGO_DEBUG', True)  # 开发默认开；生产请设 DJANGO_DEBUG=False

#: 占位密钥：仅允许在 DEBUG 下当兜底，绝不允许带到生产
_INSECURE_SECRET_KEY = 'django-insecure-!your_secret_key_here!'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or _INSECURE_SECRET_KEY
if not DEBUG and SECRET_KEY == _INSECURE_SECRET_KEY:
    # 宁可起不来，也不要带着公开的占位密钥对外服务（会话伪造/签名失效）
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        '生产模式（DJANGO_DEBUG=False）必须设置 DJANGO_SECRET_KEY。'
        '生成方法：python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"',
    )

#: 开发默认放开（本项目常在局域网内用手机访问，见 fix_lan_access.bat）；
#: 生产必须显式给出域名，例如 DJANGO_ALLOWED_HOSTS=example.com,www.example.com
ALLOWED_HOSTS = [
    host.strip() for host in os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',') if host.strip()
]

# 应用定义
INSTALLED_APPS = [  # 已安装的应用列表
    'django.contrib.admin',  # Django管理后台
    'django.contrib.auth',  # 认证系统
    'django.contrib.contenttypes',  # 内容类型框架
    'django.contrib.sessions',  # 会话框架
    'django.contrib.messages',  # 消息框架
    'django.contrib.staticfiles',  # 静态文件管理
    'rest_framework',  # Django REST框架
    'rest_framework.authtoken',  # REST框架Token认证
    'corsheaders',  # 添加 CORS 支持  # 跨域请求支持
    'django_filters',  # Django过滤器
    'api',  # 自定义API应用
]

# 静态文件托管能力探测（第 94 批）
# ----------------------------------------------------------------------------
# 必须在 MIDDLEWARE **之前**确定：WhiteNoise 的中间件位置很讲究（紧跟 SecurityMiddleware），
# 而 MIDDLEWARE 定义在文件靠前的位置。**没装 whitenoise 也能跑**是刻意设计 ——
# 静态交给 Nginx，服务照常启动，不让"多一个可选依赖"变成启动失败。
try:
    import whitenoise  # noqa: F401
    HAS_WHITENOISE = True
except ImportError:  # pragma: no cover - 只有没装时才走到
    HAS_WHITENOISE = False
WHITENOISE_ENABLED = _env_bool('DJANGO_WHITENOISE', not DEBUG) and HAS_WHITENOISE

MIDDLEWARE = [  # 中间件列表
    'corsheaders.middleware.CorsMiddleware',  # CORS 中间件，必须放在最前面
    'django.middleware.security.SecurityMiddleware',  # 安全中间件
    'django.contrib.sessions.middleware.SessionMiddleware',  # 会话中间件
    'django.middleware.common.CommonMiddleware',  # 通用中间件
    'django.middleware.csrf.CsrfViewMiddleware',  # CSRF 中间件  # CSRF保护中间件
    'django.contrib.auth.middleware.AuthenticationMiddleware',  # 认证中间件
    'api.middleware.TokenAuthenticationMiddleware',  # 自定义Token认证中间件  # 自定义Token认证
    'django.contrib.messages.middleware.MessageMiddleware',  # 消息中间件
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # 点击劫持保护中间件
    'django.middleware.locale.LocaleMiddleware',  # 本地化中间件
    'django.middleware.http.ConditionalGetMiddleware',  # 条件GET中间件
    'django.middleware.gzip.GZipMiddleware',  # GZip压缩中间件
]

# 静态文件托管（第 94 批）：装了 whitenoise 且开启时插在 SecurityMiddleware 之后。
# 位置有讲究 —— WhiteNoise 官方要求紧跟 SecurityMiddleware：
# 静态请求在那里就被短路返回，不再往下走会话/认证/CSRF 那一串中间件，省资源。
# 没装 whitenoise 就什么都不插（静态交给 Nginx），服务照常启动。
if WHITENOISE_ENABLED:  # noqa: SIM102
    MIDDLEWARE.insert(2, 'whitenoise.middleware.WhiteNoiseMiddleware')

#: 有 whitenoise 时用它压缩+版本化静态文件（文件名带 hash，可长缓存）
if WHITENOISE_ENABLED:
    STORAGES = {  # noqa: F811 - 后定义覆盖前面的默认值，这里是有意的
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

# CORS 配置（全项目唯一一份）
# 说明：CORS_ALLOWED_ORIGINS / CORS_ALLOW_METHODS / CORS_ALLOW_HEADERS 原先在文件里被
# 重复定义了 2~3 次。Django 的 settings 是普通模块赋值，**后者整体覆盖前者（不是合并）**，
# 所以"改在前一份里"完全没有效果。下面这套取值与整理前**实际生效**的那一套逐字一致
# （已用 `manage.py diffsettings` 前后快照对比确认无差异）。
# 另注：原先第一份 CORS_ALLOW_HEADERS 里多一个 'token'，但它从未生效（被后面的定义覆盖），
# 如需放行该请求头，请加回下面这份列表里。
CORS_ALLOW_ALL_ORIGINS = _env_bool('DJANGO_CORS_ALLOW_ALL', DEBUG)  # 第 82 批：生产默认关闭，改为白名单
CORS_ALLOW_CREDENTIALS = True  # 允许携带认证信息
CORS_ALLOWED_ORIGINS = [  # 允许的跨域源列表（CORS_ALLOW_ALL_ORIGINS=True 时不参与判断）
    'http://localhost:5173',  # 前端开发服务器（Vite）
    'http://127.0.0.1:5173',
    'http://localhost:5175',  # 备用端口
    'http://127.0.0.1:5175',
]
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# 会话配置
SESSION_COOKIE_NAME = 'sessionid_%s'  # 使用动态会话名称
SESSION_COOKIE_HTTPONLY = True
# 第 82 批：默认跟随 DEBUG —— 生产（DEBUG=False）默认只在 HTTPS 下发送会话/CSRF Cookie，
# 避免"上线忘了改"；开发环境仍是 False，否则 http://127.0.0.1 下会登录不上。
SESSION_COOKIE_SECURE = _env_bool('DJANGO_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SESSION_COOKIE_SAMESITE = 'Lax'  # 防止CSRF攻击
SESSION_SAVE_EVERY_REQUEST = True  # 每次请求都保存会话
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 会话过期时间（秒），这里设置为7天

# ============================================================================
# 生产安全开关（第 94 批）
# ----------------------------------------------------------------------------
# 背景：这一组设置此前**一条都没有** —— 全文只有 Cookie 的 Secure 那一项。
# 后果是"上线之后可以明文 HTTP 访问、没有 HSTS、响应里没有 nosniff"，
# 而这些都不是运行时报错，没人会注意到。
#
# 设计：全部走环境变量，且**默认值跟随 DEBUG** —— 开发环境不用配也能跑，
# 生产（DJANGO_DEBUG=False）自动切到安全的一侧。想临时放宽（例如内网 http 部署）
# 就显式设成 False。
# ============================================================================

#: 是否把 http 请求 301 到 https。生产默认开；反代已终止 TLS 时也能正确识别
#: （前提是配了 SECURE_PROXY_SSL_HEADER，见下）。
SECURE_SSL_REDIRECT = _env_bool('DJANGO_SECURE_SSL_REDIRECT', not DEBUG)

#: HSTS：告诉浏览器"以后只用 https 访问我"。默认 0（关）——
#: 一旦开了且有子域，回退代价很大（浏览器会记住 max-age），**确认 HTTPS 稳定后再开**。
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS') or 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('DJANGO_SECURE_HSTS_SUBDOMAINS', False)
SECURE_HSTS_PRELOAD = _env_bool('DJANGO_SECURE_HSTS_PRELOAD', False)

#: 禁止浏览器"猜"内容类型（否则一个被上传的 .txt 可能被当脚本执行）
SECURE_CONTENT_TYPE_NOSNIFF = True
#: 同源 opener 隔离（现代浏览器的默认行为，显式声明更稳）
SECURE_REFERRER_POLICY = os.environ.get('DJANGO_SECURE_REFERRER_POLICY', 'same-origin')

#: 反代（Nginx/宝塔/云负载均衡）终止 TLS 时，Django 靠这个头判断"原始请求是 https"。
#: 不配的话 SECURE_SSL_REDIRECT 会把所有请求判成 http → **无限重定向**。
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = _env_bool('DJANGO_USE_X_FORWARDED_HOST', not DEBUG)
USE_X_FORWARDED_PORT = _env_bool('DJANGO_USE_X_FORWARDED_PORT', not DEBUG)

#: 上传体积上限（Django 层）：帖子配图/头像/识别图都走这里。
#: 与 api/image_validation.py 的 5MB 是两道不同的闸门 ——
#: 这里挡在解析请求体之前（更省资源），那里挡在业务层（能给出可读提示）。
DATA_UPLOAD_MAX_MEMORY_SIZE = int(
    os.environ.get('DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE') or 20 * 1024 * 1024
)
FILE_UPLOAD_MAX_MEMORY_SIZE = int(
    os.environ.get('DJANGO_FILE_UPLOAD_MAX_MEMORY_SIZE') or 10 * 1024 * 1024
)

#: 生产是否由 Django 自己托管 /media/（上传的图片）。
#: 默认：DEBUG 下由 urls.py 挂载；生产默认交给 Nginx（更高效）。
#: 单机/内网小规模部署没配 Nginx 时，设 DJANGO_SERVE_MEDIA=True 即可直接跑通。
SERVE_MEDIA = _env_bool('DJANGO_SERVE_MEDIA', DEBUG)

#: 静态文件（admin 样式、DRF 浏览页）：装了 whitenoise 就用它托管，
#: 没装则跳过（交给 Nginx）。**不装也能跑**是刻意设计，避免多一个硬依赖。
#: （WHITENOISE_ENABLED / HAS_WHITENOISE 在文件靠前处就已确定，因为 MIDDLEWARE 要用。）


# REST Framework 的**唯一**配置在文件末尾「REST框架设置」处。
# （这里原先还有一份同名的 REST_FRAMEWORK，会被末尾那份整体覆盖 —— 属于「改了不生效」的陷阱。
#   它的完整内容与其失效的 6 个键已备份到 docs/系统完善记录.md 第二十节；
#   若要启用其中的过滤/搜索/限流等键，请合并进末尾那一份，并做接口回归验证。）

ROOT_URLCONF = 'crop_disease_backend.urls'  # 根URL配置

TEMPLATES = [  # 模板配置
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',  # 使用Django模板引擎
        'DIRS': [],  # 模板目录
        'APP_DIRS': True,  # 是否在应用目录中查找模板
        'OPTIONS': {  # 模板选项
            'context_processors': [  # 上下文处理器
                'django.template.context_processors.debug',  # 调试上下文处理器
                'django.template.context_processors.request',  # 请求上下文处理器
                'django.contrib.auth.context_processors.auth',  # 认证上下文处理器
                'django.contrib.messages.context_processors.messages',  # 消息上下文处理器
            ],
        },
    },
]

WSGI_APPLICATION = 'crop_disease_backend.wsgi.application'  # WSGI应用

# 数据库配置（第 254 批：支持 DATABASE_URL；不配则仍然是本地 SQLite）
#
# 为什么现在做：以前引擎与路径是写死的，换 PostgreSQL 必须改代码；写死的东西没法用环境变量
# 区分开发/生产，部署时只能手改 `settings.py`（一改就进版本库，容易把本地路径带上线）。
#
# 支持：
#   postgres://user:pass@host:5432/dbname      （需要 psycopg / psycopg2）
#   postgresql://…                             （同上，别名）
#   mysql://user:pass@host:3306/dbname         （需要 mysqlclient）
#   sqlite:///绝对路径                          （sqlite://:memory: 也行）
# 不认识的 scheme 不会让服务起不来：打印警告并**回退到本地 SQLite**
# （这类配置错误要能被看见，但不该表现为"整个站点 500 看不出原因"）。
DEFAULT_SQLITE_PATH = str(BASE_DIR / 'db.sqlite3')


def _sqlite_config(name: str = '') -> dict:
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': name or DEFAULT_SQLITE_PATH,
        'OPTIONS': {'timeout': 30},  # 增加超时时间到30秒
    }


def _parse_database_url(url: str) -> dict:
    """把 DATABASE_URL 转成 Django 的 DATABASES['default'] 字典。

    只做**纯字符串解析**（不连库），所以可以在测试里直接调用，不需要真实数据库。
    """
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    scheme = (parsed.scheme or '').lower()

    if scheme == 'sqlite':
        # sqlite:///C:/x/db.sqlite3 → path=/C:/x/db.sqlite3；sqlite://:memory: → netloc 为空
        name = parsed.path or ''
        if name.startswith('//'):
            name = name[2:]
        if name.startswith('/') and len(name) > 2 and name[2] == ':':
            name = name[1:]  # 去掉 Windows 盘符前的多余斜杠
        return _sqlite_config(name.replace('/', '\\') if ':' in name else name)

    engines = {
        'postgres': 'django.db.backends.postgresql',
        'postgresql': 'django.db.backends.postgresql',
        'mysql': 'django.db.backends.mysql',
    }
    engine = engines.get(scheme)
    if engine is None or not parsed.path:
        warnings.warn(
            f'DATABASE_URL 无法识别（scheme={scheme!r}），已回退到本地 SQLite。'
            ' 支持 postgres(ql):// / mysql:// / sqlite://',
            RuntimeWarning, stacklevel=2,
        )
        return _sqlite_config()

    config = {
        'ENGINE': engine,
        'NAME': unquote(parsed.path.lstrip('/')),
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname or '',
        'PORT': str(parsed.port or ''),
        'CONN_MAX_AGE': int(os.environ.get('DJANGO_DB_CONN_MAX_AGE') or 60),
    }
    return {key: value for key, value in config.items() if value != ''}


DATABASE_URL = (os.environ.get('DATABASE_URL') or '').strip()
DATABASES = {
    'default': _parse_database_url(DATABASE_URL) if DATABASE_URL else _sqlite_config(),
}

# 密码验证
# ---------------------------------------------------------------------------
# 这段原来是**一堆被注释掉的配置、没有任何说明** —— 读的人无法判断
# "是故意关掉的还是忘了开"，而它的实际效果是：Django 的密码校验器**全部不生效**
# （`password_validation.validate_password()` 遍历的正是这个设置，
#  空列表 = 什么都不检查。第 106 批实测：`validate_password('password')` 通过）。
#
# 第 106 批的决定：**保持这里为空，但把校验器显式放进业务代码** ——
# 见 `api/password_policy.py` 的 `EXPLICIT_VALIDATORS`（最小长度 / 常见弱口令 / 纯数字）。
#
# 为什么不干脆打开这段配置：
#   1. 它只对**显式调用 `validate_password()` 的路径**生效（注册、改密、重置），
#      所以"打开它就安全了"是错觉 —— 关键还是那三处必须真的去调；
#   2. `UserAttributeSimilarityValidator` 会拿**用户名/邮箱**做相似度判断，
#      对农户常用的"姓名+年份"式密码过于苛刻，而本项目用户名不允许中文；
#   3. 配置放在这里，改的人看不到它影响哪几个入口；放在业务代码里，
#      三处调用点一目了然（这正是第 106 批要解决的"三套密码规则"问题）。
#
# ⚠️ 因此**不要**指望改这个设置能收紧密码策略：要改请改 `api/password_policy.py`。
# 留空是刻意的（Django 默认也是空元组，行为上等价）。
AUTH_PASSWORD_VALIDATORS = []  # 见上方说明：校验器在 api/password_policy.py 里显式调用

# 国际化
LANGUAGE_CODE = 'zh-hans'  # 语言代码
TIME_ZONE = 'Asia/Shanghai'  # 时区
USE_I18N = True  # 启用国际化
USE_TZ = True  # 使用时区

# 基础URL配置
BASE_URL = 'http://localhost:8000'  # 基础URL，用于构建完整URL

# 媒体文件配置（全项目唯一一份）
# 注意写法：这里必须是 BASE_DIR / 'media'（Path），不能写成 os.path.join(...)（str）——
# 整理前文件末尾还有一份 MEDIA_ROOT 会覆盖此处，实际生效的是 Path 版本。
MEDIA_URL = '/media/'  # 媒体文件URL前缀
MEDIA_ROOT = BASE_DIR / 'media'  # 媒体文件存储路径

# 确保媒体目录存在
os.makedirs(MEDIA_ROOT, exist_ok=True)

# 确保日志目录存在
LOG_DIR = BASE_DIR / 'logs'  # 日志目录路径
LOG_DIR.mkdir(exist_ok=True)  # 创建日志目录（如果不存在）

# ============================================================================
# 缓存后端（第 54 批起步，第 97 批做成可配置）
# ----------------------------------------------------------------------------
# 为什么这件事重要（不是性能优化，是**功能正确性**）：
#   DRF 的限流计数存在 Django cache 里，而 LocMemCache 是**进程内**的。
#   gunicorn 起 N 个 worker 时，每个进程各算一份计数 —— 于是
#     「登录 10 次/分钟」「注册 10 次/小时」这类限制实际上是 N 倍，
#   而且**没有任何报错**：接口看着正常，防护已经悄悄失效。
#   另外账号锁定（failed_login_attempts）虽然没有走缓存，但登录限流走了。
#
# 取值优先级（从高到低）：
#   1. DJANGO_CACHE_URL / REDIS_URL      —— 推荐，一个变量搞定（Redis）
#   2. DJANGO_CACHE_BACKEND              —— 显式指定后端类路径（Memcached / 自建等）
#   3. 测试                              —— LocMemCache（测试要的是隔离与速度）
#   4. DEBUG=True                        —— FileBasedCache（见下方第 54 批说明）
#   5. 其它（生产）                       —— LocMemCache **并给出警告**，见 check_env / /health/
#
# 例：
#   DJANGO_CACHE_URL=redis://127.0.0.1:6379/1
#   DJANGO_CACHE_URL=rediss://:password@redis.example.com:6380/0     # TLS
#   DJANGO_CACHE_BACKEND=django.core.cache.backends.memcached.PyMemcacheCache
#   DJANGO_CACHE_LOCATION=127.0.0.1:11211
# ============================================================================
CACHE_URL = (os.environ.get('DJANGO_CACHE_URL') or os.environ.get('REDIS_URL') or '').strip()
CACHE_BACKEND_EXPLICIT = (os.environ.get('DJANGO_CACHE_BACKEND') or '').strip()
CACHE_LOCATION_EXPLICIT = (os.environ.get('DJANGO_CACHE_LOCATION') or '').strip()

if CACHE_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': CACHE_URL,
            # 限流窗口最长 1 小时；给足，让计数能自然过期
            'TIMEOUT': 3600,
            # ⚠️ OPTIONS 会原样传给 redis-py 的客户端构造函数 —— 只能放**它认识的**参数。
            #    这里踩过一次：写了 `IGNORE_EXCEPTIONS`（那是 Memcached 后端的选项），
            #    结果 `AbstractConnection.__init__() got an unexpected keyword argument`，
            #    配了 Redis 反而整个缓存不可用。所以下面只放 socket 超时。
            # 超时的意义：Redis 挂了的时候不要让请求**挂住**（默认可能等很久），
            #    宁可快速失败 —— 失败会体现在 /api/health/ 的 cache.ok=false 上。
            'OPTIONS': {
                'socket_connect_timeout': 2,
                'socket_timeout': 2,
            },
        }
    }
    CACHE_IS_SHARED = True          # 跨进程共享 —— 限流才真的生效
    CACHE_KIND = 'redis'
elif CACHE_BACKEND_EXPLICIT:
    CACHES = {
        'default': {
            'BACKEND': CACHE_BACKEND_EXPLICIT,
            'LOCATION': CACHE_LOCATION_EXPLICIT or 'crop_disease_cache',
            'TIMEOUT': 3600,
        }
    }
    CACHE_IS_SHARED = 'locmem' not in CACHE_BACKEND_EXPLICIT.lower()
    CACHE_KIND = CACHE_BACKEND_EXPLICIT.rsplit('.', 1)[-1]
elif _IS_TESTING:
    CACHE_IS_SHARED = False
    CACHE_KIND = 'LocMemCache'      # Django 默认，测试用
elif DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': str(BASE_DIR / 'cache'),
            'TIMEOUT': 3600,
            'OPTIONS': {'MAX_ENTRIES': 2000},
        }
    }
    (BASE_DIR / 'cache').mkdir(exist_ok=True)
    # 文件缓存**能**跨进程共享，但并发写没有锁 —— 开发够用，不要拿去生产
    CACHE_IS_SHARED = False
    CACHE_KIND = 'FileBasedCache'
else:
    # 生产且没配任何东西：Django 默认 LocMemCache。**保留这个回退**（否则改配置才能启动
    # 会挡住只想快速跑起来的人），但把它显式记下来，让 check_env 与 /api/health/ 能报警。
    CACHE_IS_SHARED = False
    CACHE_KIND = 'LocMemCache'
    if not os.environ.get('DJANGO_SUPPRESS_CACHE_WARNING'):
        warnings.warn(
            '生产模式（DEBUG=False）未配置共享缓存，正在使用 LocMemCache：'
            'gunicorn 多 worker 下限流计数各算一份，等于限流失效。'
            '请设置 DJANGO_CACHE_URL（例如 redis://127.0.0.1:6379/1）。'
            '确认知悉可设 DJANGO_SUPPRESS_CACHE_WARNING=1 关掉这条警告。',
            RuntimeWarning,
            stacklevel=1,
        )

# ============================================================================
# 日志（第 107 批：文件轮转改用抗并发的处理器）
# ----------------------------------------------------------------------------
# `file` 与 `debug_file` 两个 handler 只差文件名与级别，参数完全一样 ——
# 用这个工厂生成，避免"改一处漏一处"（项目里已有"5MB 上限写了三份"的先例）。
#
# 为什么从标准库的 `RotatingFileHandler` 换成自己的：
#   标准库那个只保证**同进程内**线程安全，而 `manage.py test --parallel 4`
#   会起 4 个独立进程同时抢着轮转同一个文件；Windows 上 rename 抛
#   `WinError 32`，失败方那条日志直接丢，还会刷一屏 `--- Logging error ---`。
#   自定义处理器会重试，抢不到就"跳过这次轮转、继续追加"，**绝不丢日志**。
#   详见 `api/log_handlers.py`。
# ============================================================================
def _file_handler(filename: str, level: str) -> dict:
    """生成一个文件 handler 配置（实现见 api/log_handlers.py，这里只做转发）"""
    from api.log_handlers import build_file_handler

    return build_file_handler(filename, level)


# Logging configuration
# 说明：日志配置在文件末尾统一定义（原先此处与末尾各写了一份 LOGGING，
# 后者会整体覆盖前者，容易改错地方；现已合并为一份）。

# 静态文件
STATIC_URL = 'static/'  # 静态文件URL
STATIC_ROOT = BASE_DIR / 'staticfiles'  # 静态文件根目录
# 生产：WhiteNoise 直接托管 STATIC_ROOT（collectstatic 的产物）。
# 注意 URL 补上前导斜杠 —— 模板里 {% static %} 会自己拼，但 WhiteNoise 的
# 路径匹配需要它以 / 开头，否则 /static/... 请求不会被它接管。
if WHITENOISE_ENABLED:
    STATIC_URL = '/static/'

# 自定义用户模型
AUTH_USER_MODEL = 'api.CustomUser'  # 自定义用户模型

# 认证后端
AUTHENTICATION_BACKENDS = [  # 认证后端列表
    'django.contrib.auth.backends.ModelBackend',  # 默认的认证后端  # Django模型认证后端
]

# Token 认证配置
# 第 94 批：这个值以前**只定义、没人用** —— DRF 的 TokenAuthentication 不校验它，
# api/middleware.py 也没读它，于是"凭证永不过期"。现在由
# api/middleware.TokenAuthenticationMiddleware 真正执行（见那里的说明）。
# 默认 7 天；`DJANGO_TOKEN_TTL_SECONDS=0` 表示不过期（仅开发图省事时用）。
TOKEN_EXPIRED_AFTER_SECONDS = int(
    os.environ.get('DJANGO_TOKEN_TTL_SECONDS') or 7 * 24 * 60 * 60
)

# ============================================================================
# 注册验证码（第 233 批）
# ----------------------------------------------------------------------------
# 注册是 AllowAny，靠限流挡不住换 IP 的脚本；加一道图片验证码（见 api/captcha.py）。
#   · CAPTCHA_TTL_SECONDS     一张码的有效期（秒）
#   · REGISTER_CAPTCHA_REQUIRED  是否强制校验。**默认 True**；
#     `DJANGO_REGISTER_CAPTCHA=false` 可临时关掉（本地造数据/压测时用），
#     关掉之后注册接口回到"只看限流"的旧状态 —— 别在生产上关。
CAPTCHA_TTL_SECONDS = int(os.environ.get('DJANGO_CAPTCHA_TTL_SECONDS') or 300)
# 登录验证码（第 245 批）：
#   · 默认 **关闭**（`DJANGO_LOGIN_CAPTCHA=true` 打开）—— 因为登录已经有"5 次失败锁定 15 分钟"
#     + `10/min` 限流；验证码是给"面向公网、怕撞库"的部署再加一道，不是本地开发的默认负担。
#   · 与现有限制的关系见 `LoginView.post` 的说明（验证码在密码校验**之前**，失败不累加锁定次数）。
LOGIN_CAPTCHA_REQUIRED = (
    os.environ.get('DJANGO_LOGIN_CAPTCHA', 'false').strip().lower()
    in ('1', 'true', 'yes', 'on')
)

REGISTER_CAPTCHA_REQUIRED = (
    os.environ.get('DJANGO_REGISTER_CAPTCHA', 'true').strip().lower()
    not in ('0', 'false', 'no', 'off')
)

# ============================================================================
# 账号注销冷静期（第 101 批）
# ----------------------------------------------------------------------------
# 用户申请注销后**不是立刻清空**，而是进入一个可撤回的冷静期：
#   · 期间账号立即不可登录（这是用户的直接预期）
#   · 但个人信息完好、凭密码可以取消注销
#   · 到期后由 `manage.py purge_deletion_requests` 执行真正的软删除
# 默认 15 天。设为 0 表示"申请即删除"（不推荐，只在明确要即时注销时用）。
# ⚠️ 到期清理是**定时任务**：本项配置了天数但不跑命令，申请就永远不会被执行。
#    部署时请用 cron / systemd timer / 容器调度器每天跑一次 purge_deletion_requests。
ACCOUNT_DELETION_GRACE_DAYS = int(
    os.environ.get('DJANGO_ACCOUNT_DELETION_GRACE_DAYS') or 15
)

# 登录URL
LOGIN_URL = '/api/login/'  # 登录URL

# 会话设置
# SESSION_COOKIE_AGE / SESSION_SAVE_EVERY_REQUEST 已在上方「会话配置」里统一定义，
# 这里原先又重复写了一遍（值相同），已删除。下面这条是本块独有的设置。
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # 浏览器关闭时不使会话过期

# 日志配置（全项目唯一一份；使用轮转处理器，避免日志无限增长）
LOGGING = {  # 日志配置
    'version': 1,  # 日志配置版本
    'disable_existing_loggers': False,  # 不禁用现有日志记录器
    'formatters': {  # 日志格式器
        'verbose': {  # 详细格式
            'format': '{levelname} {asctime} {module} {message}',  # 格式字符串
            'style': '{',  # 样式
        },
    },
    'handlers': {  # 日志处理器
        # 控制台只输出 INFO 以上，避免开发终端被逐请求的 DEBUG 刷屏
        'console': {  # 控制台处理器
            'level': 'INFO',  # 信息级别
            'class': 'logging.StreamHandler',  # 使用流处理器
            'formatter': 'verbose',  # 使用详细格式
        },
        # 应用日志：INFO 以上，单文件 10MB，保留 3 份
        #
        # ⚠️ 第 107 批：class 从标准的 `logging.handlers.RotatingFileHandler`
        #    换成 `api.log_handlers.SafeRotatingFileHandler`。
        #    原因：标准库那个只保证**同进程内**线程安全，而
        #    `manage.py test --parallel 4` 会起 4 个**独立进程**同时抢着轮转
        #    同一个文件；Windows 上 rename 会抛 `WinError 32`，
        #    失败方那条日志就丢了，日志里刷出一屏 `--- Logging error ---`。
        #    自定义版本会重试，抢不到就"跳过轮转、继续追加"，**绝不丢日志**。
        #    详见 `api/log_handlers.py` 的模块说明。
        'file': _file_handler(str(LOG_DIR / 'django.log'), 'INFO'),
        # 调试日志：DEBUG 以上，同样的参数，只是级别更低
        'debug_file': _file_handler(str(LOG_DIR / 'debug.log'), 'DEBUG'),
    },
    'root': {  # 根日志记录器
        'handlers': ['console', 'file'],  # 使用控制台和文件处理器
        'level': 'INFO',  # 信息级别
    },
    'loggers': {  # 日志记录器配置
        'django': {  # Django日志记录器
            'handlers': ['console', 'file'],  # 使用控制台和文件处理器
            'level': 'INFO',  # 信息级别
            'propagate': False,  # 不传播
        },
        'django.request': {  # Django请求日志记录器
            'handlers': ['console', 'file'],  # 使用控制台和文件处理器
            'level': 'WARNING',  # 只在警告及以上记录
            'propagate': False,  # 不传播
        },
        'api': {  # API日志记录器（DEBUG 只写入轮转的 debug.log）
            'handlers': ['debug_file'],  # 使用调试文件处理器
            'level': 'DEBUG',  # 调试级别
            'propagate': False,  # 不传播
        },
        'api.middleware': {  # API中间件日志记录器
            'handlers': ['debug_file'],  # 使用调试文件处理器
            'level': 'DEBUG',  # 调试级别
            'propagate': False,  # 不传播
        },
        'corsheaders': {  # CORS日志记录器
            'handlers': ['console'],  # 使用控制台处理器
            'level': 'WARNING',  # 警告级别
            'propagate': False,  # 不传播
        },
    },
}

# REST框架设置
REST_FRAMEWORK = {  # REST框架配置
    # ⚠️ 只保留 TokenAuthentication —— 不要加回 SessionAuthentication。
    #
    # 背景（第 19 批实测复现）：两个认证类并存时，同一个浏览器里会存在**两个互相独立的
    # 身份载体**：
    #   · `Authorization: Token xxx`：前端按标签页保存的那份（见 utils/authStorage.js）
    #   · `sessionid` cookie：**整个浏览器共用一份**，登录接口 `login(request, user)` 会写、
    #     Django admin 登录也会写，且永远属于"最后一次成功登录的那个账号"
    # DRF 按顺序尝试认证类：带 Token 头就用 Token，**没有 Token 头就回退到会话**。
    # 于是任何一次没带 Token 的请求（token 刚被清掉、请求发生在 store 初始化之前等）
    # 都会被当成"会话里的那个账号"。实测：
    #     会话=admin + 不带 Token 头 → GET /api/check-auth/ 返回 admin，
    #     连 GET /api/news/ 都能拿到管理员视角的草稿（普通用户账号也如此）。
    # 这会造成"界面显示的是 A，服务端却按 B 执行"的身份错位 —— 排查权限问题时会
    # 得到完全矛盾的结论。去掉它之后，API 身份**只由 Token 决定**，没有第二个来源。
    # 代价：DRF 自带可浏览 API（BrowsableAPIRenderer）的登录表单不再可用，
    # 浏览器里直接打开 /api/... 会以匿名身份呈现；Django admin 是普通视图，不受影响。
    'DEFAULT_AUTHENTICATION_CLASSES': [  # 默认认证类
        # 第 231 批：**每设备一张 token**（手机与桌面可以同时在线）。
        # 先认 `DeviceToken`（新主路径），再退回 DRF 的 `Token`（老客户端/老数据/测试）。
        'api.authentication.DeviceTokenAuthentication',
        'rest_framework.authentication.TokenAuthentication',  # 兼容旧 Token
    ],
    'DEFAULT_PERMISSION_CLASSES': [  # 默认权限类
        'rest_framework.permissions.IsAuthenticated',  # 需要认证
    ],
    'DEFAULT_PAGINATION_CLASS': 'api.pagination.CustomPagination',  # 默认分页类
    # ⚠️ 第 106 批注：这个 PAGE_SIZE **不起作用**，请不要改它来调分页。
    #
    # DRF 只在用自带分页器（`PageNumberPagination`）时才读 `PAGE_SIZE`；
    # 本项目用的是 `api.pagination.CustomPagination`，它在类里**自己写了
    # `page_size = 6`** —— 也就是说真实默认值是 6，与这里的 5 无关。
    # 另外 `news_views.StandardResultsSetPagination` 又是 10。
    #
    # 保留这个键只是为了显式表达"默认页大小存在"这个事实，
    # 改成别的数字不会有任何效果（这会让人以为改了没生效 = 有 bug）。
    # 要调默认页大小：改 `api/pagination.py` 的 `page_size`。
    'PAGE_SIZE': 5,  # 实际不生效，见上（CustomPagination 自带 page_size=6）
    'DEFAULT_RENDERER_CLASSES': [  # 默认渲染器类
        'rest_framework.renderers.JSONRenderer',  # JSON渲染器
        'rest_framework.renderers.BrowsableAPIRenderer',  # 可浏览API渲染器
        # 第 195 批：助手流式接口（SSE）需要它，否则 DRF 的内容协商找不到
        # `text/event-stream` 的渲染器 → 直接 406（实测过）。
        # 见 api/renderers.py 的说明：它只为让协商通过，不参与真正的响应体生成。
        'api.renderers.EventStreamRenderer',
    ],
    'DEFAULT_CHARSET': 'utf-8',  # 默认字符集
    'UNICODE_JSON': True,  # 使用Unicode JSON
    'COMPACT_JSON': True,  # 使用紧凑JSON
    'STRICT_JSON': False,  # 不使用严格JSON

    # 第 35 批：限流速率
    # ------------------------------------------------------------------
    # 关键点：DRF 的 SimpleRateThrottle 在**没有配置速率**时 rate=None，
    # allow_request() 会直接 return True —— 也就是"挂了限流类但完全不生效"。
    # 本项目此前正是这个状态（views_forum 里挂了 UserRateThrottle 却查不到速率配置）。
    # 这里只配速率、**不**开全局 DEFAULT_THROTTLE_CLASSES，避免影响正常页面请求；
    # 需要限流的接口自己用 ScopedRateThrottle + throttle_scope 声明。
    'DEFAULT_THROTTLE_RATES': {
        'user': '1200/hour',        # 登录用户的兜底速率（views_forum 的 UserRateThrottle 用到）
        'anon': '300/hour',         # 匿名兜底
        'login': '10/min',          # 登录：同一 IP 每分钟最多 10 次
        # 第 233 批：10 → 20。验证码填错也走这个限额（限流在视图之前），
        # 10 次/小时对"手滑两三次"的正常用户偏紧；有了验证码，放宽一倍并不会降低防护效果。
        'register': '20/hour',      # 注册：同一 IP 每小时最多 20 次（防批量注册）
        # 第 233 批：注册验证码。注册限流只管"提交"，不管"刷图" ——
        # 不单独限流的话，有人可以对着 /api/captcha/ 狂刷，把 CPU 与缓存都拖垮。
        'captcha': '20/min',        # 验证码：同一 IP 每分钟最多 20 张（一次注册用一张，够用）
        'password_reset': '10/hour',  # 找回密码：每小时最多 10 次（防邮件轰炸；NAT 后多人共用同一出口 IP，别设太死）
        'username_check': '60/min',  # 用户名可用性实时校验
        # 第 106 批：取消注销。这个接口**允许匿名**（账号已停用、拿不到 Token），
        # 靠"用户名 + 密码"认身份 —— 也就是说它是一个**匿名密码校验端点**。
        #
        # 为什么必须限流：第 91 批移除 DRF 自带的 /api/token-auth/ 时给的正是这个理由
        # （"改打这个端点就能无限撞库"）。这个接口属于同一类风险，
        # 却在第 101 批上线时漏了限流。
        #
        # 为什么不更严（比如 3/min）：NAT / 校园网后大量用户共用一个出口 IP，
        # 而这个接口是**唯一的自助恢复途径** —— 限太死会让真正要恢复账号的人
        # 因为"邻居把额度用完了"而恢复不了。10/min 已足以让在线撞库不可行。
        'cancel_deletion': '10/min',
    },
}

# CSRF 可信任的来源
# 说明：CORS_ALLOWED_ORIGINS 里同时放行了 localhost:5173 与 127.0.0.1:5173，
# 这里原先只有 localhost 系列，导致用户若用 127.0.0.1:5173 打开前端，
# 带 Origin 校验的写操作会被 CSRF 拦掉。现与 CORS 白名单对齐。
CSRF_TRUSTED_ORIGINS = [  # CSRF信任的源列表
    "http://localhost:5173",  # 本地开发服务器
    "http://127.0.0.1:5173",  # 本地开发服务器（与 CORS 白名单保持一致）
    "http://localhost:5174",  # 本地开发服务器
    "http://127.0.0.1:5174",
    "http://localhost:5175",  # 备用端口（与 CORS_ALLOWED_ORIGINS 对齐）
    "http://127.0.0.1:5175",
    'http://localhost:5176'  # 本地开发服务器
]

# ============================================================================
# 邮箱与"忘记密码"（第 35 批）
# ----------------------------------------------------------------------------
# 这一套是为**找回密码**准备的：请求重置时系统会给注册邮箱发一封带链接的邮件。
# 开发环境默认用 **控制台后端**：邮件内容（含重置链接）直接打印在后端运行的终端里，
# 不需要配置 SMTP 就能把功能跑通、也能在测试里断言。
# 上线时把 EMAIL_BACKEND 改成 SMTP 后端并填好下面几项即可。
# ============================================================================
EMAIL_BACKEND = os.environ.get(
    'DJANGO_EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = os.environ.get('DJANGO_EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('DJANGO_EMAIL_PORT', 25))
EMAIL_HOST_USER = os.environ.get('DJANGO_EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('DJANGO_EMAIL_HOST_PASSWORD', '')
# ⚠️ 第 106 批：改用 `_env_bool`。原来这里是
#     `os.environ.get(...).lower() == 'true'` —— 只认字面量 `'true'`，
#     于是 `DJANGO_EMAIL_USE_TLS=1` / `yes` / `on` 都会静默变成 False。
EMAIL_USE_TLS = _env_bool('DJANGO_EMAIL_USE_TLS', False)
DEFAULT_FROM_EMAIL = os.environ.get('DJANGO_DEFAULT_FROM_EMAIL', 'no-reply@cropcare.com')

#: 前端地址 —— 重置邮件里的链接要指回前端页面
FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://127.0.0.1:5173')
#: 重置链接有效期（秒）；Django 默认 3 天，这里收窄到 1 小时
PASSWORD_RESET_TIMEOUT = int(os.environ.get('PASSWORD_RESET_TIMEOUT', 3600))

# ============================================================================
# 内容审核（第 38 批）
# ----------------------------------------------------------------------------
# POST_REQUIRE_REVIEW=True 时，**普通用户**发的新帖会先进"待审核"状态，
# 管理员在「内容审核」页通过后才对其他用户可见（作者本人始终能看到自己的帖子）。
# 版主/管理员自己发帖不受影响；作者主动存的草稿也不受影响。
# 用环境变量可以随时关掉（例如演示时想"发完立刻可见"）。
# ============================================================================
# ⚠️ 第 106 批：改用 `_env_bool`。
#    原来这里是 `os.environ.get('POST_REQUIRE_REVIEW', 'true').lower() == 'true'` ——
#    只认字符串 `'true'`，而本文件其它开关都走 `_env_bool`（认 `1/true/yes/on`）。
#    后果是：`POST_REQUIRE_REVIEW=1` 会**静默把发帖审核关掉**。
#    一个内容安全开关在常见拼写变体下失败开放，是最不该留的惊喜。
POST_REQUIRE_REVIEW = _env_bool('POST_REQUIRE_REVIEW', True)

# ============================================================================
# AI 识别（第 107 批）
# ----------------------------------------------------------------------------
# 启动时用一张**合成的假图**完整跑一遍识别，把冷启动代价从"第一个用户"挪到启动阶段。
# 实测（CPU）：加载模型 5.5s + 第一次真实推理 21s，之后每次 0.8s ——
# 不预热的话，第一个上传图片的农户要盯着转圈 20 多秒，很容易以为"识别坏了"。
#
# 关掉它的场景：跑测试（省时间）、或在很慢的机器上不想拖长启动。
# 关掉后功能不变，只是第一个请求会慢。
#
# ⚠️ 第 107 批：**测试环境自动关掉**。不这么做的话，每跑一次 `manage.py test`
#    都会白花几十秒加载模型（而且依赖权重文件存在，CI 上没有就报错）。
#    这样测试也不必依赖"记得设那个环境变量"。
# ============================================================================
AI_WARMUP_ON_STARTUP = _env_bool('AI_WARMUP_ON_STARTUP', not _IS_TESTING)

# ============================================================================
# 用户内容的英文译文（第 85 批）
# ----------------------------------------------------------------------------
# 论坛帖子/评论是用户写的中文，英文界面要显示英文就必须**翻译**（无法预先写死在
# 语言包里）。这一组开关驱动 api/services_translate.py 的可插拔翻译：
#
#   TRANSLATE_PROVIDER = mymemory | libre | openai | none
#       mymemory（默认）免 key 公共接口，适合开发/演示，有每日额度；
#       libre/openai 需要相应的 TRANSLATE_API_URL（+ 可选 KEY / MODEL）。
#   TRANSLATE_ENABLED=False 或 TRANSLATE_PROVIDER=none → 不自动翻译，
#       只保留"作者/管理员手工填英文"的能力（发帖不受任何影响）。
#   TRANSLATE_ON_WRITE=False → 发帖/评论时**同步**翻译（默认打开）。
#       关掉后改用 `manage.py translate_forum_content` 批量补译，
#       适合接口慢、或不想让发帖请求等第三方的情况。
#   测试环境（api/tests.py）会显式关掉它，保证测试不依赖外网。
# ============================================================================
TRANSLATE_ENABLED = _env_bool('TRANSLATE_ENABLED', True)
TRANSLATE_PROVIDER = os.environ.get('TRANSLATE_PROVIDER', 'mymemory')
TRANSLATE_API_URL = os.environ.get('TRANSLATE_API_URL', '')
TRANSLATE_API_KEY = os.environ.get('TRANSLATE_API_KEY', '')
#: 百度翻译开放平台用的 APP ID（provider=baidu 时必填）
TRANSLATE_APP_ID = os.environ.get('TRANSLATE_APP_ID', '')
TRANSLATE_MODEL = os.environ.get('TRANSLATE_MODEL', '')
#: DeepL 目标语言代码，默认 EN-US（DeepL 新版接口不再接受裸 'EN'）
TRANSLATE_TARGET_LANG = os.environ.get('TRANSLATE_TARGET_LANG', '')
TRANSLATE_TIMEOUT = float(os.environ.get('TRANSLATE_TIMEOUT', '8'))
#: MyMemory 允许带一个联系邮箱把匿名额度从 5000 字/天提到 50000 字/天（可选）
TRANSLATE_CONTACT_EMAIL = os.environ.get('TRANSLATE_CONTACT_EMAIL', '')
TRANSLATE_ON_WRITE = _env_bool('TRANSLATE_ON_WRITE', True)
#: 译文后处理术语表（纠正公共接口把"早疫病"译成 Premature Disease 这类错误）。
#: 换成 DeepL/OpenAI 后可关闭，见 services_translate._GLOSSARY_RULES。
TRANSLATE_GLOSSARY = _env_bool('TRANSLATE_GLOSSARY', True)

# ----------------------------------------------------------------------------
# 智能回答助手（第 193 批，K5）
# ----------------------------------------------------------------------------
# 语料：docs/knowledge_base/作物病害知识库_校准版.json（38 条 × 7 维度，已入库）
# 设计：docs/智能回答助手框架.md    入库：docs/知识库入库方案.md
#
# ⚠️ 这一组**刻意独立于 TRANSLATE_\***：助手与翻译各有自己的降级策略 ——
#    翻译挂了只是没有英文，助手挂了要降级成"词条原文"。混用同一组配置会让
#    "改翻译的 provider"顺手把助手弄坏。
#
# ⚠️ `LLM_MODEL` **不保证精确选型**：第 192 批实测本端点请求 `deepseek-chat` 时
#    响应体的 model 字段是 `deepseek-flash`（端点侧重定向）。`assistant/llm.py`
#    会把实到的模型记进 `ChatResult.model`，`AssistantMessage.model` 留存，
#    所以"配置与实到不一致"事后可查，而不是静默接受。
# ----------------------------------------------------------------------------
#: 总开关。默认**关**（与 TRANSLATE_ENABLED 的默认 True 相反）：助手要花钱，
#: 没配 key 时打开只会让每次提问都走一遍降级链路，不如显式开。
LLM_ENABLED = _env_bool('LLM_ENABLED', False)
LLM_API_URL = os.environ.get('LLM_API_URL', 'https://api.deepseek.com/v1')
LLM_API_KEY = os.environ.get('LLM_API_KEY', '')
LLM_MODEL = os.environ.get('LLM_MODEL', 'deepseek-chat')
#: 单次生成超时（秒）。真实回答带 7 维度上下文（800~1500 字），比极短请求慢得多。
#: ⚠️ 第 204 批：输出上限提到 2000 token 后，长回答的生成时间也变长 ——
#:    20 秒对"跨两个词条"的问题偏紧，提到 30 秒（仍远低于前端 60 秒超时）。
LLM_TIMEOUT = float(os.environ.get('LLM_TIMEOUT', '30'))
#: 单次生成的最大输出 token。
#: ⚠️ 第 204 批从 800 提到 2000。原注释写"800 够写结论+依据+五类防治+免责"，
#:    那是**按单条词条**估的；实测用户会问"苹果跟葡萄"这类**跨两条词条**的问题，
#:    答案 1400+ 字，800 直接把它截在半句话（端点回 `finish_reason='length'`）。
#:    中文大致 1 字 ≈ 1 token，2000 约可写 1800 字，覆盖跨词条的长回答。
#:    被截断时不再"静默"—— `AssistantMessage.truncated` 会记下来、界面会提示。
LLM_MAX_TOKENS = int(os.environ.get('LLM_MAX_TOKENS', '2000'))

#: 单个会话最多多少条消息（到顶就建议新开会话，不做摘要压缩 —— 见框架文档"明确不做"）
#: ⚠️ 第 228 批之前这个值**只被 `check_assistant` 打印出来，没有任何地方真的执行** ——
#:    "50 条上限"是文档里的一句话，代码里并不存在。现在在 `orchestrator._prepare()`
#:    里按它拦：到顶给可操作话术（去新开会话），且**不再往这个会话里写消息**。
ASSISTANT_SESSION_MAX_MESSAGES = int(os.environ.get('ASSISTANT_SESSION_MAX_MESSAGES', '50'))
#: 多轮对话带几轮历史进模型（第 228 批；0 = 不带，退回"只看当前问题"）。
#: 一轮 = 一条用户消息 + 一条助手回答。默认 4 轮：够覆盖"这个病→那用什么药→多久打一次"
#: 这类连续追问，又不至于把上下文预算挤掉检索资料（历史总字数另有 1200 字上限）。
ASSISTANT_HISTORY_TURNS = int(os.environ.get('ASSISTANT_HISTORY_TURNS', '4'))
#: 每用户每分钟提问上限（0 = 不限）。闸门在**动模型之前**执行，所以拒绝不花额度。
ASSISTANT_RATE_PER_MINUTE = int(os.environ.get('ASSISTANT_RATE_PER_MINUTE', '10'))
#: 检索取前几条进上下文。5 条约 2000~3000 字，是"够用且不跑题"的平衡点。
#: 单次检索取几条进上下文。
#: ⚠️ 第 209 批从 5 提到 8：用户会问"苹果跟葡萄的所有病害"这类**按作物清点**的问题，
#:    苹果 4 条 + 葡萄 4 条 = 8 条。取 5 条时模型根本看不到另外 3 条，
#:    于是无论提示词怎么写都只能答一部分（这才是"答案不完整"的硬约束）。
ASSISTANT_TOP_K = int(os.environ.get('ASSISTANT_TOP_K', '8'))

# ----------------------------------------------------------------------------
# 测试环境必须**关掉**自动翻译（第 85 批）
# ----------------------------------------------------------------------------
# 单元测试里大量用例会通过接口发帖/评论。若让它们真的去调第三方翻译接口：
#   · 测试变成"依赖外网"，别人机器上跑不通、慢十几倍；
#   · 会白白消耗免费接口的每日额度；
#   · 断言会受翻译结果影响而随机失败（实测：MyMemory 对极短文本"标题"返回过
#     `<g id="2610">Captions</g>.` 这种翻译记忆库的脏数据）。
# 需要验证翻译行为的用例自己用 @override_settings(TRANSLATE_ENABLED=True, ...)
# 打开，并用 unittest.mock 把 translate_text 换成桩函数 —— 见 ForumTranslationTests。
# （_IS_TESTING 在文件上方定义，那里同时解释了"缓存也要切回 LocMem"的原因。）
# ----------------------------------------------------------------------------
if _IS_TESTING:
    TRANSLATE_ENABLED = False
    TRANSLATE_ON_WRITE = False
    # 第 193 批：助手也必须**关掉**。否则一旦本机 .env 配了 LLM_API_KEY，
    # 跑测试就会真的去调外部模型：断言受生成结果影响而随机失败、每次跑测试都花钱、
    # 而且离线环境直接挂（与上面翻译那段是同一个理由）。
    # 需要验证"真实生成"的用例自己用 @override_settings(LLM_ENABLED=True) 打开，
    # 并用 unittest.mock 把 llm.chat 换成桩 —— 见 AssistantTests。
    LLM_ENABLED = False

# ----------------------------------------------------------------------------
# 测试期间把 MEDIA_ROOT 挪到临时目录（第 110 批）
# ----------------------------------------------------------------------------
# 跑一次 `manage.py test` 会在**真实 backend/media/** 里留下文件：实测
# `media/news_images/news_<随机>.png`、`media/uploads/<随机>.jpg` 都是测试上传的，
# 而且它们没有任何数据库引用 —— 是纯垃圾，还会被 `git add -A` 收进仓库
# （首次提交时就是这么混进 98 个的）。
#
# `api/tests.py` 第 21 批立过规矩"本文件的测试不写任何媒体文件"，
# 但"靠每个测试作者记得遵守"不可靠。这个 runner 把规矩变成**默认行为**。
#
# ⚠️ 注意这里**刻意不用 `if _IS_TESTING:` 包起来**：
#    那个变量靠 `'test' in sys.argv` 判断，pytest / IDE / 直接调 runner 时判不出来。
#    `TEST_RUNNER` 是 Django 官方扩展点，只在真的跑测试时才会被实例化，
#    所以无条件配置是正确且更可靠的（生产运行时它只是一行没被读到的字符串配置）。
#
#    实现与理由见 `api/test_runner.py`。
# ----------------------------------------------------------------------------
TEST_RUNNER = 'api.test_runner.MediaIsolatedTestRunner'
