# HANDOFF — reach-main-menu (estado definitivo)

**Fecha**: 2026-10-09. **Este es el documento de entrada.** Reemplaza a `reanalysis.md` (obsoleto) y
consolida `decisions.md`. Si algo acá contradice a otro artifact, **vale este**.

> **ACTUALIZACIÓN 2026-10-10** (ver `continue.md` §"Actualización 2026-10-10" y `decisions.md`):
> el **pipeline gráfico quedó verificado fiel** (incluso contra la consola): el negro es **data del juego**
> (quads `[0,0,0,255]`). El A/B de RDRAM (recomp vs `.p2s`) da **~93.6 % de páginas idénticas**; la brecha
> dominante es **`0xC80000–0xE50000` (~2 MB) EN CERO en el recomp** (staging de textura/escena que el real
> llena). El I/O de CD funciona (30 reads con data real). **Próximo**: enganchar el path de **DMA** del
> runtime para ver quién escribe `0xC80000+`.

---

## 0. Resumen en una frase

El recomp **arranca, corre a ~60 fps y presenta frames**, pero queda **parkeado en la fase de carga**
(`gif=2`, `nonZeroRgb=0`). El **hilo loader** lee 30 archivos de CD y luego **duerme**; el **hilo
principal** hace un **busy-spin del lock**; el **dispatcher SIF** espera **sema 3**. Nadie dispara el
siguiente paso. **No es render, no es OS, no es decomp.**

---

## 1. Build y corrida (entorno)

- Binario: `work/build-game/out-linux/sword_etheria` (Linux, Ninja).
  Build: `cmake --build work/build-game/out-linux --target sword_etheria -j4`
  (**`-j4`, no más → OOM**; un no-op tarda ~5 min).
- Corrida baseline de referencia:
  ```
  SWORD_SIF_SEMA=1 timeout 180 ./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68
  ```
  `SWORD_SIF_SEMA=1` emula la interrupción SIF (sema 3) tras un RPC — **necesario** para que arranque el
  hilo 2. `SWORD_FORCE_STATE` ya es opt-in (default OFF).
- Baseline medible: `vbprof n≈10681/180 s` (~60 fps), `gif=2`, `nonZeroRgb=0`, `vramNonZero` oscila
  0/306048/524288, TYOSD-vec n=2.
- Hilos del recomp: **1** principal, **2** dispatcher SIF (`0x4d3fa0`), **3** loader CD (`0x628640`).
- ⚠️ **No editar headers** (`ps2_runtime.h`/`ps2_runtime_macros.h`): obliga a recompilar los **18 000**
  `.cpp` generados. Toda instrumentación va en `.cpp` (runtime o `game_overrides.cpp`).

---

## 2. Herramientas (todas opt-in; la baseline default queda intacta)

| Env / script | Qué da |
|---|---|
| `SWORD_TRACE_BRANCH="<lo>-<hi>"` (hex) | **Trace de control de flujo del recomp** con `tid=`, a `/tmp/sword_branch.log`. **Única vía de ver DENTRO de la mega-función** `0x4eb8d0..0x6cba48`. |
| `SWORD_CHAIN=1` | Probes del retorno de `0x4d19c8`, `0x4d0cd0`, `0x4d3730`, `0x4cee38`, `0x4cfa80`, `0x4cf860`. |
| `SWORD_RAM_DUMP=1` | Dumps crudos de RDRAM (32 MB ×8) a `/tmp/sword_ram_N.bin`. |
| `SWORD_SIF_SEMA=1` | Postea sema 3 tras cada RPC (necesario para el hilo 2). |
| `SWORD_PC_HIST`, `SWORD_FORCE_LOADER`, `SWORD_FIX_4D3740`, `SWORD_IOP_BIOS_RPC`, `SWORD_IOP_SIF_INIT` | Ver §3/§7. |
| PINE (`/tmp/pine*.py`) | Lee RAM / carga y guarda savestates del **PCSX2** (referencia real). Ver §4. |

Instrumentación ya presente en logs: `[triage-sema]` (**rate-limitado**), `[triage-vbprof]`,
`[gen-audio]`, `[gen-state]`, `[TYOSD-*]`, `[rpc-unhandled]`, `frame:upload`, `[cdread-data]`,
`[branch]` (trace).

---

## 3. FIXES reales aplicados (default ON, sin regresión)

- **Cluster truncado `0x4d3700–0x4d3770` (+ `0x4d0cd0`) corregido en el CSV de Ghidra y REGENERADO**:
  `FUN_004d0cd0` ahora devuelve `0x00873C90` (antes `0x00870000` por truncamiento); `FUN_004d3730` tiene el
  cuerpo completo. Es la **misma clase** que el fix del dispatcher SIF `0x4d3fe8`. Procedimiento en §5.
- **`SWORD_IOP_BIOS_RPC` / `SWORD_IOP_SIF_INIT`** (opt-in **OFF**): servidores IOP-BIOS (`sifcmd`/`cdvdfsv`)
  + pre-init de `sifman`. Cerraron dos gaps **reales** (`rpc-unhandled` 60→0; `yet sif hasn't been init`
  1→0) pero **no avanzaron la escena**.
- Overrides manuales del cluster retirados (el generado ya es correcto).

---

## 4. Referencia real (PCSX2) y método de comparación

- Savestates: `~/.config/PCSX2/sstates/SLES-53768*.01..05.p2s` — ZIP con compresión **zstd**
  (usar **`bsdtar`**, `unzip` no puede). Contienen `eeMemory.bin` (32 MB). Extraídos a `/tmp/pcsx2_ss/s0N/`.
- **`ss01` ≈ estado del recomp** (RAM baja idéntica byte a byte; 0,85 % de palabras distintas).
- **PINE** en Linux = **socket UNIX** en `$XDG_RUNTIME_DIR/pcsx2.sock` (`EnablePINE=true`). Framing:
  `u32 len` + `[opcode][args]`; opcodes `0x02` Read32, `0x09` SaveState, `0x0A` LoadState, `0x0F` Status.
  Snapshot de 32 MB en ~2,3 s. El **pc del EE** se extrae de `PCSX2 Internal Structures.dat` (buscar
  `gp=0xa28070`; pc = word en `gp+0x30`).
- **Trace-forward** (`LoadState(1)` + snapshots): desde `ss01`, el real hace un **burst** (≈450 k palabras
  a `0xC80000–0xDB0000`), setea `gp+0x50/0x54` a ~3,3 s y **`gp+0x58` (`0xA280C8`) a ~3,5 s**, y luego se
  asienta. El recomp **lee 30 archivos y duerme** (no hace el burst).
- El pc del real en `ss01` es `0x4d3764`; el del recomp está en el worker de audio (`0x6e4ebc`) — **el mismo
  lugar**, así que el hilo principal no es la diferencia.

---

## 5. Recompilación (procedimiento del fix del CSV)

1. Editar `aspec/changes/archive/2026-10-09-recompile-sword-of-etheria/ghidra_functions.csv`
   (`End`/`Size` del cluster).
2. `tools/PS2Recomp/out-linux/ps2xRecomp/ps2_recomp work/config-cluster-fix.toml` → `work/generated.new2`
   (~13 min).
3. Copiar **solo** los `.cpp` del cluster a `work/generated/` (no están instrumentados) + rebuild.
   (El `game/split_monsters.py` no aplica al cluster.)

---

## 6. DESCARTADO — **NO volver a recorrer esto**

| Hipótesis | Evidencia del descarte |
|---|---|
| Audio/SPU2 como bloqueo | `SPIN-EXIT` es un log; audio normal; el hilo principal no vive en el audio. |
| RTC/tiempo (`0x875418`) | `sceCdReadClock` = hora del host; VBlank 60 Hz. |
| Replies de RPC del kernel (`0x80000592`/`0x8000059c`/`0x80000006`) | HLE con el reply **real** → sin efecto. |
| Datos de `SD.BIN` en el streaming | Servir el archivo real → sin efecto. |
| Flags de SIF-init (`0x872098=0x22`, `0x873D78=1`, …) | Sembrarlos → sin efecto. |
| **`0xA2A9C0` = tabla RPC a hardcodear** | **FALSO**: es el **pool de paquetes SIF del juego** (`_sif_alloc_packet`, entradas de 64 B). Los valores de `ss01` son **síntoma**. |
| `sema 8` desbalanceado | Está balanceado (handshake LIBSD por frame). |
| `0x4d3730` (handshake SIF) como gate | Restaurar su cuerpo real **rompe el main thread** (`pc=0x0`); el stub es workaround necesario. |
| El SO anfitrión (Linux vs Windows) | El gate es lógica guest; PCSX2 renderiza en Linux. ~0 %. |
| Decomp a mano como alternativa | El recomp **ya es** una decomp; el blocker es la capa de **plataforma**, que una decomp también necesita. |
| Watchpoint de stores en el generado | Usa `FAST_WRITE32` (bypassea `Store32`); hookear la macro = 18 k rebuilds. |

---

## 7. GATE ACTUAL (dónde está exactamente)

Desde `ss01`, el recomp queda en un **wait cruzado** (medido con `SWORD_TRACE_BRANCH=4d3000-4d3400` + `tid=`):

- **Hilo 1 (principal)**: **busy-spin del lock re-entrante** (`0x4C3B50`, sema 1) —
  `GetThreadId` (`0x4d3190`) ×**75 290**, `WaitSema` (`0x4d32e0`) ×**38 931** en 60 s.
  pc en `0x4C3BC4` (retorno del lock) / `0x6E4EBC` (audio).
- **Hilo 2 (dispatcher SIF)**: espera **sema 3** (`0x4D3FE8`).
- **Hilo 3 (loader)**: lee **30 archivos de CD** (`0x4CFA80` = `sceCdRead`; lsn crecientes
  `1048576 → … → 1302477 → 1821047`) y luego entra en **`SleepThread`**
  (`0x628820 → 0x4CF860 → 0x4D31C0 → 0x4D31D0`, ~735 vueltas).
- **Nunca se alcanza el "release" `0x628A10`** (setea `gp+0x58=1` cuando `gp+0x54==1`; y `gp+0x54` **ya es
  1** en el recomp). Forzarlo (`SWORD_FORCE_LOADER`) **no** destrabó.

---

## 8. PRÓXIMO PASO EXACTO

1. **Identificar qué espera el hilo 1** en su spin del lock (¿un flag de "carga completa" que el loader
   debería setear?) y **qué espera el loader**; y **quién debería** hacer el `SignalSema`/`WakeupThread`
   que falta.
2. Usar `SWORD_TRACE_BRANCH` (+`tid=`) para seguir **ambos lados a la vez**; agregar el `a0` (sema id) al
   trace (el `[triage-sema]` está rate-limitado) para nombrar el semáforo del spin del hilo 1.
3. Comparar con el real desde `ss01` con PINE: **qué** hace el real entre el fin de la carga y el burst a
   `0xC8–0xDB` (ese paso es el que el recomp no ejecuta).

**NO hacer**: cazar flags downstream, hardcodear `0xA2A9C0`, restaurar `0x4d3730`, ni mirar el render/OS.
