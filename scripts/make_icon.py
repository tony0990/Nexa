"""Create a simple Nexa application icon (32x32 ICO)."""

from __future__ import annotations

import struct
from pathlib import Path


def _bgra_bitmap(size: int = 32) -> bytes:
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            if 8 <= x <= 23 and 10 <= y <= 22:
                pixels += bytes((255, 255, 255, 255))
            else:
                pixels += bytes((0xF2, 0x6D, 0x3D, 255))
    and_mask = bytes((0,) * size * (size // 8))
    header = struct.pack("<3I2H2I2I2I", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0)
    return header + bytes(pixels) + and_mask


def write_icon(path: Path, size: int = 32) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dib = _bgra_bitmap(size)
    # ICONDIR + ICONDIRENTRY + image
    data = struct.pack("<HHH", 0, 1, 1)
    data += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(dib), 22)
    data += dib
    path.write_bytes(data)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    write_icon(root / "resources" / "icons" / "nexa.ico")


if __name__ == "__main__":
    main()
