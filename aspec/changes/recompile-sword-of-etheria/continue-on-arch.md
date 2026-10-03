# Continuar en EndeavourOS (Arch) — guía de pendientes

Idioma: español. Contexto: build de Windows pausado al ~90% para migrar a Linux.
Todo lo pesado e irrepetible ya está hecho y viaja; en Arch solo falta compilar.

## 1. Estado al pausar (17/25 tasks)

Hecho y portable: toolchain verificado, ELF extraído (`SLES_537.68`, entry
`0x004C0008`, stripped), análisis Ghidra headless (7672 funciones + 10100 labels),
`config.toml` + CSV, C++ generado (17771 archivos) con 18 monstruos divididos
(`split_monsters.py`), proyecto `work/build-game` ya portable (sin paths duros,
flags MSVC y GCC/Clang).

No portable (no copiar): `tools/`, `out*/`, `*.obj`, `*.exe`, `*.lib`, JDK/Ghidra
instalados, el ISO (4.4 GB, ya no hace falta).

## 2. Qué copiar (USB, ~4.1 GB)

- `aspec/` (0.7 MB): proposal, design, tasks, `config.toml`,
  `ghidra_functions.csv`, wrapper Ghidra, esta guía.
- `work/elf/SLES_537.68` (6 MB): el juego. El ISO no viaja.
- `work/generated/` (~2.2 GB): los 17k `.cpp` ya divididos. **Es el input del build.**
- `work/generated_orig/` (~1.9 GB, opcional): backup pre-split, por si hay que re-dividir.
- `work/build-game/` (solo `CMakeLists.txt`, `game_main.cpp`, `split_monsters.py`).
- `.gitignore`.

Estructura esperada en Arch (misma raíz para todo):
`<repo>/aspec <repo>/work/{elf,generated,generated_orig,build-game} <repo>/.gitignore`

## 3. Setup en EndeavourOS (una vez)

```bash
sudo pacman -Syu
sudo pacman -S --needed base-devel cmake ninja git python pkgconf
# Video/SDL (según tu sesión X11 o Wayland; si el configure de SDL se queja):
sudo pacman -S --needed mesa libx11 libxext libxrandr libxfixes libxi libxcursor wayland
gcc --version   # Arch rolling trae 15+: C++20 OK
```

No instalar: Ghidra, JDK, 7-Zip (`p7zip` solo si algún día re-extraés el ISO),
ni nada de Windows. El análisis Ghidra ya está hecho y no se repite.

## 4. Build en Arch

```bash
git clone --recurse-submodules https://github.com/ran-j/PS2Recomp.git tools/PS2Recomp
cmake -S work/build-game -B work/build-game/out-linux -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build work/build-game/out-linux --target sword_etheria -j$(nproc)
```

Notas:

- `-DCMAKE_BUILD_TYPE=Release` es obligatorio (un configure quedó en Debug y
  metió `/RTC1`+`-MDd`: lento e inútil).
- La primera compilación tarda horas en máquina modesta (runtime + raylib +
  monstruos); es incremental, se puede cortar y retomar.
- Flags Linux ya puestos en el CMake (`-O0 -fno-inline -fno-stack-protector
  -g0`): build de triage, rápido de compilar. Hay `TODO(perf/seguridad)` para
  el build final.
- `ps2_runtime` está probado sobre todo con MSVC: si GCC protesta, será parche
  menor en `tools/` (no versionar: está gitignored).
- Case-sensitive: si algún `#include` falla por mayúsculas, avisar (los
  generados usan minúsculas consistentes).

## 5. `config.toml`: no tocar (salvo regeneración)

Tiene rutas absolutas de Windows, pero el build NO lo usa (compila
`work/generated/` directo). Solo importaría si re-corres `ps2_recomp`. Plan B
si algún día hace falta regenerar en Linux: `sudo pacman -S ghidra
jdk21-openjdk`, `analyzeHeadless` con el wrapper de
`aspec/changes/recompile-sword-of-etheria/ghidra/`, y re-correr
`split_monsters.py` (los divididos se pisan: el backup está en
`work/generated_orig/`).

## 6. Fase 4: primer arranque (tras el exe)

```bash
./work/build-game/out-linux/sword_etheria   # usa el ELF por defecto; o argv[1]
```

Esperable: crash temprano por stubs/syscalls vacíos (ELF stripped). Ciclo
documentado en `tasks.md`: bloqueantes primero → stubs reales →
`ret0`/`ret1`/`reta0` solo como triage → `handler@0xADDRESS` →
game override (`PS2_REGISTER_GAME_OVERRIDE`) → re-test en frío. Hito de cierre:
menú + inicio de partida; glitches menores se registran, no bloquean.

## 7. Problemas conocidos heredados (no redescubrir)

- `ps2_analyzer` se cuelga >30 min en este ELF: no usarlo.
- 5 funciones de 77–246 MB y otras 26 de 1–121 MB: ya divididas con
  `split_monsters.py` (dispatcher + bsearch + loop plano, sin stack growth).
- `FUN_007c2070` tiene instrucciones sin manejar (región de datos): el recompiler
  igual completó; vigilar en Fase 4.
- VS auto-actualizó el toolset a mitad de un build en Windows: en Arch, `pacman
  -Syu` a mitad de build tiene el mismo riesgo; preferir no actualizar durante
  compilaciones largas.
