# -*- coding: utf-8 -*-
"""T9 引擎的單元測試（不依賴 Windows API）。"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from numpad_t9.config import Config  # noqa: E402
from numpad_t9.overlay import resized_rect  # noqa: E402
from numpad_t9.t9_pinyin import (  # noqa: E402
    VK_BACK,
    VK_ESCAPE,
    VK_RETURN,
    Engine,
    KeyEvent,
    digits_for_text,
    generate_candidates,
    numpad_key,
)

SCAN = {
    "0": 0x52,
    "1": 0x4F,
    "2": 0x50,
    "3": 0x51,
    "4": 0x4B,
    "5": 0x4C,
    "6": 0x4D,
    "7": 0x47,
    "8": 0x48,
    "9": 0x49,
}


def texts(digits: str) -> list[str]:
    return [candidate.text for candidate in generate_candidates(digits)]


class TestGeneration(unittest.TestCase):
    def test_single_digit_lists_all_letters(self):
        # 單一數字直接列出該鍵全部字母，不要求是合法音節
        self.assertEqual(texts("2"), ["a", "b", "c"])
        self.assertEqual(texts("7"), ["p", "q", "r", "s"])
        self.assertEqual(texts("9"), ["w", "x", "y", "z"])

    def test_24(self):
        self.assertEqual(set(texts("24")), {"ai", "bi", "ci"})
        self.assertEqual(len(texts("24")), 3)

    def test_426(self):
        found = set(texts("426"))
        self.assertTrue({"gan", "gao", "han", "hao"} <= found)

    def test_nihao_is_ranked_high(self):
        found = texts("64426")
        self.assertIn("nihao", found)
        self.assertIn("nihao", found[:3])

    def test_multi_syllable_segmentation(self):
        # "xian" = xian（單音節）也可能是 xi + an，去重後只保留單音節那個
        candidates = generate_candidates("9426")
        xian = [c for c in candidates if c.text == "xian"]
        self.assertEqual(len(xian), 1)
        self.assertEqual(xian[0].syllables, ("xian",))

    def test_n_ng_m_hm_hng_are_back(self):
        self.assertTrue({"m", "n", "o"} <= set(texts("6")))
        self.assertTrue({"mi", "ni", "ng"} <= set(texts("64")))
        self.assertIn("hm", texts("46"))
        self.assertIn("hng", texts("464"))

    def test_rare_syllables_sort_last(self):
        found = texts("64")
        self.assertEqual(found[-1], "ng")

    def test_digits_for_text(self):
        self.assertEqual(digits_for_text("nihao"), "64426")
        self.assertEqual(digits_for_text("mw"), "69")

    def test_generation_is_fast_enough(self):
        started = time.perf_counter()
        generate_candidates("2424242424")
        self.assertLess(time.perf_counter() - started, 1.0)


class TestOverlayRender(unittest.TestCase):
    """不顯示視窗，只驗證繪製與縮放不會拋錯。"""

    def test_render_and_resize(self):
        import tkinter as tk

        from numpad_t9 import overlay as overlay_module

        original = tk.Tk

        class HiddenTk(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.withdraw()

        tk.Tk = HiddenTk
        overlay = None
        try:
            engine = Engine(send=lambda text: True)
            overlay = overlay_module.Overlay(
                engine, Config(x=50, y=50), transparent=False
            )
            engine.handle(KeyEvent(vk=0x62, scan=0x50))
            engine.handle(KeyEvent(vk=0x64, scan=0x4B))
            overlay._render(engine.snapshot())
            overlay._apply_window(50, 50, 700, 340)
            overlay._render(engine.snapshot())
            self.assertEqual(overlay.win_w, 700)
            overlay.set_font_scale(1.8)
            self.assertEqual(overlay.ui, 1.8)
            self.assertGreaterEqual(overlay.win_w, overlay.min_size()[0])
            self.assertGreaterEqual(overlay.win_h, overlay.min_size()[1])

            expanded_width = overlay.win_w
            overlay.collapse()
            self.assertTrue(overlay.collapsed)
            self.assertLess(overlay.win_w, expanded_width)
            overlay.expand()
            self.assertFalse(overlay.collapsed)
            self.assertEqual(overlay.win_w, expanded_width)
        finally:
            tk.Tk = original
            if overlay is not None:
                try:
                    overlay.root.destroy()
                except tk.TclError:
                    pass


class TestResize(unittest.TestCase):
    def test_south_east_corner(self):
        self.assertEqual(
            resized_rect("se", (100, 100, 400, 200), 50, 30, 320, 150),
            (100, 100, 450, 230),
        )

    def test_right_edge_hits_minimum(self):
        self.assertEqual(
            resized_rect("e", (100, 100, 400, 200), -300, 0, 320, 150),
            (100, 100, 320, 200),
        )

    def test_left_edge_keeps_right_edge(self):
        self.assertEqual(
            resized_rect("w", (100, 100, 400, 200), 200, 0, 320, 150),
            (180, 100, 320, 200),
        )

    def test_top_edge_keeps_bottom_edge(self):
        self.assertEqual(
            resized_rect("n", (100, 100, 400, 200), 0, 100, 320, 150),
            (100, 150, 400, 150),
        )

    def test_bottom_edge(self):
        self.assertEqual(
            resized_rect("s", (100, 100, 400, 200), 0, -100, 320, 150),
            (100, 100, 400, 150),
        )


class TestScancodes(unittest.TestCase):
    def test_numpad_by_scan(self):
        self.assertEqual(numpad_key(0x50), "2")
        self.assertEqual(numpad_key(0x4B), "4")
        self.assertEqual(numpad_key(0x1C, True), "enter")
        self.assertEqual(numpad_key(0x35, True), "/")

    def test_arrows_are_not_numpad(self):
        self.assertIsNone(numpad_key(0x50, True))  # 真正的下方向鍵
        self.assertIsNone(numpad_key(0x4B, True))  # 真正的左方向鍵


class EngineCase(unittest.TestCase):
    def setUp(self):
        self.sent: list[str] = []
        self.engine = Engine(send=lambda text: self.sent.append(text) or True)

    # -- 按鍵輔助 -------------------------------------------------------
    def numpad(self, digit: str) -> bool:
        return self.engine.handle(
            KeyEvent(vk=0x60 + int(digit), scan=SCAN[digit])
        )

    def top(self, number: int, shift: bool = False) -> bool:
        return self.engine.handle(
            KeyEvent(vk=0x30 + number, scan=0x01 + number, shift=shift)
        )

    def enter(self) -> bool:
        return self.engine.handle(KeyEvent(vk=VK_RETURN, scan=0x1C))

    def backspace(self) -> bool:
        return self.engine.handle(KeyEvent(vk=VK_BACK, scan=0x0E))

    def escape(self) -> bool:
        return self.engine.handle(KeyEvent(vk=VK_ESCAPE, scan=0x01))

    def snapshot(self):
        return self.engine.snapshot()

    # -- 標準模式 -------------------------------------------------------
    def test_typing_digits(self):
        self.assertTrue(self.numpad("2"))
        self.assertTrue(self.numpad("4"))
        snapshot = self.snapshot()
        self.assertEqual(snapshot.digits, "24")
        self.assertEqual([c.text for c in snapshot.visible], ["ai", "bi", "ci"])

    def test_select_then_enter(self):
        self.numpad("2")
        self.numpad("4")
        self.assertTrue(self.top(2))
        self.assertEqual(self.snapshot().selected, 1)
        self.assertEqual(self.sent, [])
        self.assertTrue(self.enter())
        self.assertEqual(self.sent, ["bi"])
        self.assertEqual(self.snapshot().digits, "")

    def test_enter_submits_first_candidate(self):
        self.numpad("2")
        self.numpad("4")
        first = self.snapshot().visible[0].text
        self.enter()
        self.assertEqual(self.sent, [first])

    def test_number_row_passthrough_when_idle(self):
        self.assertFalse(self.top(3))
        self.assertFalse(self.enter())

    def test_number_row_swallowed_only_when_active(self):
        self.numpad("2")
        self.assertTrue(self.top(1))
        self.enter()
        self.assertFalse(self.top(1))  # 送出後立刻把數字行還給輸入法

    def test_shift_number_row_passthrough(self):
        self.numpad("2")
        self.numpad("4")
        self.assertFalse(self.top(3, shift=True))

    def test_backspace(self):
        self.numpad("2")
        self.numpad("4")
        self.assertTrue(self.backspace())
        self.assertEqual(self.snapshot().digits, "2")
        self.assertTrue(self.backspace())
        self.assertEqual(self.snapshot().digits, "")
        self.assertFalse(self.backspace())

    def test_escape(self):
        self.numpad("2")
        self.assertTrue(self.escape())
        self.assertEqual(self.snapshot().digits, "")
        self.assertFalse(self.escape())

    def test_no_candidates_message(self):
        self.numpad("4")
        self.numpad("5")  # 45 沒有任何合法拼音切法
        self.assertEqual(self.snapshot().visible, ())
        self.enter()
        self.assertEqual(self.sent, [])
        self.assertIn("沒有", self.snapshot().message)

    def test_single_digit_select_and_confirm(self):
        self.numpad("2")
        self.assertEqual([c.text for c in self.snapshot().visible], ["a", "b", "c"])
        self.assertTrue(self.top(2))
        self.assertEqual(self.snapshot().selected, 1)
        self.assertEqual(self.sent, [])  # 還沒按 Enter
        self.enter()
        self.assertEqual(self.sent, ["b"])

    def test_single_digit_keeps_two_digit_parsing(self):
        self.numpad("2")
        self.numpad("4")
        self.assertEqual([c.text for c in self.snapshot().visible], ["ai", "bi", "ci"])

    def test_click_candidate_submits(self):
        self.numpad("2")
        self.numpad("4")
        self.engine.click_candidate(2)
        self.assertEqual(self.sent, ["ci"])
        self.assertEqual(self.snapshot().digits, "")

    def test_click_out_of_range_does_nothing(self):
        self.numpad("2")
        self.engine.click_candidate(9)
        self.assertEqual(self.sent, [])

    def test_click_letter_in_abbr_mode(self):
        self.numpad("0")
        self.numpad("7")
        self.engine.click_candidate(3)  # s
        self.assertEqual(self.snapshot().abbr_display, "s")
        self.assertEqual(self.sent, [])
        self.enter()
        self.assertEqual(self.sent, ["s"])

    def test_digit_cap(self):
        for _ in range(20):
            self.numpad("2")
        self.assertLessEqual(len(self.snapshot().digits), 10)

    # -- 0 前綴 ---------------------------------------------------------
    def test_abbr_flow(self):
        self.assertTrue(self.numpad("0"))
        self.assertEqual(self.snapshot().mode, "abbr")
        self.numpad("6")
        self.assertEqual([c.text for c in self.snapshot().visible], ["m", "n", "o"])
        self.assertTrue(self.top(2))
        self.assertEqual(self.snapshot().abbr_display, "n")
        self.numpad("9")
        self.assertEqual([c.text for c in self.snapshot().visible], ["w", "x", "y", "z"])
        self.assertTrue(self.top(1))
        self.assertEqual(self.snapshot().abbr_display, "n w")
        self.assertTrue(self.enter())
        self.assertEqual(self.sent, ["nw"])
        self.assertEqual(self.snapshot().mode, "standard")

    def test_abbr_blocks_enter_until_complete(self):
        self.numpad("0")
        self.numpad("6")
        self.numpad("9")
        self.top(1)  # 6 -> m
        self.enter()
        self.assertEqual(self.sent, [])
        self.assertIn("還有", self.snapshot().message)
        self.top(1)  # 9 -> w
        self.enter()
        self.assertEqual(self.sent, ["mw"])

    def test_abbr_backspace(self):
        self.numpad("0")
        self.numpad("6")
        self.top(1)
        self.numpad("9")
        self.assertTrue(self.backspace())
        self.assertEqual(self.snapshot().abbr_digits, "6")
        self.assertEqual(self.snapshot().abbr_display, "m")
        self.assertTrue(self.backspace())
        self.assertEqual(self.snapshot().mode, "standard")

    def test_abbr_exit_with_zero(self):
        self.numpad("0")
        self.numpad("0")
        self.assertEqual(self.snapshot().mode, "standard")

    def test_abbr_out_of_range_choice(self):
        self.numpad("0")
        self.numpad("6")
        self.top(9)
        self.assertEqual(self.snapshot().abbr_display, "?")
        self.assertEqual(self.sent, [])

    def test_abbr_any_letters(self):
        # 不套拼音規則：可以拼出 cz、mw 這種不是音節的串
        for digit, letter in (("2", 3), ("9", 4)):
            self.numpad("0") if digit == "2" else None
            self.numpad(digit)
            self.top(letter)
        self.assertEqual(self.snapshot().abbr_letters, "cz")
        self.enter()
        self.assertEqual(self.sent, ["cz"])

    # -- 其他 -----------------------------------------------------------
    def test_ctrl_alt_m_requests_collapse(self):
        self.engine.handle(KeyEvent(vk=0x4D, scan=0x32, ctrl=True, alt=True))
        self.assertTrue(self.engine.take_collapse_toggle())
        self.assertFalse(self.engine.take_collapse_toggle())

    def test_ctrl_alt_n_toggles(self):
        self.engine.handle(
            KeyEvent(vk=0x4E, scan=0x31, ctrl=True, alt=True)
        )
        self.assertFalse(self.snapshot().enabled)
        self.assertFalse(self.numpad("2"))
        self.engine.handle(
            KeyEvent(vk=0x4E, scan=0x31, ctrl=True, alt=True)
        )
        self.assertTrue(self.snapshot().enabled)

    def test_injected_events_ignored(self):
        self.assertFalse(
            self.engine.handle(KeyEvent(vk=0x62, scan=0x50, injected=True))
        )
        self.assertEqual(self.snapshot().digits, "")

    def test_keyup_of_swallowed_key_is_swallowed(self):
        self.numpad("2")
        up = KeyEvent(vk=0x62, scan=0x50, down=False)
        self.assertTrue(self.engine.handle(up))
        self.assertFalse(self.engine.handle(up))


if __name__ == "__main__":
    unittest.main(verbosity=2)
