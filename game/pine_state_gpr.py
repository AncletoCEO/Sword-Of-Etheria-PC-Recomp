#!/usr/bin/env python3
"""Lee los GPRs del EE desde PCSX2 (workaround al panel GPR roto del debugger).

Los GPRs viven en el savestate (`PCSX2 Internal Structures.dat`): array de 32
registros, stride 0x10, r0 en el offset 0x162 (gp=r28 en 0x322). PINE sirve para
disparar un SaveState en el momento exacto (p.ej. parado en un breakpoint).

Requisitos:
  - PCSX2 corriendo con PINE habilitado (`EnablePINE=true`, socket en $XDG_RUNTIME_DIR/pcsx2.sock).
  - `bsdtar` para extraer el .p2s (es zip+zstd).

Uso:
  python3 game/pine_state_gpr.py save 9    # PINE SaveState(slot 9) + imprime GPRs
  python3 game/pine_state_gpr.py read 9    # imprime GPRs del slot 9 ya existente
"""

from __future__ import annotations

import os
import socket
import struct
import subprocess
import sys
import time

SD = os.path.expanduser("~/.config/PCSX2/sstates")
STATE_PREFIX = "SLES-53768 (88E95888)"
GP = 0x00A28070
STRIDE = 0x10
NAMES = [
    "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
    "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
    "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
    "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra",
]


def _sock_path() -> str:
    return (os.environ.get("XDG_RUNTIME_DIR") or "/tmp") + "/pcsx2.sock"


def pine_savestate(slot: int, timeout: float = 15.0) -> int:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(_sock_path())

    def recv() -> bytes:
        hdr = b""
        while len(hdr) < 4:
            hdr += s.recv(4 - len(hdr))
        n = struct.unpack("<I", hdr)[0]
        body = b""
        while len(body) < n - 4:
            body += s.recv(n - 4 - len(body))
        return body

    s.sendall(struct.pack("<I", 5) + bytes([0x09, slot & 0xFF]))
    rep = recv()[0]
    s.close()
    return rep


def gp_regs(slot: int) -> dict[str, int]:
    path = os.path.join(SD, f"{STATE_PREFIX}.{slot:02d}.p2s")
    data = subprocess.run(
        ["bsdtar", "-xOf", path, "PCSX2 Internal Structures.dat"],
        capture_output=True,
    ).stdout
    if not data:
        raise SystemExit(f"no pude leer {path}")
    i = data.find(struct.pack("<I", GP))
    if i < 0:
        raise SystemExit("no encontré gp=0xA28070 en las structures")
    base = i - 28 * STRIDE
    return {NAMES[r]: struct.unpack_from("<I", data, base + r * STRIDE)[0] for r in range(32)}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd, slot = sys.argv[1], int(sys.argv[2])
    if cmd == "save":
        print(f"savestate(slot={slot}) reply={pine_savestate(slot)}")
        time.sleep(0.5)
    elif cmd != "read":
        print(__doc__)
        return 2
    for name, val in gp_regs(slot).items():
        print(f"{name:4s} = {val:08x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
