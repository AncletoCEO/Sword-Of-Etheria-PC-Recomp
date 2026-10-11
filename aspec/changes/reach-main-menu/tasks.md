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

## Pendiente (próxima sesión)

- [ ] **Escritor de `0xC80000+` (lead principal)**: el A/B de RDRAM (recomp vs `.p2s`) da **~93.6 % de páginas
      idénticas**; la divergencia dominante es **`0xC80000–0xE50000` (~2 MB) = CERO en el recomp** y con data
      tipo **textura/staging** en el real. No viene de un `sceCdRead` (los 30 reads aterrizan en
      `0xA4xxxx–0xA8xxxx` y **sí traen data real**) ni de stores literales en `work/generated` ⇒ se llena por
      **puntero calculado o DMA**. **Próximo**: (a) hook en el path de **DMA** del runtime (1 archivo);
      (b) dump a **2 ticks** (early vs late) y ver qué páginas de `0xC80000+` cambian alguna vez;
      (c) rebuild completo activando `ps2TraceGuestWrite` (header de 18 311 .cpp → caro).
- [ ] **Limpieza**: quitar el probe temporal `[build]` (no env-gated) en
      `work/generated/FUN_006cba48_0x6cba48_p10.cpp`.

## Cerrado / inválido (no retomar)

- Fase 4 pasos "hardcodear `0xA2A9C0` / repoblar RPC" → **inválidos** (era síntoma).
- `0x4d3730` como gate → descartado (su cuerpo real rompe el main thread).
- Audio/SPU2, RTC, `SD.BIN`, flags SIF, replies de RPC → descartados con evidencia.
- **"El bloqueo es el GS / el recomp emite prims negros por un bug"** → **FALSO** (2026-10-10): el pipeline
  gráfico (display, GS, parseo, VIF1-UNPACK, VU1, XGKICK, geometría y color) quedó verificado **fiel**,
  incluso contra la consola. El color negro `[0,0,0,255]` **es data del juego** (quads de fade/clear).
- **"Falta el color en el VU1/path de RGBAQ"** → **FALSO**: el micro guarda `vf22 = vertex_color × alpha`
  y el `vertex_color` ya viene `[0,0,0,255]` en la data del juego.
