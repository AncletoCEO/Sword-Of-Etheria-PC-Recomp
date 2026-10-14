# Decisions — reach-main-menu (CONSOLIDADO)

> **Documento de entrada: `HANDOFF.md`.** Este archivo guarda la evidencia y las decisiones.
> Consolidado 2026-10-09: se eliminó el detalle exploratorio y las entradas superseded para no inducir a
> error. El historial completo está en git.

---

## Reglas / entorno (no re-descubrir)

- Build: `cmake --build work/build-game/out-linux --target sword_etheria -j4` (**-j4**, más = OOM).
- **No editar headers** (`ps2_runtime.h`/`ps2_runtime_macros.h`): 18 k rebuilds. Instrumentar en `.cpp`.
- Corrida baseline: `SWORD_SIF_SEMA=1 timeout 180 ./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68`
  → `vbprof n≈10681/180 s`, `gif=2`, `nonZeroRgb=0`, `vramNonZero` 0/306048/524288.
- El código del juego en **`0x4eb8d0..0x6cba48` es UNA mega-función** (`FUN_004eb8d0`); `0x6cba48..` otra.
  El runtime **reemplaza cada slot del rango por la mega-función** ⇒ `replaceFunction` sobre un slot de ahí
  **no tiene efecto**. Para ver el flujo interno: `SWORD_TRACE_BRANCH` (runtime) o instrumentar la mega.
- `[triage-sema]` está **rate-limitado** (sus conteos no son representativos).
- Syscalls: `0x32`=SleepThread, `0x33`=WakeupThread, `0x40`=CreateSema, `0x42`=SignalSema, `0x44`=WaitSema.

---

## Evidencia clave (real vs recomp)

- **`ss01` ≈ recomp**: RAM baja idéntica byte a byte; **71 741 palabras** distintas (0,85 %).
- **El real, desde `ss01`**: hace un **burst** (~450 k palabras a `0xC80000–0xDB0000`), setea
  `gp+0x50/0x54` a ~3,3 s y **`gp+0x58` (`0xA280C8`) a ~3,5 s**, y luego se asienta.
- **El recomp**: lee **30 archivos de CD** (`0x4CFA80`=`sceCdRead`; lsn crecientes) y luego **duerme**
  (`SleepThread`); **nunca** alcanza el release `0x628A10`.
- **Wait cruzado** (traza `SWORD_TRACE_BRANCH` con `tid=`): hilo 1 = busy-spin del lock
  (`GetThreadId` ×75 290 + `WaitSema` ×38 931/60 s); hilo 2 = `WaitSema(3)`; hilo 3 = `SleepThread`.
- **Nombres de semáforos (2026-10-10, `a0` en el trace)**: el spin del hilo 1 es **sema 1** — el lock
  re-entrante `FUN_004c3b50` (acquire; sema id en `*(0x8744A0)`) / `FUN_004c3bd0` (release; `j 0x4D32C0`).
  90 s: 75 290 entradas al lock, 37 642 `WaitSema(1)`. **sema 8** lo balancea el propio hilo 1
  (4 230/4 230). Hilo 2 = **sema 3**; hilo 3 = **sema 6** (`PollSema`/`SignalSema`) + `SleepThread`.
  El hilo 1 ejecuta el helper `0x628950` (`WakeupThread(3)` si `*(gp+0x58)==1`).
- **Caveat de traza**: `SWORD_TRACE_BRANCH` no ve tail-calls directos (`j 0x4D32C0`), así que subcuenta
  `SignalSema`; no tomar "0 signals" como señal faltante.

---

## 2026-10-10 — el gate del loader YA NO es el bloqueo (medido)

- **`gp+0x58` (0xA280C8, carga completa) SÍ llega a 1** (vb≈2761, baseline sin envs); `gp+0x54`=1 siempre.
  ⇒ el loader `while(*(gp+0x58)==0) SleepThread()` **se libera** (contradice §7 del HANDOFF). El hilo 1
  sale del lock (`0x4C3BC4`) y pasa al loop de audio (`0x6E4EBC`).
- **Después del gate el juego está activo**: `sceCdRead` con datos reales (`mission16.bin`, magia `SIMB`),
  `[dmairq]`, `[vif1-chain]`, `[vu1:mscal]`, `gs:prim`.
- **Pero la escena es negra**: todos los `gs:prim` tienen `rgba0` en `{(0,0,0,0),(0,0,0,128)}` y **0 prims
  con textura** (`tme=0` siempre); un sprite full-screen pinta `fbp=0` de negro. `nonZeroRgb=0`.
- **Conclusión**: el bloqueo es **downstream del gate** (el juego no produce salida con color/textura),
  no el `SleepThread` del loader. Próximo foco: por qué no llega color/textura al GS.
- **Burst `0xC80000–0xDB0000` PARCIAL (causa concreta)**: el recomp lo llena **idéntico al real hasta
  `0xCEFFFF`** y **se corta**; `0xCF0000–0xDAFFFC` queda en cero. Faltan **177 271 words** (s02: 233 246
  nz vs recomp: 67 973). Coincide con s02 en `0xA3–0xA6` y lee los 30 CD (lsn→1302477). El recomp hace un
  burst **truncado en `0xCF0000`**. Evidencia: `/tmp/sword_recomp_late.bin` vs `s02/eeMemory.bin`
  (`SWORD_DUMP_LATE=1`).
- **La cola `0xCF0000–0xDB0000` NUNCA se escribe** (`SWORD_SEED_TAIL=1`: marcador `0xDEADBEEF` intacto,
  `tail_marker=196608` todo el run) ⇒ el código que la llena **no se ejecuta** (no escribe ceros).
  El recomp **sí** arma tablas dentro de `0xC7–0xCA` con `memcpy` chicos y repetidos (stride ~0xC0,
  `ra=0x74B8F8`/`0x74D31C`) — una rutina en `0x74xxxx`. El corte en `0xCF0000` sugiere un **bound/contador
  de esa construcción**, no un dato ausente.
- **Trace-forward PCSX2/PINE**: el real, desde s01, corre `0x4D3764 → 0x74A3D4 → 0x6E4CDC` y llena la
  región completa (`0xC5–0xDA`). El recomp **también** pasa por `0x74xxxx` ⇒ **mismo camino de código**.
- **Loop interno (p10 `0x74B8F8`)**: es `while (fp < *(sp+0x28)) memcpy(...)`, con `fp=$r30`. Termina
  **normalmente** (`fp` llega a `limit`). Arma **batches**: `dst=0xC8F420` (limit 0x188, n=0x78),
  `dst=0xCD6CC0` (limit 0x480, n=0xC8), `dst=0xCE82F0` (limit 0x480). El **último batch llegó a
  `0xCE9B60`** y no hubo más. ⇒ **la divergencia está en el loop EXTERNO** (cuántos batches/ítems
  arma), no en este loop. `burst_maxdst=0xCE9B60`. Probe: `[burst-loop]` (env default ON, log acotado).
- **CORRECCIÓN (2026-10-10)**: comparar *conteos* de no-cero no alcanza. La diff **word a word** recomp vs
  s02 en `0xC50000–0xCE0000` muestra **miles de words distintas por bloque** (2114…15751), y `0xCF–0xDA`
  100% distintas (recomp=0). ⇒ la región no está sólo **truncada**: el recomp la arma con **valores
  distintos**. Probe interno `[build]` (p10 `0x74A3E0`): construye objetos (índice `s2`, base `0xC803E0`,
  objeto `s7=0xA887B8`, virtuales en `+0x118`/`+0x108`) pero con contenido diferente. **Causa raíz = data/flujo
  aguas arriba del armado de escena** (no un bound aislado).
- **Trace de ejecución del real: inviable con el tooling actual.** `[EmuCore/TraceLog]` + `EE.r5900` está en
  el binario (PCSX2 2.8.2) pero **no emite**; `-debugger` deja la VM **pausada** y no se reanuda headless
  (sin `xdotool`); y el debugger a mano ya se sabe que **se traba** (sesiones previas). PINE sólo da RAM.
- **Probe interno extendido** (`0x74A3E0`): el recomp escribe **punteros** (`v0=0xA94570…`, objetos alocados)
  en un array `0xC803E0 + s2*4`; el real tiene **floats** ahí (0.5, 0.14…). ⇒ estructuras/heap ubicados
  distinto. Comparar *exactamente* qué rama/valor diverge requiere trace de ejecución del real (bloqueado).
  Probe temporal en `work/generated/FUN_006cba48_0x6cba48_p10.cpp` (`[build]`, no env-gated).

## 2026-10-10 — Debugger de PCSX2 (intérprete) y verificación de código

- **El debugger se destraba con el intérprete** (`[EmuCore/CPU] EnableEE/IOP=false`) + **shutdown y recargar
  la ISO** (desde boot limpio se traba y no llega al breakpoint). Así **sí rompe** en `0x74A3D4`/`0x74A3E0`.
- **PERO su panel GPR está roto**: no actualiza entre hits (queda con el estado de boot: `s0..s7=0`, `gp=0`).
  ⇒ el debugger sólo sirve para **breakpoints + Memory** (y Memory ya lo teníamos por PINE/savestates).
- **Código verificado idéntico** en `0x74A3C0..0x74A3EC` entre ELF, s01, s02 y el recomp → **no hay
  overlay ni mala recompilación**.
- **Estado/heap**: en `0xC803E0` real y recomp usan **la misma base** pero con **punteros distintos**
  (real `0xC781B0…`; recomp `0xC7A290…`); flags `gp+0x50/54` iguales. ⇒ divergencia de **valores/estado
  aguas arriba**, no de control.
- **Bloqueo final**: aislar el primer punto necesita **trace con registros vivos** — no disponible
  (GPR roto; sin herramienta headless).

## 2026-10-10 — Conclusión de la línea "llegar al menú"

El **hito visual mínimo está demostrado** (`SWORD_TEST_PATTERN` → "HELLO WORLD"). El menú real requiere
cerrar la divergencia de **estado/heap en el armado de escena** (`FUN_006cba48` p10, `0xC803E0`), que
necesita un **trace de ejecución con registros** (herramienta aparte).

## 2026-10-10 — GPRs vivos vía savestate (workaround) y DESCARTE del armado de escena

- **Workaround al GPR roto del debugger**: los GPRs del EE están en el savestate
  (`PCSX2 Internal Structures.dat`): array de 32 regs, **stride 0x10**, `r0` en el offset **0x162**
  (`gp`=`r28` en `0x322`). Se leen por PINE `SaveState(slot)` + extracción.
- **Comparación real vs recomp en el armado** (real `@0x74A3D4` vs recomp `@0x74A3E0`):
  `s0=0xA887B8`, `s2=0`, `s7=0xA887B8`, `gp=0xA28070` → **IDÉNTICOS**. Sólo difieren punteros de heap
  (`s4`, `fp`, `v0`) por un **offset constante 0x150** (layout de heap distinto).
- ⇒ **El armado de escena NO es la divergencia** (falso positivo previo: se comparaban estados de heap
  distintos). **El bloqueo está en el camino render/GS** (prims negros, 0 texturas).

## 2026-10-10 — Trabajo autónomo (render/GS)

- **Main thread**: el real en s05/s06 está en `0x6E4CDC` (loop de audio), **igual** que el recomp
  (`0x6E4EBC`) ⇒ que el main esté ahí **no es divergencia**.
- **VRAM (recomp vs real)**: el recomp tiene los **primeros 2 MB = `0x7F000000`** (negro, **alpha 0x7F**),
  o sea **su propio clear**; el **real tiene esa zona en CERO**. El contenido del real vive en
  `0x200000`/`0x3C0000` (otro `fbp`). ⇒ el recomp **presenta `fbp=0` (su clear negro)** mientras el
  contenido del real está en otra página/`fbp`.
  - Dump del recomp: `SWORD_DUMP_VRAM=1` → `/tmp/recomp_vram.bin` (present #1500).
- **Herramienta nueva**: `game/pine_state_gpr.py` (GPRs vía savestate) + guía `PCSX2_DBG.md`.
- **Texturas**: en el recomp **no llega ninguna subida de textura al GS**. Todos los `[gs:gif]` son
  `flg=0` (**PACKED**) — **cero paquetes IMAGE** (`flg=2`); `[gsblk]` = 0; y el VRAM del recomp sólo tiene el
  clear (`0x7F000000`) — **sin los datos de textura** que el real sí tiene (regiones `0x2xxxxx`/`0x3Cxxxx`).
  ⇒ **la subida de textura del juego no llega al GS del recomp**. Lead: revisar el camino GIF/PATH3
  (DMA-a-GS) y por qué el juego no emite el paquete IMAGE en el recomp.
- **Setup GS: descartado**. En el real, `sceGsSyncV`/`SetDefDispEnv`/`SetDefDrawEnv`/`SetDefClear`
  (call sites ra≈`0x6F02xx`) tienen el **mismo env** (`0xA8D0B0`), **mismo pmode** (`0x8067`) y display
  idénticos a los del recomp.
- **Sitio del DRAW (VIF1 kick) = `0x6E4468`** (log `[dma:kick] VIF1 CHCR=0x145 pc=0x6e4468 ra=0x6e4ebc`,
  cada frame; llamado desde el loop principal `0x6E4EBC`). **El recomp llega al mismo `0x6E4468`** ⇒ el
  flujo del draw coincide; lo que **difiere es la DATA** que se manda al VIF1/VU1 (prims negros).
  - Savestates del real: slots 1-4 = breakpoints de los 4 `sceGs*`; slot 5 = menú (video format).
    GPRs legibles con `game/pine_state_gpr.py read <slot>`.
- **En `0x6E4468` (real) el setup del draw coincide con el recomp**: `v0=0x145` (CHCR escrito),
  `s1=0x10009000` (CHCR), `t5=0x10009010` (MADR), `s2=0x10009020` (QWC), `a1=0xA96800` (fuente del chain
  VIF1 — dentro de la región de chains del recomp `0xA967xx`). GS: `PMODE=0x8067` (coincide). ⇒ **el
  dispatch del draw coincide** (mismo VIF1 kick, mismo chain). El recomp **sí** arma los chains VIF1 con data
  (`[vif1-chain]` qw=194/86/177 en `0xA9xxxx`). ⇒ la divergencia está **aguas abajo del armado**: en el
  **procesamiento VU1** (microcódigo) o en el **parseo del paquete GIF/GS** (los prims llegan negros).
- **VU1**: el recomp **sí ejecuta** el microcódigo (`[vu1:mscal] startPc=0x0 endPc=0x168 cycles≈771`,
  kick en `eePc=0x6E4468`). Y las escrituras a registros GS por `Store32` son **muy pocas** (6-8; addrs
  `0x10003xxx` GIF) ⇒ los sprites del menú **no** van por writes de registro GS, van por **VU1→GIF**.
  ⇒ el bloqueo está en el **VU1 microcode / ensamblado del paquete GIF** (los prims llegan negros).
  - Probe: `[gs:wpc]` (pc de writes a `0x12xxxxxx`/`0x10003xxx`); `[vu1:mscal]`/`[vu1:mscnt]`.
- **Tooling nuevo**: `game/pine_state_gpr.py` (GPRs por savestate), `game/pcsx2_state.py`
  (guardar/restaurar savestates por nombre en `work/pcsx2_states/`, gitignored — rotar los 9 slots),
  `aspec/changes/reach-main-menu/PCSX2_DBG.md` (workflow debugger + estados).
- **El parseo GIF del recomp SÍ maneja IMAGE (`flg=2`)** (`gs_frontend.cpp` → `uploadImageNative`). Y el
  real en `0x4D3730` (sceGsSyncV) da un estado consistente. ⇒ **no es el parse ni el GS**: el juego **nunca
  emite un paquete IMAGE/textura** en el recomp → **no llega a subir texturas ni a dibujar la escena**.
  El bloqueo es de **flujo del juego** (no render/GS/parseo).
- **Límite del tooling de debug**: el debugger de PCSX2 **no expone VU1 ni el stream GIF**; no se puede
  frenar el XGKICK. Y la **inyección de input (xdotool/ydotool) no registra** en esta sesión **Wayland/KWin**
  ⇒ no puedo manejar el debugger headless (sí puedo *ver* por `import` + *leer* por PINE/savestates).
- **CORRECCIÓN (auditoría del generado)**: `0x6E4EBC` es el retorno de la **función de audio `0x6E4068`**
  (retorna en `0x6E4ED0`, rodeada de logs `[gen-audio]`), y `0x6E4468` cae **dentro de esa función** ⇒ lo
  que se llamó "el draw `0x6E4468`" es un **kick de DMA dentro del path de audio**, **NO** el draw de escena.
  Por eso `0x6E4468` no pega al mostrarse el menú. **El draw de escena sigue sin identificarse.**
- **CORRECCIÓN 2 (probe `[gs:kick]`/`[gs:gif]` con `pc`)**: los paquetes/prims GS salen con **`pc=0x6E4468`**
  (94 `gs:kick`, 46 `gs:gif`) ⇒ **`0x6E4468` SÍ es el draw** (el kick VIF1 que corre el VU1 → GS). El label
  `[gen-audio]` era engañoso. ⇒ el **draw corre y entrega paquetes al GS** (con data: size 2832/2576/1136…,
  `flg=0` PACKED), pero los prims salen **negros** ⇒ la **data** (del VU1/GIF) es negra. Foco: VU1 → GIF.
  - Probe: `[gs:kick] pc=`, `[gs:gif] pc=` (pc global `g_lastStorePc` en `Store32/Store128`).
- **DATO CLAVE (regs crudos del paquete)**: los paquetes del draw (`pc=0x6e4468`, `tagHi=0x412` →
  regs `[ST(2), RGBAQ(1), XYZF2(4)]`) traen **`RGBAQ = 0`** (color negro) pero **sí** traen geometría
  (floats de ST/XYZ: `0x3E2E0000`,`0x3F028000`,…). ⇒ el **VU1 produce la geometría pero el COLOR sale 0**.
  **No es el parseo** (lee 0 porque es 0): la divergencia es el **color** que el juego/VU1 manda.
  - Probe: `[gs:gif]   tagHi=… regs=…` (primeros 4 qwords del payload).
- **Chain VIF1 del draw (input del VU1)**: tiene **geometría** (floats de posición `0x42800000`, `0x432e0000`,
  escalas `0x3f800000`, patrones `0x55555555`) pero **no un color RGBA claro**, y el VU1 **emite `RGBAQ=0`**.
  ⇒ el bloqueo está en el **path de COLOR del VU1** (o en el input de color del juego), no en la geometría.
  - Probe: `[vif1-chain] #N src=… qw=… data=<16 words>` (ps2_memory.cpp).
- **Auditoría del VIF1 UNPACK**: el decode de formato es **correcto** (V4-32: `vn=3,vl=0`;
  V4-5 = 5/5/5/1; S-32/16/8; `components=vn+1`). El `MASK=0xC000C000` es un patrón normal del juego
  (write-protect de campos 2/3 en ciclos 1 y 3); `row/col` en 0 pero **no se usan** (todo de SRC).
  ⇒ **el unpack NO está roto**. El vértice que entra es **posición + 2 valores raros** (`0xc77b3599`,
  `0x55555555`), **sin color**. El color **no está en el vertex input** → sale del **microcódigo VU1**
  (literal/registro) o de un unpack de constantes aparte.
  - Probe: `[UNPACK] … m=… row=… col=… src=…` (ps2_vif1_interpreter.cpp, cap 400).
- **Dump del paquete crudo del XGKICK** (`[XGKICK-fin] … raw=<q0|q1|…>`, ps2_vu1_core.cpp): cada loop =
  `[ST, RGBAQ, XYZF2]`. **ST** y **XYZF2** traen geometría/UV real (floats/posición), pero
  **RGBAQ = `0:0x8000000000`** ⇒ **RGBA = 0 (negro)**. El VU1 arma la geometría bien pero **escribe
  `RGBAQ=0`**. ⇒ el bloqueo es **el microcódigo VU1** (no XGKICK, no parseo, no unpack, no geometría).
  - Probe: `[XGKICK-fin] totalBytes=… src=… raw=…` (ps2_vu1_core.cpp).
- **DÓNDE ESCRIBE EL MICRO EL COLOR** (instrumentando `queueStore`, `[VU1-store]`): el micro arma el vertex
  de salida en la VU1 mem `0xc00+`. El **`RGBAQ`** son los stores en **`pc=0x100/0x108/0x110`** y escriben
  **siempre el mismo valor constante `[0, 0, 0, 0x80]`** (x=0,y=0,z=0,w=128.0) ⇒ **RGBA=0 (negro), alpha 0x80**,
  igual para todos los vértices. Decode de `pc=0x100` (`lower=0x03ebb002 upper=0x000002ff`): `SQ` de `vf[11]`
  a `vi[21]`, y el upper del mismo pc (`fd=11, fs=0, ft=0`) computa `vf[11]` desde `vf[0]` ⇒ **`vf[0]`=0**.
  - **Conclusión**: el micro **no** saca color del vértice (el input sólo trae posición + 2 constantes);
    el color sale de **`vf[0]`/una constante de la VU1 que está en 0**. El bug está en ese **origen de
    color (constante VU1 = 0)**, no en geometría/GS/unpack/XGKICK.
  - Probe: `[VU1-store] pc=… addr=… lane=… w=…` (ps2_vu1_core.cpp) + `SWORD_DUMP_VU1CODE=1` →
    `/tmp/recomp_vu1code.bin`, `/tmp/recomp_vu1data.bin`.
- **CADENA COMPLETA DEL COLOR (desensamblado del microcódigo)**: el micro del draw es:
  ```
  0x030 LQ vf28, vi0+1019     ; constante = (1.0, 1.0, 1.0, 0.502)  ← sólo escala ALPHA
  0x058.. LQ vf8/9/10  (pos, vi10+0/4/8)
          LQ vf22/23/24 (color, vi10+2/6/10)
  0x0a8   MUL vf22,vf22,vf28 ; color = vertex_color × vf28
  0x100   SQ vf22 -> vi11+2  ; RGBAQ
  ```
  `[VU1-color]` muestra que **el color del vértice en la VU1 mem = `[0,0,0,255.0]` (RGB = 0)**, igual
  para **todos** los vértices/draws ⇒ el micro **no inventa** el negro: **la data de color que el juego
  subió a la VU1 mem ya viene en RGB=0**.
  - **CONCLUSIÓN FINAL DEL BLOQUEO**: `GS RGBAQ=0` ← micro guarda `vf22 = vertex_color × alpha_const` ←
    **la data de color del juego (VU1 mem) es `[0,0,0,255]` (RGB=0)**. El micro/VU1/GS están OK.
  - Probe: `[VU1-color] vf… addr=… w=… | vi10=… vi11=…` (ps2_vu1_lower.cpp) + `vue1dis.py` en scratchpad.
- **ORIGEN DEL `[0,0,0,255]` = DATA DEL JUEGO**: el chain VIF1 (`src=0xa97ef0`) trae los vértices así:
  `[pos x=64,y=174][uv 0.125,0.34][0 0 0 <<437f0000=255.0>>]`. ⇒ **el color negro viene del propio dato
  del juego**, y el recomp lo lee **fielmente**. **No hay bug en el pipeline de color**: el juego está
  dibujando **quads negros semitransparentes** (fade/clear), no el contenido del menú.
  ⇒ **Reencuadre del bloqueo**: el pipeline gráfico es fiel; la brecha restante es **el estado de escena /
  lógica del juego** (el recomp se queda en draws negros), no el color/GS/VU1.
- **A/B RDRAM real↔recomp en `0xa97ef0` (data del draw)** — extraído con `eeMemory.bin` del `.p2s`:
  - State `draw_vif1kick_006E4468`: **el real tiene la MISMA data negra** `[0,0,0,255]` que el recomp
    (única diff: `c77b3595` vs `c77b3599` — un nibble).
  - State `videoformat_menu`: la data ya es **otra fase** (`3f009a34`×3 + `3f001919`, `437f0001`…).
  ⇒ **En el draw el recomp es FIEL** (mismo color). La brecha es **progresión de escena**: el recomp no
  llega a la fase del menú. (Script: `eeMemory.bin` vía `zipfile`; ver `game/rdram_diff.py`.)
- **A/B RDRAM COMPLETA (recomp tick=1200 vs savestates reales)** — `SWORD_RDRAM_DUMP_LATE` (dump 32 MB full;
  **ojo: `tick` vive dentro de `PS2_IF_AGRESSIVE_LOGS`, hay que esperar ~130 s** para tick≥1200):
  - vs `draw_vif1kick_006E4468`: **solo 6.4 %** de páginas 64 KB distintas (33/512) ⇒ recomp **muy fiel**.
  - vs `videoformat_menu`: 12.7 % distintas (más divergencia en fases avanzadas).
  - **Focos de divergencia (consistentes en ambos)**: (1) **`0xC80000–0xE40000` = región del "burst"**
    (~15 k words/página; coincide con `burst_first=0xc80000 burst_maxdst=0xcd8530`); (2) RAM baja
    `0x0/0x10000/0x80000`; (3) heap `0xA8xxxx`:
    - **`0xa828d0` = 0 en el recomp pero NO-cero en AMBOS states reales** ⇒ estructura que el recomp
      **nunca inicializa** (lead fuerte).
    - pointers corridos (`0xa88874: 0xcb5b18 vs 0xcb5818`).
    - **tabla indexada divergente** (`0xa88934+: recomp `04 02 02 00…` vs real `03 02 01 00…`).
  - Script: `full_ab.py` en scratchpad (`/tmp/recomp_late.bin` vs `.p2s`).
- **Análisis de `0xa828d0`**: el struct `0xa82800` tiene **48 words IDÉNTICAS** real↔recomp (la data/tabla del
  juego es fiel); la divergencia son **5 punteros** en `0xa828d0`:
  `real 000dc200 0010aa40 000dc200 000dca00 00104a40` vs `recomp 0 0002e840 0 00000800 00028840`.
  Los destinos apuntados están **en cero** en ambos; los deltas del heap son grandes y mezclados
  (`+1507351 ×1796`, `+23 ×1796`, `-1441814 ×1294`…) ⇒ **no es un corrimiento simple: es estado dinámico
  del heap/allocation que diverge**. ⇒ el recomp reproduce la data **estática** fiel (~93.6 % de páginas);
  la brecha es **estado de runtime (heap/burst)**, coherente con el reencuadre de escena.
- **CLASIFICACIÓN DE DIVERGENCIAS (lo importante)**: la mayoría de las páginas divergentes son
  **`0xC80000–0xE50000` (~2 MB) con el recomp TODO EN CERO** y el real con data de tipo **asset/textura**
  (`01010101…`, `49485959…`, `6391756a…`, `d6988f4f…`). ⇒ **el recomp NUNCA carga esa región**.
  Además `0x0` parcialmente vacío, y tablas con índices corridos (`0xCA0000`: recomp `00bb00ba` vs real
  `00d200d1`), floats donde el recomp tiene 0 (`0xC90000`).
  - **Hipótesis raíz (fuerte)**: el juego **lee data/assets a `0xC80000+`** (donde vive el contenido del
    menú) y en el recomp esa lectura **queda en cero** (gap de carga de archivo/resource).
  - Script: `classify.py` (scratchpad).
- **Verificación del I/O**: los `sceCdRead` (30) **sí entregan data real** del disco
  (`[cdread-data]: 53 49 4d 42`="SIMB", `mission16.bin`, `str01000201.bin`…) y se encuentran
  `OL/CHARA/BG/EFFECT/INTER/EED/EEE/EEF/EEI/EEU.BIN` (10 `sceCdSearchFile:ok`). **Pero los buffers caen en
  `0xA4xxxx–0xA8xxxx` (heap), NO en `0xC80000+`.** ⇒ La región de 1.9 MB en cero es un **buffer de
  trabajo/procesado (staging de textura/escena)** que el real llena procesando la data cargada y el recomp
  **no** → **es el lead más fuerte** (explica la falta de contenido y el `tme=0` en los quads negros).
- **Escritor de `0xC80000+` (búsqueda)**: **no hay `FAST_WRITE32/128(0x0C8..–0x0E4..)` literales** en
  `work/generated` ⇒ la región se llena por **punteros calculados o DMA** (no stores estáticos). El hook
  natural es `ps2TraceGuestWrite` (hoy **no-op**, en `ps2xRuntime/include/ps2_runtime.h`) pero ese header lo
  incluyen **18 311 .cpp** generados (2.1 GB) ⇒ editarlo = rebuild completo (inviable rápido).
  - Próximas opciones: (a) hook en el path de **DMA** del runtime (1 archivo); (b) rebuild completo con el hook;
    (c) dump a **2 ticks** (early vs late) y ver qué páginas de `0xC80000+` cambian alguna vez.

---

## 2026-10-11 — Escritor de `0xC80000+` (hook `mprotect`) — REFUTA el lead "DMA/staging"

- **Hook implementado** (`ps2_memory.cpp`, env `SWORD_WP_WRITER`, default OFF): tras `new uint8_t[ramSize]`
  se hace `mprotect(PROT_READ)` sobre `0xC80000–0xE50000` y se instala un handler `SIGSEGV`; en el fault se
  lee `REG_RIP` y se **escanea el stack** por direcciones de retorno dentro del `.text` del binario para
  identificar al **caller** (el `rip` cae en la copia out-of-line de `Ps2FastWrite32`, compartida). Cada 32
  faults se re-arma la región RO para **enumerar todos** los escritores (no sólo el primero por página).
  Sin tocar el header ⇒ **no** recompila los 18 311 `.cpp` (1 archivo + relink).
- **Resultado (70 sitios de escritura, 200 s)** — simbolizados con `nm`:
  - `FUN_006cba48` p10/p0/p1/p2/p9 (el **armado de escena**), `FUN_004eb8d0` p3/p7/p16/p21/p22/p35/p40,
    `FUN_004c3000` (familia **malloc**: lock `0x4C3B50` + smallbins) y `FUN_004c1ee0`.
  - **Ningún** escritor de DMA, CD, GS, o del runtime. ⇒ El lead "se llena por DMA / staging que falta"
    es **FALSO**: son stores de puntero calculado del **propio juego**.
- **Nunca escrito**: `0xCF0000–0xE50000` no lo toca ninguna ruta (páginas en `PROT_READ` todo el run; el
  marcador `0xDEADBEEF` intacto) ⇒ coherente con `burst_maxdst=0xCE9B60`.
- **A/B de contenido** (`/tmp/recomp_late3.bin` vs `videoformat_menu.p2s`): el recomp **sí** produce
  `0xC80000–0xCE9B60` (67 945 words ≠ 0; el real 73 562 en ese rango). Correlación por corrimiento:
  **máximo exacto en `+0x150`** (6 686 words coincidentes con ambos ≠ 0 vs ≈2 100 en ±0x10 y 2 495 en 0).
  ⇒ el contenido del recomp es **el del real corrido `0x150`** (el mismo offset de heap ya visto), pero por
  encima de `0xCE9B60` el recomp no escribe y el real tiene ~270 k words más.
- **Consecuencia de método**: el rebuild completo con `ps2TraceGuestWrite` **no agrega información** (los
  escritores ya están enumerados y son guest PCs de las mismas funciones) ⇒ no justifica las horas.
- **Nota**: las notas previas decían "`0xC80000+` = CERO en el recomp". Con el dump actual el recomp **sí**
  escribe hasta `0xCE9B60`; el `.02.p2s` de referencia actual tiene esa región en **cero** (los slots se
  rotaron el 2026-10-10) ⇒ usar `videoformat_menu.p2s` como referencia de fase avanzada.

### Burst del armado (2026-10-11) — secuencia, plateau y fuentes

- **Probe `[burst-loop]` con `src`** (en el stub de `memcpy` `0x4C38D8`, `game_overrides.cpp`): el armado es
  una **secuencia de sub-loops** `p10 0x74AFD0..0x74B8F8`, cada uno copiando de una **tabla fuente fija**
  (`src=0xc8db00/0xc81170/0xc80be0/0xc7db20/0xc911c0/0xce3a50…`) a un destino (`dst=0xc8f420…`, `n`, `limit`).
- **`burst_maxdst` progresa y se estanca**: `0xc8fde0→…→0xcd8530→0xCE9B60`, y se queda en `0xCE9B60` durante
  ~161 s ⇒ **no es lentitud: el loop termina**. El corte no es un dato ausente sino el fin del recorrido.
- **Las fuentes divergen** (recomp vs `videoformat_menu.p2s`): `src` con **mismo conteo de no-cero pero 0
  coincidencias** (firma de *punteros*; coherente con el offset de heap); la **última fuente `0xce3a50` está
  casi vacía en el recomp (25 nz vs 250)** ⇒ el último batch copia de una tabla sin poblar.
- **Estado aguas arriba VERIFICADO OK**: `*(gp+0x720)=*(0xA28790)=0x534` **coincide** (es el mismo contador
  que usa el loop), y el **objeto de escena `0xA887B8`** (incluidos sus **virtuales** `+0x108..+0x11C`:
  `0x5ea770/0x5ea650/0x5ea400/0x5ea5a0`, y `0x6d5f90/0x6d5fb8`) **coincide 1:1 con el real** (116 nz / 91·128
  words iguales). ⇒ la divergencia **no** está en este objeto ni en el contador del loop.
- **`0x55555555`**: el recomp tiene ~19 k words con ese patrón (p.ej. `0xA320EC+`); comparar contra el real.

### FASE del recomp = "draw" (no "menu") — corrige el marco (2026-10-11)

- **Comparar el dump del recomp contra TODOS los savestates del real** (`game/pcsx2_state*` /
  `videoformat_menu` / `scenebuild_0074A3D4` / `draw_vif1kick_006E4468`), región `0xC80000–0xE50000`:
  - `draw_vif1kick_006E4468`: nz=**66888** (recomp **67964**), **match@0 = 398 272/409 600 = 97 %**.
  - `videoformat_menu`: nz=343 002, match@0 = 122 716 (30 %).
  - `s02`/`ss01`/`menu_sceGsSyncV`: región en **cero**; `scenebuild_0074A3D4`: nz=198.
- ⇒ **El recomp reproduce FIELMENTE la fase `draw`** (97 %). La "región en cero / gap de DMA" de las notas
  previas salía de comparar el recomp (fase draw) contra el **menú** (fase posterior). **No es un gap de
  carga**: es una diferencia de **fase**.
- **Reencuadre del bloqueo**: el recomp llega al **draw** y se asienta ahí (main thread en loop
  `0x6e4ebc`/`0x51148c`, `gp58=1`, GS `rgbNZ=0`); el real **avanza del draw al menú**. La pregunta pasa a ser
  **qué dispara la transición draw→menú**, no "quién escribe `0xC80000+`".
- **Nota de método**: cualquier A/B de RAM debe hacerse **contra la fase correcta** (`draw` para el recomp);
  comparar contra `videoformat_menu` induce a error.
- **Gradiente de la región** (`nz` en `0xC80000–0xE50000`): `ss01`/`s02`/`slice03`/`slice04` = **0** →
  `scenebuild_0074A3D4` = 198 → `draw_vif1kick_006E4468` = **66 888** → `slice05`/`videoformat_menu` =
  **343 002**. ⇒ el real **pasa por el `draw` (nz≈67 k) y sigue hasta el menú (343 k)**; el recomp se queda
  en el `draw`. La construcción de la escena es un **build único grande** entre `slice04` (0) y `slice05`
  (343 k).
- **`draw` vs `menu`**: difieren en **sólo 56/512 páginas** de 64 KB. Cambios en el bloque `gp`: `gp+0x58`
  (`1→0`), `gp+0x74` (`1→0`), `gp+0x80` (`0→0xffffffff`), `gp+0x5cc` (`0x00010000→0x01020000`), `gp+0x5d0`
  (`0→1`), `gp+0x5e0` (ptr), `gp+0x638/0x63c` (ptrs), y **`gp+0x740` (`0→0x00C68C10`, un puntero al área de
  escena) + `gp+0x744` (`0→2`)** — candidatos a **estado/fase del menú**.

### El recomp está CLAVADO en la fase `draw` (2026-10-11) — diagnóstico

- **Fidelidad global**: dump del recomp (10 min) vs `draw_vif1kick_006E4468` = **98.33 % de las palabras**
  idénticas (vs `menu` 94.26 %); **RAM baja = 100 %**. El recomp **reproduce la fase `draw` fielmente**
  (la "región" sola da 83.8 % vs draw, 25.8 % vs menu, pero el resto del RAM es ~100 %).
- **Está clavado, no lento**: en 600 s, `burst_maxdst=0xCE9B60`, `gp58=1`, **`gp740=0x0` y `gp744=0x0`
  constantes**. La transición al menú **nunca ocurre**.
- **Nunca ejecuta el código de la fase menú `0x75Bxxx`**: traza `SWORD_TRACE_BRANCH` (0 src/tgt en
  `0x75b000–0x75b400` en 90 s). En cambio el main thread corre el callback `entry_0051147c` → `0x50F750`/
  `0x50FDD0` y el loop de escena (p10 `0x74B970` recorre una lista llamando los **thunks del objeto de
  escena** `0x6d5f90`→`0x5ea770` y `0x6d5fb8`→`0x5ea650`, ~18 k veces/90 s).
- **DRAW VACÍO**: en el estado clavado, el kick de dibujo `[dma:kick] VIF1 CHCR=0x145 madr=0x0 qwc=0x0
  pc=0x6e4468 ra=0x6e4ebc` → **no transfiere nada** ⇒ pantalla negra coherente (el juego no manda geometría).
- **RPC sin réplica**: siguen apareciendo `rpc-unhandled` a `sid=0x80000592`/`0x80000006`/`0x8000059c`
  (×63, `rpc=0`), y `[TYOSD] rpc=0x0 ack done`. (El opt-in `SWORD_IOP_BIOS_RPC` ya se probó sin avance;
  reverificar sólo si el trigger de fase lo señala.)
- **Conclusión concreta**: el bloqueo NO es el escritor, ni el DMA, ni el pipeline gráfico — es la
  **máquina de estados de escena que no avanza de la fase `draw` a la fase `menú`**. Próximo: ubicar el
  **trigger/condición** de esa transición (el código de `0x75Bxxx` que setea `gp+0x740/0x744`, y qué lo
  habilita), comparando el estado `draw` con una fase posterior.
- **Fase menú identificada**: **`FUN_0075b0e0`** (`0x75B0E0`-`0x75B0F8`) es la que setea `gp+0x740` (en
  `0x75B150/0x75B1CC/0x75B250`). Se invoca **por puntero**: hay una palabra `0x0075B0E0` en los **datos del
  juego en `0x95F3D4`** (tabla de punteros a funciones). El recomp **nunca** la ejecuta (0 branches en
  `0x75bxxx`; sin `jal`/dispatch estático) ⇒ la selección de esa entrada (índice/estado) nunca ocurre.
- **Tabla de fases + descriptor (datos)**: `0x95F3D0`→`0x95F3C0`, `0x95F3D4`→`0x75B0E0`, `0x95F3E0`→`0x75B8F8`
  (punteros, **idénticos recomp/draw/menu**). Pero el **descriptor `0x95F400+`** está **en cero en `draw` y
  en el recomp**, y **poblado en `menu`**: `0x95F410: 0→0x101`, `0x95F418: 0→4`, `0x95F424: 0→4`,
  `0x95F428: 0→0x0095F430`. ⇒ la transición **inicializa ese descriptor**; el recomp nunca llega ahí.
- **La entrada NO destraba** (2026-10-11): se agregó `SWORD_PAD_PRESS` (pulsa un botón sintético; pad del
  recomp estaba neutro) y se corrió con `start` toggled 200 s → `gp740=0x0` todo el run, `burst_maxdst`
  sin cambio. Descarta (al menos start) que la transición dependa de input.
- **Loop principal del recomp**: `0x51D900–0x51DBFC` (`FUN_0051d900`, ~3.6 it/s) llamando `0x4EA2B8` +
  el handshake de sema 8 (`WaitSema 0x4D32E0`/`SignalSema 0x4D32C0`). El cargador (hilo 3, `0x628688`) es un
  handshake con `gp+0x58`: espera `gw+0x58!=0` (SleepThread `0x4D31C0`) → procesa hasta 8 ítems → limpia
  `gp+0x58`. No es el gate (cicla normalmente).
- **Recompiler note**: `FUN_006cba48` (`0x6CBA48–0x9CBD34`) y `FUN_004eb8d0` (`0x4EB8D0–0x72B9C8`) son rangos
  **gigantes** que se tragan datos (`0x95F2xx` es DATA emitida como código: `nop`/`jr $0`/Unhandled SPECIAL)
  y sub-funciones (`FUN_0075b0e0`, `FUN_0051d900`), que el barrido de la mega-función **ensombrece**.

### Teleport al estado del menú (2026-10-11) — el estado SÍ se alcanza

- **`SWORD_LOAD_RDRAM` (sólo RDRAM) al `videoformat_menu.p2s`**: el juego **entra al estado del menú** —
  `gp740=0xc68c10` en 114 muestras (antes 0). ⇒ **la máquina de estados puede estar en menú**; lo que no
  llegaba era el estado (no se alcanzaba por lógica).
- **Faltaba la VRAM del GS**: se agregó **`SWORD_LOAD_GS=<GS.bin>`** (inyecta los 4 MB de VRAM del savestate
  en el GS del recomp; el teleport de RDRAM no la incluía). Con RDRAM+VRAM: **`nonZeroRgb` 0 → 1116/262144**
  y `vramNonZero` 0 → 29544 (primer frame con contenido no-negro), `[gs:diag] crt1 (fbp=0) rgbNZ=1026`.
- **Pero el menú completo NO se ve** (1116 px = motas sueltas, no una pantalla). La VRAM del real tiene el
  contenido en **`0x280000`** (fbp≈80) mientras el recomp **presenta `fbp=0`**; probablemente falta teleportar
  los **registros del GS** (`dispfb`/`display`/`pmode`, en `GS.bin` hdr / `eeHwRegs.bin`) o fijar el fbp de
  display. Es el siguiente paso concreto para *ver* el menú.
- Herramientas nuevas: `SWORD_LOAD_GS=<GS.bin>` (VRAM), `SWORD_PAD_PRESS`, `SWORD_WP_WRITER`.

## Fixes vigentes (default ON, sin regresión)

- **Cluster truncado `0x4d3700–0x4d3770` + `0x4d0cd0`**: corregido en `ghidra_functions.csv` y
  **regenerado**. `FUN_004d0cd0` ahora devuelve **`0x00873C90`** (antes `0x00870000`), con lo que
  `FUN_004d19c8` deja de saltear `FUN_004d3730`. Misma clase que el fix del dispatcher SIF `0x4d3fe8`.
- **Stub de `sceCdDiskReady` (`0x4cf860`)**: el cuerpo real esperaba un semáforo de libcdvd y RPC
  `cdvdfsv` que con el HLE de `sceCdRead` nunca llegaba, retornando `6` (`SCECdNotReady`) y trancando
  al loader thread con `gp+0x58=1`. Stub retorna `SCECdComplete (2)`. Destraba la carga y avanza a `0x6D6FE8`.
- **Cluster truncado `FUN_00742270` y `FUN_00742808`**: `FUN_00742270` estaba recortada a 4 bytes.
  Se corrigió el extent a 1432 B (`0x742270..0x742808`) y `FUN_00742808` a 1880 B (`0x742808..0x742F60`).
  Esto restaura el cuerpo real de armado de datos de escena invocado antes de los virtual dispatches.
- (`SWORD_IOP_BIOS_RPC`/`SWORD_IOP_SIF_INIT`, opt-in OFF): servidores IOP-BIOS + pre-init de `sifman`.
  Cerraron gaps reales, sin avance de escena.

---

## Descartado — con evidencia (NO volver a recorrer)

| Hipótesis | Evidencia del descarte |
|---|---|
| Audio/SPU2 | `SPIN-EXIT` es un log; audio normal; hilo principal no vive ahí. |
| RTC / tiempo (`0x875418`) | `sceCdReadClock` = hora del host; VBlank 60 Hz. |
| Reply de RPC kernel (`0x80000592`/`59c`/`0x80000006`) | Reply **real** en HLE → sin efecto. |
| Datos de `SD.BIN` | Servir el archivo real → sin efecto. |
| Flags SIF-init (`0x872098=0x22`, `0x873D78=1`, …) | Sembrarlos → sin efecto. |
| **`0xA2A9C0` = tabla RPC de config** | **FALSO**: es el **pool de paquetes SIF** (`_sif_alloc_packet`). `ss01` = **síntoma**. |
| `sema 8` desbalanceado | Balanceado (handshake LIBSD por frame). |
| `0x4d3730` (handshake SIF) como gate | Restaurar su cuerpo real **rompe el main thread** (`pc=0x0`). El stub es necesario. |
| SO anfitrión (Linux vs Windows) | Gate = lógica guest; PCSX2 renderiza en Linux. ~0 %. |
| Decomp a mano como alternativa | El recomp **ya es** una decomp; falta la capa de **plataforma**. |
| Watchpoint de stores en el generado | `FAST_WRITE32` bypassea `Store32`. |

---

## Gate actual y próximo paso

Ver `HANDOFF.md` §7–§8. En corto: **wait cruzado** (hilo 1 spin de lock / hilo 3 SleepThread / hilo 2 sema 3);
falta identificar **quién** debe hacer el `SignalSema`/`WakeupThread` y **qué** espera cada uno. Herramientas:
`SWORD_TRACE_BRANCH` (+`tid=`), `SWORD_CHAIN`, PINE.
