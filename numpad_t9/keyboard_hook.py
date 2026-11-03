# -*- coding: utf-8 -*-
"""全域低階鍵盤鉤子。

鉤子必須安裝在「自己執行訊息迴圈」的執行緒上，因此整個鉤子
（安裝、回呼、訊息迴圈、卸載）都在同一個背景執行緒完成。
"""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable, Optional

from .t9_pinyin import KeyEvent
from .win32_api import (
    HC_ACTION,
    HOOKPROC,
    KBDLLHOOKSTRUCT,
    LLKHF_EXTENDED,
    LLKHF_INJECTED,
    PM_NOREMOVE,
    VK_CONTROL,
    VK_LWIN,
    VK_MENU,
    VK_RWIN,
    VK_SHIFT,
    WH_KEYBOARD_LL,
    WM_KEYDOWN,
    WM_SYSKEYDOWN,
    kernel32,
    user32,
)

logger = logging.getLogger(__name__)

WM_QUIT = 0x0012


def _is_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class KeyboardHook:
    """handler(KeyEvent) -> bool；回傳 True 表示吞掉該按鍵。"""

    def __init__(self, handler: Callable[[KeyEvent], bool]) -> None:
        self._handler = handler
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[HOOKPROC] = None
        self._handle = None
        self._thread_id: Optional[int] = None
        self._ready = threading.Event()
        self._stopping = False
        self._ok = False
        self.last_error = 0
        self.calls = 0
        self.last_message_result = 0

    @property
    def ok(self) -> bool:
        return self._ok

    def start(self, timeout: float = 3.0) -> bool:
        if self._thread is not None:
            return self._ok
        self._thread = threading.Thread(
            target=self._run, name="t9-keyboard-hook", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout)
        return self._ok

    def _run(self) -> None:
        try:
            message = wintypes.MSG()
            # 先建立執行緒訊息佇列，否則 SetWindowsHookEx 的回呼不會被派送。
            user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_NOREMOVE)
            self._thread_id = int(kernel32.GetCurrentThreadId())
            self._proc = HOOKPROC(self._callback)
            self._handle = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL,
                self._proc,
                kernel32.GetModuleHandleW(None),
                0,
            )
            if not self._handle:
                self.last_error = ctypes.get_last_error()
                logger.error("安裝鍵盤鉤子失敗，錯誤碼 %s", self.last_error)
                return
            if self._stopping:
                return
            self._ok = True
            self._ready.set()

            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result in (0, -1):
                    self.last_message_result = result
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception:
            logger.exception("鍵盤鉤子執行緒異常")
        finally:
            if self._handle:
                user32.UnhookWindowsHookEx(self._handle)
                self._handle = None
            self._proc = None
            self._ok = False
            self._ready.set()

    def _callback(self, n_code: int, w_param: int, l_param: int) -> int:
        self.calls += 1
        if n_code == HC_ACTION:
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                flags = int(info.flags)
                event = KeyEvent(
                    vk=int(info.vkCode),
                    scan=int(info.scanCode),
                    extended=bool(flags & LLKHF_EXTENDED),
                    down=w_param in (WM_KEYDOWN, WM_SYSKEYDOWN),
                    ctrl=_is_down(VK_CONTROL),
                    alt=_is_down(VK_MENU),
                    shift=_is_down(VK_SHIFT),
                    win=_is_down(VK_LWIN) or _is_down(VK_RWIN),
                    injected=bool(flags & LLKHF_INJECTED),
                )
                if self._handler(event):
                    return 1
            except Exception:
                logger.exception("處理按鍵時發生錯誤")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def stop(self) -> None:
        self._stopping = True
        self._ready.wait(1.0)
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._handle:
            user32.UnhookWindowsHookEx(self._handle)
            self._handle = None
        self._ok = False
