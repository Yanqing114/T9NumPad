# -*- coding: utf-8 -*-
"""Windows API 封裝（ctypes）。

包含：全域低階鍵盤鉤子所需的常數與函式、SendInput 字母注入、
前景視窗 / DPI / 工作區 / 單一實例 / IME 狀態查詢。
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from typing import Optional

logger = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    imm32 = ctypes.WinDLL("imm32", use_last_error=True)
except OSError:  # pragma: no cover - 極少數精簡系統
    imm32 = None

# ---------------------------------------------------------------------------
# 常數
# ---------------------------------------------------------------------------

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_BACK = 0x08
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_LWIN = 0x5B
VK_RWIN = 0x5C

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

WH_KEYBOARD_LL = 13
HC_ACTION = 0
LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
GA_ROOT = 2
SPI_GETWORKAREA = 0x0030
PM_NOREMOVE = 0x0000
ERROR_ALREADY_EXISTS = 183

IME_CMODE_NATIVE = 0x0001

# ---------------------------------------------------------------------------
# 結構
# ---------------------------------------------------------------------------


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

# ---------------------------------------------------------------------------
# 函式原型
# ---------------------------------------------------------------------------

user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
user32.GetKeyboardLayout.restype = wintypes.HKL

user32.VkKeyScanExW.argtypes = (ctypes.c_wchar, wintypes.HKL)
user32.VkKeyScanExW.restype = ctypes.c_short

user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short

user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.GetMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
)
user32.GetMessageW.restype = ctypes.c_int
user32.PeekMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
)
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = wintypes.HANDLE

user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND

_GetWindowLong = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
_SetWindowLong = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
_GetWindowLong.argtypes = (wintypes.HWND, ctypes.c_int)
_GetWindowLong.restype = ctypes.c_ssize_t
_SetWindowLong.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
_SetWindowLong.restype = ctypes.c_ssize_t

user32.SetWindowPos.argtypes = (
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
)
user32.SetWindowPos.restype = wintypes.BOOL

user32.SystemParametersInfoW.argtypes = (
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    wintypes.UINT,
)
user32.SystemParametersInfoW.restype = wintypes.BOOL
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int

user32.MessageBoxW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
user32.MessageBoxW.restype = ctypes.c_int

if imm32 is not None:
    imm32.ImmGetContext.argtypes = (wintypes.HWND,)
    imm32.ImmGetContext.restype = wintypes.HANDLE
    imm32.ImmGetConversionStatus.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    )
    imm32.ImmGetConversionStatus.restype = wintypes.BOOL
    imm32.ImmReleaseContext.argtypes = (wintypes.HWND, wintypes.HANDLE)
    imm32.ImmReleaseContext.restype = wintypes.BOOL


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _key_input(vk: int, up: bool) -> INPUT:
    item = INPUT()
    item.type = INPUT_KEYBOARD
    item.u.ki = KEYBDINPUT(
        wVk=vk,
        wScan=0,
        dwFlags=KEYEVENTF_KEYUP if up else 0,
        time=0,
        dwExtraInfo=0,
    )
    return item


def _vk_for_char(ch: str, layout: int) -> tuple[int, bool]:
    """取得字元在指定鍵盤配置下的 VK 與是否需要 Shift。"""
    result = user32.VkKeyScanExW(ch, layout)
    if result != -1:
        vk = result & 0xFF
        shift = bool(result & 0x0100)
        ctrl = bool(result & 0x0200)
        alt = bool(result & 0x0400)
        if vk and not ctrl and not alt:
            return vk, shift
    return ord(ch.upper()), False


def send_letters(text: str) -> bool:
    """把字母當成「真實按鍵」送進目前的前景視窗，讓輸入法接管組字。

    刻意不使用 KEYEVENTF_UNICODE：Unicode 注入會繞過輸入法。
    """
    if not text:
        return True

    hwnd = user32.GetForegroundWindow()
    thread_id = user32.GetWindowThreadProcessId(hwnd, None)
    layout = user32.GetKeyboardLayout(thread_id)

    events: list[INPUT] = []
    for ch in text:
        vk, shift = _vk_for_char(ch, layout)
        if shift:
            events.append(_key_input(VK_SHIFT, up=False))
        events.append(_key_input(vk, up=False))
        events.append(_key_input(vk, up=True))
        if shift:
            events.append(_key_input(VK_SHIFT, up=True))

    if not events:
        return True

    array = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(array), array, ctypes.sizeof(INPUT))
    if sent != len(array):
        logger.warning(
            "SendInput 只送出 %s/%s 個事件（錯誤碼 %s）",
            sent,
            len(array),
            ctypes.get_last_error(),
        )
        return False
    return True


def foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)


def ime_is_native(hwnd: Optional[int] = None) -> Optional[bool]:
    """輸入法是否處於中文（native）模式；無法判斷時回傳 None。"""
    if imm32 is None:
        return None
    hwnd = hwnd or foreground_window()
    if not hwnd:
        return None
    context = imm32.ImmGetContext(hwnd)
    if not context:
        return None
    try:
        conversion = wintypes.DWORD()
        sentence = wintypes.DWORD()
        if not imm32.ImmGetConversionStatus(context, ctypes.byref(conversion), ctypes.byref(sentence)):
            return None
        return bool(conversion.value & IME_CMODE_NATIVE)
    finally:
        imm32.ImmReleaseContext(hwnd, context)


def work_area() -> tuple[int, int, int, int]:
    rect = RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def make_overlay_window(hwnd: int) -> None:
    """無邊框面板：不搶焦點、不進 Alt+Tab、永遠置頂。"""
    style = _GetWindowLong(hwnd, GWL_EXSTYLE)
    _SetWindowLong(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
    )


def set_dpi_awareness() -> None:
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


_held_mutex: Optional[int] = None


def acquire_single_instance(name: str = "Local\\T9NumPad.SingleInstance") -> bool:
    """回傳 False 表示已經有另一個實例在跑。"""
    global _held_mutex
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    _held_mutex = handle
    return True


def message_box(text: str, title: str = "T9 NumPad", flags: int = 0x40) -> None:
    user32.MessageBoxW(None, text, title, flags)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
