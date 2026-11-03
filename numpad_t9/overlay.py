# -*- coding: utf-8 -*-
"""不搶焦點的懸浮候選面板（tkinter Canvas 自繪，可自由縮放、可調字號）。

重點：
* WS_EX_NOACTIVATE + WS_EX_TOOLWINDOW：點擊面板不會搶走前景視窗焦點，
  也不會出現在 Alt+Tab / 工作列。
* 四邊 / 四角可拖曳，寬高各自獨立（非等比）；候選格自動填滿可用空間。
* 字號獨立於視窗大小：Ctrl+Alt+= / Ctrl+Alt+- 或 Ctrl+滾輪調整。
"""

from __future__ import annotations

import math
import time
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable, Optional

from .config import Config
from .t9_pinyin import DEFAULT_FONT_SCALE, Engine, Snapshot
from .win32_api import GA_ROOT, ime_is_native, make_overlay_window, user32, work_area

BASE_W = 470
BASE_H = 214
HEADER_H = 34
BUFFER_H = 58
FOOTER_H = 28
GRID_TOP = HEADER_H + BUFFER_H
MIN_ROW = 30.0
COLLAPSED_W = 84
COLLAPSED_H = 26

PANEL = "#1c2330"
BG = "#161b24"
BORDER = "#2c3647"
TEXT = "#e8edf7"
MUTED = "#8b96ab"
ACCENT = "#5b9dff"
OK = "#41c98b"
WARN = "#f0b64b"
CHIP = "#232c3c"
SELECTED = "#22314b"
KEY_COLOR = "#010203"

FONT_MIN = 0.8
FONT_MAX = 2.2

CURSORS = {
    "n": "size_ns",
    "s": "size_ns",
    "e": "size_we",
    "w": "size_we",
    "ne": "size_ne_sw",
    "sw": "size_ne_sw",
    "nw": "size_nw_se",
    "se": "size_nw_se",
}


def resized_rect(
    direction: str,
    rect: tuple[int, int, int, int],
    dx: int,
    dy: int,
    min_w: int,
    min_h: int,
) -> tuple[int, int, int, int]:
    """依拖曳方向與位移算出新的 (x, y, w, h)；寬高各自獨立，拖到最小時釘住對邊。"""
    x, y, w, h = rect
    right = x + w
    bottom = y + h

    if "e" in direction:
        w += dx
    if "s" in direction:
        h += dy
    if "w" in direction:
        x += dx
        w -= dx
    if "n" in direction:
        y += dy
        h -= dy

    if w < min_w:
        if "w" in direction:
            x = right - min_w
        w = min_w
    if h < min_h:
        if "n" in direction:
            y = bottom - min_h
        h = min_h
    return x, y, w, h


class Overlay:
    def __init__(self, engine: Engine, config: Config, transparent: bool = True) -> None:
        self.engine = engine
        self.config = config
        self._hits: list[tuple[float, float, float, float, Callable[[], None]]] = []
        self._drag_offset: Optional[tuple[int, int]] = None
        self._resize: Optional[tuple[str, int, int, int, int, int, int]] = None
        self.collapsed = False
        self._expanded: Optional[tuple[int, int, int, int]] = None
        self._press_moved = False
        self._was_active = False
        self._snap: Optional[Snapshot] = None
        self._message_seq = -1
        self._message_at = 0.0
        self._message_hidden = False
        self._ime: Optional[bool] = None
        self._ime_at = 0.0
        self._ime_rendered: Optional[bool] = None

        self.root = tk.Tk()
        self.root.title("T9NumPad")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        self.base_scale = self._dpi_scale()
        self.ui = max(FONT_MIN, min(FONT_MAX, config.font_scale))
        self.fs = self.base_scale * self.ui

        self.win_w = int(BASE_W * self.fs)
        self.win_h = int(BASE_H * self.fs)
        if config.w and config.h:
            self.win_w = max(self.min_size()[0], int(config.w))
            self.win_h = max(self.min_size()[1], int(config.h))

        families = set(tkfont.families(self.root))
        self.family = "Segoe UI"
        for name in ("Microsoft JhengHei UI", "Microsoft YaHei UI", "Microsoft JhengHei", "Segoe UI"):
            if name in families:
                self.family = name
                break
        self.mono_family = "Consolas" if "Consolas" in families else "Courier New"

        self.transparent = False
        try:
            if not transparent:
                raise tk.TclError("transparency disabled")
            self.root.configure(bg=KEY_COLOR)
            self.root.wm_attributes("-transparentcolor", KEY_COLOR)
            self.key_color = KEY_COLOR
            self.transparent = True
        except tk.TclError:
            self.key_color = PANEL

        self.canvas = tk.Canvas(
            self.root,
            width=self.win_w,
            height=self.win_h,
            bg=self.key_color,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.place(x=0, y=0, width=self.win_w, height=self.win_h)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)

        self.root.update_idletasks()
        self._make_noactivate()
        self._place_initial()

    # ------------------------------------------------------------------
    # 尺寸 / 字號
    # ------------------------------------------------------------------

    def _dpi_scale(self) -> float:
        try:
            return max(1.0, min(1.8, self.root.winfo_fpixels("1i") / 96.0))
        except tk.TclError:
            return 1.0

    def min_size(self) -> tuple[int, int]:
        return int(340 * self.fs), int(210 * self.fs)

    def set_font_scale(self, value: float) -> None:
        value = round(max(FONT_MIN, min(FONT_MAX, value)), 2)
        if abs(value - self.ui) < 1e-6:
            return
        self.ui = value
        self.fs = self.base_scale * self.ui
        self.config.font_scale = value

        if self.collapsed:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.win_w = int(COLLAPSED_W * self.fs)
            self.win_h = int(COLLAPSED_H * self.fs)
            self._apply_window(x, y, self.win_w, self.win_h)
            self.engine.note(f"字號 {value:.2f}×")
            return

        min_w, min_h = self.min_size()
        w = max(self.win_w, min_w)
        h = max(self.win_h, min_h)
        self.win_w, self.win_h = w, h
        x, y = self._clamp(self.root.winfo_x(), self.root.winfo_y())
        self._apply_window(x, y, w, h)
        self.engine.note(f"字號 {value:.2f}×")

    def collapse(self) -> None:
        """收合成一顆小膠囊，點它或按 Ctrl+Alt+M 還原。"""
        if self.collapsed:
            return
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self._expanded = (x, y, self.win_w, self.win_h)
        self.collapsed = True
        self.win_w = int(COLLAPSED_W * self.fs)
        self.win_h = int(COLLAPSED_H * self.fs)
        self._apply_window(x, y, self.win_w, self.win_h)

    def expand(self) -> None:
        if not self.collapsed:
            return
        self.collapsed = False
        if self._expanded:
            x, y, w, h = self._expanded
        else:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            w, h = int(BASE_W * self.fs), int(BASE_H * self.fs)
        min_w, min_h = self.min_size()
        self.win_w, self.win_h = max(w, min_w), max(h, min_h)
        x, y = self._clamp(x, y)
        self._apply_window(x, y, self.win_w, self.win_h)

    def _make_noactivate(self) -> None:
        try:
            hwnd = int(user32.GetAncestor(int(self.root.winfo_id()), GA_ROOT) or 0)
            if hwnd:
                make_overlay_window(hwnd)
        except Exception:
            pass

    def _place_initial(self) -> None:
        left, top, right, bottom = work_area()
        if self.config.x is not None and self.config.y is not None:
            x, y = self.config.x, self.config.y
        else:
            x = right - self.win_w - int(24 * self.base_scale)
            y = bottom - self.win_h - int(24 * self.base_scale)
        x, y = self._clamp(x, y)
        self.root.geometry(f"{self.win_w}x{self.win_h}+{x}+{y}")

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        left, top, right, bottom = work_area()
        x = max(left, min(int(x), right - self.win_w))
        y = max(top, min(int(y), bottom - self.win_h))
        return x, y

    def _apply_window(self, x: int, y: int, w: int, h: int) -> None:
        self.win_w, self.win_h = int(w), int(h)
        self.root.geometry(f"{self.win_w}x{self.win_h}+{int(x)}+{int(y)}")
        self.canvas.config(width=self.win_w, height=self.win_h)
        self.canvas.place(x=0, y=0, width=self.win_w, height=self.win_h)
        snapshot = self._snap or self.engine.snapshot()
        self._render(snapshot)

    # ------------------------------------------------------------------
    # 滑鼠
    # ------------------------------------------------------------------

    def _edge_at(self, x: int, y: int) -> str:
        grip = max(5, int(6 * self.base_scale))
        left = x <= grip
        right = x >= self.win_w - grip - 1
        top = y <= grip
        bottom = y >= self.win_h - grip - 1
        direction = ""
        if top:
            direction += "n"
        elif bottom:
            direction += "s"
        if left:
            direction += "w"
        elif right:
            direction += "e"
        return direction

    def _on_hover(self, event) -> None:
        if self.collapsed:
            try:
                self.canvas.config(cursor="hand2")
            except tk.TclError:
                pass
            return
        if self._resize is not None or self._drag_offset is not None:
            return
        direction = self._edge_at(event.x, event.y)
        try:
            self.canvas.config(cursor=CURSORS.get(direction, ""))
        except tk.TclError:
            pass

    def _on_press(self, event) -> Optional[str]:
        if self.collapsed:
            self._drag_offset = (
                event.x_root - self.root.winfo_x(),
                event.y_root - self.root.winfo_y(),
            )
            self._press_moved = False
            return "break"

        for x1, y1, x2, y2, callback in self._hits:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                callback()
                return "break"

        direction = self._edge_at(event.x, event.y)
        if direction:
            self._resize = (
                direction,
                event.x_root,
                event.y_root,
                self.root.winfo_x(),
                self.root.winfo_y(),
                self.win_w,
                self.win_h,
            )
            return "break"

        if event.y <= HEADER_H * self.fs:
            self._drag_offset = (
                event.x_root - self.root.winfo_x(),
                event.y_root - self.root.winfo_y(),
            )
        return None

    def _on_motion(self, event) -> None:
        if self.collapsed:
            if self._drag_offset is not None:
                x = event.x_root - self._drag_offset[0]
                y = event.y_root - self._drag_offset[1]
                if abs(x - self.root.winfo_x()) > 2 or abs(y - self.root.winfo_y()) > 2:
                    self._press_moved = True
                self.root.geometry(f"+{x}+{y}")
            return
        if self._resize is not None:
            direction, start_x, start_y, wx, wy, ww, wh = self._resize
            min_w, min_h = self.min_size()
            x, y, w, h = resized_rect(
                direction,
                (wx, wy, ww, wh),
                event.x_root - start_x,
                event.y_root - start_y,
                min_w,
                min_h,
            )
            self._apply_window(x, y, w, h)
            return
        if self._drag_offset is not None:
            x = event.x_root - self._drag_offset[0]
            y = event.y_root - self._drag_offset[1]
            self.root.geometry(f"+{x}+{y}")

    def _on_release(self, _event=None) -> None:
        if self.collapsed:
            if self._drag_offset is None:
                return
            moved = self._press_moved
            self._drag_offset = None
            self._press_moved = False
            if not moved:
                self.expand()
            return
        if self._resize is not None:
            self._resize = None
            self._save_geometry()
            return
        if self._drag_offset is not None:
            self._drag_offset = None
            self.config.x = self.root.winfo_x()
            self.config.y = self.root.winfo_y()

    # ------------------------------------------------------------------
    # 主迴圈
    # ------------------------------------------------------------------

    def run(self, smoke_seconds: float = 0.0) -> None:
        self._snap = self.engine.snapshot()
        self._render(self._snap)
        self._ime = ime_is_native()
        self._ime_rendered = self._ime
        self._ime_at = time.monotonic()
        if smoke_seconds > 0:
            self.root.after(int(smoke_seconds * 1000), self.engine.request_quit)
        self.root.after(40, self._poll)
        self.root.mainloop()

    def _poll(self) -> None:
        if self.engine.quit_requested:
            self._save_geometry()
            self.root.destroy()
            return

        if self.engine.take_font_reset():
            self.set_font_scale(DEFAULT_FONT_SCALE)

        delta = self.engine.take_font_delta()
        if delta:
            self.set_font_scale(self.ui + delta * 0.05)

        snapshot = self.engine.snapshot()

        toggle = self.engine.take_collapse_toggle()
        if toggle:
            if self.collapsed:
                self.expand()
            else:
                self.collapse()
            self._was_active = snapshot.active
        else:
            if self.collapsed and snapshot.active and not self._was_active:
                self.expand()
            self._was_active = snapshot.active

        now = time.monotonic()
        if now - self._ime_at > 0.8:
            self._ime_at = now
            self._ime = ime_is_native()

        if snapshot.message_seq != self._message_seq:
            self._message_seq = snapshot.message_seq
            self._message_at = now
            self._message_hidden = False

        if snapshot != self._snap or self._ime != self._ime_rendered:
            self._snap = snapshot
            self._render(snapshot)
            self._ime_rendered = self._ime
        elif snapshot.message and not self._message_hidden and now - self._message_at > 2.6:
            self._message_hidden = True
            self._render(snapshot)

        self.root.after(40, self._poll)

    def _save_geometry(self) -> None:
        if self.collapsed and self._expanded:
            x, y, w, h = self._expanded
        else:
            try:
                x, y = self.root.winfo_x(), self.root.winfo_y()
            except tk.TclError:
                x, y = self.config.x, self.config.y
            w, h = self.win_w, self.win_h
        self.config.x, self.config.y = x, y
        self.config.w, self.config.h = w, h
        self.config.font_scale = self.ui

    # ------------------------------------------------------------------
    # 繪製
    # ------------------------------------------------------------------

    def _font(self, px: float, weight: str = "normal", mono: bool = False):
        size = -max(7, int(round(px * self.fs)))
        return (self.mono_family if mono else self.family, size, weight)

    def _round(self, x1, y1, x2, y2, radius, fill, outline="", width=1) -> None:
        radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
        points: list[float] = []
        for cx, cy, start, end in (
            (x1 + radius, y1 + radius, 180, 270),
            (x2 - radius, y1 + radius, 270, 360),
            (x2 - radius, y2 - radius, 0, 90),
            (x1 + radius, y2 - radius, 90, 180),
        ):
            for step in range(5):
                angle = math.radians(start + (end - start) * step / 4)
                points.append(cx + radius * math.cos(angle))
                points.append(cy + radius * math.sin(angle))
        self.canvas.create_polygon(
            points, fill=fill, outline=outline or fill, width=width, smooth=False
        )

    def _text(self, x, y, text, px, fill, anchor="w", weight="normal", mono=False) -> None:
        self.canvas.create_text(
            x, y, text=text, anchor=anchor, fill=fill, font=self._font(px, weight, mono)
        )

    def _register_hit(self, x1, y1, x2, y2, callback) -> None:
        self._hits.append((x1, y1, x2, y2, callback))

    def _button(self, x1, y1, x2, y2, label, callback) -> None:
        self._round(x1, y1, x2, y2, 5 * self.fs, CHIP)
        self._text((x1 + x2) / 2, (y1 + y2) / 2, label, 9, TEXT, anchor="center")
        self._register_hit(x1, y1, x2, y2, callback)

    def _render_collapsed(self, snapshot: Snapshot) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self._hits.clear()
        fs = self.fs
        W, H = self.win_w, self.win_h
        self._round(0, 0, W - 1, H - 1, 9 * fs, PANEL, BORDER)
        center_y = H / 2
        dot = OK if snapshot.enabled else WARN
        canvas.create_oval(
            10 * fs, center_y - 3.5 * fs, 17 * fs, center_y + 3.5 * fs,
            fill=dot, outline="",
        )
        self._text(23 * fs, center_y, "T9  ›", 9.5, TEXT, weight="bold")

    def _render(self, snapshot: Snapshot) -> None:
        if self.collapsed:
            self._render_collapsed(snapshot)
            return

        canvas = self.canvas
        canvas.delete("all")
        self._hits.clear()

        fs = self.fs
        W, H = self.win_w, self.win_h
        pad = 14 * fs
        header_h = HEADER_H * fs
        footer_h = FOOTER_H * fs
        grid_top = GRID_TOP * fs
        grid_bottom = H - footer_h
        available = grid_bottom - grid_top
        row_h = available / 3 if available > 0 else MIN_ROW * fs
        row_h = max(MIN_ROW * fs, min(46 * fs, row_h))

        self._round(0, 0, W - 1, H - 1, 12 * fs, PANEL, BORDER)

        # ── 標題列 ─────────────────────────────────────────────
        center_y = header_h / 2
        dot = OK if snapshot.enabled else WARN
        canvas.create_oval(
            pad + 2 * fs, center_y - 4 * fs, pad + 10 * fs, center_y + 4 * fs,
            fill=dot, outline="",
        )
        self._text(
            pad + 16 * fs, center_y, "九宮格 T9", 11.5,
            TEXT if snapshot.enabled else MUTED, weight="bold",
        )

        right = W - pad
        top = 6 * fs
        height = 21 * fs
        quit_box = (right - 40 * fs, top, right, top + height)
        toggle_box = (quit_box[0] - 6 * fs - 48 * fs, top, quit_box[0] - 6 * fs, top + height)
        collapse_box = (
            toggle_box[0] - 6 * fs - 28 * fs,
            top,
            toggle_box[0] - 6 * fs,
            top + height,
        )
        ime_box = (
            collapse_box[0] - 6 * fs - 28 * fs,
            top,
            collapse_box[0] - 6 * fs,
            top + height,
        )

        self._button(*quit_box, "退出", self.engine.request_quit)
        self._button(
            *toggle_box,
            "暫停" if snapshot.enabled else "啟用",
            self.engine.toggle,
        )
        self._button(*collapse_box, "—", self.collapse)

        if self._ime is True:
            ime_label, ime_color = "中", OK
        elif self._ime is False:
            ime_label, ime_color = "英", WARN
        else:
            ime_label, ime_color = None, None
        if ime_label:
            self._round(*ime_box, 5 * fs, CHIP)
            self._text(
                (ime_box[0] + ime_box[2]) / 2,
                (ime_box[1] + ime_box[3]) / 2,
                ime_label, 9.5, ime_color, anchor="center", weight="bold",
            )

        # ── 輸入緩衝 ───────────────────────────────────────────
        status_y = header_h + 11 * fs
        if not snapshot.enabled:
            status = "已暫停"
        elif snapshot.mode == "abbr":
            status = "0 前綴 · 小鍵盤 " + (
                " ".join(snapshot.abbr_digits) if snapshot.abbr_digits else "（等數字）"
            )
        elif snapshot.digits:
            status = "拼音候選"
        else:
            status = "小鍵盤 2–9 輸入拼音"
        self._text(pad, status_y, status, 8.5, MUTED)

        if not snapshot.enabled:
            big = "—"
        elif snapshot.mode == "abbr":
            big = snapshot.abbr_display or "?"
        else:
            big = " ".join(snapshot.digits)
        big_y = header_h + 42 * fs
        if big:
            self._text(
                pad, big_y, big,
                22 if len(big) <= 14 else 17,
                TEXT if snapshot.enabled else MUTED,
                weight="bold", mono=True,
            )
        else:
            self._text(pad, big_y, "以小鍵盤 2–9 開始輸入", 12.5, MUTED)

        if snapshot.enabled:
            if snapshot.mode == "abbr":
                pending = snapshot.abbr_display.count("?")
                total = len(snapshot.abbr_digits)
                right_text = f"{total - pending}/{total} 位" if total else ""
            elif snapshot.digits:
                right_text = (
                    f"共 {snapshot.total} · {snapshot.page + 1}/{snapshot.page_count}"
                )
            else:
                right_text = ""
            if right_text:
                self._text(W - pad, status_y, right_text, 8.5, MUTED, anchor="e")

        # ── 候選格 ─────────────────────────────────────────────
        visible = snapshot.visible if snapshot.enabled else ()
        cell_w = (W - 2 * pad) / 3
        rows = (len(visible) + 2) // 3 if visible else 0
        block_h = rows * row_h
        grid_y0 = grid_top + max(0.0, (available - block_h) / 2)
        if visible:
            for index, candidate in enumerate(visible):
                column = index % 3
                row = index // 3
                x = pad + column * cell_w
                y = grid_y0 + row * row_h
                width = cell_w - 4 * fs
                selected = snapshot.mode == "standard" and index == snapshot.selected
                if selected:
                    self._round(x, y + 1 * fs, x + width, y + row_h - 2 * fs, 6 * fs, SELECTED)
                badge = 18 * fs
                bx1 = x + 4 * fs
                by1 = y + (row_h - badge) / 2
                bx2 = bx1 + badge
                by2 = by1 + badge
                self._round(bx1, by1, bx2, by2, 4 * fs, ACCENT if selected else CHIP)
                self._text(
                    (bx1 + bx2) / 2, (by1 + by2) / 2, str(index + 1),
                    9.5, BG if selected else MUTED, anchor="center", weight="bold",
                )
                text = candidate.text
                size = 12.5 if len(text) <= 7 else (11 if len(text) <= 10 else 9.5)
                self._text(x + 27 * fs, y + row_h / 2, text, size, TEXT, mono=True)
                self._register_hit(
                    x, y, x + width, y + row_h,
                    lambda i=index: self.engine.click_candidate(i),
                )
        elif snapshot.enabled:
            middle_y = (grid_top + grid_bottom) / 2
            if snapshot.mode == "abbr" and snapshot.abbr_digits and not snapshot.abbr_pending:
                self._text(W / 2, middle_y, "按 Enter 送出字母", 11, OK, anchor="center")
            elif snapshot.digits:
                self._text(W / 2, middle_y, "沒有符合的拼音", 11, MUTED, anchor="center")
            elif snapshot.mode == "abbr":
                self._text(W / 2, middle_y, "輸入小鍵盤數字，逐位選字母", 11, MUTED, anchor="center")

        # ── 底部提示 ───────────────────────────────────────────
        line_y = H - footer_h
        canvas.create_line(pad, line_y, W - pad, line_y, fill=BORDER)

        if snapshot.message and not self._message_hidden and (
            time.monotonic() - self._message_at < 2.6 or self._message_at == 0.0
        ):
            hint, color = snapshot.message, ACCENT
        else:
            if not snapshot.enabled:
                hint, color = "已暫停：小鍵盤恢復一般功能", WARN
            elif snapshot.mode == "abbr":
                hint, color = "數字行或滑鼠選字母 · Enter 送出 · Esc 取消", MUTED
            elif snapshot.digits:
                hint, color = "數字行或滑鼠點選 · Enter 送出 · Esc 取消", MUTED
            else:
                hint, color = "小鍵盤 2–9 輸入 · 0 前綴 · Ctrl+Alt+= 調字號", MUTED
        if len(hint) > 34:
            hint = hint[:33] + "…"
        text_y = line_y + footer_h / 2
        self._text(pad, text_y, hint, 8.5, color)
        self._text(
            W - pad, text_y,
            "Ctrl+Alt+=/- 字號 · Ctrl+Alt+N 暫停", 7.5, MUTED, anchor="e",
        )
