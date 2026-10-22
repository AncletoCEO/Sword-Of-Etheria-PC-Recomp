# Sword of Etheria — recompilación nativa para PC

Recompilación estática del ejecutable PS2 `SLES_537.68` (Sword of Etheria,
versión PAL Europa) a binario nativo de PC con
[PS2Recomp](https://github.com/ran-j/PS2Recomp).

## Estado (0.0.1 · 2026-10-21)

Experimental: el juego arranca, carga sus `.BIN` desde el ISO e inicializa
GS/VSync. **El selector de video PAL/NTSC se ve y se opera** (teclado/pad), y la
**pantalla de idioma** se ve y responde. Al confirmar el idioma el **fade sale
naturalmente** (fix del submitter `0x6e4ed8`), pero la transición a **Task 1/FMV**
se bloquea con un `JALR` a `0x1a1b00`; todavía no llega al FMV, título, menú ni
gameplay. Audio y guardado sin verificar. Release de prueba:
`dist/public/v0.0.1/` (tools + launcher; el binario se compila localmente).
Detalle y mediciones: `aspec/changes/reach-playable-game/decisions.md` §18.

## Requisitos

- Tu ISO original: `Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso`
- MD5 esperado: `b9c5115b77b7f05fbf14a67df8d3f99d`
- Linux: Git, CMake 3.20+, GCC C++20, Python 3, `bsdtar`, SDL/mesa
  (`base-devel cmake ninja git python pkgconf mesa libx11 ...`)
- Windows: Git, CMake 3.20+, MSVC C++20, Python 3, 7-Zip

## Uso

### Release 0.0.1 (Linux x86_64, tools + launcher)

```bash
tar -xzf sword-of-etheria-recomp-0.0.1-tools-linux-x86_64.tar.gz
cd v0.0.1
./run.sh "/ruta/Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso"
```

El paquete **no incluye datos del juego**: trae el recompilador, la fuente del
runtime y el launcher. El launcher verifica el MD5, extrae `SLES_537.68` e
`IOP/`, recompila/compila **en tu máquina** (la primera vez puede tardar horas;
después cachea) y ejecuta. El binario y el C++ generado quedan solo en tu disco.

En desarrollo, para reutilizar el árbol actual:
`python game/launcher.py --work work --no-pin --no-build`.

### Build desde fuente

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

## Herramientas

Cómo se usó cada una en este proceso:

- Flujo spec-driven con [`@ancleto/spec`](https://www.npmjs.com/package/@ancleto/spec)
  ([repo](https://github.com/damianarganaras/spec)): proposal, design y tasks en
  `aspec/changes/recompile-sword-of-etheria/`; skills `ancleto-apply` (implementar),
  `ancleto-verify` (verificar) y `cleto-*` en el agente; memoria del proyecto en
  `.ancleto/memory.db`.
- Modelos de IA: la **generación inicial** de los `.cpp` recompilados (arranque del
  proyecto) se hizo con **Big Pickle** y **Muse Spark**, ofrecidos por **OpenCode Zen**
  (agente OpenCode con las skills de arriba, commits atomizados + push por cada cambio).
  De ahí en adelante el trabajo se hace con **Command Code** (agente) más **Gemini** como
  consulta externa, a la que se le pasa el contexto del proyecto en el primer mensaje.
- Recompilador: [PS2Recomp](https://github.com/ran-j/PS2Recomp) (proyecto original, solo
  atribución). **El runtime que se usa y se parchea es el fork
  [AncletoCEO/Ps2Recomp-of-etheria](https://github.com/AncletoCEO/Ps2Recomp-of-etheria)**
  (GPLv3): `build_release.py` y el CI clonan ese fork — el CI contra un **commit pinneado**.
  `ps2xAnalyzer` como vía alternativa de análisis; `ps2xRecomp` tradujo el ELF a C++
  (17771 archivos en `work/generated/`); `ps2xRuntime` es contra lo que enlaza
  el juego e incluye `game_overrides.cpp` (162 syscall stubs + hooks de
  CD/Pad/GS); `ps2xIOP` ejecuta los IRX originales con fallbacks HLE.
- Análisis: [Ghidra](https://github.com/NationalSecurityAgency/ghidra) (12.1.4,
  requiere JDK) con `ExportPS2Functions.java` de PS2Recomp: exportó
  `ghidra_functions.csv` (7672 funciones) y el `config.toml` base; wrapper
  headless en `aspec/.../ghidra/`. MCP experimental
  [ghidra-mcp](https://github.com/bethington/ghidra-mcp) (clon local, no versionado).
- Toolchain Linux: Git (SSH), CMake 3.20+, Ninja → Unix Makefiles (Ninja se traba
  con 18k archivos), GCC C++20, Python 3 (`build_release.py`, `split_monsters.py`
  para partir monstruos de 75–235 MB), `bsdtar` (extracción ISO → `SLES_537.68`).
  Windows: MSVC C++20 y 7-Zip para lo mismo.
- Librerías del runtime (las baja CMake): [raylib](https://github.com/raysan5/raylib)
  5.5 (ventana 640x448 y subida del framebuffer), [Dear ImGui](https://github.com/ocornut/imgui)
  + rlImGui (UI de debug), FFmpeg (video), SDL/mesa (GL en Linux).
- Disco: tu ISO PAL Europa (MD5 arriba); el repo nunca versiona ISO, ELF, BINs
  ni `work/`/`tools/`.

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
