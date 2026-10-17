# HANDOFF — reach-main-menu (estado definitivo)

**Fecha**: 2026-10-09. **Este es el documento de entrada.** Reemplaza a `reanalysis.md` (obsoleto) y
consolida `decisions.md`. Si algo acá contradice a otro artifact, **vale este**.

> ### ESTADO ACTUAL (2026-10-16)

> - **Único cambio de flujo de la sesión**: fix del **semáforo de completado RPC** en `sifBindRpcStub`
>   (`game_overrides.cpp`). El stub no creaba el semáforo que el SDK sí crea. Efecto medido: el loader
>   del hilo 3 **pasó de mudo a emitir RPC** (`client=0xa468f0 rpcNum=0x1`/`0x2`). `init=1` queda como
>   **shim documentado** (el SDK usa `init=0`; volver cuando el runtime señale el completado de BIOS).
> - **La pantalla sigue negra.** `vramNonZero=0/4194304` en corridas reales; **2 kicks de DMA, los dos
>   vacíos** (`qwc=0`). Con savestate inyectado dibuja bien (`vramNonZero=29544`): **el renderer está sano**.
> - **Cadena medida de punta a punta**: el motor gráfico entra (`[hit-6e4cc0]`, `[hit-6e4848]`), su setup
>   de boot es correcto, y el flip **sí corre** (probado por `[dma:kick] … ra=0x6e4ebc`, posterior al
>   bloque). `gp+0x638`/`gp+0x63C` son **cursor por frame** y valen 0 porque **no hay paquetes que enviar**.
> - **Raíz acotada**: **nadie encola geometría** (`FUN_006e58b8` sin llamadas de producción) porque
>   **`FUN_0075b0e0` — la fase del menú — no tiene ni un `jal` en todo el binario**; sólo se alcanza por
>   la tabla `0x95F3D0`/`0x95F3D4`.
> - **Hallazgo abierto (posible bug del recompilador)**: esa tabla quedó **decodificada como código**
>   (`throw std::runtime_error("Unhandled SPECIAL instruction")` en `0x95f3c0`/`0x95f3d4`) y tiene
>   entrada en la tabla de funciones (`// 0x95f3d0`). Hay dos saltos reales hacia ella
>   (`FUN_009470e0:2852`, `FUN_00953bc8:46643`). Pendiente: hook en `FUN_0095b2a8` para ver si entra.
> - **Verificado contra savestate real**: loader (`gp+0x74`/`0x80`), motor (`gp+0x5DC`/`0x610`) y
>   **los tres callbacks del árbol de escena** coinciden con consola. La divergencia es sólo el cursor,
>   y es consecuencia.
> - **Reglas nuevas**: (a) **medir contra el savestate antes de encadenar deducciones** — 6 hipótesis
>   cayeron hoy, todas por dato duro; (b) **`replaceFunction` sobre una dirección INTERNA de una función
>   es INERTE** (el C++ recompilado cae con `goto`, nunca consulta la tabla) ⇒ revisar todos los
>   `[triage-*]` del proyecto con esa lente.
>
> ---
>
> ⚠️ **SUPERSEDED (2026-10-15).** El diagnóstico nuclear de este documento (juego *parkeado en la fase
> de carga*; hilo 1 en *busy-spin del lock `0x4C3B50`*; hilo 3 en `SleepThread` sin alcanzar `0x628A10`;
> `gp+0x58=0`; `nonZeroRgb=0` con `dma=3`) quedó **obsoleto**. La fuente vigente es **`decisions.md`**
> (§2026-10-15) y el detalle de tareas en `tasks.md`. Abajo, §"ESTADO ACTUAL".
>
> ### ESTADO ACTUAL (2026-10-15)
>
> - **El arranque y el render están desbloqueados**: `gp+0x58` se libera, el streaming completa
>   (`burst_maxdst` `0xDAFE80`), el main thread está en el loop de escena (`0x6D6FE8`),
>   **`dma` pasó de 3 a ~1.700** y la **VRAM tiene datos reales (~475 KB)**.
> - **`activeThreads=3`, `gif=2`, `vif=6`**, sin crash. **CI en verde** (Linux + Windows).
> - **Lo que falta**: el **frame PRESENTADO sigue negro** (`nonZero=0`, con `rgbNZ=0 / aNZ≈238k`) —
>   el juego dibuja el **fade/clear** (quads negros) pero no llega el contenido con color/textura.
> - **Causa raíz en curso**: la tabla de handlers RenderWare `0x008A4CAC` (`{id:0x16}` = `FUN_006f2630`,
>   llamada **182×/frame** sin slot) ya se resolvió (missing-target: 200 → 2); ahora la **FSM de carga
>   `FUN_00628640`** (switch `jr $v0` con un hueco de 740 B en el CSV, jump table en `0x009E0180`)
>   quedó cubierta (784 B) y **hay un build corriendo** con el CSV de **20.434** filas.
> - **Regla vigente**: ningún build sin `work/validate_csv.py` en verde (`0 SHADOW / 0 MIDFUNC`).
> - Fecha del resto del documento: 2026-10-09/11 (histórico).

> **ACTUALIZACIÓN 2026-10-11 (Parte 2)** (ver `tasks.md` §"Sesión 2026-10-11 (Parte 2)"):
> 1. **Destrabe de Streaming y Transición de Escena**: se descubrió que el hilo 3 (cargador de streaming
> `0x628640`) cicla llamando a `0x4CF860` (`sceCdDiskReady`). Al estar `sceCdRead` en HLE, el semáforo
> interno de libcdvd nunca se señalizaba y retornaba 6 (`SCECdNotReady`) infinitamente, reteniendo
> `gp+0x58=1`. Al implementar el stub de `sceCdDiskReady` en `game_overrides.cpp` retornando
> `SCECdComplete = 2`: **el hilo 3 completó el streaming, limpió `gp+0x58=0`, `burst_maxdst` saltó de
> `0xCE9B60` a `0xDAFE80` (>116k words escritas) y el hilo principal avanzó al loop de escena `0x6D6FE8`**.
> 2. **Causa del indirect call nulo en loop de escena (`pc=0` en `0x6D2688`)**:
> `0x6D2688` hace un dispatch de método virtual (`0xA887B8 + 0x10C`) dentro de `0x6D23F0`, la cual es llamada
> desde `0x742270` (`FUN_00742270`). En `ghidra_functions.csv`, `FUN_00742270` estaba **truncada a sólo 4
> bytes** (`0x742270..0x742274`), emitiendo solo la reserva de stack y dejando sin ejecutar la inicialización
> real de la estructura de escena. Se corrigieron los extents de `FUN_00742270` (1432 B) y `FUN_00742808`
> (1880 B). Próximo paso: terminar regeneración con `ps2_recomp` e integrar.
>
> **ACTUALIZACIÓN 2026-10-11**:
> se implementó un **hook de escritores por `mprotect`** (`SWORD_WP_WRITER`, runtime `.cpp`, default OFF) que
> captura el PC del que escribe `0xC80000–0xE50000` por `SIGSEGV`, **sin recompilar los 18 311 `.cpp`**.
> Resultado: **los únicos escritores son el propio juego** (`FUN_006cba48` p10 = armado de escena,
> `FUN_004eb8d0`) y el **allocador `FUN_004c3000`**; **CERO escritores de DMA/CD/runtime** ⇒ la hipótesis
> "DMA/staging" queda **refutada**. `0xCF0000–0xE50000` **nunca** se escribe (coincide con
> `burst_maxdst=0xCE9B60`). El contenido del recomp **alinea con el real en un corrimiento exacto `+0x150`**.
> **Burst trazado con `src`** (`[burst-loop]`, stub de `memcpy` `0x4C38D8`): el armado son sub-loops que copian
> de **tablas fuente fijas dentro de la región**; `burst_maxdst` **sube y se estanca** en `0xCE9B60` (~161 s)
> ⇒ **el loop externo termina** (no es lentitud). Las fuentes divergen (mismo conteo, 0 coincidencias =
> punteros) y la **última fuente `0xce3a50` está casi vacía en el recomp (25 nz vs 250)**.
> **CORRECCIÓN DE FASE (clave)**: el dump del recomp coincide con `draw_vif1kick_006E4468` en **98.33 % de
> todo el RAM** (RAM baja **100 %**; vs `videoformat_menu` 94.26 %) ⇒ **el recomp es FIEL en la fase `draw`**;
> el "gap de la región" era **diferencia de fase**, no carga faltante. Está **CLAVADO ahí** (600 s:
> `gp740=0`/`gp744=0`/`burst_maxdst=0xCE9B60` constantes) y **nunca ejecuta el código de la fase menú
> `0x75Bxxx`**. El bloqueo es la **máquina de estados de escena que no avanza `draw`→`menú`** (el kick de
> draw sale vacío, `VIF1 qwc=0`). **Próximo**: el trigger de esa transición. El rebuild completo con
> `ps2TraceGuestWrite` **no agrega** (los escritores ya están enumerados).

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
| `SWORD_WP_WRITER=1` | **Hook de escritores a `0xC80000–0xE50000`** (`mprotect`+`SIGSEGV`): enumera cada rutina que escribe la región (PC del caller + rango), sin rebuild de los `.cpp` generados. |
| `SWORD_PAD_PRESS=<btn>` (+`SWORD_PAD_TOGGLE=1`) | Pulsa un botón sintético permanente (o 1 s on/off) — harness headless (el pad queda neutro sin teclado). |
| `SWORD_LOAD_RDRAM=<eeMemory.bin>` (+ `<file>.ranges`) | Teleport de RAM (RDRAM del savestate) al recomp; `SWORD_LOAD_GS=<GS.bin>` inyecta además los 4 MB de **VRAM del GS** (sin esto el estado teleportado queda negro). |
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
