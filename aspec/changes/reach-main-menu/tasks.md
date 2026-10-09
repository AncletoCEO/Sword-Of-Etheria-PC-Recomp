# Tasks: reach-main-menu

## Fase 0 — Baseline y trazado (diagnóstico)

- [x] Congelar baseline medible (`SWORD_SIF_SEMA=1 SWORD_FORCE_STATE=0`, 180 s): `vbprof n`,
      `[gen-audio]`, `[TYOSD] rpc=`, `[triage-sema]`, `frame:upload`/`shot-vb nonZeroRgb`.
      → **Resultado**: `vbprof n=10681`, `nonZeroRgb=0`, TYOSD-vec n=2, `[gen-audio]` ~551 (normal),
      sema3=60×/sema8=17w-9s/sema1=9×; pc top del thread 1 = `0x6e4ebc` con **sólo 1.2%** de muestras.
- [x] **Descartar el audio/SPU2 como bloqueo** (el `SPIN-EXIT` es un log, el audio corre normal, el
      thread principal no vive en el audio) → registrar en `proposal.md`/`design.md`.
- [x] Trazar el **waiter exacto de `sema 8`** (`0x51ee84` wait / `0x51eeb4` signal): quién espera,
      con qué `ra`/thread, y quién debería señalizar (cubrir las ~8 esperas sin señal).
      → **Resultado**: el hook del runtime **sí** funciona (el generado está bypasseado por el barrido de
      `0x4eb8d0..0x6cba48`); con backtrace guest, los llamadores son `0x51e334`/`0x51dbc8`/`0x51e7cc`/
      `0x51e74c` = módulo **LIBSD** (`0x51exxx`). `sema 8` está **balanceado al inicio** (handshake por
      frame) ⇒ **no es el bloqueo**. Ver `decisions.md` (1–3).
- [ ] Localizar la **variable/paso del state machine de escena** que no avanza (watchpoint) y su
      condición de transición; comparar con el real (que llega al menú).

## Fase 1 — Desbloquear el avance de fase

- [ ] Cerrar el **`sema 8`** (señal correcta en el punto que falta) y verificar waits ≈ signals.
- [ ] Si el state machine espera **respuesta de RPC** (`0x80000592`/`0x8000059c`/`0x80000006`):
      dar réplica / registrar el servidor correspondiente y verificar que deja de salir `unhandled`.
- [ ] Confirmar que el **paso de escena avanza** (watchpoint cambia de valor; el thread principal
      sale de los pcs de la fase negra).

## Fase 2 — Hito: menú visible

- [ ] Apagar `SWORD_FORCE_STATE` por default (no forzar 2→5; estado natural **2**).
- [ ] Corrida larga con los triages apagados y **frame con `nonZeroRgb>0`** (título/menú).
- [ ] A/B de no-regresión: `missing-target=0`, boot estable, video mode correcto.

## Fase 3 — Limpieza

- [ ] Drenar la cola de streaming y **revertir los triages** activos
      (`triage-vis`, `triage6e4d98`, `libsd→v0=1`) una vez estable.
- [ ] Consolidar la instrumentación en **un `env` por experimento** + helper `fprintf` compartido.
- [ ] Revertir atajos activos y dejar sólo fixes reales; actualizar `decisions.md`.
- [ ] (Posterior / change aparte) prep de GitHub: `.gitignore`, commit limpio, tag `v0.1.0`.

## Contingencia (sólo si el trazado lo re-señala)

- [ ] Modelo SPU2 (IOP): `ENDX`/`STATX`/voces/posición en `iop_memory.cpp`.
- [ ] Streaming `SD.BIN`: layout del comando de 16 B (destino+tamaño) + avance de cola.
