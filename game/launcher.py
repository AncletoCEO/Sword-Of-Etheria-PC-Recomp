#!/usr/bin/env python3
"""Launcher de Sword of Etheria — recomp nativo.

Flujo de producto (sin distribuir contenido del juego):

  1. Pide/recuerda la ruta de tu ISO PAL Europa y verifica su MD5.
  2. Extrae el ELF y el IOP del ISO a un directorio de datos del usuario.
  3. Recompila el ELF y compila el binario nativo **en tu máquina** la primera
     vez (cachea el build en el directorio de datos).
  4. Lanza el juego con el ELF y el ISO que aportaste.

El binario recompilado y el C++ generado nunca se distribuyen: son derivados de
tu ELF y quedan solo en tu disco. El release público son las herramientas.

Uso:
  python game/launcher.py
  python game/launcher.py --iso "Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso"
  python game/launcher.py --iso mi.iso --work /ruta/work --no-build
  python game/launcher.py --iso mi.iso --rebuild --jobs 4
  python game/launcher.py --check-only
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from build_release import ELF_NAME, EXPECTED_ISO, EXPECTED_MD5  # noqa: E402

APP_DIR_NAME = "sword-of-etheria"
CONFIG_NAME = "config.json"


def config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


def data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_NAME


def config_path() -> Path:
    return config_dir() / CONFIG_NAME


def load_config() -> dict:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def md5_of(path: Path) -> str:
    import hashlib

    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_iso(path: Path) -> bool:
    print(f"[launcher] Verificando MD5 de {path.name} (4.4 GB)...")
    digest = md5_of(path)
    if digest != EXPECTED_MD5:
        print("[launcher] MD5 no coincide.", file=sys.stderr)
        print(f"  esperado: {EXPECTED_MD5}", file=sys.stderr)
        print(f"  obtenido: {digest}", file=sys.stderr)
        print("Se requiere el ISO PAL Europa de Sword of Etheria.", file=sys.stderr)
        return False
    print("[launcher] MD5 OK.")
    return True


def pick_iso(current: str | None) -> str | None:
    """Pide la ruta por consola; intenta un diálogo si hay Tk/display."""
    if current:
        try:
            answer = input(f"ISO [{current}]: ").strip()
        except EOFError:
            answer = ""
        return answer or current
    try:
        answer = input(f"Ruta al ISO PAL Europa ({EXPECTED_ISO}): ").strip()
    except EOFError:
        answer = ""
    return answer or None


def extract_game_files(iso: Path, elf_dir: Path) -> None:
    """Extrae SLES_537.68 + IOP/ del ISO al directorio del ELF (una vez)."""
    elf_dir.mkdir(parents=True, exist_ok=True)
    if (elf_dir / ELF_NAME).is_file() and (elf_dir / "IOP").is_dir():
        return
    print("[launcher] Extrayendo SLES_537.68 e IOP/ del ISO...")
    extractor = shutil.which("bsdtar") or shutil.which("7z")
    if not extractor:
        raise SystemExit("error: falta bsdtar o 7z para extraer el ELF del ISO")
    if Path(extractor).name == "7z":
        cmd = [extractor, "x", "-y", f"-o{elf_dir}", str(iso), ELF_NAME, "IOP"]
    else:
        cmd = [extractor, "-xf", str(iso), "-C", str(elf_dir), ELF_NAME, "IOP"]
    subprocess.run(cmd, check=True)


def build_if_needed(iso: Path, work: Path, tools: Path, jobs: str, no_pin: bool, rebuild: bool) -> Path:
    exe = work / "build-game" / "out-release" / "sword_etheria"
    if exe.is_file() and not rebuild:
        print(f"[launcher] Usando build existente: {exe}")
        print("[launcher] (--rebuild para regenerarlo desde cero)")
        return exe
    cmd = [
        sys.executable,
        str(REPO_ROOT / "build_release.py"),
        "--iso", str(iso),
        "--work", str(work),
        "--tools", str(tools),
        "--jobs", str(jobs),
    ]
    if no_pin:
        cmd.append("--no-pin")
    print("[launcher] Compilando (la primera vez puede tardar horas)...")
    subprocess.run(cmd, check=True)
    if not exe.is_file():
        raise SystemExit(f"error: el build terminó pero no existe {exe}")
    return exe


def launch(exe: Path, elf: Path, iso: Path, work: Path, extra_args: list[str]) -> int:
    # El runtime autodetecta el ISO por nombre en el cwd. Usamos un cwd privado
    # con un symlink al nombre esperado, sin tocar la carpeta del usuario.
    exe = exe.resolve()
    elf = elf.resolve()
    iso = iso.resolve()
    work = work.resolve()
    run_dir = work / ".run"
    run_dir.mkdir(parents=True, exist_ok=True)
    link = run_dir / EXPECTED_ISO
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(iso.resolve())
    except OSError:
        # Windows sin permisos de symlink: copiamos solo el nombre esperado.
        shutil.copy2(iso, link)

    env = os.environ.copy()
    env.setdefault("SWORD_SIF_SEMA", "1")
    print(f"[launcher] Ejecutando {exe.name}…")
    return subprocess.run([str(exe), str(elf), *extra_args], cwd=run_dir, env=env).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Launcher de Sword of Etheria (recomp nativo).")
    ap.add_argument("--iso", help="ruta al ISO PAL Europa")
    ap.add_argument("--work", help="directorio de trabajo/build (default: datos del usuario)")
    ap.add_argument("--tools", help="clon de PS2Recomp (default: tools/PS2Recomp del repo)")
    ap.add_argument("--jobs", default="4", help="paralelismo del build (default 4)")
    ap.add_argument("--check-only", action="store_true", help="solo verifica el ISO y sale")
    ap.add_argument("--no-build", action="store_true", help="usar el build cacheado, no compilar")
    ap.add_argument("--rebuild", action="store_true", help="forzar recompilación")
    ap.add_argument("--no-pin", action="store_true", help="no hacer checkout del pin del runtime (dev)")
    ap.add_argument("--no-save", action="store_true", help="no guardar la ruta del ISO en la config")
    ap.add_argument("game_args", nargs=argparse.REMAINDER, help="argumentos extra para el juego")
    args = ap.parse_args()

    cfg = load_config()
    iso_arg = args.iso or cfg.get("iso")
    iso_path = Path(iso_arg).expanduser() if iso_arg else None
    if iso_path is None or not iso_path.is_file():
        picked = pick_iso(str(iso_path) if iso_path else None)
        if not picked:
            print("error: no se indicó un ISO.", file=sys.stderr)
            return 2
        iso_path = Path(picked).expanduser()
    if not iso_path.is_file():
        print(f"error: no existe el ISO: {iso_path}", file=sys.stderr)
        return 2

    if not verify_iso(iso_path):
        return 1
    if args.check_only:
        return 0

    work = Path(args.work).expanduser() if args.work else Path(cfg.get("work") or data_dir() / "work")
    tools = Path(args.tools).expanduser() if args.tools else Path(cfg.get("tools") or REPO_ROOT / "tools" / "PS2Recomp")
    work = work.resolve()
    tools = tools.resolve()
    work.mkdir(parents=True, exist_ok=True)
    elf_dir = work / "elf"
    extract_game_files(iso_path, elf_dir)
    elf = elf_dir / ELF_NAME

    if not args.no_save:
        cfg.update({"iso": str(iso_path.resolve()), "work": str(work), "tools": str(tools), "jobs": str(args.jobs)})
        save_config(cfg)

    exe = work / "build-game" / "out-release" / "sword_etheria"
    if not args.no_build:
        exe = build_if_needed(iso_path, work, tools, args.jobs, args.no_pin, args.rebuild)
    elif not exe.is_file():
        print(f"error: --no-build pero no existe {exe}", file=sys.stderr)
        return 2

    extra = [a for a in args.game_args if a != "--"]
    return launch(exe, elf, iso_path, work, extra)


if __name__ == "__main__":
    raise SystemExit(main())
