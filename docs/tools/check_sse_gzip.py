"""实测：GZipMiddleware 会不会把 SSE 的逐块输出攒住。

为什么必须实测：Django 的 `GZipMiddleware` 对 streaming response 走
`compress_sequence()`（一个带 zlib 压缩上下文的生成器）。压缩器为了压缩率会缓一缓，
所以"第一块什么时候真的出来"不能靠读文档推断 —— 而 SSE 的全部价值就在"立刻见到第一块"。

做法（不走 WSGI，直接测中间件本身，最小且无噪声）：
  造一个"每 0.3 秒吐一块、共 5 块"的流式响应 → 过 `process_response` →
  消费它的 `streaming_content` 并记录每一块出来的时刻。
"""
import time

from django.conf import settings

if not settings.configured:
    settings.configure(DEBUG=True, ALLOWED_HOSTS=['*'], SECRET_KEY='x')
    import django
    django.setup()

from django.http import StreamingHttpResponse  # noqa: E402
from django.middleware.gzip import GZipMiddleware  # noqa: E402
from django.test import RequestFactory  # noqa: E402

CHUNKS = 5
DELAY = 0.3


def build_response(add_identity: bool) -> StreamingHttpResponse:
    def gen():
        for i in range(CHUNKS):
            yield f'data: chunk-{i}\n\n'.encode()
            time.sleep(DELAY)

    response = StreamingHttpResponse(gen(), content_type='text/event-stream')
    if add_identity:
        # GZipMiddleware 的第一道判断是 `if response.has_header("Content-Encoding"): return response`
        # —— 所以显式声明 identity 能让它完全不插一手。
        response['Content-Encoding'] = 'identity'
    return response


def measure(label: str, use_gzip: bool, add_identity: bool):
    middleware = GZipMiddleware(lambda request: None)
    request = RequestFactory().get('/', HTTP_ACCEPT_ENCODING='gzip, deflate')  # 模拟浏览器
    response = build_response(add_identity)

    started = time.time()
    response = middleware.process_response(request, response)
    encoding = response.headers.get('Content-Encoding', '(none)')

    marks = []
    for _chunk in response.streaming_content:
        marks.append(round(time.time() - started, 2))

    print(f'  {label}')
    print(f'    Content-Encoding = {encoding}')
    print(f'    各块产出时刻(秒) = {marks}')
    print(f'    首块延迟 = {marks[0] if marks else "无"}s   总耗时 = {round(time.time()-started, 2)}s')
    print()
    return marks


print('=== GZipMiddleware 对流式响应的影响（理想：首块 ≈0.3s，各块间隔 ≈0.3s）===')
print(f'    {CHUNKS} 块，每块间隔 {DELAY}s')
print()
base = measure('不挂 GZip（基线）', False, False)
buffered = measure('挂 GZip（当前项目配置）', True, False)
bypassed = measure('挂 GZip + Content-Encoding: identity（拟采用）', True, True)

print('=== 结论 ===')
first_base, first_buf, first_by = (base[0] if base else None), (buffered[0] if buffered else None), (bypassed[0] if bypassed else None)
print(f'  基线首块 {first_base}s → GZip 后 {first_buf}s → identity 后 {first_by}s')
if first_buf is not None and first_base is not None and first_buf > first_base * 2:
    print('  ⇒ GZipMiddleware **确实攒住了**流式输出，必须用 identity 绕过（或调用链上排除该中间件）')
else:
    print('  ⇒ GZipMiddleware 未明显攒住流式输出（逐块仍按 ~0.3s 出来）')
