"""SSE（Server-Sent Events）的 DRF 渲染器（第 195 批）。

## 为什么需要它：不加就是 406

`AssistantAskStreamView` 里返回的是 Django 的 `StreamingHttpResponse`
（**不是** DRF 的 `Response`），所以真正的内容由我们自己拼。但 DRF 在进入视图方法**之前**
会先跑 `initial()`，其中就包含**内容协商**：

    request.accepted_renderer = self.perform_content_negotiation(request)

协商时它拿请求的 `Accept` 去和 `DEFAULT_RENDERER_CLASSES` 比对。浏览器发
`Accept: text/event-stream`，而项目只注册了 `JSONRenderer` / `BrowsableAPIRenderer`
—— 匹配不上就抛 `NotAcceptable`，表现为 **HTTP 406**。

实测就是这样：直接打流式接口返回 `HTTP Error 406: Not Acceptable`。

## 这个渲染器的 `render()` 为什么几乎什么都不做

因为流式视图根本不经过渲染器 —— 内容是我们手动拼的 SSE 字节串。
它存在的唯一理由是**让协商能通过**（DRF 只是要一个 `media_type == 'text/event-stream'`
的渲染器对象）。所以 `render()` 直接返回 `data`，不重排、不序列化：
万一将来有人误把这个渲染器用在普通 `Response` 上，至少行为是"原样透传"而不是抛异常。
"""
from rest_framework.renderers import BaseRenderer


class EventStreamRenderer(BaseRenderer):
    """`text/event-stream`：只为让 DRF 的内容协商认可这个 media type。"""

    media_type = 'text/event-stream'
    format = 'txt'          # SSE 本质是纯文本；`format` 用于 URL 后缀协商（`?format=`）
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b''
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return data.encode(self.charset)
        # 走到这里说明有人把普通 dict 交给了本渲染器 —— 不是本项目的用法，
        # 但给出可读内容比抛异常好（流式响应不该在这里失败）。
        return str(data).encode(self.charset)
