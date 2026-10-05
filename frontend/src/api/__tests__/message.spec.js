/**
 * 私信正文的编码与解析（第 114 批）
 * ------------------------------------------------------------------
 * 图片消息的**协议**是：`content` 是一段 JSON `{"type":"image","url":"…"}`。
 *
 * 为什么这层必须单独测：`content` 是一个能被任何来源写入的 TextField ——
 * 历史遗留的纯文本、别人手工塞进去的 JSON、将来可能新增的其他类型消息，
 * 都会走到解析函数里。**一条消息解析不了绝不能让整个聊天窗口崩掉**，
 * 所以"解析失败怎么办"是这里最重要的用例。
 */
import { describe, expect, it } from 'vitest';
import { encodeImageMessage, parseMessageContent } from '@/api/message';

describe('私信正文的解析（第 114 批）', () => {
  it('普通文字原样返回', () => {
    const result = parseMessageContent('你好，在吗？');
    expect(result.kind).toBe('text');
    expect(result.text).toBe('你好，在吗？');
  });

  it('识别图片消息并取出 url', () => {
    const content = encodeImageMessage('http://127.0.0.1:8000/media/uploads/a.jpg');
    const result = parseMessageContent(content);
    expect(result.kind).toBe('image');
    expect(result.url).toBe('http://127.0.0.1:8000/media/uploads/a.jpg');
  });

  it('以 { 开头但不是合法 JSON → 当普通文字（不能抛）', () => {
    const result = parseMessageContent('{这不是合法 JSON');
    expect(result.kind).toBe('text');
    expect(result.text).toBe('{这不是合法 JSON');
  });

  it('合法 JSON 但结构不对 → 当普通文字', () => {
    for (const raw of ['{"foo":"bar"}', '{"type":"image"}', '{"type":"image","url":123}', '[]', '"文本"']) {
      const result = parseMessageContent(raw);
      expect(result.kind, `应当把 ${raw} 当普通文字`).toBe('text');
      expect(result.text).toBe(raw);
    }
  });

  it('未知的消息类型不会当成图片（为将来留出余地）', () => {
    // 将来若新增 {"type":"file",…}，老前端应当显示原文而不是试图渲染成图片
    const raw = '{"type": "file", "url": "http://x/a.pdf"}';
    const result = parseMessageContent(raw);
    expect(result.kind).toBe('text');
    expect(result.text).toBe(raw);
  });

  it('空值 / 非字符串不会抛', () => {
    for (const raw of [null, undefined, 0, '', '   ']) {
      const result = parseMessageContent(raw);
      expect(result.kind).toBe('text');
      expect(typeof result.text).toBe('string');
    }
  });

  it('前面有空白字符的 JSON 也能识别', () => {
    const result = parseMessageContent('  \n {"type":"image","url":"http://x/b.png"}');
    expect(result.kind).toBe('image');
    expect(result.url).toBe('http://x/b.png');
  });

  it('编码结果能被解析回来（往返一致）', () => {
    const url = 'http://127.0.0.1:8000/media/uploads/%E4%B8%AD%E6%96%87.png';
    expect(parseMessageContent(encodeImageMessage(url))).toEqual({ kind: 'image', url });
  });
});
