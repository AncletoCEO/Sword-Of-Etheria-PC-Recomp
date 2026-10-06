#!/usr/bin/env python3
"""Sincroniza fuentes versionadas game/ -> work/build-game/ (A2).

Fuente de verdad: `game/` (versionado). El build de dev compila
`work/build-game/` (ignorado) por razones históricas (caché de objetos de
18k archivos; reconfigurar contra `game/` implicaría rebuild total).
Este script copia los archivos versionados cuando difieren, para que ambos
árboles no diverjan en silencio. Ejecutar antes de cada build de dev y desde
`build_release.py`.

Uso: python3 game/sync_work.py [--check-only]
Sale 0 siempre salvo error de IO (en --check-only sale 1 si hay diferencias).
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DIR = os.path.join(REPO_ROOT, "game")
WORK_DIR = os.path.join(REPO_ROOT, "work", "build-game")

SYNCED_FILES = ["CMakeLists.txt", "game_main.cpp", "split_monsters.py"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Sincroniza game/ -> work/build-game/.")
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()

    diffs = 0
    for name in SYNCED_FILES:
        src = os.path.join(GAME_DIR, name)
        dst = os.path.join(WORK_DIR, name)
        if not os.path.isfile(src):
            print(f"falta origen versionado: {src}")
            return 2
        same = os.path.isfile(dst) and filecmp.cmp(src, dst, shallow=False)
        if same:
            print(f"igual: {name}")
            continue
        diffs += 1
        if args.check_only:
            print(f"DIFIERE: {name}")
            continue
        shutil.copy2(src, dst)
        print(f"sincronizado: {name} -> work/build-game/")

    if args.check_only and diffs:
        print(f"divergencias={diffs}")
        return 1
    print(f"divergencias={diffs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
