# -*- coding: utf-8 -*-
"""使用者設定：面板位置與啟用狀態。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


def config_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "T9NumPad"
    return Path.home() / ".t9numpad"


@dataclass
class Config:
    x: Optional[int] = None
    y: Optional[int] = None
    w: Optional[int] = None
    h: Optional[int] = None
    font_scale: float = 1.15
    enabled: bool = True

    @classmethod
    def load(cls) -> "Config":
        path = config_dir() / "config.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()

        config = cls()
        for key in ("x", "y", "w", "h"):
            value = data.get(key)
            if isinstance(value, int):
                setattr(config, key, value)
        if isinstance(data.get("font_scale"), (int, float)):
            config.font_scale = min(2.2, max(0.8, float(data["font_scale"])))
        if isinstance(data.get("enabled"), bool):
            config.enabled = data["enabled"]
        return config

    def save(self) -> None:
        path = config_dir() / "config.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
