# -*- coding: utf-8 -*-
"""T9 九宮格拼音引擎（純邏輯，不依賴 Windows / tkinter）。

職責
----
1. 小鍵盤掃描碼 -> 數字（NumLock 開關都能辨識）。
2. 數字串 -> 合法拼音候選（含多音節切分）。
3. 0 前綴通道：逐位消歧，把任意字母串交給輸入法（簡拼）。
4. 完整輸入狀態機：數字行選候選 / Enter 提交 / Backspace / Esc。

本模組不建立漢字詞庫，也不處理漢字候選。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Optional

# ---------------------------------------------------------------------------
# 基本鍵位資料
# ---------------------------------------------------------------------------

T9_KEYPAD: dict[str, str] = {
    "2": "abc",
    "3": "def",
    "4": "ghi",
    "5": "jkl",
    "6": "mno",
    "7": "pqrs",
    "8": "tuv",
    "9": "wxyz",
}

LETTER_TO_DIGIT: dict[str, str] = {
    letter: digit for digit, letters in T9_KEYPAD.items() for letter in letters
}

# 小鍵盤掃描碼（set 1）。用掃描碼而不用 VK：NumLock 關閉時 VK 會變成方向鍵。
_NUMPAD_SCAN: dict[int, str] = {
    0x52: "0",
    0x4F: "1",
    0x50: "2",
    0x51: "3",
    0x4B: "4",
    0x4C: "5",
    0x4D: "6",
    0x47: "7",
    0x48: "8",
    0x49: "9",
    0x53: ".",
    0x4E: "+",
    0x4A: "-",
    0x37: "*",
}

# 小鍵盤上唯二帶擴展位元的鍵
_NUMPAD_EXT_SCAN: dict[int, str] = {
    0x1C: "enter",
    0x35: "/",
}

# 虛擬鍵碼
VK_BACK = 0x08
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_N = 0x4E
VK_M = 0x4D
VK_Q = 0x51
VK_0 = 0x30
VK_9 = 0x39
VK_OEM_PLUS = 0xBB
VK_OEM_MINUS = 0xBD
VK_ADD = 0x6B
VK_SUBTRACT = 0x6D

FONT_STEP = 0.05
DEFAULT_FONT_SCALE = 1.15


def numpad_key(scan: int, extended: bool = False) -> Optional[str]:
    """由掃描碼判斷小鍵盤按鍵，回傳 '0'-'9' / '.' / '+' / '-' / '*' / '/' / 'enter'。

    實體方向鍵是擴展位元，因此不會被誤判成小鍵盤數字。
    """
    if extended:
        return _NUMPAD_EXT_SCAN.get(scan)
    return _NUMPAD_SCAN.get(scan)


def is_number_row(vk: int) -> bool:
    """字母區上方的數字行 1-9（VK 0x31-0x39）。"""
    return VK_0 < vk <= VK_9


# ---------------------------------------------------------------------------
# 合法拼音音節表（無聲調，ü 以 v 表示）
# ---------------------------------------------------------------------------

_SYLLABLE_TEXT = """
a ai an ang ao
o ou
e ei en eng er
n ng m hm hng
ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
pa pai pan pang pao pei pen peng pi pian piao pie pin ping po pou pu
ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo mou mu
fa fan fang fei fen feng fo fou fu
da dai dan dang dao de dei deng di dia dian diao die ding diu dong dou du duan dui dun duo
ta tai tan tang tao te teng ti tian tiao tie ting tong tou tu tuan tui tun tuo
na nai nan nang nao ne nei nen neng ni nian niang niao nie nin ning niu nong nou nu nuan nuo nv nve
la lai lan lang lao le lei leng li lia lian liang liao lie lin ling liu lo long lou lu luan lun luo lv lve
ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui gun guo
ka kai kan kang kao ke ken keng kong kou ku kua kuai kuan kuang kui kun kuo
ha hai han hang hao he hei hen heng hong hou hu hua huai huan huang hui hun huo
ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun
qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun
xi xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun
zha zhai zhan zhang zhao zhe zhei zhen zheng zhi zhong zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo
cha chai chan chang chao che chen cheng chi chong chou chu chuai chuan chuang chui chun chuo
sha shai shan shang shao she shei shen sheng shi shou shu shua shuai shuan shuang shui shun shuo
ran rang rao re ren reng ri rong rou ru ruan rui run ruo
za zai zan zang zao ze zei zen zeng zi zong zou zu zuan zui zun zuo
ca cai can cang cao ce cen ceng ci cong cou cu cuan cui cun cuo
sa sai san sang sao se sen seng si song sou su suan sui sun suo
ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun
wa wai wan wang wei wen weng wo wu
"""

SYLLABLES: tuple[str, ...] = tuple(_SYLLABLE_TEXT.split())

# 粗略使用頻率排序，只用於候選排序，不影響正確性。
_COMMON_TEXT = """
a ai an ang ao e ei en er o ou
de shi yi bu you zhe le wo ren li ta dao zhong guo shang ge da wei jiu zai shuo
yao xiao ye yu jian hui chi kan xiang na hao zhi xia me xin tian sheng chu lai dui
zi ran zou yong fa cheng neng wu qing wen ming bai chang ting du xie zuo lu chi fan
he shui jiao qi chuang ban xue xi gong sheng huo peng you jia fu mu er nv xiong di
jie mei ai hun yin sheng ri kuai le xing fu tong ku nan guo gao xi huan tao yan dan
xin fang an zhun bei kai shi jie shu ji xu ting zhi bian hua fa zhan jin bu cheng gong
shi bai nu li jian chi qi wang meng xiang ji hua mu biao xing dong jie guo yuan yin
wen ti ban fa dong xi di fang shi hou qian xian jin ming zuo wan zao wu zhong guo ren
min gong he ni hao ma zhe ge na shen me wei zen ke yi bu yao zhi dao xi huan neng
duo shao hao kan ting shuo du xie zuo zou lu chi he shui shui jiao qi chuang shang ban
xia xue xi gong zuo sheng huo peng you jia ren fu mu er zi nv er xiong di jie mei
ai qing hun yin jie hun li hun sheng ri kuai le xing fu tong ku nan guo gao xing xi
huan tao yan sheng qi hai pa dan xin fang xin an xin zhun bei kai shi jie shu ji xu
ting zhi bian hua fa zhan jin bu cheng gong shi bai nu li jian chi fang qi xi wang
meng xiang ji hua mu biao xing dong jie guo yuan yin wen ti ban fa fang fa dong xi di
fang shi jian shi hou yi qian xian zai jin tian ming tian zuo tian shang wu xia wu wan
shang zao shang shui jiao chi fan he shui shang ban xia ban xue xi gong zuo sheng huo
peng you jia ren fu mu er zi nv er xiong di jie mei ai qing hun yin jie hun li hun
sheng ri kuai le xing fu tong ku nan guo gao xing xi huan tao yan sheng qi hai pa dan
xin fang xin an xin zhun bei kai shi jie shu ji xu ting zhi bian hua fa zhan jin bu
"""

_COMMON = tuple(dict.fromkeys(_COMMON_TEXT.split()))
_RANK: dict[str, int] = {syllable: i for i, syllable in enumerate(_COMMON)}

# 合法但罕用的音節（感嘆詞）。保留在表中，只靠排序壓到最後。
_RARE_RANK: dict[str, int] = {
    "n": 1400,
    "m": 1300,
    "ng": 1500,
    "hm": 1600,
    "hng": 1700,
}


def _rank_of(syllable: str) -> int:
    if syllable in _RARE_RANK:
        return _RARE_RANK[syllable]
    return _RANK.get(syllable, 900)

# 常見簡拼片語：只影響排序，不會被當成漢字詞庫。
_PHRASES = frozenset(
    """
nihao xiexie zaijian duibuqi meiguanxi buhaoyisi qingwen xianzai jintian mingtian
zuotian shenme weishenme zenme keyi buyao zhidao xihuan pengyou laoshi xuesheng
gongzuo dianhua shouji diannao wangzhan youxiang mima denglu tuichu xiazai shangchuan
wenjian zhaopian shipin yinyue dianying shijian difang wenti banfa dongxi haochi
piaoliang gaoxing nanguo kuaile shengri zhufu jiaqi lvxing jihua mubiao nuli jiayou
fangxin manyi fuwu zhichi ganxie zaijian duibuqi
""".split()
)

# 數字簽名 -> 音節（依常見度排序）
_BY_SIG: dict[str, list[str]] = {}
for _syllable in SYLLABLES:
    _sig = "".join(LETTER_TO_DIGIT[ch] for ch in _syllable)
    _BY_SIG.setdefault(_sig, []).append(_syllable)
for _sig, _items in _BY_SIG.items():
    _items.sort(key=lambda s: (_rank_of(s), s))

MAX_DIGITS = 10
MAX_ABBR_SLOTS = 12
PAGE_SIZE = 9


@dataclass(frozen=True)
class Candidate:
    """一個拼音候選；text 就是送給輸入法的字串。"""

    text: str
    syllables: tuple[str, ...]
    score: int = 0

    @property
    def syllable_count(self) -> int:
        return len(self.syllables)


def _score(text: str, syllables: tuple[str, ...]) -> int:
    total = sum(_rank_of(s) for s in syllables)
    total += (len(syllables) - 1) * 4
    if len(syllables) > 1 and text in _PHRASES:
        total -= 400
    return total


def generate_candidates(digits: str, max_results: int = 600) -> list[Candidate]:
    """把數字串切成合法拼音音節，回傳排序後的候選。

    單一數字是特例：直接列出該鍵的全部字母（即使不是合法音節），
    例如 2 -> a b c、7 -> p q r s，由使用者自己選。

    同一字串若有多種切法（例如 xian = xi+an），只保留音節數最少的那個。
    """
    digits = "".join(ch for ch in digits if ch in T9_KEYPAD)
    if not digits:
        return []

    if len(digits) == 1:
        return [
            Candidate(text=letter, syllables=(letter,))
            for letter in T9_KEYPAD[digits]
        ]

    best: dict[str, tuple[tuple[str, ...], int]] = {}
    stack: list[tuple[int, tuple[str, ...]]] = [(0, ())]
    nodes = 0
    truncated = False

    while stack:
        pos, syllables = stack.pop()
        if pos == len(digits):
            text = "".join(syllables)
            previous = best.get(text)
            if previous is None or len(syllables) < len(previous[0]):
                best[text] = (syllables, _score(text, syllables))
            continue
        for length in range(1, 7):
            end = pos + length
            if end > len(digits):
                break
            group = _BY_SIG.get(digits[pos:end])
            if not group:
                continue
            for syllable in group:
                nodes += 1
                if nodes > 80000:
                    truncated = True
                    break
                stack.append((end, syllables + (syllable,)))
            if truncated:
                break
        if truncated:
            break

    items = sorted(
        best.items(),
        key=lambda kv: (len(kv[1][0]), kv[1][1], kv[0]),
    )
    return [Candidate(text=t, syllables=s, score=sc) for t, (s, sc) in items[:max_results]]


def digits_for_text(text: str) -> str:
    """字母串 -> 數字串（測試 / 除錯用）。"""
    return "".join(LETTER_TO_DIGIT[ch] for ch in text.lower() if ch in LETTER_TO_DIGIT)


# ---------------------------------------------------------------------------
# 鍵盤事件與狀態機
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeyEvent:
    vk: int
    scan: int = 0
    extended: bool = False
    down: bool = True
    ctrl: bool = False
    alt: bool = False
    shift: bool = False
    win: bool = False
    injected: bool = False


class Mode(str, Enum):
    STANDARD = "standard"
    ABBR = "abbr"


@dataclass(frozen=True)
class Snapshot:
    enabled: bool
    mode: str
    digits: str
    abbr_digits: str
    abbr_letters: str
    abbr_display: str
    abbr_pending: bool
    visible: tuple[Candidate, ...]
    total: int
    page: int
    page_count: int
    selected: int
    message: str
    message_seq: int

    @property
    def active(self) -> bool:
        return bool(self.digits) or bool(self.abbr_digits)


class Engine:
    """輸入狀態機。所有公開方法都是執行緒安全的。"""

    def __init__(self, send: Optional[Callable[[str], bool]] = None) -> None:
        self._lock = threading.RLock()
        self._send = send or (lambda text: True)

        self.enabled = True
        self.mode = Mode.STANDARD
        self.digits = ""
        self.candidates: tuple[Candidate, ...] = ()
        self.page = 0
        self.selected = 0

        self.abbr_slots: list[list] = []  # [[digit, letter|None], ...]

        self.message = ""
        self.message_seq = 0
        self.quit_requested = False
        self.font_delta = 0
        self.font_reset = False
        self.collapse_toggle = False
        self._swallow_up: set[tuple[int, bool]] = set()

    # -- 對外 ---------------------------------------------------------------

    def handle(self, event: KeyEvent) -> bool:
        """回傳 True 表示吞掉這個按鍵。"""
        with self._lock:
            token = (event.scan, event.extended)
            if not event.down:
                if token in self._swallow_up:
                    self._swallow_up.discard(token)
                    return True
                return False
            if event.injected:
                return False
            if self._hotkey(event):
                return self._swallow(event)
            if not self.enabled:
                return False

            numpad = numpad_key(event.scan, event.extended)
            if numpad is not None:
                return self._on_numpad(numpad, event)

            if (
                is_number_row(event.vk)
                and not event.shift
                and not event.ctrl
                and not event.alt
                and not event.win
                and self._active()
            ):
                return self._on_number_row(event)

            if event.vk == VK_RETURN and self._active():
                return self._on_enter()
            if event.vk == VK_BACK and self._active():
                return self._on_backspace()
            if event.vk == VK_ESCAPE and self._active():
                return self._on_escape()
            return False

    def snapshot(self) -> Snapshot:
        with self._lock:
            visible = self._visible()
            return Snapshot(
                enabled=self.enabled,
                mode=self.mode.value,
                digits=self.digits,
                abbr_digits="".join(slot[0] for slot in self.abbr_slots),
                abbr_letters="".join(slot[1] or "" for slot in self.abbr_slots),
                abbr_display=" ".join(slot[1] or "?" for slot in self.abbr_slots),
                abbr_pending=self._pending_index() is not None,
                visible=visible,
                total=len(self.candidates) if self.mode is Mode.STANDARD else len(self.abbr_slots),
                page=self.page,
                page_count=self._page_count(),
                selected=self.selected,
                message=self.message,
                message_seq=self.message_seq,
            )

    def toggle(self) -> bool:
        with self._lock:
            self.enabled = not self.enabled
            self._clear()
            self._set_message("已啟用九宮格輸入" if self.enabled else "已暫停：小鍵盤恢復一般功能")
            return self.enabled

    def set_enabled(self, value: bool) -> None:
        with self._lock:
            if value != self.enabled:
                self.enabled = value
                self._clear()

    def note(self, text: str) -> None:
        """由外部（例如發送失敗）寫入提示訊息。"""
        with self._lock:
            self._set_message(text)

    def request_quit(self) -> None:
        with self._lock:
            self.quit_requested = True

    def take_font_delta(self) -> int:
        with self._lock:
            delta = self.font_delta
            self.font_delta = 0
            return delta

    def take_font_reset(self) -> bool:
        with self._lock:
            reset = self.font_reset
            self.font_reset = False
            return reset

    def take_collapse_toggle(self) -> bool:
        with self._lock:
            toggle = self.collapse_toggle
            self.collapse_toggle = False
            return toggle

    def click_candidate(self, index: int) -> None:
        """滑鼠點選候選：標準模式直接送出；0 前綴模式填入該位字母。"""
        with self._lock:
            visible = self._visible()
            if not (0 <= index < len(visible)):
                return
            choice = visible[index]
            self.selected = index
            if self.mode is Mode.ABBR:
                pending = self._pending_index()
                if pending is None:
                    return
                digit = self.abbr_slots[pending][0]
                self.abbr_slots[pending][1] = choice.text
                remaining = self._pending_count()
                if remaining:
                    self._set_message(f"{digit} → {choice.text}，還有 {remaining} 位")
                else:
                    self._set_message(f"{digit} → {choice.text}，按 Enter 送出")
                return
            self._submit(choice.text)

    # -- 按鍵處理 -----------------------------------------------------------

    def _hotkey(self, event: KeyEvent) -> bool:
        if event.ctrl and event.alt and not event.shift:
            if event.vk == VK_N:
                self.toggle()
                return True
            if event.vk == VK_Q:
                self.quit_requested = True
                return True
            if event.vk == VK_M:
                self.collapse_toggle = True
                return True
            if event.vk in (VK_OEM_PLUS, VK_ADD):
                self.font_delta += 1
                return True
            if event.vk in (VK_OEM_MINUS, VK_SUBTRACT):
                self.font_delta -= 1
                return True
            if event.vk == VK_0:
                self.font_reset = True
                return True
        return False

    def _on_numpad(self, key: str, event: KeyEvent) -> bool:
        if key == "enter":
            return self._on_enter()

        if key in ("*", "/"):
            if not self._active():
                return False
            self._change_page(-1 if key == "*" else 1)
            return self._swallow(event)

        if key == "0":
            if self.mode is Mode.ABBR:
                if self.abbr_slots:
                    self._set_message("0 前綴已在使用中：Enter 送出、Esc 取消")
                else:
                    self.mode = Mode.STANDARD
                    self._set_message("已離開 0 前綴")
                return self._swallow(event)
            if self.digits:
                self._set_message("請先清空數字（Backspace / Esc）再使用 0 前綴")
                return self._swallow(event)
            self.mode = Mode.ABBR
            self.abbr_slots = []
            self._set_message("0 前綴：小鍵盤輸入數字，數字行逐位選字母")
            return self._swallow(event)

        if key == "1":
            if self._active():
                self._set_message("1 沒有對應字母，保留不用")
            return self._swallow(event)

        if key in "23456789":
            if self.mode is Mode.ABBR:
                if len(self.abbr_slots) >= MAX_ABBR_SLOTS:
                    self._set_message(f"最多 {MAX_ABBR_SLOTS} 位")
                else:
                    self.abbr_slots.append([key, None])
                    self._set_message("")
                return self._swallow(event)
            if len(self.digits) >= MAX_DIGITS:
                self._set_message(f"最多 {MAX_DIGITS} 位數字")
                return self._swallow(event)
            if not self.digits:
                self._set_message("")
            self.digits += key
            self._recompute()
            return self._swallow(event)

        # . + - 等：輸入中吞掉，閒置時放行
        return self._swallow(event) if self._active() else False

    def _on_number_row(self, event: KeyEvent) -> bool:
        number = event.vk - VK_0  # 1..9
        if self.mode is Mode.STANDARD:
            if 1 <= number <= len(self._visible()):
                self.selected = number - 1
                self._set_message(f"已選第 {number} 個：{self._visible()[number - 1].text}")
            return self._swallow(event)

        index = self._pending_index()
        if index is None:
            return self._swallow(event)
        digit = self.abbr_slots[index][0]
        letters = T9_KEYPAD[digit]
        if 1 <= number <= len(letters):
            self.abbr_slots[index][1] = letters[number - 1]
            remaining = self._pending_count()
            if remaining:
                self._set_message(f"{digit} → {letters[number - 1]}，還有 {remaining} 位")
            else:
                self._set_message(f"{digit} → {letters[number - 1]}，按 Enter 送出")
        else:
            self._set_message(f"第 {number} 個不存在，這一位只有 {len(letters)} 個字母")
        return self._swallow(event)

    def _on_enter(self) -> bool:
        if not self._active():
            return False
        if self.mode is Mode.STANDARD:
            if not self.candidates:
                self._set_message("這個數字組合沒有合法拼音")
                return True
            visible = self._visible()
            index = min(self.selected, len(visible) - 1)
            self._submit(visible[index].text)
            return True

        pending = self._pending_count()
        if pending:
            self._set_message(f"還有 {pending} 位字母沒選")
            return True
        text = "".join(slot[1] or "" for slot in self.abbr_slots)
        if not text:
            self._set_message("沒有可送出的字母")
            return True
        self._submit(text)
        return True

    def _on_backspace(self) -> bool:
        if self.mode is Mode.ABBR:
            if not self.abbr_slots:
                return False
            self.abbr_slots.pop()
            if not self.abbr_slots:
                self._clear()
            self._set_message("")
            return True
        if not self.digits:
            return False
        self.digits = self.digits[:-1]
        if self.digits:
            self._recompute()
        else:
            self._clear()
        return True

    def _on_escape(self) -> bool:
        if not self._active() and self.mode is Mode.STANDARD:
            return False
        self._clear()
        self._set_message("已取消")
        return True

    # -- 內部 ---------------------------------------------------------------

    def _submit(self, text: str) -> None:
        # 先清空狀態：數字行 / 候選面板立刻失效，把 1-9 還給輸入法。
        self._clear()
        try:
            ok = bool(self._send(text))
        except Exception:  # pragma: no cover - 送出行為不應讓輸入中斷
            ok = False
        self._set_message(("已送出：" if ok else "送出失敗（目標視窗權限較高？）：") + text)

    def _clear(self) -> None:
        self.mode = Mode.STANDARD
        self.digits = ""
        self.candidates = ()
        self.page = 0
        self.selected = 0
        self.abbr_slots = []

    def _recompute(self) -> None:
        self.candidates = tuple(generate_candidates(self.digits))
        self.page = 0
        self.selected = 0
        if not self.candidates:
            self._set_message("這個組合沒有合法拼音")

    def _active(self) -> bool:
        if self.mode is Mode.ABBR:
            return bool(self.abbr_slots)
        return bool(self.digits)

    def _page_count(self) -> int:
        if self.mode is Mode.ABBR:
            return 1
        return max(1, (len(self.candidates) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _visible(self) -> tuple[Candidate, ...]:
        if self.mode is Mode.ABBR:
            index = self._pending_index()
            if index is None:
                return ()
            digit = self.abbr_slots[index][0]
            return tuple(Candidate(text=ch, syllables=(ch,)) for ch in T9_KEYPAD[digit])
        start = self.page * PAGE_SIZE
        return self.candidates[start : start + PAGE_SIZE]

    def _pending_index(self) -> Optional[int]:
        for i, slot in enumerate(self.abbr_slots):
            if slot[1] is None:
                return i
        return None

    def _pending_count(self) -> int:
        return sum(1 for slot in self.abbr_slots if slot[1] is None)

    def _change_page(self, delta: int) -> None:
        if self.mode is Mode.ABBR:
            return
        count = self._page_count()
        if count <= 1:
            self._set_message("只有一頁")
            return
        self.page = (self.page + delta) % count
        self.selected = 0
        self._set_message(f"第 {self.page + 1}/{count} 頁")

    def _set_message(self, text: str) -> None:
        if text != self.message:
            self.message = text
            self.message_seq += 1

    def _swallow(self, event: KeyEvent) -> bool:
        self._swallow_up.add((event.scan, event.extended))
        return True


__all__ = [
    "Candidate",
    "Engine",
    "KeyEvent",
    "Mode",
    "Snapshot",
    "T9_KEYPAD",
    "digits_for_text",
    "generate_candidates",
    "is_number_row",
    "numpad_key",
]
