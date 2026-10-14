#!/usr/bin/env python3
"""Guarda/restaura savestates de PCSX2 por NOMBRE (para rotar los 9 slots).

Los .p2s viven en ~/.config/PCSX2/sstates/SLES-53768 (88E95888).NN.p2s.
Este script los copia a `work/pcsx2_states/<nombre>.p2s` y de vuelta, así podés
tener muchos estados guardados aunque PCSX2 sólo tenga 9 slots.

Uso:
  python3 game/pcsx2_state.py save <slot> <nombre>   # copia slot -> carpeta
  python3 game/pcsx2_state.py restore <nombre> <slot> # copia carpeta -> slot
  python3 game/pcsx2_state.py list                    # lista guardados
  python3 game/pcsx2_state.py slots                   # lista slots en PCSX2
"""

from __future__ import annotations

import glob
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SD = os.path.expanduser("~/.config/PCSX2/sstates")
PREFIX = "SLES-53768 (88E95888)"
STORE = os.path.join(REPO, "work", "pcsx2_states")


def slot_path(slot: int) -> str:
    return os.path.join(SD, f"{PREFIX}.{slot:02d}.p2s")


def main() -> int:
    os.makedirs(STORE, exist_ok=True)
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "save" and len(sys.argv) == 4:
        slot, name = int(sys.argv[2]), sys.argv[3]
        shutil.copy2(slot_path(slot), os.path.join(STORE, f"{name}.p2s"))
        print(f"slot {slot} -> {STORE}/{name}.p2s")
    elif cmd == "restore" and len(sys.argv) == 4:
        name, slot = sys.argv[2], int(sys.argv[3])
        shutil.copy2(os.path.join(STORE, f"{name}.p2s"), slot_path(slot))
        print(f"{name}.p2s -> slot {slot}")
    elif cmd == "list":
        for f in sorted(glob.glob(os.path.join(STORE, "*.p2s"))):
            print(os.path.basename(f)[:-4])
    elif cmd == "slots":
        for f in sorted(glob.glob(os.path.join(SD, f"{PREFIX}.*.p2s"))):
            b = os.path.basename(f)
            print(f"{b.rsplit('.', 1)[0].split('.')[-1]}  {os.path.getsize(f)}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
