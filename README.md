# Sword of Etheria — recompilación nativa para PC

Recompilación estática del ejecutable PS2 `SLES_537.68` (Sword of Etheria,
versión PAL Europa) a binario nativo de PC con
[PS2Recomp](https://github.com/ran-j/PS2Recomp).

## Estado

Experimental: el juego arranca, carga sus `.BIN` desde el disco, inicializa
GS/VSync y corre a 60 FPS, pero queda en pantalla negra en un spin-wait
(`0x6e4d98`, ver `game/6e4d98-spinwait-triage.md`). Todavía no hay menú
jugable. Los glitches gráficos/sonoros son limitación conocida de PS2Recomp.

## Requisitos

- Tu ISO original: `Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso`
- MD5 esperado: `b9c5115b77b7f05fbf14a67df8d3f99d`
- Linux: Git, CMake 3.20+, GCC C++20, Python 3, `bsdtar`, SDL/mesa
  (`base-devel cmake ninja git python pkgconf mesa libx11 ...`)
- Windows: Git, CMake 3.20+, MSVC C++20, Python 3, 7-Zip

## Uso

```bash
python build_release.py --iso "Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso"
./work/build-game/out-release/sword_etheria work/elf/SLES_537.68
```

Solo verificación del disco, sin compilar:

```bash
python build_release.py --iso tu.iso --check-only
```

El build completo tarda horas (recompila el ELF a ~18k `.cpp` y enlaza
~1.5 GB). Usá `-j4`; con más paralelismo el OOM killer mata `cc1plus`.
El splitter (`game/split_monsters.py`) corre solo tras cada `ps2_recomp`.

## Layout

- `game/` — `CMakeLists.txt`, `game_main.cpp`, `split_monsters.py`,
  parches de overrides (`game/patches/`) y notas de triage. Se versiona.
- `aspec/` — propuesta, diseño y tareas del change. Se versiona.
- `build_release.py`, `.github/workflows/` — release y CI. Se versionan.
- `work/` (13 GB), `tools/` (clones externos), `*.iso` — nunca se versionan.

## Nota legal

Trabajá solo con tu copia original y no distribuyas el ISO, el ELF ni los
`.BIN`. El repo y sus releases contienen únicamente código y herramientas;
el contenido del juego lo aporta cada usuario con su disco.
