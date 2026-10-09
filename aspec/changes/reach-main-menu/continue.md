# Continuar: reach-main-menu

Punto de retomada al cerrar la sesión del 2026-10-09.

## Dónde estamos

- **Change previo archivado**: `recompile-sword-of-etheria` → `aspec/changes/archive/2026-10-09-recompile-sword-of-etheria/`.
  Ahí está el fix grande: **causa raíz del gap del dispatcher SIF** = el CSV de Ghidra tenía
  `FUN_004d3fa0,End=0x4D3FE8` **truncado**; se corrigió a `End=0x4D4078` + `entry_points=["0x4d3fe8"]`,
  se regeneró (`work/generated.new`) y se recompiló (copia quirúrgica de 89 archivos, sin OOM).
  **Resultado**: `missing-target=0`, el dispatcher corre, el thread 2 se desbloqueó.
- **Change actual**: `reach-main-menu` — objetivo: llegar al menú. Foco revisado tras el baseline:
  **state machine de escena + RPC sin réplica** (el audio/SPU2 quedó **descartado** como bloqueo).

## Estado del build / entorno

- Binario: `work/build-game/out-linux/sword_etheria` (Linux, Ninja). Build: `cmake --build work/build-game/out-linux --target sword_etheria -j4`
  (usar `-j4`; más paralelismo mata `cc1plus` por OOM). Regeneración del recompilado: ver `recompile-plan.md` del change archivado.
- Corrida de referencia (la que hay que comparar siempre):
  ```
  SWORD_SIF_SEMA=1 SWORD_FORCE_STATE=0 timeout 180 ./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68 > /tmp/run.log 2>&1
  ```
  - `SWORD_SIF_SEMA=1` → emula la interrupción SIF posteando **sema 3** al completar un RPC (necesario para que arranque el thread 2 / dispatcher). Cambio en `RPC.cpp`.
  - `SWORD_FORCE_STATE=0` → **NO** forzar el estado del driver de sonido `2→5` (el default lo fuerza y **daña**: `5`=idle; la rama activa es `2`).
- Métricas del baseline (180 s): `vbprof n=10681` (~60 fps), `nonZeroRgb=0`, TYOSD-vec n=2,
  `[gen-audio]` ~551 (normal), `sema3=60×`, `sema8` ~balanceado al inicio, `sema1=9×`;
  pc top del thread 1 = `0x6e4ebc` con **sólo 1.2%** de muestras (el juego corre repartido, no clavado).

## Instrumentación activa (y una trampa importante)

- **Trampa (A)**: el runtime **barre `0x4eb8d0..0x6cba48` y reemplaza cada slot por `fullGameFunc` (0x4eb8d0)**
  (y `0x6cba48..` por `fullRenderFunc`) — en `game_overrides.cpp` (~L3594). ⇒ **Instrumentar código generado
  dentro de esos rangos NO tiene efecto** (ej.: los wrappers `0x51ee70`/`0x51eea0` ya están editados en
  `work/generated/` con un `fprintf("[wp-sema]…")` que **nunca dispara** porque se bypassa). Para instrumentar
  ahí: agregar la dirección a la excepción del barrido (como `0x51f328`), o instrumentar la mega-función.
- **Camino que SÍ funciona (B)**: el **hook del runtime** en `game_overrides.cpp::swordOfEtheriaSyscallStub`
  (`[triage-sema]`) — se le agregó `sp` + mini-backtrace guest (`*(sp+0x10/0x20/0x30)`).
- Artefactos de traza existentes: `[triage-vbprof]`, `[triage-sema]`, `[gen-audio]`/`[gen-state]`,
  `[TYOSD-*]`, `[IOP/RPC trace:unhandled]`, `frame:upload`, `[guest-branch:missing-target]`, watchpoints `[wp-…]`.

## Hallazgos de la sesión (detalle en `decisions.md` 1–3)

1. El audio/SPU2 **no** bloquea: `[gen-audio] 6e4dd8 SPIN-EXIT` es un contador de log (la sección crítica
   `di`/`sync.p`/`mfc0 Status` sale naturalmente), y el thread principal no vive en el audio.
2. **Arquitectura**: el código del juego en `0x4eb8d0..0x6cba48` es **una mega-función** (`FUN_004eb8d0`),
   y `0x6cba48..` otra (`FUN_006cba48`).
3. Wrappers SDK identificados: `0x4d3190`=GetThreadId(47), `0x4d32a0`=CreateSema(64), `0x4d32b0`=DeleteSema(65),
   `0x4d32c0`=**SignalSema(66)**, `0x4d32d0`=iSignalSema(-67), `0x4d32e0`=**WaitSema(68)**; los stubs SDK se
   interceptan por PC (tabla `kSwordOfEtheriaSyscallStubs`, 162 entradas).
4. `sema 1` = **lock re-entrante** del juego (`0x4c3b50`/`0x4c3bd0`), funciona por contador (no es deadlock).
5. `sema 8` = **handshake por frame de LIBSD** (`0x51exxx`; llamadores `0x51e334`/`0x51dbc8`/…);
   **balanceado** al inicio ⇒ **no es el bloqueo**.
6. Presentación OK: `dispfb1=0x1000` → `fbp=0, fbw=8, psm=PSMCT32` = donde dibuja el juego.

## Próximos pasos (en orden sugerido)

1. **State machine de escena** (candidato #1): instrumentar la **variable/paso de fase** del juego vía el
   **hook del runtime** (único camino no bypasseado) o watchpoints; comparar contra el real (que sí llega al
   menú). Buscar la condición que frena la transición desde la fase negra.
2. **RPC sin réplica** (candidato #2): `sid=0x80000592`/`0x8000059c`/`0x80000006` dan `rpc=0`
   (`unhandled`). Ver si el state machine espera su respuesta; si sí, dar réplica o registrar el servidor
   (posible módulo sysmem/`IOPRP300` que el recomp no carga). Ojo: `SWORD_RPC_FILL` ya se probó sin efecto
   en su momento.
3. **Hito**: frame con `nonZeroRgb>0` con los triages apagados ⇒ drenar cola y **revertir triages**
   (`triage-vis`, `triage6e4d98`, `libsd→v0=1`) y el hack `SWORD_FORCE_STATE`.
4. Limpieza: consolidar instrumentación en un `env` por experimento; revertir los `[wp-sema]` generados
   (bypasseados) y dejar sólo fixes reales.

## Pendiente de housekeeping

- **Memoria del repo**: el MCP (`recordDecision`/`recordRule`) **no estaba disponible** en esta sesión;
  las lecciones quedaron en los `decisions.md` (este change + el archivado).
- `git status`: revisar qué quedó modificado (artifacts versionados del change + el archivado; el fix del
  CSV; `config-linux-sif-fix.toml`; las ediciones de runtime en `tools/PS2Recomp` — clon ignorado por git).
