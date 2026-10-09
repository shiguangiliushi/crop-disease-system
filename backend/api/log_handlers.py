"""
日志处理器（第 107 批新增）
============================================================================
**解决什么问题**：Windows 上日志轮转失败会刷出一大堆 `--- Logging error ---`。

实测现象（跑 `manage.py test --parallel 4` 时满地都是）：

    --- Logging error ---
    PermissionError: [WinError 32] 另一个程序正在使用此文件，进程无法访问。:
      'logs\\debug.log' -> 'logs\\debug.log.1'

**根因**：标准库的 `RotatingFileHandler` 只保证**同进程内**的线程安全
（`doRollover` 里有 `threading.RLock`），而：

  · 文件重命名（`os.rename`）**不是原子操作**，在 Windows 上更严：
    只要还有**任何**进程/线程持有那个文件的句柄，rename 就抛 `WinError 32`；
  · Django 的 `--parallel N` 会起 N 个**独立进程**，每个进程都有自己的
    handler 与自己的锁 —— 它们会同时判断"该轮转了"，然后互相抢同一个源文件。

于是失败方**丢掉那条日志**（`Handler.emit` 的异常被 `logging.raiseExceptions`
兜住并打到 stderr），表现成"明明该有的记录却没了" + 一屏报错。

**做法**：轮转时**重试**；实在轮不动就退化成"继续追加原文件"，
**绝不因为轮转失败而丢日志**；并且失败后**进入冷却窗口**，
避免"注定失败"的环境下每条日志都白等一次重试窗口（第 118 批补，见 `shouldRollover`）。

为什么不用 `concurrent-log-handler` 这个现成包：它确实能解决，
但为这一个功能引入第三方依赖（以及它的供应链风险）不划算 ——
自研这几十行更容易看懂，思路也一样（都是靠重试/锁绕开 rename 的竞态）。
"""
from __future__ import annotations

import os
import time
from logging.handlers import RotatingFileHandler

#: 轮转重试窗口默认值：最多等这么久（每次间隔 RETRY_INTERVAL）。
#: ⚠️ 这是**类属性**而不是模块常量，就是为了能被测试调小 ——
#:    第一版写成模块常量，结果"轮转一直失败"那两条测试各跑了 3 分钟
#:    （每条日志都要等满 1 秒重试窗口），整套 377 秒。
#:    行为逻辑不变，只是把"等多久"变成可注入的。
DEFAULT_RETRY_SECONDS = 1.0
RETRY_INTERVAL = 0.05

#: 轮转失败后的**冷却窗口**（秒，第 118 批）。
#: 为什么必须有它：见 `doRollover` 末尾的说明 —— 没有冷却时，
#: "轮转注定失败"的环境下**每条日志**都要等满重试窗口，把整个服务拖垮。
#: 同样是类属性，测试可注入。
DEFAULT_COOLDOWN_SECONDS = 30.0


class SafeRotatingFileHandler(RotatingFileHandler):
    """
    轮转失败不丢日志的 `RotatingFileHandler`。

    行为约定：
      · 优先正常轮转（与父类完全一致）；
      · 抢不到文件（`PermissionError` / `OSError`）时**重试**约 1 秒 ——
        多数情况下别的进程几十毫秒内就写完了；
      · 最终还是失败就**放弃这次轮转、继续往原文件追加**，
        并**进入冷却窗口**（`cooldown_seconds`，默认 30 秒）：
        冷却期内不再尝试轮转，日志照常追加（见 `shouldRollover`）。
        单文件会短暂超过 `maxBytes`，但那远好过丢日志 ——
        排查问题时"少了一条日志"比"文件大了 2MB"严重得多。
    """

    #: 重试窗口（秒）。测试里会调成 0，见模块顶部说明。
    retry_seconds = DEFAULT_RETRY_SECONDS
    #: 轮转失败后的冷却窗口（秒）。测试里会调小。
    cooldown_seconds = DEFAULT_COOLDOWN_SECONDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #: 冷却截止时间戳（0 = 未冷却）
        self._rollover_blocked_until = 0.0

    def shouldRollover(self, record):  # noqa: D102  （父类方法，说明见类 docstring）
        """
        冷却期内**直接回答"不用轮转"**。

        ⚠️ 第 118 批补这一步的原因（真实现象）：
          轮转失败后文件仍然超过 `maxBytes`，于是**下一条日志**又会走到
          `doRollover()` 里等满重试窗口 —— 只要环境里"文件一直被别的进程占着"
          （本项目 dev server 就是：`runserver` 的父进程与自动重载子进程同时打开
          `logs/debug.log`，rename 永远失败），代价就从"偶发 1 秒"变成
          **每条日志 1 秒**。实测：`debug.log` 涨到 10.2MB 之后，
          一个请求要打十来条日志 → `/api/health/` 从几十毫秒变成 **9~12 秒**，
          E2E 全线假红（用例超时时浏览器还掐掉在途请求，日志里留下 Broken pipe）。
          把"尝试轮转"限制成"每冷却窗口最多一次"，日志一条不丢，服务恢复速度正常。
        """
        if time.time() < self._rollover_blocked_until:
            return False
        return super().shouldRollover(record)

    def doRollover(self):  # noqa: D102  （父类方法，说明见类 docstring）
        deadline = time.time() + self.retry_seconds
        attempt = 0
        while True:
            attempt += 1
            try:
                super().doRollover()
                # 轮转成功 → 解除冷却
                self._rollover_blocked_until = 0.0
                if attempt > 1:
                    # 重试成功也留痕：频繁重试说明有并发写入，值得知道
                    self._note(f'日志轮转在第 {attempt} 次尝试后成功')
                return
            except (PermissionError, OSError) as exc:
                if time.time() >= deadline:
                    # 放弃轮转：把流重新指向原文件，保证后续日志继续落盘，
                    # 并在接下来的 cooldown_seconds 内不再尝试（见 shouldRollover）
                    self._reopen()
                    self._rollover_blocked_until = time.time() + self.cooldown_seconds
                    self._note(
                        f'日志轮转失败（{attempt} 次尝试，最后一次：{exc}）—— '
                        f'本次跳过轮转并冷却 {self.cooldown_seconds:g} 秒，'
                        '期间继续写入原文件以免丢日志'
                    )
                    return
                time.sleep(RETRY_INTERVAL)

    # ------------------------------------------------------------------
    def _reopen(self) -> None:
        """
        重新打开原日志文件。

        为什么必须做：父类 `doRollover()` 是**先 `self.stream.close()` 再改名**，
        改名失败时流已经是关的 —— 不重开的话，这一条之后的**所有日志都会丢**
        （写进已关闭的流会抛 `ValueError`，又被 logging 静默吞掉）。
        这一步是"不丢日志"这个承诺的关键。
        """
        try:
            if self.stream:
                try:
                    self.stream.close()
                except Exception:  # noqa: BLE001
                    pass
            self.mode = 'a'
            self.stream = self._open()
        except Exception:  # noqa: BLE001
            # 连重开都失败（磁盘满 / 权限没了）—— 这时什么都做不了，
            # 交给 logging 默认的错误处理打到 stderr。
            pass

    def _note(self, message: str) -> None:
        """
        把"轮转出过问题"记到 stderr。

        为什么不写进业务日志文件：这个类就是用来**兜住日志系统自身故障**的，
        出故障时再走日志系统容易递归；而且 `--parallel` 下几十个进程同时
        轮转失败是正常现象，写进文件只会又刷一屏。
        """
        try:
            import sys

            sys.stderr.write(f'[log] {message}\n')
        except Exception:  # noqa: BLE001
            pass


def build_file_handler(filename: str, level: str, **extra) -> dict:
    """
    生成 Django `LOGGING` 里的文件 handler 配置片段。

    用函数生成而不是复制两份字典：两份字典容易改一处漏一处 ——
    这个项目里已经有"5MB 上限写了三份、文案 key 里还带数字"的先例。
    """
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    return {
        'level': level,
        'class': 'api.log_handlers.SafeRotatingFileHandler',
        'filename': filename,
        'maxBytes': 10 * 1024 * 1024,
        'backupCount': 3,
        'encoding': 'utf-8',
        'formatter': 'verbose',
        **extra,
    }
