#!/usr/bin/env python3
"""Build del ejecutable nativo de Sword of Etheria (SLES_537.68) desde tu ISO.

Modelo legal (Ship of Harkinian, etc.): el repo distribuye solo código; vos
aportás tu ISO original PAL Europa. El script verifica su MD5 antes de tocarla.

Flujo (probado en Linux EndeavourOS 2026-10):
  1. Verifica MD5 del ISO (rechaza cualquier otro disco).
  2. Extrae el ELF SLES_537.68 a work/elf/ con bsdtar (o 7z en Windows).
  3. Genera config.toml con paths locales (stubs/skip mínimos).
  4. Compila ps2_recomp si falta, recompila el ELF a C++.
  5. Corre game/split_monsters.py (obligatorio tras cada ps2_recomp).
  6. Configura con Unix Makefiles y compila con -j4 (el build completo tarda
     horas y enlaza ~1.5 GB; usa Ninja solo si sabes lo que haces).

Uso:
  python build_release.py --iso "Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso"
  python build_release.py --iso tu.iso --check-only   # solo verifica MD5
  python build_release.py --help
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys

EXPECTED_MD5 = "b9c5115b77b7f05fbf14a67df8d3f99d"
EXPECTED_ISO = "Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso"
ELF_NAME = "SLES_537.68"

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def md5_of(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_iso(iso: str) -> str:
    if not os.path.isfile(iso):
        sys.exit(f"error: no existe el ISO: {iso}")
    print(f"verificando MD5 de {os.path.basename(iso)} (4.4 GB, tarda unos segundos)...")
    digest = md5_of(iso)
    if digest != EXPECTED_MD5:
        sys.exit(
            f"error: MD5 {digest} no coincide con el esperado {EXPECTED_MD5}.\n"
            f"Se requiere el ISO PAL Europa '{EXPECTED_ISO}'."
        )
    print("MD5 OK: ISO PAL Europa verificado.")
    return digest


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compila Sword of Etheria nativo desde tu ISO.")
    ap.add_argument("--iso", required=True, help="ruta a tu ISO PAL Europa")
    ap.add_argument("--work", default=os.path.join(REPO_ROOT, "work"), help="dir de trabajo local (no se versiona)")
    ap.add_argument("--tools", default=os.path.join(REPO_ROOT, "tools", "PS2Recomp"), help="clon de PS2Recomp")
    ap.add_argument("--jobs", default="4", help="paralelismo del build (default 4, seguro contra OOM)")
    ap.add_argument("--check-only", action="store_true", help="solo verifica MD5 y sale")
    args = ap.parse_args()

    check_iso(args.iso)
    if args.check_only:
        return

    elf_dir = os.path.join(args.work, "elf")
    gen_dir = os.path.join(args.work, "generated")
    build_dir = os.path.join(args.work, "build-game", "out-release")
    os.makedirs(elf_dir, exist_ok=True)

    elf_path = os.path.join(elf_dir, ELF_NAME)
    if not os.path.isfile(elf_path):
        extractor = shutil.which("bsdtar") or shutil.which("7z")
        if not extractor:
            sys.exit("error: se necesita bsdtar o 7z para extraer el ELF del ISO")
        run([extractor, "x", args.iso, "-o" + elf_dir, ELF_NAME]
            if os.path.basename(extractor) == "7z"
            else [extractor, "-x", "-C", elf_dir, "-f", args.iso, ELF_NAME])

    config_path = os.path.join(args.work, "config-release.toml")
    with open(config_path, "w") as f:
        f.write(
            "# Generado por build_release.py. Paths locales, stubs mínimos.\n"
            "[general]\n"
            f'input = "{elf_path}"\n'
            f'output = "{gen_dir}"\n'
            "single_file_output = false\n"
            "patch_syscalls = false\n"
            "patch_cop0 = true\n"
            "patch_cache = true\n"
            "stubs = []\n"
            "skip = []\n"
            "[patches]\n"
            "instructions = [\n"
            "    { address = 0x4c008c, value = 0x08130086 },\n"
            "]\n"
        )

    recomp = os.path.join(args.tools, "out", "ps2_recomp")
    if not os.path.isfile(recomp):
        run(["cmake", "-S", args.tools, "-B", os.path.join(args.tools, "out"),
             "-G", "Unix Makefiles", "-DCMAKE_BUILD_TYPE=Release"])
        run(["cmake", "--build", os.path.join(args.tools, "out"), "-j", args.jobs])
    run([recomp, config_path])
    # Regla de oro: splitter SIEMPRE después de ps2_recomp, antes de compilar.
    run([sys.executable, os.path.join(REPO_ROOT, "game", "split_monsters.py"), gen_dir])

    run(["cmake", "-S", os.path.join(REPO_ROOT, "game"), "-B", build_dir,
         "-G", "Unix Makefiles", "-DCMAKE_BUILD_TYPE=Release"])
    run(["cmake", "--build", build_dir, "-j", args.jobs])
    print(f"listo: {os.path.join(build_dir, 'sword_etheria')}")


if __name__ == "__main__":
    main()
