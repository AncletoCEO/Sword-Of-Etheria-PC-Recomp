# Tasks: reach-main-menu

> Estado 2026-10-09. Entrada: **`HANDOFF.md`**. Se podaron las tareas superseded para no inducir a error.

## Hecho

- [x] Baseline medible + descarte de: **audio/SPU2**, **RTC/tiempo**, **replies de RPC kernel**,
      **datos `SD.BIN`**, **flags SIF-init**, **`sema 8`**.
- [x] Auditoría vs `ss01`: **`0xA2A9C0` = pool de paquetes SIF** (no config) ⇒ invalidados los pasos que lo
      hardcodeaban.
- [x] **Fix cluster truncado `0x4d3700–0x4d3770` + `0x4d0cd0`**: CSV corregido + **regenerado** (default ON,
      sin regresión). Ver `HANDOFF.md` §5.
- [x] Experimento **plataforma IOP-BIOS / pre-init SIF** (opt-in OFF): cerró gaps reales, **sin avance**.
- [x] **Trace-forward PCSX2 + PINE**: el real hace un **burst** y setea `gp+0x58` (`0xA280C8`) a ~3,5 s;
      el recomp **lee 30 archivos y duerme**.
- [x] **Acelerador**: `SWORD_TRACE_BRANCH` (control de flujo, con `tid=`) + `SWORD_CHAIN` (probes de retorno).
- [x] **Gate localizado**: wait cruzado (hilo 1 lock / hilo 3 `SleepThread` / hilo 2 sema 3).

## Sesión 2026-10-10 (§8 del HANDOFF)

- [x] **`a0` (sema id) + `tid=` en el trace**: agregado a `SWORD_TRACE_BRANCH` en `ps2_runtime.cpp`
      (`dispatchGuestBranch`). Nombra el semáforo del spin del hilo 1.
- [x] **Spin del hilo 1 nombrado**: `WaitSema` desde `src=0x4C3B98` (lock `FUN_004c3b50`) con **`a0=1`**
      ⇒ el sema id sale de `*(0x8744A0)` = **sema 1**. El release `FUN_004c3bd0` lo señaliza.
      Conteos/90 s: `GetThreadId` ×75 290 (todos `src=0x4C3B60`), `WaitSema(1)` ×37 642.
      El hilo 1 además balancea **sema 8** (`WaitSema(8)` ×4 230 / `SignalSema(8)` ×4 230, wrappers
      `0x51ee70`/`0x51eea0`).
- [x] **Caveat de la herramienta**: `SWORD_TRACE_BRANCH` **no ve los tail-calls directos** (p.ej. el
      release hace `j 0x4D32C0`, que el generado emite como llamada C directa, sin `dispatchGuestBranch`).
      Por eso un `SignalSema` puede aparecer como "0" aun ejecutándose. **No confundir con señal faltante.**

## Sesión 2026-10-10 — "forzar el visual" (triage)

- [x] **Diagnóstico del VRAM de los savestates**: s01 está **pre-menú** (VRAM en blanco); s03–s05 tienen
      contenido parcial. **No hay framebuffer de menú decodificable** (escaneados todos los `fbp`, PSMCT32
      y PSMCT16, con y sin el header de 509 B). ⇒ no hay imagen de menú para inyectar: el menú lo **genera**
      el juego.
- [x] **`SWORD_LOAD_RDRAM` (teleport de RAM)**: cargar los 32 MB de s02 mata el hilo 1 (`pc=0`, pisa
      stacks ~`0x1FED...`). Inyectando **sólo las regiones que difieren** s01→s02 (3,2 MB, 16 rangos) el
      hilo 1 **sobrevive** y el juego **avanza**: `pc 0x4C3BC4 → 0x74A5B8`, `frame:upload` pasa de
      `512x512` a **`640x448/640x511`** (modo PAL). Pero `vramNonZero=0` y `nonZeroRgb=0`: **sigue negro**.
- [x] **Teleport s03/s05** (`.ranges` por estado): s03 → hilo 1 vivo en `0x74A5B8`, `vramNonZero=0`;
      **s05 → `vramNonZero=16384`** (primer VRAM con contenido) y hilo 1 vivo en `0x74A4F0`; pero `fbp=0`
      sigue negro (`nonZeroRgb=0`). **Límite del force**: el teleport reemplaza DATA guest, no el
      **contexto de hilos** del recomp (scheduler C++), así que el hilo 1 no reanuda en el PC del real.
      ⇒ **el force está agotado**: el menú requiere el fix real.
- [x] **Prueba del camino de presentación (`SWORD_TEST_PATTERN=1`)**: se forzó un patrón en
      `GSCpuBackend::Present` (gradiente + "HELLO WORLD") y **se ve en pantalla**:
      `nonZeroRgb=327680/327680`. ⇒ **el render/present funciona**: el negro es porque **el juego no
      dibuja**, no porque el display esté roto. Queda como **harness** (env-gated, default OFF) para
      validar visualmente cualquier avance posterior.

## Sesión 2026-10-11 — escritor de `0xC80000+` (hook por `mprotect`)

- [x] **Hook de escritores por `mprotect`** (`SWORD_WP_WRITER`, runtime `.cpp`, default OFF): protege
      `0xC80000–0xE50000` y captura el PC del escritor vía `SIGSEGV` (sin tocar el header ⇒ sin rebuild de
      los 18 311 `.cpp`). Con re-armado periódico **enumeró 70 sitios de escritura**.
- [x] **Escritores identificados: TODOS son código del juego** — mega-funciones `FUN_004eb8d0` y
      `FUN_006cba48` (p0/p1/p2/p9/**p10** = armado de escena), el **allocador `FUN_004c3000`** (familia
      `malloc`: toma el lock `0x4C3B50`, chequea smallbins) y `FUN_004c1ee0`. **CERO escritores de DMA / CD
      / runtime.** ⇒ **la hipótesis "se llena por DMA / staging" queda REFUTADA**: son stores de puntero
      calculado del juego.
- [x] **Nunca escrito**: `0xCF0000–0xE50000` (≈270 k words) **no lo escribe ninguna ruta** en 200 s (las
      páginas quedaron en `PROT_READ`; el marcador `0xDEADBEEF` del seed quedó intacto). Coincide con
      `burst_maxdst=0xCE9B60`.
- [x] **Contenido + corrimiento (A/B `SWORD_RDRAM_DUMP_LATE` vs `videoformat_menu.p2s`)**: el recomp **sí**
      produce `0xC80000–0xCE9B60` (67 945 words ≠ 0; el real 73 562 en ese rango). El contenido del recomp
      **alinea con el del real en un corrimiento exacto `+0x150`** (spike real: 6 686 words coinciden con
      ambos ≠ 0, vs ≈2 100 en ±0x10) — el mismo offset de heap ya documentado. Por encima de `0xCE9B60` el
      recomp no escribe y el real tiene ~270 k words más.
- [x] **Burst trazado con `src`** (probe `[burst-loop]` en el stub de `memcpy` `0x4C38D8`): el armado es una
      secuencia de sub-loops, cada uno copiando de una **tabla fuente fija dentro de la misma región**
      (`src=0xc8db00/0xc80be0/0xc911c0/0xce3a50…`) a un destino (`dst=0xc8f420…`). `burst_maxdst` **sube y
      se estanca** en `0xCE9B60` durante ~161 s ⇒ **no es lentitud: el loop externo termina**.
- [x] **Las fuentes divergen**: comparadas recomp vs real, las tablas fuente tienen **mismo conteo de
      no-cero pero 0 coincidencias** (firma de *punteros*); y la **última fuente `0xce3a50` está casi vacía
      en el recomp (25 nz vs 250 del real)** ⇒ el último batch copia de una tabla sin poblar.
- [x] **Fase del recomp = `draw` (corrige el marco)**: el dump del recomp coincide con
      `draw_vif1kick_006E4468` en **98.33 %** de TODO el RAM (vs `videoformat_menu` 94.26 %; **RAM baja 100 %**);
      en la región sola, 83.8 % vs draw / 25.8 % vs menu. ⇒ **el recomp es fiel en la fase `draw`**; el "gap
      de la región" era **diferencia de fase**, no carga faltante.
- [x] **El recomp está CLAVADO (no lento) en `draw`**: 600 s con `gp740=0x0`/`gp744=0x0`/`burst_maxdst=0xCE9B60`
      constantes; **nunca ejecuta el código de la fase menú `0x75Bxxx`** (traza `SWORD_TRACE_BRANCH`); corre el
      loop de escena (thunks `0x6d5f90`→`0x5ea770`, `0x6d5fb8`→`0x5ea650`). El kick de draw sale **vacío**
      (`VIF1 qwc=0x0`) y quedan RPC `unhandled` (`0x80000592`/`0x80000006`/`0x8000059c`).
- [x] **Limpieza**: probe temporal `[build]` quitado de `work/generated/FUN_006cba48_0x6cba48_p10.cpp`.

## Sesión 2026-10-11 (Parte 2) — Destrabe de Streaming y Transición de Escena

- [x] **Identificación del gate en loader thread (`0x4cf860` / `sceCdDiskReady`)**:
      El hilo 3 (cargador CD de streaming `0x628640`) llamaba en loop a `0x4cf860` (`sceCdDiskReady`).
      El cuerpo real hacía `PollSema` de la libcdvd y RPC a `cdvdfsv` (sid `0x8000059c`). Al estar `sceCdRead`
      en HLE, ese semáforo nunca se liberaba y `sceCdDiskReady` retornaba `6` (`SCECdNotReady`) infinitamente,
      dejando al hilo 3 parqueado y `gp+0x58=1`.
- [x] **Stub de `sceCdDiskReady` aplicado**: En `game_overrides.cpp` se implementó el reemplazo llamando a
      `ps2_stubs::sceCdDiskReady` (retorna `SCECdComplete = 2`).
- [x] **Transición verificada y desbloqueo de escena**:
      Al retornar éxito, el hilo 3 completó el streaming, limpió `gp+0x58=0`, `gp+0x740` avanzó a `0x6D6FE8`,
      `burst_maxdst` subió de `0xCE9B60` a **`0xDAFE80`** (>116k words escritas) y el hilo 1 avanzó al loop
      de escena `0x6D6FE8`.
- [x] **Localización del indirect call nulo (`pc=0x0` en `0x6D2688`)**:
      El loop de escena invoca `0x6D23F0`, llamada desde `0x742270` (`FUN_00742270`).
      En `ghidra_functions.csv`, `FUN_00742270` estaba truncada a 4 bytes (`0x742270..0x742274`), emitiendo
      solamente el `addiu $sp, $sp, -0xe0` y retornando sin ejecutar su cuerpo real ni poblar los campos del
      objeto de escena (`0xA887B8 + 0x10C` que luego se dispara en `0x6D2688`).
- [x] **Corrección de extents de funciones 0x742270 y 0x742808**:
      `FUN_00742270` corregido de 4 bytes a 1432 bytes (`0x742270..0x742808`).
      `FUN_00742808` corregido de 36 bytes a 1880 bytes (`0x742808..0x742F60`).
- [ ] **Regeneración e integración del cluster 0x742xxx**:
      Ejecutar `ps2_recomp`, copiar los archivos corregidos a `work/generated/` y compilar.

## Cerrado / inválido (no retomar)

- Fase 4 pasos "hardcodear `0xA2A9C0` / repoblar RPC" → **inválidos** (era síntoma).
- `0x4d3730` como gate → descartado (su cuerpo real rompe el main thread).
- Audio/SPU2, RTC, `SD.BIN`, flags SIF, replies de RPC → descartados con evidencia.
- **"El bloqueo es el GS / el recomp emite prims negros por un bug"** → **FALSO** (2026-10-10): el pipeline
  gráfico (display, GS, parseo, VIF1-UNPACK, VU1, XGKICK, geometría y color) quedó verificado **fiel**,
  incluso contra la consola. El color negro `[0,0,0,255]` **es data del juego** (quads de fade/clear).
- **"Falta el color en el VU1/path de RGBAQ"** → **FALSO**: el micro guarda `vf22 = vertex_color × alpha`
  y el `vertex_color` ya viene `[0,0,0,255]` en la data del juego.
- **"`0xC80000+` se llena por un DMA / una carga de asset que falta"** → **FALSO** (2026-10-11, hook
  `mprotect`): los únicos escritores son el **propio juego** (`FUN_006cba48` p10, `FUN_004eb8d0`) y el
  **allocador `FUN_004c3000`**. No hay path de DMA/CD/runtime que escriba esa región.
- Rebuild completo con `ps2TraceGuestWrite` para "encontrar al escritor" → **innecesario** (el escritor ya
  está enumerado) y caro (18 311 `.cpp`).
