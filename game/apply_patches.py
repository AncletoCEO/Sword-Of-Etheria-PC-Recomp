#!/usr/bin/env python3
"""Aplica los parches versionados del juego sobre un clon de PS2Recomp (A1).

Los cambios al runtime que hacen avanzar el juego viven en el clon externo
`tools/PS2Recomp` (ignorado por git). Este script los reproduce desde
`game/patches/upstream/*.patch` (exportados con `git diff -w` sobre el
commit pineado) para que un clon limpio llegue al mismo estado.

Uso:
  python3 game/apply_patches.py --tools tools/PS2Recomp [--check-only]

- Idempotente: si un parche ya está aplicado (reverse-check limpio), se omite.
- `git apply --ignore-whitespace`: los patches se generaron con `-w` porque
  el árbol local mezcla finales de línea; el contenido semántico manda.
- Requiere que el clon esté en el commit pineado (ver PS2RECOMP_PIN);
  en otro caso `git apply` falla en contexto y el script aborta.

Sale 0 si todo aplicado/verificado, 1 si algo falla.
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH_DIR = os.path.join(REPO_ROOT, "game", "patches", "upstream")

# Commit de PS2Recomp contra el que se generaron los parches.
PS2RECOMP_PIN = "75d729ce40d7eed9649fd4bb05628dee520f3d0c"


def run(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Aplica parches del juego a PS2Recomp.")
    ap.add_argument("--tools", required=True, help="clon de PS2Recomp destino")
    ap.add_argument("--check-only", action="store_true", help="solo verifica")
    args = ap.parse_args()

    patches = sorted(glob.glob(os.path.join(PATCH_DIR, "*.patch")))
    if not patches:
        print("error: sin parches en game/patches/upstream/")
        return 1

    head = run(["git", "rev-parse", "HEAD"], args.tools)
    if head.returncode == 0:
        pinned = head.stdout.strip() == PS2RECOMP_PIN
        print(f"tools HEAD={head.stdout.strip()} pineado={pinned}")
        if not pinned:
            print(f"aviso: se esperan parches contra {PS2RECOMP_PIN}")

    failed: list[str] = []
    applied = skipped = 0
    for p in patches:
        name = os.path.basename(p)
        # ¿Ya aplicado? reverse-check limpio => skip.
        rev = run(["git", "apply", "--reverse", "--check", "--ignore-whitespace", p], args.tools)
        if rev.returncode == 0:
            print(f"skip (ya aplicado): {name}")
            skipped += 1
            continue
        if args.check_only:
            chk = run(["git", "apply", "--check", "--ignore-whitespace", p], args.tools)
            if chk.returncode != 0:
                print(f"FALLA check: {name}\n{chk.stderr.strip()[:400]}")
                failed.append(name)
            continue
        ap_ = run(["git", "apply", "--ignore-whitespace", p], args.tools)
        if ap_.returncode != 0:
            print(f"FALLA apply: {name}\n{ap_.stderr.strip()[:400]}")
            failed.append(name)
        else:
            print(f"ok: {name}")
            applied += 1

    print(f"aplicados={applied} omitidos={skipped} fallidos={len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
