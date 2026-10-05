#!/usr/bin/env python3
"""Reporte estandarizado de smoke para Sword of Etheria recompilado.

Corre el binario con timeout, captura el log y resume en una tabla:
tick/gif/VRAM, modo audio (poll-storm vs transfers), spin 0x6e4d98,
imports sin resolver, triages activos y causa de salida.

Uso:
  python3 game/smoke_report.py [--secs 60] [--bin work/build-game/out-linux/sword_etheria]
                               [--elf work/elf/SLES_537.68] [--log /tmp/opencode/smoke.log]
  python3 game/smoke_report.py --parse-only --log /tmp/opencode/smoke.log

Solo stdlib. No toca el juego: solo ejecuta y parsea.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys


def parse_log(text: str) -> dict:
    rep: dict = {}
    ticks = [int(x) for x in re.findall(r"tick=(\d+)", text)]
    rep["tick_max"] = max(ticks) if ticks else None
    rep["tick_samples"] = len(ticks)
    rep["gif"] = sorted({m for m in re.findall(r"gif=(\d+)", text)})
    vram = re.findall(r"vramNonZero=(\d+)/(\d+)", text)
    rep["vram"] = sorted({f"{a}/{b}" for a, b in vram})
    rep["polls_20000"] = len(re.findall(r"rpc=0x20000", text))
    rep["transfers_30000"] = len(re.findall(r"rpc=0x30000", text))
    rep["hybrid_pre"] = len(re.findall(r"real corre", text))
    m = re.findall(
        r"0x6e4d98 counters a=(\d+) b=(\d+) flag5D0=(\d+) flag630=(\d+)(?: flag640=(\d+))?",
        text,
    )
    rep["spin_last"] = m[-1] if m else None
    rep["spin_hits"] = len(m)
    unh = re.findall(r"unhandled import ([a-z0-9]+:[0-9]+)", text)
    counts: dict[str, int] = {}
    for u in unh:
        counts[u] = counts.get(u, 0) + 1
    rep["unhandled"] = sorted(counts.items(), key=lambda kv: -kv[1])[:8]
    rep["triage"] = sorted(
        {
            name
            for name, pat in [
                ("vis", r"triage-vis"),
                ("iop-libsd", r"triage-iop. libsd"),
                ("spu-rw", r"triage-spu. (read|write)"),
                ("spu-dma", r"triage-spu. DMA start"),
                ("cdvd", r"triage-cdvd"),
                ("sleep", r"SleepThread id="),
                ("pos", r"TYOSD-pos"),
            ]
            if re.search(pat, text)
        }
    )
    tail = text[-600:]
    if "window close requested" in tail or "breaking out of loop" in tail:
        rep["end"] = "ventana cerrada (salida limpia temprana)"
    elif "terminate" in tail or "fatal" in tail or "SIGSEGV" in tail:
        rep["end"] = "CRASH (revisar cola del log)"
    else:
        rep["end"] = "timeout (corrida completa)"
    return rep


def verdict(rep: dict) -> str:
    if rep["tick_max"] is None:
        return "SIN ARRANQUE (sin ticks: revisar head del log)"
    gifs = rep["gif"]
    if gifs and all(g != "2" for g in gifs):
        return "PROGRESO (gif>2: hay escena nueva)"
    if rep["transfers_30000"] > 0 and rep["polls_20000"] == 0:
        return "TRANSFER (modo transfer estable, spin/cola por verificar)"
    if rep["polls_20000"] > 1000 and rep["transfers_30000"] == 0:
        return "POLL-STORM (driver atascado pre-transfer)"
    if rep["spin_last"] and rep["spin_last"][0] != rep["spin_last"][1]:
        return "SPIN-ACTIVO (cola sin drenar)"
    return "PARKED (estable sin crash, sin avance visible)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke + reporte de Sword of Etheria.")
    ap.add_argument("--secs", type=int, default=60)
    ap.add_argument("--bin", default="work/build-game/out-linux/sword_etheria")
    ap.add_argument("--elf", default="work/elf/SLES_537.68")
    ap.add_argument("--log", default="/tmp/opencode/smoke.log")
    ap.add_argument("--parse-only", action="store_true")
    args = ap.parse_args()

    if not args.parse_only:
        os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
        with open(args.log, "w") as f:
            try:
                subprocess.run(
                    [args.bin, args.elf],
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=args.secs,
                    check=False,
                )
                print(f"fin: exit 0 antes del timeout ({args.secs}s)")
            except subprocess.TimeoutExpired:
                print(f"fin: timeout {args.secs}s (comportamiento normal)")
            except FileNotFoundError as e:
                print(f"error: binario no encontrado: {e}")
                return 2

    with open(args.log, errors="replace") as f:
        text = f.read()
    rep = parse_log(text)
    print(f"== smoke: {args.log} ({len(text)} bytes) ==")
    print(f"tick_max={rep['tick_max']} muestras={rep['tick_samples']}")
    print(f"gif={rep['gif']} vram={rep['vram']}")
    print(f"polls_20000={rep['polls_20000']} transfers_30000={rep['transfers_30000']} hybrid_pre={rep['hybrid_pre']}")
    print(f"spin_hits={rep['spin_hits']} spin_last={rep['spin_last']}")
    print(f"unhandled={rep['unhandled']}")
    print(f"triage={rep['triage']}")
    print(f"fin={rep['end']}")
    print(f"VEREDICTO: {verdict(rep)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
