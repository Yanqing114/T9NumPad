# -*- coding: utf-8 -*-
"""產生 assets/t9.ico（純標準函式庫，不需要 Pillow）。

圖案：深色圓角方塊 + 九宮格圓點，中心點用藍色。
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "t9.ico"

BACKGROUND = (0x1C, 0x23, 0x30)
BORDER = (0x2C, 0x36, 0x47)
ACCENT = (0x5B, 0x9D, 0xFF)
DOT = (0xE8, 0xED, 0xF7)


def _png(width: int, height: int, rgba: bytes) -> bytes:
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def _rounded_box_distance(px: float, py: float, size: float, radius: float, inset: float) -> float:
    half = size / 2 - inset
    qx = abs(px - size / 2) - (half - radius)
    qy = abs(py - size / 2) - (half - radius)
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    inside = min(max(qx, qy), 0.0)
    return outside + inside - radius


def render(size: int) -> bytes:
    middle = size / 2
    radius = size * 0.22
    inset = max(1.0, size * 0.02)
    dot_radius = size * 0.072
    spacing = size * 0.215

    centers = [
        (middle + dx * spacing, middle + dy * spacing)
        for dy in (-1, 0, 1)
        for dx in (-1, 0, 1)
    ]

    buffer = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            distance = _rounded_box_distance(px, py, size, radius, inset)
            coverage = min(1.0, max(0.0, 0.5 - distance))
            if coverage <= 0:
                continue

            color = BACKGROUND
            # 內描邊
            edge = _rounded_box_distance(px, py, size, radius, inset + size * 0.012)
            if edge > -max(1.0, size * 0.012):
                color = BORDER

            r, g, b = color
            a = coverage

            for index, (cx, cy) in enumerate(centers):
                dot_distance = math.hypot(px - cx, py - cy) - dot_radius
                dot_cover = min(1.0, max(0.0, 0.5 - dot_distance))
                if dot_cover <= 0:
                    continue
                dot_color = ACCENT if index == 4 else DOT
                r = int(r * (1 - dot_cover) + dot_color[0] * dot_cover)
                g = int(g * (1 - dot_cover) + dot_color[1] * dot_cover)
                b = int(b * (1 - dot_cover) + dot_color[2] * dot_cover)

            offset = (y * size + x) * 4
            buffer[offset] = r
            buffer[offset + 1] = g
            buffer[offset + 2] = b
            buffer[offset + 3] = int(255 * a)
    return bytes(buffer)


def main() -> int:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []
    for size in sizes:
        images.append((size, _png(size, size, render(size))))

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    directory = bytearray()
    payload = bytearray()
    for size, data in images:
        directory += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,
            0 if size >= 256 else size,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        )
        payload += data
        offset += len(data)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(header + bytes(directory) + bytes(payload))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
