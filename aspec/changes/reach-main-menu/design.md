# Design: reach-main-menu

> **ENTRADA VIGENTE: `HANDOFF.md`.** El enfoque de abajo (scene machine / `sema 8` / RPC sin réplica /
> watchpoint) quedó **superseded**. El enfoque vigente es **trace-forward con PCSX2+PINE** + un
> **acelerador de control de flujo** (`SWORD_TRACE_BRANCH`) para localizar el primer desvío; el gate actual
> es un **wait cruzado** de hilos en la fase de carga (`HANDOFF.md` §7–§8).

## Approach

Diagnóstico dirigido por **traza de runtime instrumentada** + **A/B con el baseline** congelado
(180 s, `SWORD_SIF_SEMA=1 SWORD_FORCE_STATE=0`: `vbprof n=10681`, `nonZeroRgb=0`, TYOSD n=2,
sema3=60×/sema8=17w-9s/sema1=9×, pc top del thread 1 solo 1.2%).

1. **Trazar `sema 8`**: instrumentar los sitios `0x51ee84` (wait) y `0x51eeb4` (signal) con el `ra`
   y el thread; encontrar las ~8 esperas sin cubrir y quién debería señalizarlas.
2. **Instrumentar el state machine de escena**: identificar la variable/paso de fase del juego y su
   condición de avance; comparar contra el real (que sí llega al menú). Preferir watchpoints sobre
   la variable de escena antes que recompilar.
3. **RPC del juego**: confirmar si el state machine espera la respuesta de `0x80000592`/`0x8000059c`/
   `0x80000006`; si sí, dar réplica/registrar el servidor (IOP HLE o módulo faltante).
4. **Cerrar el bucle**: con (1)-(3) resueltos, verificar el avance de fase sin parches y exigir el
   hito (`nonZeroRgb>0`).

## Architecture

- **State machine de escena (generado, no se recompila)**: identificación por watchpoint/lectura de
  la variable de fase; el runner ya tiene el hook de watchpoints (`[wp-XXXX]`).
- **`sema 8`**: creado en `0x51ef10` (`CreateSema`), esperado en `0x51ee84`, señalado en `0x51eeb4`.
  Los wrappers del SDK ya están identificados: `GetThreadId`47, `CreateSema`64, `DeleteSema`65,
  **`SignalSema`66**, `iSignalSema`-67, **`WaitSema`68**. El trace de semáforos ya existe
  (`[triage-sema] op/sema/ra`).
- **RPC del juego**: camino EE→IOP en `RPC.cpp` (`SifBindRpc`/`SifCallRpc`) + el transporte IOP
  (`ps2xIOP`). Los sids del juego (`0x80000592`/`0x8000059c`/`0x80000006`) hoy dan `rpc=0`
  (`unhandled`); la consola los registra desde módulos sysmem/`IOPRP300`.
- **Presentación** (ya OK, sólo para validar): `dispfb1=0x1000` → `fbp=0, fbw=8, psm=PSMCT32`.
- **Audio/SPU2** (fuera de foco, hipótesis descartada): `iop_memory.cpp` con boot mínimo
  (`ENDX=0x00FFFFFF`, `STATX=0`); el driver del juego (`FUN_006cba48`, `0x6e4068`) corre normal.

## Validation

- **Métrica primaria**: frame presentado con `nonZeroRgb > 0` (`shot-vb` / `frame:upload`) =
  título o menú visible, **con los triages apagados** (`SWORD_FORCE_STATE=0`).
- **Métricas de soporte**:
  - `[triage-sema]`: `sema 8` balanceado (waits ≈ signals); sin esperas colgadas.
  - La variable de fase/escena avanza (watchpoint cambia de valor) y el thread principal sale del
    conjunto de pcs de la fase negra.
  - `[IOP/RPC trace]`: las RPC del juego (`0x80000592`/`0x8000059c`/`0x80000006`) dejan de aparecer
    como `unhandled`.
  - `[TYOSD-vec]` avanza más allá de `n=2`.
- **A/B de no-regresión**: contra el baseline (`missing-target=0`, 89 archivos del fix del
  dispatcher, `sword_etheria` compilando, boot estable).
- **Reversión**: apagar la instrumentación nueva y los triages al cerrar; dejar sólo fixes reales.

## Decisión de diseño

Se **descarta el modelo SPU2** como camino principal (ver `proposal.md`): el audio no bloquea
(evidencia del baseline). El foco pasa al **state machine de escena + `sema 8` + RPC sin réplica**.
El SPU2 queda sólo como contingencia si el trazado de fase lo vuelve a señalar.

## Producto final — arquitectura (plan 2026-10-15, no implementado)

**Componentes (separación de responsabilidades):**

- **`sword_etheria` (el juego)**: ventana raylib + runtime + C++ recompilado. Lee un **config**
  (ruta del ISO + opciones) y arranca. No pide input de usuario en consola.
- **Launcher (front-end propio, liviano)**: una sola pantalla.
  - `ISO`: selector de archivo + validación **MD5** (reutiliza `check_iso` de `build_release.py`) +
    persistencia de la ruta (p. ej. `%APPDATA%/sword-etheria/config.toml` en Windows,
    `~/.config/sword-etheria/config.toml` en Linux).
  - `Opciones`: resolución, modo ventana/fullscreen, escalado (entero/lineal), vsync, límite de FPS,
    dispositivo de audio/volumen, pad y remapeo, idioma si aplica.
  - `Acciones`: **Generar** (si falta el build: invoca `build_release.py --iso <ruta>` con progreso y
    log visible) y **Jugar** (lanza `sword_etheria --config <archivo>`).
  - Recomendación: launcher **aparte** (no un menú in-game) — mantiene el core limpio y permite que
    el juego siga siendo scriptable por CI.
- **Config único (`.toml`)**: lo comparten launcher y juego. El juego mapea opciones a lo que ya
  existe (env `SWORD_*` + `config.toml`), sin inventar un segundo mecanismo.

**Reproducibilidad del CSV (punto 7 del proposal):**

- `game/generate_functions_csv.py`: reproduce `ghidra_functions.csv` desde el ELF + reglas explícitas
  (baseline, `MANDATORY_OVERRIDES`, splits de fusionadas, clamps de `entry_` invasoras, filtro de
  **referencias reales**, y las altas puntuales tipo `FUN_006f2630`). El CSV commiteado pasa a ser la
  **salida** del script ⇒ cada cambio es un diff revisable y no depende de tener Ghidra.
- Regla operativa vigente: **ningún build sin `validate_csv.py` en verde**.

**CI (`release.yml`) — estado y plan:**

- Hecho: clonar el **fork pinneado** (`AncletoCEO/Ps2Recomp-of-etheria`, `main`), sin `apply_patches`;
  deps de FFmpeg en Linux; Ninja en Windows; `-msse4.1` + `g_tyosdTransferActive` en el fork.
- Plan: agregar el **paso del gate** (`validate_csv.py`) y, en el job de release por tag, empaquetar
  **launcher + tools + `build_release.py`** para Windows y Linux.

**Modelo legal (sin contenido con copyright):**

- Nunca al repo: `*.iso`, `*.elf`, `*.bin`, `*.exe`, `work/`, `*.recomp.cpp`, capturas.
- Sí al repo: nuestro código (recompilador, runtime, `build_release.py`, CI), el CSV
  (nombres/direcciones/tamaños = metadatos, sin bytes de código ni assets) y los artifacts del change.
- El runtime (fork) es **GPLv3**; el binario distribuido que lo enlaza queda cubierto por esa licencia,
  con su fuente disponible (el fork).
