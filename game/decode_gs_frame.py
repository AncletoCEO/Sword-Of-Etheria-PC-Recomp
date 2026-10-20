#!/usr/bin/env python3
"""Decodifica un volcado de VRAM PS2 en formato PSMCT32 a PNG.

El volcado se genera desde el runtime con:
  SWORD_DUMP_VRAM=/ruta/vram.bin SWORD_DUMP_VRAM_AT=<present> ./sword_etheria <elf>

El layout de direcciones es el mismo de
`tools/PS2Recomp/ps2xRuntime/include/runtime/gs/ps2_gs_psmct32.h`.
Se usa para verificar visualmente un frame (p. ej. el selector de video) en vez
de conformarse con `rgbNZ > 0`, que también lo cumple un fondo cualquiera.

Uso:
  python3 game/decode_gs_frame.py <vram.bin> <salida.png>
      [--fbp 0] [--fbw 10] [--width 640] [--height 448]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

BLOCK_TABLE_32 = (
    (0, 1, 4, 5, 16, 17, 20, 21),
    (2, 3, 6, 7, 18, 19, 22, 23),
    (8, 9, 12, 13, 24, 25, 28, 29),
    (10, 11, 14, 15, 26, 27, 30, 31),
)

COLUMN_TABLE_32 = (
    (0, 1, 4, 5, 8, 9, 12, 13),
    (2, 3, 6, 7, 10, 11, 14, 15),
    (16, 17, 20, 21, 24, 25, 28, 29),
    (18, 19, 22, 23, 26, 27, 30, 31),
    (32, 33, 36, 37, 40, 41, 44, 45),
    (34, 35, 38, 39, 42, 43, 46, 47),
    (48, 49, 52, 53, 56, 57, 60, 61),
    (50, 51, 54, 55, 58, 59, 62, 63),
)

VRAM_SIZE = 4 * 1024 * 1024


def addr_psmct32(block: int, width: int, x: int, y: int) -> int:
    page = (block >> 5) + (y >> 5) * width + (x >> 6)
    block_id = (block & 0x1F) + BLOCK_TABLE_32[(y >> 3) & 3][(x >> 3) & 7]
    page_offset = (block_id >> 5) << 13
    local_block = block_id & 0x1F
    return (
        (page << 13)
        + page_offset
        + local_block * 256
        + COLUMN_TABLE_32[y & 7][x & 7] * 4
    )


def decode(vram: bytes, fbp: int, fbw: int, width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            offset = addr_psmct32(fbp, fbw, x, y)
            pixels[x, y] = (vram[offset], vram[offset + 1], vram[offset + 2])
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vram", type=Path, help="volcado de 4 MB de VRAM")
    parser.add_argument("output", type=Path, help="PNG de salida")
    parser.add_argument("--fbp", type=int, default=0, help="FBP en bloques (default 0)")
    parser.add_argument("--fbw", type=int, default=10, help="FBW en páginas (default 10)")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=448)
    args = parser.parse_args()

    vram = args.vram.read_bytes()
    if len(vram) < VRAM_SIZE:
        print(f"error: {args.vram} tiene {len(vram)} bytes, se esperaban {VRAM_SIZE}", file=sys.stderr)
        return 1

    image = decode(vram, args.fbp, args.fbw, args.width, args.height)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)

    pixels = image.load()
    nonzero = 0
    bright = 0
    for y in range(args.height):
        for x in range(args.width):
            r, g, b = pixels[x, y]
            if r or g or b:
                nonzero += 1
            if max(r, g, b) >= 180:
                bright += 1

    print(
        f"{args.output}: {args.width}x{args.height} fbp={args.fbp} fbw={args.fbw} "
        f"nz={nonzero} bright={bright}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
