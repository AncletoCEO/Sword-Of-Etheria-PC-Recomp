#!/usr/bin/env python3
"""Genera el overlay menu.bin (OL.BIN) recompilado para el build local.

El C++ derivado del overlay NO se versiona ni se distribuye: se regenera en la
maquina del usuario a partir de su ISO. Este script:

1. Localiza OL.BIN (o lo extrae del ISO con bsdtar/7z si hace falta).
2. Encuentra el overlay menu.bin (MWo3, load 0x100000, .ctors 0x1a1b20).
3. Construye un ELF32 sintetico con el payload en 0x100000 y simbolos en los
   destinos main->overlay detectados en work/generated.
4. Corre ps2_recomp con esos entry points.
5. Prepara work/generated-overlay (header/shim/registro dinamico) para que
   game/CMakeLists.txt lo compile como menu_overlay.

Uso:
  python3 game/build_overlay.py --olbin work/elf/OL.BIN \
      --generated work/generated --out work/generated-overlay \
      --recomp tools/PS2Recomp/out/ps2_recomp
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import subprocess
import sys

MENU_LOAD = 0x00100000
MENU_CTORS_START = 0x001A1B20
BASE_SYMBOLS = (0x100080, 0x1096C0, 0x1A1B00)


def find_mwo3_entries(data: bytes) -> list[int]:
    out: list[int] = []
    i = 0
    while True:
        i = data.find(b"MWo3", i)
        if i < 0:
            return out
        out.append(i)
        i += 1


def read_overlay_header(data: bytes, off: int) -> dict:
    words = struct.unpack_from("<8I", data, off + 4)
    return {
        "hdr": words[0],
        "load": words[1],
        "text": words[2],
        "data": words[3],
        "bss": words[4],
        "ctors_start": words[5],
        "ctors_end": words[6],
    }


def find_menu_overlay(data: bytes) -> tuple[int, int, dict]:
    entries = find_mwo3_entries(data)
    for idx, off in enumerate(entries):
        h = read_overlay_header(data, off)
        if h["load"] == MENU_LOAD and h["ctors_start"] == MENU_CTORS_START:
            end = entries[idx + 1] if idx + 1 < len(entries) else len(data)
            return off, end, h
    raise SystemExit("no se encontro el overlay menu.bin (MWo3 load=0x100000, .ctors=0x1a1b20)")


def extract_olbin_from_iso(iso: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, "OL.BIN")
    if os.path.isfile(dst):
        return dst
    extractor = None
    for cand in ("bsdtar", "7z"):
        for path in os.environ.get("PATH", "").split(os.pathsep):
            p = os.path.join(path, cand)
            if os.path.isfile(p):
                extractor = p
                break
        if extractor:
            break
    if not extractor:
        raise SystemExit("falta OL.BIN y no hay bsdtar/7z para extraerlo del ISO")
    if os.path.basename(extractor) == "7z":
        cmd = [extractor, "x", iso, "-o" + out_dir, "OL.BIN", "-y"]
    else:
        cmd = [extractor, "-x", "-C", out_dir, "-f", iso, "OL.BIN"]
    subprocess.run(cmd, check=True)
    if not os.path.isfile(dst):
        raise SystemExit(f"no se pudo extraer OL.BIN de {iso}")
    return dst


def collect_overlay_targets(generated_dir: str, text_end: int) -> list[int]:
    """Destinos main->overlay que el ELF principal despacha por direccion."""
    targets: set[int] = set(BASE_SYMBOLS)
    pat = re.compile(r"0x1[0-9a-fA-F]{5}")
    for name in os.listdir(generated_dir):
        if not name.endswith(".cpp"):
            continue
        path = os.path.join(generated_dir, name)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "dispatchGuestBranch" not in line:
                        continue
                    for m in pat.finditer(line):
                        a = int(m.group(0), 16)
                        if 0x100080 <= a < text_end and (a & 3) == 0:
                            targets.add(a)
        except OSError:
            continue
    return sorted(targets)


def build_elf32(payload: bytes, load: int, symbols: list[int]) -> bytes:
    shstr = b"\x00.text\x00.strtab\x00.symtab\x00.shstrtab\x00"
    names = {".text": 1, ".strtab": 7, ".symtab": 15, ".shstrtab": 23}

    strtab = bytearray(b"\x00")
    syms: list[tuple[int, int]] = []
    for a in symbols:
        name = f"f_{a:08x}".encode() + b"\x00"
        syms.append((len(strtab), a))
        strtab += name

    off = 0x1000
    shoff = off + len(payload)
    strtab_off = shoff + 5 * 40
    symtab_off = strtab_off + len(strtab)
    shstr_off = symtab_off + 16 * (1 + len(syms))

    e_ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\x00" * 8
    hdr = e_ident + struct.pack(
        "<HHIIIIIHHHHHH",
        2, 8, 1, 0x100080, 52, shoff, 0x20924001, 52, 32, 1, 40, 5, 4,
    )
    ph = struct.pack("<IIIIIIII", 1, off, load, load, len(payload), len(payload), 7, 0x80)

    def sh(name, typ, flags, addr, offset, size, link=0, info=0, align=1, entsize=0):
        return struct.pack("<IIIIIIIIII", name, typ, flags, addr, offset, size, link, info, align, entsize)

    sections = sh(0, 0, 0, 0, 0, 0)
    sections += sh(names[".text"], 1, 0x6, load, off, len(payload), 0, 0, 0x80, 0)
    sections += sh(names[".strtab"], 3, 0, 0, strtab_off, len(strtab))
    sections += sh(names[".symtab"], 2, 0, 0, symtab_off, 16 * (1 + len(syms)), 2, 1, 4, 16)
    sections += sh(names[".shstrtab"], 3, 0, 0, shstr_off, len(shstr))

    symdata = bytearray(struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0))
    for nameoff, addr in syms:
        symdata += struct.pack("<IIIBBH", nameoff, addr, 0, 0x12, 0, 1)

    out = bytearray(hdr + ph)
    out += b"\x00" * (off - len(out))
    out += payload
    out += sections
    out += strtab
    out += symdata
    out += shstr
    return bytes(out)


def write_config(path: str, elf: str, out_dir: str, targets: list[int]) -> None:
    eps = ", ".join(f'"0x{a:x}"' for a in targets)
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "[general]\n"
            f'input = "{elf}"\n'
            f'output = "{out_dir}"\n'
            "single_file_output = false\n"
            "patch_syscalls = false\n"
            "patch_cop0 = true\n"
            "patch_cache = true\n"
            "stubs = []\n"
            "skip = []\n"
            f"entry_points = [{eps}]\n"
        )


def postprocess(recomp_dir: str, out_dir: str) -> int:
    os.makedirs(os.path.join(out_dir, "include"), exist_ok=True)
    funcs = 0
    for name in os.listdir(recomp_dir):
        src = os.path.join(recomp_dir, name)
        if name == "ps2_recompiled_functions.h":
            continue
        if not name.endswith(".cpp"):
            continue
        with open(src, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        if name == "register_functions.cpp":
            text = text.replace("g_ps2RecompiledFunctionTableSlotCount", "g_menuOverlayFunctionTableSlotCount")
            text = text.replace("g_ps2RecompiledFunctionTableBase", "g_menuOverlayFunctionTableBase")
            text = text.replace("g_ps2RecompiledFunctionTableEnd", "g_menuOverlayFunctionTableEnd")
            text = text.replace("g_ps2RecompiledFunctionTable", "g_menuOverlayFunctionTable")
            text += """

#include <iostream>
void sword_register_overlay_functions(PS2Runtime &rt)
{
    uint32_t n = 0;
    for (uint32_t i = 0; i < g_menuOverlayFunctionTableSlotCount; ++i)
    {
        if (g_menuOverlayFunctionTable[i])
        {
            rt.registerFunction(g_menuOverlayFunctionTableBase + i * 4u, g_menuOverlayFunctionTable[i]);
            ++n;
        }
    }
    std::cerr << "[menu-overlay] registered " << n << " entrypoints" << std::endl;
}
"""
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(text)
        funcs += 1

    hdr_src = os.path.join(recomp_dir, "ps2_recompiled_functions.h")
    with open(hdr_src, "r", encoding="utf-8", errors="ignore") as f:
        hdr = f.read()
    hdr = hdr.replace("PS2_RECOMPILED_FUNCTIONS_H", "MENU_OVERLAY_FUNCTIONS_H")
    with open(os.path.join(out_dir, "menu_overlay_functions.h"), "w", encoding="utf-8") as f:
        f.write(hdr)

    # El shim resuelve el header principal por layout hermano work/generated.
    with open(os.path.join(out_dir, "include", "ps2_recompiled_functions.h"), "w", encoding="utf-8") as f:
        f.write(
            "#pragma once\n"
            '#include "../../generated/ps2_recompiled_functions.h"\n'
            '#include "../menu_overlay_functions.h"\n'
        )
    return funcs


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera el overlay menu.bin recompilado.")
    ap.add_argument("--olbin", default="", help="ruta a OL.BIN")
    ap.add_argument("--iso", default="", help="ISO del juego (si falta OL.BIN)")
    ap.add_argument("--generated", default="work/generated", help="C++ generado del ELF principal")
    ap.add_argument("--out", default="work/generated-overlay", help="directorio de salida")
    ap.add_argument("--recomp", default="tools/PS2Recomp/out/ps2_recomp", help="binario ps2_recomp")
    ap.add_argument("--work", default="work/overlay", help="directorio de artefactos temporales")
    args = ap.parse_args()

    olbin = args.olbin
    if not olbin:
        cand = os.path.join(os.path.dirname(args.generated), "OL.BIN")
        if os.path.isfile(cand):
            olbin = cand
    if not olbin or not os.path.isfile(olbin):
        if args.iso:
            olbin = extract_olbin_from_iso(args.iso, os.path.join(args.work, "elf"))
        else:
            raise SystemExit("falta OL.BIN (usar --olbin o --iso)")

    data = open(olbin, "rb").read()
    start, end, hdr = find_menu_overlay(data)
    payload = data[start:end]
    text_end = hdr["load"] + hdr["text"]
    print(f"[overlay] OL.BIN {olbin}: menu.bin 0x{start:x}..0x{end:x} "
          f"({len(payload)} bytes), load=0x{hdr['load']:x} text_end=0x{text_end:x}")

    targets = collect_overlay_targets(args.generated, text_end)
    print(f"[overlay] {len(targets)} entrypoints main->overlay")

    os.makedirs(args.work, exist_ok=True)
    elf_path = os.path.join(args.work, "menu-overlay.elf")
    with open(elf_path, "wb") as f:
        f.write(build_elf32(payload, hdr["load"], targets))

    recomp_out = os.path.join(args.work, "generated")
    if os.path.isdir(recomp_out):
        for name in os.listdir(recomp_out):
            os.unlink(os.path.join(recomp_out, name))
    os.makedirs(recomp_out, exist_ok=True)
    cfg = os.path.join(args.work, "config.toml")
    write_config(cfg, elf_path, recomp_out, targets)

    recomp = args.recomp
    if not os.path.isfile(recomp):
        raise SystemExit(f"no existe ps2_recomp: {recomp}")
    subprocess.run([recomp, cfg], check=True)

    os.makedirs(args.out, exist_ok=True)
    for name in os.listdir(args.out):
        p = os.path.join(args.out, name)
        if os.path.isfile(p) or os.path.islink(p):
            os.unlink(p)
    funcs = postprocess(recomp_out, args.out)
    print(f"[overlay] listo: {funcs} archivos en {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
