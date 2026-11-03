# -*- coding: utf-8 -*-
"""程式入口：把鉤子、引擎、面板串起來。"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Optional

from .config import Config
from .keyboard_hook import KeyboardHook
from .overlay import Overlay
from .t9_pinyin import Engine
from .win32_api import (
    acquire_single_instance,
    message_box,
    send_letters,
    set_dpi_awareness,
)

logger = logging.getLogger(__name__)


class App:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.engine = Engine(send=self._send)
        self.engine.set_enabled(config.enabled)
        self.overlay = Overlay(self.engine, config)
        self.hook = KeyboardHook(self.engine.handle)

    def _send(self, text: str) -> bool:
        return send_letters(text)

    def run(self, smoke_seconds: float = 0.0) -> None:
        if not self.hook.start():
            self.engine.note("鍵盤攔截失敗：請以系統管理員身分執行本程式")
        try:
            self.overlay.run(smoke_seconds)
        finally:
            self.hook.stop()
            self.config.enabled = self.engine.snapshot().enabled
            self.config.save()


def _probe(text: str, delay: float = 4.0) -> int:
    print(f"{delay:.0f} 秒後送出「{text}」，請先切到記事本並確認輸入法在中文模式…")
    time.sleep(delay)
    ok = send_letters(text)
    print("送出成功" if ok else "送出失敗")
    return 0 if ok else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="numpad_t9", description="九宮格 T9 小鍵盤拼音輔助工具"
    )
    parser.add_argument(
        "--smoke", type=float, default=0.0, help="啟動後 N 秒自動退出（測試用）"
    )
    parser.add_argument(
        "--probe", type=str, default="", help="倒數後送出一串字母（測試輸入法整合）"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if sys.platform != "win32":
        print("此工具僅支援 Windows。")
        return 2

    set_dpi_awareness()

    if args.probe:
        return _probe(args.probe)

    if not acquire_single_instance():
        message_box("九宮格 T9 已經在執行中。", "T9 NumPad")
        return 0

    config = Config.load()
    app = App(config)
    app.run(smoke_seconds=args.smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
