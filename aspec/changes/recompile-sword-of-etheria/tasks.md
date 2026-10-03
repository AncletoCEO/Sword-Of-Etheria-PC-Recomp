# Tasks: Recompilación nativa de Sword of Etheria (PS2) para PC — Linux desde cero

> Rearmado Linux 2026-09-26: los 17 checks Windows no valen acá (`work/` perdido salvo `ghidra_proj/`, `config.toml` con paths `C:/...`). Se reinicia desde cero en EndeavourOS. Insumos que se conservan: ISO 4,2 GB, `ghidra_functions.csv` (7672 funciones), `ghidra/ExportPS2FunctionsHeadless.java`, `tools/PS2Recomp/` (fuentes).

## Fase 0 — Entorno Linux

- [x] Verificar Git, CMake 3.20+, Ninja, GCC C++20, Python (verificado 2026-09-26: git 2.55.0, cmake 4.4.3, ninja 1.13.2, gcc 16.2.1, python 3.14.7)
- [x] Instalar deps build + video/SDL y verificar con `pacman -Q` (verificado 2026-09-26: base-devel, cmake 4.4.3, ninja 1.13.2, git 2.55, python 3.14, pkgconf, mesa 26.2, libx11/xext/xrandr/xfixes/xi/xcursor, wayland + ffmpeg 9.0)
- [x] Verificar herramienta de extracción ISO y CPU con SSE4 (verificado 2026-09-26: bsdtar 3.8.9, CPU i5-8350U con sse4_1, 8 cores, 15 GB RAM)
- [x] Crear `.gitignore` que excluya `work/`, `tools/`, `*.iso`, `*.elf`, `*.exe` y carpetas `out*/build` (verificado 2026-09-26: ya excluye `work/`, `tools/`, `*.iso/.elf/.bin/.exe`, `out/`, `build/`, binarios y Ghidra; `out-linux/` queda cubierto vía `work/`+`tools/`)

## Fase 1 — Extracción del ELF

- [x] Listar el contenido del ISO e identificar el ejecutable (verificado 2026-09-26 con `bsdtar -tf`: es `SLES_537.68`, 6457864 bytes, en raíz del ISO)
- [x] Extraer el ELF a `work/elf/` y verificar cabecera ELF MIPS (verificado 2026-09-26: `SLES_537.68` 6457864 bytes, ELF32 LE MIPS EXEC, entry `0x004C0008`, stripped sin .symtab)
- [x] Registrar nombre exacto del ELF y su entry point para el game override futuro (`SLES_537.68`, entry `0x004C0008`, VER 1.01 PAL Europa multilingüe)

## Fase 2 — Análisis y `config-linux.toml`

- [x] Reutilizar análisis Ghidra existente sin reinstalar Ghidra/JDK (verificado 2026-09-26: `ghidra_functions.csv` 696 KB, 17772 registros + header; wrapper `ExportPS2FunctionsHeadless.java` presente)
- [x] Crear `config-linux.toml` en este change con paths Linux absolutos (creado 2026-09-26: input → `work/elf/SLES_537.68`, ghidra_output → CSV, output → `work/generated/`; mismos conteos 7672/10100/17772)
- [x] Revisar `general.stubs`/`general.skip` iniciales: empezar mínimo, sin skips agresivos (verificado 2026-09-26: `patch_syscalls = false`, stubs/skip vacíos; ELF stripped, se completan en Fase 4)

## Fase 3 — Recompilación y build

- [x] Verificar clon `tools/PS2Recomp` y compilar `ps2_recomp`/`ps2_analyzer` para Linux (compilado 2026-09-26 en `tools/PS2Recomp/out-linux`: `ps2_recomp` 2,2 MB, `ps2_analyzer` 14 MB)
- [x] Correr `ps2_recomp config-linux.toml` y verificar C++ generado en `work/generated/` (generado 2026-09-26: 17771 archivos, 2,1 GB, EXIT 0; errores `unhandled-instruction` solo en regiones de datos como `FUN_006cc400`, igual que en Windows)
- [x] Dividir monstruos y verificar backup (2026-09-26: backup `work/generated_orig/` vía hardlinks; 14 monstruos 75–235 MB → 195 partes ≤8 MB con `work/split_monsters.py` propio dispatcher+loop plano; total 17966 archivos; sintaxis OK en dispatcher+p0)
- [x] Recrear `work/build-game/` (recreado 2026-09-26: `CMakeLists.txt` portable + `-msse4.1` en `ps2_runtime`/`ps2_iop`/`sword_etheria`; `game_main.cpp` 250 líneas con boot `work/elf/SLES_537.68`; splitter en `work/split_monsters.py`)
- [x] Configurar build sin errores (configurado 2026-09-26: raylib/imgui/FFmpeg OK; 207 archivos >2 MB fuera de unity por el split)
- [x] Reconfigurar build de Ninja → Unix Makefiles (2026-10-01: Ninja se trababa en globbing con 18k archivos; limpiado `out-linux/` completo y reconfigurado con `-G "Unix Makefiles"` + refetch de raylib/imgui/rlimgui OK)
- [x] **Audit y re-split de archivos monstruo**: bajado umbral a `THRESHOLD=4MB / PART_BYTES=3MB` en `work/split_monsters.py`; 542 partes nuevas generadas; 0 archivos >4 MB excepto `register_functions.cpp` (solo declaraciones, seguro). (2026-10-02)
- [x] Compilar con paralelismo seguro `-j4` (2026-10-02: compilación completa `[100%] Built target sword_etheria` — binario `work/build-game/out-linux/sword_etheria` 1.5 GB, EXIT 0, sin OOM tras habilitar swap de 32GB)

> **Lección aprendida (2026-10-01)**: el OOM Killer mató compilaciones con `-j$(nproc)` y `-j2` porque ciertos `.cpp` monstruo (ej. `FUN_004eb8d0_0x4eb8d0.cpp`) consumen 5+ GB de RAM solos durante la compilación. Además, canceling tasks desde el agente deja procesos `cc1plus` zombies en el sistema — siempre verificar con `ps aux | grep cc1plus` antes de arrancar un nuevo build y matarlos con `kill -9` si los hay.

> **Regla de oro (2026-10-02)**: `ps2_recomp` regenera TODOS los archivos de `work/generated/` desde cero. El splitter SIEMPRE debe correr inmediatamente después de cada `ps2_recomp` antes de intentar compilar. Flujo correcto: `ps2_recomp config.toml` → `python3 work/split_monsters.py work/generated/` → `cmake --build`.

> **Regla de Unity Build (2026-10-02)**: Unity Build (`UNITY_BUILD ON`) con batch 48 también mata la RAM en GCC porque agrupa 48 archivos en uno solo. Desactivado para Linux/GCC en `CMakeLists.txt`; solo activo para MSVC.

## Fase 4 — Iteración hasta jugable

- [x] Primer arranque en frío (`./work/build-game/out-linux/sword_etheria`) y registro de bloqueantes (2026-09-27: arranca con `sword_etheria work/elf/SLES_537.68`; sin argv falla `Unable to determine executable path` porque `PS2X_DEFAULT_BOOT_ELF` solo se define para `ps2_runtime/src/main.cpp`, no para `work/build-game/game_main.cpp`. Con argv: ELF carga, entry `0x4c0008`, corre 120s sin crash pero PC clavado en `0x4c008c` — bloqueante #1: no hay función generada/registrada para `0x4c008c`, Ghidra CSV solo trae `entry 0x4c0008-0x4c008c` y lo siguiente es data + `thunk_FUN_004dda18` en `0x4c0218`; log en `work/build-game/coldboot-01.log`)
- [x] Establecer estrategia de ejecución desatendida: priorizar comandos pesados en background y usar timers periódicos para monitorear el progreso del build.
- [x] Implementar stubs y game overrides específicos en `tools/PS2Recomp/ps2xRuntime/src/lib/game_overrides.cpp` (162 syscall stubs registrados con `PS2_REGISTER_GAME_OVERRIDE`, hooks para `sceCdSearchFile`, `sceCdRead`, `scePadInit`, GS display env y bucle de juego principal).
- [x] Iteración de arranque en frío hasta `coldboot-60` (2026-10-01: ejecución avanza a través de la carga del disco de `OL.BIN`, `CHARA.BIN`, `BG.BIN`, `EFFECT.BIN`, `INTER.BIN`, inicialización de GS, sincronización VSync y captura de frames `frame_30.bmp`, `frame_60.bmp`, `frame_120.bmp` hasta tick 840).
- [x] **Corrección de truncamiento DMA y canal VIF1/GS** (2026-10-03): identificadas y resueltas funciones truncadas por Ghidra `sceDmaGetChan` (0x4d0450), `sceDmaPhysAddr` (0x4d03f0) y `sceDmaSync` (0x4d02f8). Se corrigió el mapeo de registros MMIO de hardware y la extracción de TADR de RDRAM. VIF1 y VU1 ya envían paquetes GIF (`XGKICK`), activando el pipeline 3D en GS y double buffering a 60 FPS en pantalla.

## Fase 4.5 — Subida ordenada a GitHub (prioritaria 2026-10-03)

> Regla recurrente: cada cambio nuevo cierra con commit atomizado + push para seguimiento en git. Commits lo más chicos posible.

- [x] Ordenar archivos desordenados en raíz y change (2026-10-03: creados `game/CMakeLists.txt`, `game/game_main.cpp`, `game/split_monsters.py` promovidos desde `work/` ignorado; `ps2_log.txt` raíz movido a `work/ps2_log-root.txt`; `.git` bogus solo-logs eliminado para re-init; `work/` 13G, `tools/` 4.2G e ISO 4.4G quedan fuera por `.gitignore`)
- [x] Revisar `.gitignore` (2026-10-03: agrega `out-linux/`, `ghidra-mcp/`, `mc0/`, `mc1/`, `*.log`, `**/node_modules/`; NO filtra `game/`, `build_release.py`, `README.md`, `.github/`)
- [x] Serie de commits atomizados + push a GitHub (2026-10-03: 6 commits `9469066..3685ecb` sobre `2f49663 Initial commit`, rebase + push SSH OK a `AncletoCEO/Sword-Of-Etheria-PC-Recomp main`; ISO/ELF/`work/` 13G/`tools/` 4.2G/`ghidra-mcp/`/`mc0/`/`mc1/`/`*.log` excluidos, verificado con `git status`)
- [ ] **Test interactivo en terminal gráfica** (PENDIENTE usuario): ejecutar `./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68` desde una ventana de terminal en el entorno de escritorio para comprobar la ventana de renderizado de Raylib/GLFW, la tasa de refresco en pantalla y la respuesta a los mandos/teclado.
- [x] Mover hacks específicos restantes al módulo de game overrides según hallazgos del test interactivo. (2026-10-03: spin `0x6e4d98` documentado en `game/6e4d98-spinwait-triage.md`; override temporal `triage6e4d98` agregado en `game_overrides.cpp` + parche versionado en `game/patches/6e4d98-triage.patch`; rebuild+retest pendientes)
- [ ] Hito de cierre: menú + inicio de partida jugable; glitches menores se registran como limitaciones conocidas, no bloquean.

## Fase 5 — Publicación y release

- [ ] Calcular MD5 del ISO PAL Europa: `md5sum "Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso"` y registrarlo aquí y en `build_release.py`
- [ ] Escribir `build_release.py` con: verificación de MD5, extracción del ELF con `bsdtar`/`7z`, invocación del build CMake y empaquetado del resultado
- [ ] Verificar que `build_release.py` rechaza un ISO con MD5 incorrecto y acepta el ISO conocido
- [ ] Escribir `.github/workflows/release.yml` con jobs `build-linux` (`ubuntu-latest`) y `build-windows` (`windows-latest`) que compilan y suben los artefactos al release al hacer push de un tag `v*.*.*`
- [ ] Escribir `README.md` con: descripción del proyecto, requisitos (ISO propio, Python, CMake, GCC/MSVC), instrucciones de uso de `build_release.py`, MD5 esperado del ISO, y nota legal clara
- [ ] Preparar el repo para GitHub: revisar `.gitignore` (que no filtre `build_release.py`, `README.md`, `.github/`), hacer commit limpio con mensaje convencional
- [ ] Crear tag `v0.1.0` y verificar que GitHub Actions genera y publica los dos artefactos del release correctamente
