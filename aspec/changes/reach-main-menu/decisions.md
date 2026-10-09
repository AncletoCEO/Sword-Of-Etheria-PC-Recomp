# Decisions — reach-main-menu

## 2026-10-09 (1) — Arquitectura del runtime: barrido de stubs a mega-funciones

- `tools/PS2Recomp/ps2xRuntime/src/lib/game_overrides.cpp` (~L3594) hace:
  - `for (addr = 0x4eb8d0; addr < 0x6cba48; addr += 4)` → **`replaceFunction(addr, fullGameFunc = 0x4eb8d0)`**
    (excepto `0x51f328`), logueando *"Replaced 395709 separate/truncated stub function slots…"*.
  - análogo con `fullRenderFunc = 0x6cba48` (*"…18884…"*).
- ⇒ El código del juego en **`0x4eb8d0..0x6cba48` es UNA mega-función** (`FUN_004eb8d0`) y
  `0x6cba48..` **otra** (`FUN_006cba48`); todos los slots se re-apuntan a ellas.
- **Consecuencia práctica**: instrumentar un slot dentro de ese rango (p.ej. el wrapper `0x51ee70`/
  `0x51eea0`) **no tiene efecto** — se bypassa. Para instrumentar ahí hay que:
  (a) agregar la dirección a la lista de excepciones del barrido (como `0x51f328`), o
  (b) instrumentar la mega-función en su dispatch por `pc`.
- **Evidencia**: `[game_overrides] Replaced 395709 … fullGameFunc (0x004eb8d0)` en la corrida; el
  `.o` instrumentado contenía `fprintf` pero nunca se logueó; el `ra=0x51ee84` de `[triage-sema]`
  cae dentro de ese rango y es un `pc` **dentro de la mega-función**.

## 2026-10-09 (2) — Descartado el modelo SPU2 como bloqueo (revisión del plan)

- Ver `proposal.md`/`design.md`: el audio corre normal (`[gen-audio]` es un contador de log, no un
  rescate), y el thread principal no está clavado en el audio (1.2% de muestras en el pc top).
- Foco real: **state machine de escena + `sema 8` + RPC sin réplica**.
- `sema 8` medido: 13-17 waits vs 9 signals en las corridas (desbalance sostenido).

## 2026-10-09 (3) — B: backtrace guest en el hook de syscalls (funciona) + `sema 8` = LIBSD
- Se extendió el hook `[triage-sema]` (game_overrides) para loguear `sp` + un mini-backtrace guest
  (`*(sp+0x10/0x20/0x30)`, que son los `$ra` guardados por los wrappers). **Funciona** (el lado runtime
  no es bypasseado).
- Resultado (llamadores reales del wrapper `0x51ee70` para `sema 8`): **`0x51e334`, `0x51dbc8`,
  `0x51e7cc`, `0x51e74c`** — todos en el módulo **`0x51exxx` = LIBSD (librería de sonido del juego)**;
  se ve `jal 0x51ee70` en `0x51e32c`/`0x51dbc0`. Consistente con las 947 menciones de `libsd` en el log.
- **`sema 8` está balanceado al inicio** (`n=23 wait / 24 signal / 25 wait / 26 signal…`): es un
  **handshake por frame de LIBSD** ⇒ **NO es el bloqueo**. Se debilita esta hipótesis.
- Llamadores de `sema 1` (lock): `0x4c2d2c`, `0x4c2d84`, `0x4c2b04` (código del juego).
- ⇒ Estado: el fix del dispatcher SIF quedó confirmado; el bloqueo residual **sigue sin localizar**:
  el juego corre (pc repartido), el handshake de LIBSD cicla, el render es negro a propósito.
  Próximos candidatos: **state machine de escena** (variable de fase) y **RPC sin réplica**.
