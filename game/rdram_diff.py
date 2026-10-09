#!/usr/bin/env python3
"""A/B de RDRAM: diff entre un dump del recomp y un savestate de PCSX2.

Uso:
  ./recomp_bin   con  SWORD_RDRAM_DUMP=/tmp/recomp.bin   (volcado de 512 KB desde 0xA20000)
  python3 rdram_diff.py /tmp/recomp.bin [savestate.p2s]

El savestate de PCSX2 2.x es un ZIP con `eeMemory.bin` (RDRAM de 32 MB).
Muestra el delta dominante (los punteros del heap suelen estar corridos) y las
primeras diferencias, lo que permite ubicar asignaciones/estructuras faltantes.
"""
import glob
import os
import struct
import sys
import zipfile
from collections import Counter

BASE = 0x00A20000
SIZE = 0x00080000


def default_savestate() -> str:
    hits = sorted(glob.glob(os.path.expanduser("~/.config/PCSX2/sstates/*.p2s")))
    if not hits:
        sys.exit("no encontre savestates en ~/.config/PCSX2/sstates/")
    return hits[0]


def main() -> None:
    dump = sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/recomp_rdram2.bin"
    ss_path = sys.argv[2] if len(sys.argv) > 2 else default_savestate()
    recomp = open(dump, "rb").read()
    with zipfile.ZipFile(ss_path) as z:
        m = z.read("eeMemory.bin")
    ss = m[BASE:BASE + len(recomp)]

    diffs = []
    for i in range(0, len(recomp), 4):
        a = struct.unpack_from("<I", recomp, i)[0]
        b = struct.unpack_from("<I", ss, i)[0]
        if a != b:
            diffs.append((BASE + i, a, b))

    total = len(recomp) // 4
    print(f"dump={dump}\nsavestate={os.path.basename(ss_path)}")
    print(f"total diffs: {len(diffs)} de {total} ({100 * len(diffs) / total:.1f}%)")

    deltas: Counter = Counter()
    other = []
    for addr, a, b in diffs:
        if 0x00A93000 <= a < 0x00AB0000 and 0x00A93000 <= b < 0x00AB0000:
            deltas[b - a] += 1
        else:
            other.append((addr, a, b))
    print("deltas en punteros del heap (consola-recomp):",
          dict(sorted(deltas.items(), key=lambda kv: -kv[1])[:8]))

    print(f"\nprimeras {min(25, len(other))} diferencias no-heap:")
    for addr, a, b in other[:25]:
        print(f"  {addr:#010x}: recomp={a:08x} consola={b:08x}")


if __name__ == "__main__":
    main()
