# Decisions — reach-main-menu (CONSOLIDADO)

> **Documento de entrada: `HANDOFF.md`.** Este archivo guarda la evidencia y las decisiones.
> Consolidado 2026-10-09: se eliminó el detalle exploratorio y las entradas superseded para no inducir a
> error. El historial completo está en git.

---

## Reglas / entorno (no re-descubrir)

- Build: `cmake --build work/build-game/out-linux --target sword_etheria -j4` (**-j4**, más = OOM).
  Usa **Makefiles**: re-escanea dependencias de los ~20 k `.cpp` (~5-6 min en no-op) y recién después
  compila/linkea (binario ~382 MB).
- **No editar headers** (`ps2_runtime.h`/`ps2_runtime_macros.h`): 18 k rebuilds. Instrumentar en `.cpp`.
- Corrida baseline: `SWORD_SIF_SEMA=1 timeout 180 ./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68`
  → medido 2026-10-17: `vbprof n≈10 600`, `nonZeroRgb=0`, **`vramNonZero` sube a 368801/475456** (ya NO es
  "0 en corridas reales": el render escribe VRAM), ≈**9 ticks/s** del task update (`[tick-prof]`).
- El código del juego en **`0x4eb8d0..0x6cba48` era UNA mega-función** (`FUN_004eb8d0`); `0x6cba48..` otra, y
  el barrido reemplazaba cada slot del rango (⇒ `replaceFunction` dentro del rango no tenía efecto).
  **CORREGIDO 2026-10-17: el generado ya está dividido** — `register_functions.cpp` mapea cada dirección a su
  propia función (`0x512630`→`FUN_00512630_0x512630`, `0x51fea0`→`FUN_0051fea0_0x51fea0`) y
  `FUN_004eb8d0_0x4eb8d0.cpp` tiene 4 KB (no contiene el código del rango). Los hooks sobre funciones
  completas del rango **sí disparan** (`[frame1]`, `[frame-loop]`, `[phase-hook]`). Antes de dar por inerte un
  hook: mirar `register_functions.cpp` y `hasFunction`.
- `[triage-sema]` está **rate-limitado** (sus conteos no son representativos). Igual que `[dma:kick]`.
- **Un log de síntoma puede ser artefacto**: ver §"Artefactos de medición" al final del archivo.
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

---

## 2026-10-15 — Decisiones de producto y de método (plan; NO implementado)

> Definidas en conversación. El "qué" queda fijo para no re-decidirlo; el "cómo" se ejecuta al cerrar
> el hito del menú. Detalle: `proposal.md` §"Producto final" y `design.md` §"Producto final — arquitectura".

**Producto**

- **Alcance**: el juego **completo**, por fases. El hito vigente sigue siendo **llegar al menú**
  (`nonZeroRgb > 0` con los triages apagados).
- **Plataformas**: **Windows + Linux**.
- **Distribución**: **GitHub Releases** por tag `v*`, con **launcher + tools + `build_release.py`**.
- **Launcher**: componente **aparte** (no menú in-game) — pide el ISO, expone opciones (resolución,
  escalado, vsync/FPS, audio, pad), escribe un **config `.toml` compartido** con el juego y ofrece
  **Generar** (`build_release.py --iso`) y **Jugar** (`sword_etheria --config …`).

**Contenido y licencia**

- El repo **no versiona nada con copyright**: ISO, ELF, `*.bin`, `*.exe`, `work/`, `*.recomp.cpp` y
  capturas quedan fuera (`.gitignore`). El usuario aporta su ISO (validado por **MD5**).
- **CORRECCIÓN de criterio**: el ISO se necesita **también en runtime** (los assets se leen del CD vía
  `io.cdRoot`) ⇒ el launcher **persiste la ruta del ISO** y la usa para generar **y** para jugar.
- El runtime/IOP parcheado vive en el **fork GPLv3** pinneado (`AncletoCEO/Ps2Recomp-of-etheria`); el
  binario distribuido queda cubierto por GPLv3 con su fuente en el fork. Este repo sigue **MIT**.

**Fidelidad (deuda declarada)**

- Se **aceptan** los overrides por dirección de `game_overrides.cpp` por ahora. La revisión de
  fidelidad (runtime sin parches puntuales) queda **explícitamente como deuda** para cuando el juego
  esté completo. Mismo tratamiento para el alcance funcional completo (gameplay/audio/cinemáticas/guardado).

**Método (reglas nuevas, no re-descubrir)**

- **Ningún build sin el gate del CSV**: `validate_csv.py` en verde (`0 SHADOW / 0 MIDFUNC / 0 MISSING`)
  antes de recompilar. Costó un build de ~5 h entenderlo. Se mueve a `game/` y corre en CI.
- **Los `missing-target` se clasifican por REFERENCIA REAL** (JAL/J, branch externo, tabla de punteros,
  vtable, pares LUI+ADDIU del registro de plugins) **y nunca por “estar después de un `jr $ra`”**.
  El split por epílogo solo (4.240 puntos) rompió el runtime (falsos positivos: ramas internas sobre
  early-returns, p.ej. `0x4ddab0`); con el filtro quedaron **1.134 reales**.
- **El CSV es un input de build**: se versiona, pero con **generador reproducible** en `game/`
  (`generate_functions_csv.py`) para que cada cambio sea un diff revisable sin depender de Ghidra.
- **Edit del runtime por el fork**: los cambios de runtime/IOP van al fork pinneado (commit + push) y el
  CI clona ese commit — no se regeneran parches. `game/patches/upstream/` queda **legacy**.

**Hechos (CI) del 2026-10-15**

- CI en verde: fork pinneado + FFmpeg dev (Linux) + Ninja (Windows) + `-msse4.1` +
  `g_tyosdTransferActive` movido a `iop_emulator.cpp`.
- Fix del CSV que **desbloqueó el render**: VRAM pasó de `0` a **475 KB** no-cero y `dma` de `3` a `1727`.
- Causa del **frame presentado negro** identificada: `FUN_006f2630` (handler `{id:0x16}` de la tabla
  `0x008a4cac`, que debe devolver `true`) se llamaba **182 veces por frame** sin slot ⇒ sin swap/fade.
  Fix aplicado (clamp de `FUN_006f25a0` + alta de `FUN_006f2630`); build en curso al escribir esto.

**Hechos del 2026-10-16 (sesión larga: fix del loader + cadena medida + refutaciones)**

- **FIX APLICADO Y VERIFICADO — semáforo de completado RPC.** El stub `sifBindRpcStub`
  (`game_overrides.cpp`, reemplazo de `sceSifBindRpc` en `0x004d7008`) no creaba el semáforo que el
  SDK nativo sí crea (`0x4d7084: jal CreateSema` → `0x4d7090: sw $v0, 0x8($s1)`). Se agregó
  `eeScheduler().createSemaphore(1, 1, 0, 0)` y se escribe el id en `clientPtr + 8`.
  **Efecto medido**: `hdr.sema_id` pasó de `0xffffffff` a ids reales (10/11/14/15) y **el loader del
  hilo 3 pasó de mudo a emitir RPC** (`client=0xa468f0 rpcNum=0x1` y `0x2`, con `[seed-a46940]`
  disparando). Antes: bindeaba y nunca llamaba.
  - **`init=1` es un SHIM, no lo que dice el SDK.** El SDK usa `init_count=0, max_count=1`
    (`0x4d7078`/`0x4d7088`). Con `init=0` el `WaitSema` bloquea de verdad y, como el runtime no
    señala el completado de los SIDs de BIOS (`0x80000592`, con `SWORD_IOP_BIOS_RPC` apagado), el
    Hilo 1 queda dormido y el juego **sale solo** (`Game thread returned. PC=0x74a428`).
    Volver a `init=0` cuando el runtime señale bien ese completado.

- **REFUTACIONES de la sesión (todas por medición, no por razonamiento):**
  1. **Sembrado de `0xA46940`** (fix del `end_func` `FUN_00628610`): apunta a `sid==0x30`, pero la
     ruta real llega con `sid=0x80000592` y `endFn=0`. Nunca se cumple.
  2. **Fallback `completionSemaphore = endParameter`** (RPC.cpp): **ELIMINADO**. `end_para` es un
     dato arbitrario para `end_func(void*)`, nunca un id. El guard `>0xFFFF` filtraba bien.
  3. **Semáforo 8 / semáforo 3 como bloqueantes**: no lo son. El 3 lo cubre `SWORD_SIF_SEMA=1`; el
     8/12 es el mutex del pad, que se toma y suelta en el mismo frame.
  4. **`gp+0x5EC` / `gp+0x62C` como "compuerta cerrada" y "anillo vacío"**: **valen 0 también en la
     consola.** El guard `0x6e4ce0: beqz → 0x6e4d84` toma el **camino rápido hacia el flip**, no lo
     saltea.
  5. **`gp+0x610` en cero (guard de overflow)**: **falso, vale `0xb15a80`** — el motor se inicializa
     bien (coincide con consola en `0x5DC`/`0x614`).
  6. **"El juego alcanzó el menú"**: falso. Los `gp740=0xc68c10`/`gp744=2` venían **solo de las
     corridas con savestate inyectado** (`[load-gs] VRAM inyectada`, `[id=1 st=5]`), no del flujo.

- **LECCIÓN DE MÉTODO (regla nueva):** **medir contra el savestate ANTES de encadenar deducciones.**
  En esta sesión se encadenaron y cayeron 6 hipótesis; cada corrección vino de un dato duro.

- **LECCIÓN TÉCNICA (regla nueva, invalida trabajo previo):** **todo `replaceFunction` sobre una
  dirección INTERNA de una función es INERTE.** El C++ recompilado cae de forma secuencial con `goto
  label_...` y **nunca consulta `m_functionTable` para saltos internos**. Prueba: `[triage-flow]`
  (`0x6e4e1c`, instrucción inline dentro de `FUN_006e4cc0`) nunca disparó… y el flip **sí corrió**
  (probado por `[dma:kick] … ra=0x6e4ebc`, posterior al bloque). **Revisar todos los `[triage-*]` del
  proyecto con esta lente.**

- **CADENA MEDIDA HOY (de causa a síntoma):** el motor gráfico entra (`[hit-6e4cc0]`,
  `[hit-6e4848]`), el setup de boot es correcto, y **el único kick de DMA sale vacío**
  (`qwc=0`, `madr=0`). Sin paquetes ⇒ `gp+0x61C` no avanza ⇒ el flip despacha un lote de tamaño 0.

- **COMPARACIÓN CONTRA SAVESTATE REAL (`work/teleport/eeMemory.bin`, menú):** coinciden
  `gp+0x74`/`gp+0x80` (loader), `gp+0x5DC`, `gp+0x610`, y **los tres callbacks del árbol de escena**
  (`0x00a888c8`/`cc`/`d0` = `0x5ea400`/`0x5ea5a0`/`0x6d5f90` ≡ `s7_110`/`114`/`118` del recomp).
  **Única diferencia: `gp+0x638`/`gp+0x63C`** — que son **cursor por frame** (`0x638` avanza de a 8
  bytes por descriptor) y valen 0 porque no hay nada que dibujar. El problema es el **productor**.

- ~~**RAÍZ ACOTADA (2026-10-16):** **nadie encola geometría.**~~ **(REFUTADO 2026-10-17: `FUN_006e58b8` sí
  se ejecuta y tiene call sites; ver §2026-10-17.)** `FUN_006e58b8` (enqueue de packets) no
  recibe llamadas de producción; el árbol de escena corre con la lista de entidades vacía.
  **`FUN_0075b0e0` (constructor de la fase del menú) no tiene ni un `jal` en todo el binario** —
  sólo aparece en la tabla de fases (`0x95f3d4: .word 0x0075B0E0`) y en la tabla de registro.

- **HALLAZGO NUEVO — la tabla de fases está registrada como CÓDIGO:** en
  `FUN_0095b2a8_0x95b2a8.cpp` la tabla se decodificó como instrucciones:
  `0x95f3c0: throw std::runtime_error("Unhandled SPECIAL instruction: 0x1 at 0x9593C0")` y lo mismo
  en `0x95f3d4`. Y `register_functions.cpp` tiene
  `g_ps2RecompiledFunctionTable[1211634] = FUN_0095b2a8_0x95b2a8; // 0x95f3d0`.
  Hay **dos saltos reales** a la tabla: `FUN_009470e0:2852 → 0x95F3D0` y `FUN_00953bc8:46643 →
  0x95F3D4` (desde `0x9593C8: beq $zero, $v1, +0x1802<<2`). **Si el juego toma esa rama, el recomp
  ejecuta datos como código y lanza excepción.** Pendiente de confirmar con hook en la entrada de
  `FUN_0095b2a8` (sin crash en el log de 35 s ⇒ o no se dispara o no se registra).

- **Herramientas perdidas:** `SWORD_WP_WRITER` (watchpoint de escritura) ya no existe en el fork;
  habría servido para vigilar `0xA286A8` (`gp+0x638`).

**Bucle de frame y por qué el juego no avanza del Frame 1 (2026-10-16, cierre de sesión)**

- **El bucle de frames existe y es infinito**: `FUN_0051fea0` (`0x51fea0-0x51ff20`). El bucle
  **arranca en `0x51FED4`** y contiene, en orden: `0x51FED4` → `51F370`, `51FEDC` → `513370`
  (input/pad), **`0x51FEE8` → `512AB0` (update de escena/fases)**, `51FEF0` → `512630`,
  `51FEF8` → `512140`, `51FF00` → `513320` (render submit), `51FF08` → `51FD90`,
  `51FF10` → `51F330`; y cierra con **`0x51FF18: b 0x51FED4`**.
  **Ojo**: el `goto label_51fed4` aparece al FINAL del label en el generado, pero la arista de
  retorno va después del `jal`, así que la llamada SÍ está dentro del bucle. (Error de lectura
  cometido y corregido el 2026-10-16.)
- **El runtime NO debe conducir el frame**: los juegos de PS2 corren su propio bucle infinito en el
  hilo 1; el scheduler sólo debe dejarlo correr y atender las interrupciones (VBlank/DMA). El CRT0
  que defiere `0x51FEA0` está bien.
- **El selector de fase se consulta UNA sola vez** (hooks sobre funciones completas, que sí
  funcionan): `FUN_0051f450` = 1, `FUN_0051f580` = 1 en 35 s. Es consecuencia de que el Frame 1 no
  cierra, no una causa.
- **REFUTADO (v64 de Gemini)**: que `FUN_0074a308` quede atrapada en el bucle de lista de `0x74a4f0`.
  Instrumentada entrada vs retorno: **ENTER 18 / RETURN 20** — entra y **vuelve siempre**. Las
  muestras del hilo 1 se reparten entre `0x74a4f0` (12), `0x74a428` (12) y `0x74a5b8` (2): son sus
  tres búsquedas secuenciales, o sea **recorre, no está clavada**.
- **MAPA del bucle de escena** (dato firme): `FUN_0074cab8` → **`FUN_0074ac48`**
  (`0x74ac48-0x74bb00`, 7400 líneas; **contiene el bucle `0x74B970`** en la línea 6668) →
  `FUN_0074a308` (18×). `FUN_0074cab8` **no tiene `jal` directo**: se entra por indirección.
- **Condición de salida del bucle de escena** (`0x74b980: bnez $s0, → 0x74B970`): recorre una lista
  con `$s0` como iterador, pasa `$a1 = $s0` y llama un **método virtual (`jalr`)** por iteración;
  sale cuando `$s0 == 0` y entonces llama a `FUN_006d640`.
- **PENDIENTE (próximo paso)**: instrumentar los **targets de las llamadas indirectas**
  (`GuestBranchKind::IndirectCall`) en el rango `0x74b970-0x74b980`. Si el iterador avanza por nodos
  distintos la lista está sana y el frame se frena por otra razón; si repite el mismo nodo, **hay un
  ciclo en la lista**.
- **Técnica que SÍ funciona (regla)**: hook sobre **función completa** registrando **entrada y
  retorno** (patrón `lookupFunction` + `replaceFunction` con log antes y después de delegar). Es la
  única forma de probar "se colgó acá" sin tropezar con la regla del punto 7 de los caminos muertos.

**2026-10-17 — REFUTADO: "`FUN_00512630` retorna con el `$ra` equivocado" (la causa raíz de `work/START_NEXT_SESSION.md`)**

> Leído el artefacto antes de afirmar (regla 1). No hay nada que arreglar en el generado/CSV por este lado,
> y el dato que sostenía la hipótesis es un **artefacto del hook**.

- **El frame de `FUN_00512630` está balanceado y es fiel al ELF.** Generado
  (`work/generated/FUN_00512630_0x512630.cpp`, 2346 líneas) vs. ELF (`0x512630..0x512aa0`, desensamblado):
  - prólogo `0x512630: addiu $sp,$sp,-0x80` + `0x512634: sd $ra,0x60($sp)`;
  - epílogo `0x512a74: ld $ra,0x60($sp)` … `0x512a90: jr $ra` con delay slot `0x512a94: addiu $sp,$sp,0x80`;
  - **un solo prólogo y un solo epílogo**: el único otro `addiu $sp` del archivo es justamente el del
    delay slot del `jr` (grep), y la única escritura dentro del frame es `sw $zero,0x7C($sp)` (slot
    distinto del `$ra` en `0x60`). ⇒ ninguna ruta ajusta `$sp` sin revertirlo, y el slot del `$ra` no se pisa.
- **`raOut=0x5129e4` es artefacto del wrapper, no un `$ra` corrupto.** El hook `[frame-loop]`
  (`game_overrides.cpp`≈4407) mide `ctx->r[31]` **después** de `ORIG(...)` **sin mirar `ctx->pc`**. El
  generado hace `return` desde el cuerpo por dos vías normales:
  1. aristas hacia atrás con `eeCheckpointDue()` (`0x512a6c → 0x512674`);
  2. `dispatchGuestBranch` devuelve `false` en el checkpoint previo a una llamada
     (`ps2_runtime.cpp:1440`), y el llamador hace `return`.
  En ambas, el wrapper loguea "RETURN" de una función **que no terminó**, y `$ra` en ese instante es sólo
  el retorno del último `jalr` interno: `0x5129e4` = `0x5129dc + 8`, el `jalr $t9` de la vtable en
  `0x5129dc` (target: la hoja `FUN_00591b90`, `0x591b90..0x591bd0`, un setter de float con clamp).
  - **Evidencia directa**: muestreo del hilo 1 (`[triage-vbprof]`) → `pc=0x591b90 ra=0x5129e4`
    (vb≈1741): el estado "parked en el dispatch a la hoja", exactamente lo que predice un yield.
  - **Instrumentación corregida** (local, sin commitear en el fork): el wrapper loguea
    `pcIn/pcOut/spIn/spOut/dsp` y clasifica `RETURN` sólo si `pcOut == retorno esperado`
    (`0x51fef8/0x51ff00/0x51ff08/0x51ff10/0x51ff18`); si no, `YIELD`.
  - **Prueba definitiva** (rebuild + corrida de 120 s, 2026-10-17):
    ```
    [frame-loop] f512630 ENTER n=1 pcIn=0x512630 raIn=0x51fef8 spIn=0x1fedee0
    [frame-loop] f512630 YIELD n=1 yields=1 pcOut=0x591b90 raOut=0x5129e4 spOut=0x1fede60 dsp=0xffffff80
    ```
    `pcOut=0x591b90` = **la entrada de la hoja** (el dispatch que quedó pendiente), y `dsp=-0x80` = el
    frame del prólogo **todavía asignado** (epílogo no ejecutado). No hubo retorno: hubo yield.
- **Caveat de método (nuevo): el trace no sirve para conteos chicos.** `SWORD_TRACE_BRANCH` abre su
  `static std::ofstream` en el primer match y **nunca lo flushea**; `timeout` mata con SIGTERM ⇒ un rango
  con pocas transferencias deja `/tmp/sword_branch.log` en **0 bytes aunque sí haya matcheado** (el
  archivo existe). No concluir "no pasó nada" de un log vacío: usar un rango ancho (miles de líneas) o
  agregar flush.

**Medición 2026-10-17 (180 s, `SWORD_SIF_SEMA=1 timeout 180`, build 2026-10-17 00:45)**

- `[frame1] FUN_00512ab0` ENTER/RETURN **n=1** (t≈0,5 s) y `[frame-loop] f512630` ENTER/YIELD **n=1**
  (t≈25 s, vb≈1501) ⇒ **una sola iteración del bucle de frame en 180 s**; `0x512140/0x513320/0x51fd90/0x51f330`
  nunca se alcanzan. (El hook loguea `n<=4`, así que para `n=1` el conteo es exacto, no rate-limitado.)
- **Pero el juego SÍ avanza por otro camino**: el hook de `0x50f750` ("task/scene update") corre
  **≥1200 veces** en 180 s (dumps `frame_1..frame_1200.bmp` de su propio contador) ⇒ **~5-7 ticks/s**
  (~9× más lento que 60 fps), no "Frame 1 congelado".
- **Quién itera**: `FUN_00512630` es un **bucle** (`0x512674..0x512a6c`, condición `lw $v1,0x8($s1)`) que
  llama `FUN_00510f20` (`0x512968`) → **`0x50f750`**. La única invocación de `0x512630` itera cientos de
  veces: el bucle de frame espera a que ese lazo de fase termine.
- **Trayectoria del hilo 1** (vbprof): `0x74a428/0x74a4f0` (lazo de `FUN_0074a308`, yields en la arista
  trasera) de vb 61 a 1621 (≈27 s) → `0x547b60`/`0x4f5074` → **`0x6279d0` con `ra=0x0`** (vb 1741) →
  desde vb≈1981 `pc=0x0` con excursiones a `0x6e58d4` (`FUN_006e58b8`) y `0x51a758`.
  - `0x6279d0` es el **callback RPC invocado con `$ra=0` por diseño** (`RPC.cpp:777`
    `SET_GPR_U32(&callback.context, 31, 0u)` + `invocationStackTop()`), y `pc=0` es la marca de
    "invocación terminada" del scheduler. Revisar si ese `pc=0` del hilo 1 es legítimo.
- **`FUN_006e58b8` (el *enqueue* de packets) SÍ se ejecuta** y tiene call sites reales
  (`0x6e7ca0`, `0x6e7d44`, `0x6e7da4`, `0x6f28c0`, `0x638db0`) ⇒ revisar el "sin llamadas de producción"
  del 2026-10-16.
- `gp+0x638 == gp+0x63C == 0xa96688` (**no 0**) ⇒ el cursor de la cola de packets no está vacío;
  `gp+0x740`/`gp+0x744` siguen en 0 (fase menú nunca registrada).
- **VRAM**: `vramNonZero` pasa de 0 a **368801/475456** recién al final (`[gs:present] #730..#750`) ⇒ el
  render sí sube datos. El frame **presentado** sigue negro (`[gs:diag] crt1 (fbp=0) rgbNZ=0 aNZ=262144`).
- **`[dma:kick]` está rate-limitado a n≤25** y las 25 salen `qwc=0` ⇒ **no se puede concluir** que los
  kicks posteriores estén vacíos. Des-rate-limitarlo antes de afirmarlo.

**Próximo paso corregido** (NO revisar el balance de `$sp`; NO tocar el CSV por esto)
> Los 4 puntos quedaron ejecutados el mismo 2026-10-17: el 1 confirmó el `YIELD`; el 2 se midió
> (≈9 ticks/s, ver segunda ronda); el 3 sigue abierto; el 4 se hizo (y refutó el "kick vacío").

1. Rebuild con el wrapper corregido y leer `RETURN` vs `YIELD` de las cinco llamadas del bucle de frame.
2. ~~Por qué ~1,7 ticks/s~~ medir `eeCycle` por tick (dio ≈9 ticks/s + patrón a ráfagas).
3. El `pc=0` del hilo 1: decidir si es la convención del scheduler (legítimo) o el flujo real perdido
   (contaminación del contexto del callback RPC sobre el del hilo 1).
4. ~~Des-rate-limitar `[dma:kick]`~~ hecho: los `qwc=0` eran modo cadena (ver segunda ronda).

**2026-10-17 (segunda ronda) — el "kick VIF1 vacío" también era artefacto; y el tick corre a ~9/s**

- **Instrumentación agregada** (fork local, branch `diag-loader-rpc`): `[dma:kick]` sin rate-limit
  (primer tramo + cada kick con datos + resumen cada 600, con `withData=`), `[tick-prof]` en el hook de
  `0x50f750` (`eeCycle`/`dCycle`/`cycPerTick`/`vsync`/`dVsync` + estado de hilos), `vsync=` en
  `[rpc-call]`/`[rpc-callback]` y **auditoría `[dma-reg]`** de las escrituras a los registros de canal
  DMA (`0x10008000-0x1000AFFF`, dedup por valor).
- **`[dma:kick]`: 395 001 kicks en 180 s, `withData=0` en todos** — pero **eso NO significa que no se
  transfiera nada**: el juego NO usa MADR/QWC. `[dma-reg]` muestra que escribe **`TADR`
  (`0x10009030`)** (alternando `0xa96700`/`0xb15b00`) y `CHCR=0x145`; **MADR jamás se escribe**.
  `0x145` ⇒ `mode = (chcr>>2)&3 == 1` ⇒ **modo cadena**: el runtime toma el camino de TADR
  (`ps2_memory.cpp:1600+`, que además implementa `CHCR.TTE` bit 6 = 0x40 para canales VIF). ⇒
  el probe de `madr/qwc` en el kick es **el tercer artefacto de medición de la sesión** (después del
  wrapper del frame-loop y del flush del trace). **NO concluir "no hay geometría" de `qwc=0`.**
- **La geometría SÍ fluye**: `[vif1-chain]` con datos reales (`qw=177`, `qw=4`, `qw=1`…, p.ej.
  `src=0xa96710 qw=177 data=8006 10000000 e 0 44 0 42 0 …`) y **`[gs:kick] drawing=1 prim=6/5
  vtxCount=1..3 pc=0x6e4468`** (94 en 60 s) ⇒ el GS recibe prims desde el sitio de draw del juego.
- **Perfil del tick (180 s)**: `[tick-prof]` da **~9 ticks/s** (1610 ticks) contra **58 VBlank/s**;
  `cycPerTick` dentro del task update es **chico** (0,5-1 M ciclos) y el reloj EE está **anclado a
  tiempo real** (`294 MHz` ⇒ `eeCycle=5,17e10` en 180 s ✔). El patrón es **a ráfagas**: 10 ticks dentro
  de 1 VBlank y después huecos de **~340-360 VBlank (~5,8 s)**. O sea: el hilo 1 está **ocioso (`pc=0`)**
  la mayor parte del tiempo y despierta en ráfagas; cuando corre un tick aparece en `SignalSema`
  (`pc=0x4d32c0 ra=0x51eeb4`).
- **VRAM sí tiene contenido** (`vramNonZero=368801/475456`) pero el **frame presentado** sigue negro:
  `[gs:diag] crt1 (fbp=0) rgbNZ=0 aNZ=131233` ⇒ la página **presentada** es la del clear/fade (alpha
  sin RGB) y el contenido dibujado vive en **otra página**. `gp+0x740`/`0x744` siguen en 0 (fase menú
  nunca registrada).

**Próximo paso (tercera versión)**

1. **La pantalla**: el bloqueador ya no es "falta geometría" (llega al GS) sino **qué página se
   presenta**. Comparar `DISPFB`/`DISPLAY`/`PMODE` del recomp contra el savestate de la misma fase y
   ver si el juego llega a flipear (`[gs:present]` da `dispfb1=0x1400`/`dispfb2=0x80000001000`), y si el
   camino de presentación del runtime respeta `DISPFB` o presenta una página fija.
2. **Por qué el tick es a ráfagas y el hilo 1 está ocioso**: qué espera en los huecos de ~5,8 s
   (¿thread 3 en `0x628948` + RPC `sid=0x573`?). Medir con el `vsync=` que ahora tienen las trazas RPC.
3. Revisar (con la lente de esta sesión) **todo dato de log que se haya usado como síntoma**:
   `madr/qwc` en el kick, "RETURN" del wrapper, y logs vacíos por falta de flush.

---

## Artefactos de medición (2026-10-17) — logs que MINTIERON y por qué

> Costaron varias hipótesis falsas (propias y de sesiones previas). **Antes de concluir de un log,
> verificar el instrumento**: qué mide exactamente, cuándo se emite y qué convención tiene el generado.

1. **`[frame-loop] … RETURN n=1 raOut=0x5129e4`** ⇒ en realidad era un **YIELD**. El wrapper leía
   `ctx->r[31]` después de `ORIG(...)` sin mirar `ctx->pc`; el generado hace `return` desde el cuerpo
   (aristas hacia atrás con `eeCheckpointDue`, y `dispatchGuestBranch` → `false` en el checkpoint previo a
   una llamada, `ps2_runtime.cpp:1440`). En un yield, `$ra` es sólo el retorno del último `jalr` interno.
   ⇒ **Corregido**: el wrapper loguea `pcIn/pcOut/spIn/spOut/dsp` y sólo dice `RETURN` si
   `pcOut == retorno esperado`. Ese log falso sostuvo la "causa raíz" del `$ra` equivocado.
2. **`/tmp/sword_branch.log` vacío** ⇒ en realidad **no hubo flush**. El `static std::ofstream` del
   `SWORD_TRACE_BRANCH` nunca se flushea y `timeout` mata con SIGTERM: con pocas transferencias quedan 0
   bytes *aunque haya matcheado* (el archivo existe, se creó al construirse el stream). ⇒ usar un rango
   ancho (miles de líneas) o agregar flush. **No concluir "no pasó" de un log vacío.**
3. **`[dma:kick] … madr=0x0 qwc=0x0`** ⇒ en realidad es **modo cadena**: el juego escribe `TADR`
   (`0x10009030`) + `CHCR=0x145` (`mode=(chcr>>2)&3 == 1`) y **nunca MADR/QWC**, que en ese modo no se
   usan. El runtime camina la cadena desde TADR (`ps2_memory.cpp:1600+`). ⇒ el `[dma-reg]` (auditoría de
   escrituras a los registros de canal DMA, dedup por valor) es la fuente correcta. **`qwc=0` NO significa
   "no transfiere nada"**: `[vif1-chain]` y `[gs:kick] drawing=1 … pc=0x6e4468` muestran data llegando al GS.
4. **Logs rate-limitados** (`n<=25`, `%500`, `%600`): un corte no es una distribución. `[dma:kick]` estuvo
   así y de ahí salió el "2 kicks vacíos" del 2026-10-16. Ahora resume con `withData=`.
5. **Snapshots del scheduler (`[triage-vbprof]`, `[tick-prof]`)**: el `pc` publicado para un hilo es el de
   su **último safe point**, no el que tiene vivo el hilo en ese instante; y para invocaciones del scheduler
   (`pc=0` = "invocación terminada", ver `RPC.cpp:777` `SET_GPR_U32(...,31,0)`) publican ese 0. No leer
   `pc=0` como "el hilo murió" sin más.
6. **`Store32` NO ve la RAM normal**: el generado escribe RAM con `WRITE32(...)` → `isSpecialAddress()==false`
   → **`FAST_WRITE32`**, que no pasa por `PS2Runtime::Store32`. Un watchpoint puesto en `Store32` es
   **ciego** para cualquier dirección normal (p.ej. heap `0xA9xxxx`); sólo ve registros/IO. Ya estaba
   advertido en HANDOFF §6 ("watchpoint de stores en el generado") y se volvió a pisar: el `[phase-flag]`
   de esta sesión dio 0 escrituras por esto. Para RAM normal hace falta **mprotect+SIGSEGV**
   (el viejo `SWORD_WP_WRITER`, hoy ausente) o instrumentar el **generado** de la función dueña.

---

## 2026-10-17 (tercera ronda) — la fase: el lazo de `FUN_00512630` no tiene salida

- **`[gs:present]` ahora trae histograma de VRAM y el fbp del contexto**: el contenido está en los
  **primeros 2 MB** (buckets 0-7 de 256 KB con ~25% de bytes ≠ 0) y el patrón de 25% = **sólo alpha**
  (el clear/fade `0x7F000000`). El **contexto de dibujo dice `fbp=80`** (0x280000) y esa región está
  **vacía** (bucket 10 = 0); la **presentación** lee `DISPFB1` = `fbp=0` (el default del runtime,
  `ps2_memory.cpp:578`), que es justo la página con el fade.
- **Los prims que llegan al GS vienen con RGBAQ = 0** (`[gs:gif] tagHi=0x412 regs=<ST> 0 <XYZ> <ST>`):
  el juego está pintando **quads negros** (fade), no contenido de escena. Consistente con
  `[gs:diag] crt1 (fbp=0) rgbNZ=0 aNZ` creciendo. ⇒ el pipeline está bien; **la escena no se produce**.
- **Cómo entra el tick (`ra` del llamador)**: alterna **`0x51148c`** (`entry_0051147c` → `0x50f750`, el
  callback de escena) y **`0x510f48`** (`FUN_00510f20` → `0x50f750`, que es la llamada **dentro del lazo
  de `FUN_00512630`**, `0x512968`). O sea: el tick NO es una invocación del scheduler; es el código del juego.
- **`[gs-cb]` = 0**: el juego **nunca registra callback de VSync** (`m_gsVsyncCallback == 0`), así que el
  runtime no encola nada por VBlank; el pacing del juego no viene de ahí.
- **El lazo de fase casi no itera** (instrumentando el generado de `FUN_00512630`):
  - `[phase-loop] n=1 flag=0x0 s1=0xa93720 zero=1 nz=0` — **una sola lectura** del flag `*(s1+8)` en 75 s
    (el contador no llegó a 100k, que era el siguiente log). El flag **nunca** vale ≠ 0.
  - `[phase-flag-set]` = 0: la escritura `0x51297c: sw $v0(=1), 0x8($s1)` **nunca se ejecuta**.
    **⚠️ Corrección de un paso en falso propio**: primero escribí acá "0x512978/0x51297c es código muerto
    (tras el `b 0x512980` de 0x512970)" — **es falso**: el bloque es alcanzable desde
    **`0x5127ac: bnez $v0, → 0x512978`** (verificado en el ELF y en el generado, `goto label_512978`).
    Lección: el `b` incondicional no implica inalcanzable; hay que buscar *todas* las ramas al target.
  - Con `flag == 0` la arista `0x512a6c: beqz $v1 → 0x512674` **vuelve al lazo**: el lazo no puede cerrar
    por sí mismo. El hilo 1 queda dentro del **cuerpo** (los 9 ticks/s salen de ahí, vía
    `0x510f20 → 0x51147c → 0x50f750`), y el bucle de frame (`0x51fea0`) no itera → **la fase no avanza
    al menú** (`gp740/744 = 0`).
- **Objeto de fase**: `a0` de `FUN_00512630` = `0xa93720` (el que devuelve `0x513370` en el bucle de
  frame). Su flag en `+8` es la condición de salida del lazo.
- **Condición de salida, medida** (`[tick-prof]` ahora loguea `phP/ph0/phC`):
  `FUN_00510EF0` es un **getter**: `return (*(obj+0) != 0) ? 0 : *(obj+0xC)` con `obj = *(gp-0x324)`;
  ese valor ≠ 0 es lo que lleva a `0x512978` (flag = 1 → sale el lazo).
  Medido en 75 s: **`phP = 0xc61890`** (¡región de escena `0xC6xxxx`, la misma familia que el
  `gp+0x740 = 0x00C68C10` del estado de menú real!), **`ph0 = 1 → 2 → 3`** (sube y nunca vuelve a 0) y
  **`phC = 0` siempre**. ⇒ el lazo **no puede salir**: falta que alguien **limpie `*(0xc61890)`** (o ponga
  `+0xC`) — el juego está esperando esa señal y no llega.

**2026-10-17 (cuarta ronda) — el freno está en el PAD (barrera 2), con la estructura confirmada contra los `.p2s`**

- **La comparación contra los savestates reales (v65 de Gemini, con el corrimiento de heap `+0x150`)
  reencuadra el lazo**: en el **menú real** `*(s1+8)` sigue siendo **0** y `*(mgr+0)` vale **4** ⇒
  `FUN_00512630` **no tiene que salir**: el menú es la **4ª tarea**, que spawnea Task#1 al cambiar su handler
  de `FUN_00500570` a `FUN_00500490`. Mi lectura previa ("la fase termina cuando el count llega a 0") era
  **incorrecta**; el count *sube* (3 → 4). Respuesta guardada en `work/gemini/ans_gemini_v65.md`.
- **Cadena de tareas verificada en nuestro run** (`[task]`, leyendo RAM desde el hook de `0x50f750`):
  `root=0xcb2710` con `h20=0x5006d0` (init de Task#1, **igual dirección que en PCSX2**) → `h20=0x500570`
  → count 1→2→3 ✓. El objeto de fase es el mismo que ve `FUN_00512630` (`mgr=0xc61890`).
- **Barrera 1 (archivo `0x07010000`): se PASA** (`ldSt` 2 → 3 a los ~30 s) ⇒ el freno no es el loader.
- **Barrera 2 (pad): acá se clava** — `root sub=2` (esperando `FUN_0051c680(0)`) desde ~f=450 hasta el final.
  - `[pad-e1a0] port=0 state=3` (nunca cambia) y `[pad-state] port=0 ret=0`.
  - **⚠️ Corrección a la semántica del v65**: leído el generado, `FUN_0051c680` devuelve **0 si el estado
    del pad es 0 o 3**, 1 si es 4 y 2 si es 1/2/5/6/7/8; el caller espera `!= 0`. (En el real port0 = 6 →
    pasa.) Nuestro estado es **3**.
- **`[pad-getstate]` = 0 llamadas**: el juego **no** usa el stub HLE `scePadGetState` (que devolvería
  `kPadStateStable`). Su estado lo mantiene el **libpad recompilado**, que habla por SIF RPC con
  **PADMAN.IRX dentro del IOP emulado** ⇒ el estado clavado es de la **capa de plataforma**, no del código
  del juego.
- **El runtime NO tiene dispositivo SIO2**: `grep` de los registros SIO2 (`0x1F8082xx`) y de `sio2` en
  `ps2xIOP`/`ps2xRuntime` no encuentra manejo alguno (sólo el *nombre* del módulo en
  `iop_module_manager.cpp`). **PCSX2 sí lo tiene** (fuente local en `tools/ps2emu/pcsx2/SIO/Pad/`:
  `Pad.cpp`, `PadDualshock2.cpp`, …) ⇒ es la referencia para implementar el dispositivo y que padman
  complete sus comandos (estado del pad → 6 = Stable).

**2026-10-17 (quinta ronda) — verificado: el SIO2 del IOP es memoria muerta (por eso el pad no llega a "ready")**

- (a) **`FRAME_1` decode: correcto** (duda cerrada con PCSX2 `GIFRegFRAME`): el runtime hace
  `fbp = value & 0x1FF`, **`fbw = (value >> 16) & 0x3F`**, `psm = (value >> 24) & 0x3F`
  (`gs_frontend.cpp:1362-1365`) ⇒ coincide con el hardware. Explica el `[gs:present] ctx=80/8/0`
  (página 80 = 0x280000, 512 px, PSMCT32). `decodeDisplayFrame` (bits 0-8/9-14/15-19) es el de `DISPFB` ✓.
- (b) **`sio2man` y `padman` SÍ se cargan y arrancan** en el IOP emulado:
  `[iop-preload] SIO2MAN.IRX moduleId=1 start=0` / `PADMAN.IRX moduleId=2 start=0` +
  `[ps2xIOP] [IOP] loaded IRX id=2 entry=0x14304 base=0x11000`. Y el HLE del EE **sí** intercepta
  `scePadInit (0x4e9aa8)` y `scePadPortOpen (0x4e9eb0) port=0/1`.
- **(c) La causa**: los registros SIO2 (`0x1F8082xx`) **no están implementados** en el IOP:
  `IopMemory::writeHardware32` guarda el valor en `m_hardware[address]` (sin dispositivo detrás) y
  `readHardware32` devuelve **0** (`default: return 0u`, `emulator/core/iop_memory.cpp:253/283`).
  Los únicos imports implementados son cdvd/heaplib/intrman/ioman/loadcore/stdio/sysclib/sysmem/
  timrman/vblank ⇒ **no hay pad ni sio2**. ⇒ padman escribe sus comandos y lee ceros para siempre:
  el estado del pad queda en **3** y la barrera 2 nunca pasa.
- **No hay binds RPC de pad/sio2** en el log (sólo `0x80000592` cdvd, `0x80000006`, `0x573`, `0x30`), y
  `[pad-getstate]` (el stub HLE de `scePadGetState`) = **0 llamadas**: la máquina de estados del pad es la
  del juego (0x51xxxx + libpad recompilado 0x4E9xxx/0x4EA2B8), y su fuente es **padman en el IOP**.

**2026-10-17 (sexta ronda) — FIX REAL: la tabla de stubs de libpad estaba CORRIDA (una función) ⇒ la fase avanza al menú**

- **Diagnóstico (v66 de Gemini, verificado contra el generado)**: la tabla de `replaceFunction` de libpad
  (`game_overrides.cpp`≈4084-4155) estaba **desplazada una función** desde `0x4ea2b8`:
  - `0x004ea2b8` **es `scePadGetState`** (`FUN_004ea2b8` lee `lbu 0x70($s0)` = state y `lbu 0x71($s0)` =
    reqState) pero estaba hookeada como `padSetMainModeStub` ⇒ devolvía **1 = PAD_STATE_FINDPAD** y el juego
    guardaba ese 1 en `*(port+0x8C)`.
  - `0x004ea460` **es `scePadGetReqState`** (`lbu 0x71($v0)`) pero estaba hookeada como `padGetStateStub`
    (por eso `[pad-getstate]` nunca disparó: GetReqState sólo se consulta con state 6/2).
- **Fix aplicado** (fork, branch `diag-loader-rpc`): remapeo completo —
  `0x4ea2b8`→GetState, `0x4ea3b8`→SetReqState, `0x4ea460`→GetReqState (0 = COMPLETE),
  `0x4ea4e8`→InfoAct, `0x4ea608`→InfoComb, `0x4ea728`→InfoMode (**sin** el hack `res==0→7`, que corrompía
  term=3), `0x4ea860`→SetMainMode, `0x4ea918`→SetActDirect, `0x4ea9d8`→SetActAlign,
  `0x4eaab0`→GetButtonMask, `0x4eab68`→SetButtonInfo, `0x4eac18`→InfoPressMode, `0x4eac78`→EnterPressMode,
  `0x4eacd0`→ExitPressMode; y `scePadInfoMode` (HLE) ahora reporta la tabla de modos
  `{4 = digital, 7 = DS2}` con `PAD_MODECUROFFS` = offset del modo actual.
- **Efecto medido (run de 75 s)**: `[pad-e1a0] port=0 state=4` y `port=1 state=4` (**READY**, era 3) →
  `[pad-state] ret=1` en **ambos** puertos → Task#1 sale del substep 2 y **para f≈170 su handler ya es
  `FUN_00500490`**; `*(mgr+0)` = **4** (`ph0=0x4`, igual que el `videoformat_menu.p2s`) y **`gp+0x740`
  pasa de 0 a `0xc674a0`** (puntero del área de escena, como el `0x00C68C10` del menú real).
  Se creó **Task#4** (`t3=0xe21590`, la región `0xE2xxxx` donde Gemini ubicó la tarea del menú).
- **Nueva barrera (la siguiente)**: Task#1 queda en **`h20=0x500490 sub=1`** (240 s sin moverse) y el
  contexto de dibujo pasó a `ctx=0/8/0` (página 0, la misma que se presenta ⇒ el draw ahora apunta a la
  pantalla), con **VRAM borrada** (`vramNonZero` 527407 → 3119 → 0; `[gs:diag] aNZ=0`). La pantalla sigue
  negra: la fase del menú arrancó **limpiando** y todavía no dibuja (falta cargar sus assets).
  El loader sigue mostrando el nodo `id=0x07010000` en `state=3`.

**2026-10-17 (séptima ronda) — el estado del juego YA ES el del menú real; lo que falta son los assets del menú**

- ⚠️ **Corrección de la ronda anterior**: dije "sexta barrera: `FUN_00500490 sub=1`". **Falso**: medido
  contra el savestate real (`work/teleport/eeMemory.bin` = estado de menú), Task#1 del **menú real** está
  en `h20=0x500490`, **`+0x38 = 1`**, `count=4` ⇒ **nuestro estado coincide exactamente con el del menú**.
  `FUN_00500490` no lee el substep: el gate lo hace con el getter `FUN_005105F0` = `return *(task+0x38)`
  (verificado: `jr $ra` + delay slot `lw $v0, 0x38($a0)`), y sólo con `== 2` instala otro handler
  (`0x004FFBE0`) — camino que el real **tampoco** toma (`[menu-gate] ret` va 0 → 1 y se queda en 1 ✓).
- **La Task#4 (menú) es idéntica al real**: real `t4+0x00=0x51, +0x08=2, +0x10=0x28, +0x20=0x0083d990,
  +0x34=4, +0x38=0xa`; nuestro `t3st=2 t3sub=10` (mismos `+0x08`/`+0x38`) ✓ y `count=4` ✓.
- **El fix del pad funciona como se esperaba**: `[pad-getstate] port=0/1 open=1 state=5/6` alternando
  (¡el HLE ahora sí se llama: 400+ veces!) ⇒ la FSM del juego avanza y llegó al handler del menú.
- **Lo único que difiere del menú real**: **la lista del loader**. En el real
  (`*(gp-0x348)`, sentinel embebido en `loader+0x68`) hay **6 nodos** con los assets del menú en `state=3`:
  `0x06051601, 0x06054801, 0x06020800, 0x06020000, 0x06054001, 0x07010000` (+ el sentinel `id=0 st=4`).
  En nuestro run sólo aparece `id=0x07010000 st=3` y el resto de la lista no tiene nodos válidos
  ⇒ **los 5 assets del menú nunca se encolaron** ⇒ la Task#4 del menú no tiene con qué dibujar ⇒ negro.
  (Coherente: VRAM quedó borrada al entrar la fase y no se volvió a escribir: `[gs:diag] aNZ=0`.)

**2026-10-17 (octava ronda) — los assets del menú SÍ se encolan, pero uno queda en `state=2`**

- **Corrección de la séptima ronda**: dije "los 5 assets del menú nunca se encolaron". **Falso** (mi walk
  estaba mal: imprimía el *loader* como si fuera el head). Instrumentado el enqueue real
  (`FUN_004f9f50`, `a1` = id), el juego pide **los 6 ids exactos, una vez cada uno**:
  ```
  id=0x7010000 ra=0x500600   id=0x6054001 ra=0x83cfe4   id=0x6020000 ra=0x7f820c
  id=0x6020800 ra=0x83dcb8   id=0x6054801 ra=0x83dcc8   id=0x6051601 ra=0x83dcd8
  ```
  (el primero desde la barrera 1 `FUN_00500570`; los otros desde la tarea del menú `0x83xxxx`/`0x7fxxxx`).
- **El freno real**: el head de la lista (`loader = *(gp-0x348)`; sentinel embebido en `loader+0x68`,
  `next` del sentinel en `loader+0x68`) es **`id=0x06020000` con `state=2`** — en el savestate de menú ese
  asset está en **`state=3`**. ⇒ **un asset del menú quedó a medio cargar** y la tarea del menú no tiene con
  qué dibujar (VRAM sube a 527407 pero `[gs:diag] crt1 rgbNZ=0`: lo que hay son los quads de fade).
- Nota de método: el walk anterior leía `sentinel = (gp-0x348) + 0x68` (dirección del **puntero**) en vez de
  `loader + 0x68` (valor) ⇒ 0 nodos. Ya corregido.

**2026-10-17 (novena ronda) — el grafo del menú está COMPLETO y coincide con el real; no se dibuja nada**

- **Corrección (otra vez mía)**: lo de "asset en `state=2`" era **timing**: con el walk corregido (el
  `next` del nodo está en **+4**, no en +0 — `+0` es `prev`; el sentinel vive en `loader+0x68` y su head en
  `+0x6C`) los **6 assets están en `st=3` con `md=3`** (`0x07010000, 0x06054001, 0x06020000, 0x06020800,
  0x06054801, 0x06051601`), igual que en el savestate. Los heads de recursos del loader también están
  poblados (`res10=0xe89320`, `res34=0xe7ce60`, `res58=0xe21760`).
- **La Task#4 del menú está construida y registrada** (medido en `*(*(mgr+4)+8)` = 0xe21590):
  `h20=0x83d990 sub=10` (**idéntico al real**), y con lo que pidió el v67:
  **`+0x5C = 0xe84f60`** (draw tree), **`+0x7C = 0xe89a10`** (controlador de sprites),
  **`C0 = 0xe81c30`** (recurso de layout `0x15616100`), **`1B4 = 0xe81bc0`** (textura `0x65216110`),
  `+0x84 = 0xe7c750` (array de 9), `+0x8C` (capa 2D). Es la **misma estructura que el menú real**
  (`+5C=0xE27440`, `$s0=0xE27260`, `C0=0xE27420`, `1B4=0xE26E40`). (Nota: `*(Task#1+0x80)` es 0; el
  puntero a Task#4 sale de `*(mgr+4)`.)
- **Y sin embargo no se dibuja NADA**: `[gs:diag] crt1 rgbNZ=0 aNZ=0` y `vramNonZero=3119` (ni los quads
  de fade que aparecían antes) ⇒ el pase de dibujo del menú **no emite paquetes al GS**.
  ⇒ **El bloqueo ya no está en la lógica de tareas ni en la carga**: está en el **render** (quién recorre el
  draw tree `+0x5C` / la capa 2D / el fade-in `*(gp-0x33C)` vtable+0x5C) o en la presentación.

**2026-10-17 (décima ronda) — el pipeline 2D corre hasta el encolado; el hueco es la etapa 3 (flush)**

- **v68 de Gemini (guardado en `work/gemini/msg_gemini_Responsev68.md`)**: el planificador por frame es
  `FUN_00511430 → FUN_0050f750(task)` (handler `+0x20` y después traversal **incondicional** de
  `*(task+0x5C)` vía `FUN_0050d8d0`); la submission 2D es `$s0->vtbl[+0x154]` = **`FUN_00506af0`** →
  `FUN_00743568(*($s0+0xC0))` → los **16 hijos** del layout (`Child[i]->+0x48` = `FUN_00743268`) →
  `FUN_00702890(queue, child, 1)`; y el flush = `FUN_00754398` / `FUN_0075ccc8` / `FUN_0070b868`.
- **Medido con traces (`SWORD_TRACE_BRANCH`, sin rebuild)**:
  - Rango UI (`0x500000-0x520000`): `FUN_00506a70` ×189, **`FUN_00506af0` ×189**, `FUN_0050d8d0` ×413,
    `FUN_00511430` ×240, `FUN_0050f750` ×938, y **`tgt=0x743568`/`0x743268` ×189** ⇒ el *dispatch* de dibujo
    2D, el traversal y el emit por hijo **sí corren** (y con eso, el guard `*($gp-0x34C) != 0` **pasa**).
  - Rango flush (`0x700000-0x760000`): `FUN_00743568` ×102, `FUN_00743268` ×394, `FUN_00702890` ×394 y
    **`FUN_006e58b8` (el enqueue de geometría) ×394** ✓✓ — o sea **los sprites del menú SÍ se encolan**
    (~6,6/s = al ritmo del tick de ~9/s, no por VBlank). En cambio **`FUN_00754398` = 0 y
    `FUN_0070b868` = 0** llamadas, y `FUN_0075ccc8` sólo **4** ⇒ **la etapa 3 (flush/emisión) no corre**.
- **Dato del savestate**: `*(gp-0x34C)` en el menú real es **`0x00cb50d0`** (un **puntero**, no un flag 0/1)
  ⇒ el guard es "puntero ≠ 0" y en nuestro run pasa (el traversal llegó a `FUN_00743568` ×189).
- Consecuencia: el bloqueo ya no es "no hay geometría" ni "no hay productor": **la cola 2D se llena pero no
  se vacía al GS**. Es un problema de **flush/emisión** (o de que el flush corre en una fase/thread que no
  se ejecuta en nuestro scheduler).

**2026-10-17 (undécima ronda) — el menú se dibuja y lo tapa el fade (el frame está cubierto por un quad negro con alpha)**

- **La cadena de dibujo corre completa hasta el GS**: `vu1:mscal` ×60, `gs:kick`/`gs:gif` ×96, `XGKICK` ×40,
  `vif1-chain` ×60 ⇒ VU1/GS vivos; y los prims que llegan son **`prim=6` = `GS_SPRITE`** (los sprites del
  menú, no sólo el fade) con **`tme=1` ×12** (draws **texturizados** ✓) además de los `tme=0`.
- **El síntoma exacto**: `[gs:diag] crt1 (fbp=0) rgbNZ=0 aNZ=286720` — **286720 = 640×448 = la pantalla
  entera** con alpha ≠ 0 y **RGB = 0** ⇒ lo último que se pintó es **un quad negro que cubre todo**: el
  **fade**. Es decir: el menú está dibujado (o se dibuja) pero **el fade lo tapa**, y su alpha no está
  llegando a 0.
  - VRAM: `vramNonZero=478575` con el patrón alpha-only en los primeros 2 MB + `per256K=[10]=3119`
    (la página del *draw*, 80) ⇒ hay contenido, pero lo del frame es alpha sin color.
- **Corrección a la etapa 3 del v68**: `FUN_00754398`, `FUN_0070b868` y `FUN_0075ccc8` **no están
  referenciadas en ningún lado** (ni `jal` en el generado ni puntero en los 32 MB de RAM del savestate) ⇒
  no son el flush real. (Como referencia: `FUN_00743268` —el emit por hijo— **sí** aparece como puntero en
  el heap (9+ nodos en `0xC7xxxx`) y `FUN_00743568` se llama por `jal` desde `FUN_00506af0`.)

**Próximo paso (duodécima versión)** — atacar el **fade**: loguear su valor/estado por tick (el argumento del
setter `*(gp-0x33C)` vtable `+0x5C`, o el alpha del quad del fade en los `[gs:gif]`), y comparar con el real
(en `eeMemory.bin` el estado de menú ya tiene el fade terminado: su framebuffer tiene contenido **con color**).
Si el fade no baja a 0, hay que ver **quién debería bajarlo** (un contador por frame / un VBlank) y por qué no
avanza en nuestro run.

**2026-10-17 (duodécima ronda) — el fade está bien; el problema es que lo dibujado no tiene color (página/alpha)**

- **Fade: refutado mi hipótesis.** `*(gp-0x33C)` = objeto del motor (su vtable está en `+0x1C` = `0x9f45c0`;
  el slot `+0x5C` = `0x58f0c0`), y `FUN_00512630` le llama el virtual **`+0x30` 3×/tick** con
  `f12 = *(gp-0x320)` (la tasa; 0.02 = 1/50 ⇒ 0.5 s). El virtual es un *avance* (hoja `0x591b90`:
  `*(a0+8) += min(delta,0.25)`), y medido por tick **`*(engine+8)` avanza 0 → 0.04 → 1.18 → 1.2** ⇒
  **el fade termina** (en el menú real vale 3.115, >1, igual criterio).
- **Página presentada vs dibujada**: el contexto de dibujo es **página 80** (`ctx=80/8/0`; su contenido:
  `per256K=[10]=3119`) y la presentación lee **página 0** = el **default del runtime** (`DISPFB1=0x1400`,
  `ps2_memory.cpp:578`). Los registros del real (`work/teleport/GSregs.bin`, con `PMODE=0x8067` ✓ que
  confirma el layout) dan `DISPFB1 = 0x00080080` ⇒ **FBP = 0x80 = 128** ⇒ el real presenta una página
  concreta, no la 0. Es el lead que este archivo ya anotaba el 2026-10-11 ("falta fijar el fbp de display").
- **Matiz decisivo**: nuestro `Present` **ya** intenta fallback a los `contextFrames` cuando la página del
  display está negra, y **no la elige porque el contenido de la página 80 también es alpha-only (RGB=0)**.
  ⇒ el problema no es sólo *qué página* se lee: **lo dibujado no tiene color** (el frame presentado queda
  `rgbNZ=0` con `aNZ=286720 = 640×448`, o sea la pantalla entera con alpha y sin RGB).
- Referencia visual del objetivo: **`work/teleport/state_menu.png`** = el menú real ("Select video format…
  NTSC(60Hz) / PAL(50Hz)").

**2026-10-17 (decimotercera ronda) — sin subida de texturas al GS: todo se dibuja negro con alpha**

- **El probe `[gs:prim]` (64 prims) lo dice directo**: los prims del juego son **`type=6` = `GS_SPRITE`** con
  **`tme=0`** y **`rgba=(0,0,0,0)`**, dibujados en **`fbp=128`, `fbw=8`** (`alpha=0x44`), y sólo 12 con
  `tme=1` (texturizados). ⇒ los sprites del *menú* van **texturizados** pero **el color del vértice es 0**: el
  color tendría que venir de la **textura**.
- **Y no hay texturas**: en el log, **todos** los paquetes GIF son **`flg=0` (PACKED) y ninguno `flg=2`
  (IMAGE)** (48/48 en los dos runs medidos) ⇒ **nunca se sube una textura a `tmem`** ⇒ los sprites con
  `tme=1` se rasterizan con textura vacía = **negro + el alpha de la textura** ⇒ **explica el síntoma exacto**
  del frame presentado: pantalla completa con `aNZ=286720 (640×448)` y `rgbNZ=0`.
  - Coincide con la nota del **2026-10-10** que quedó abierta: *"no llega ninguna subida de textura al GS;
    todos los `[gs:gif]` son `flg=0` (PACKED), cero paquetes IMAGE (`flg=2`)"*.
- **Contexto que sostiene esto**: el juego ya está lógicamente en el menú (Task#4 == real), el pipeline 2D
  corre (dispatch → traversal → encolado, `FUN_006e58b8` ×394), el VU1/GS está vivo, el fade terminó
  (`*(engine+8)` → 1.2) y la presentación lee la página que le dicen los registros (DISPFB1 = el default del
  runtime, `fbp=0`; el real tiene `DISPFB1 = 0x00080080` ⇒ FBP=128, la misma página en la que el probe ve
  dibujar los prims). El único eslabón faltante es **la textura**.

**2026-10-17 (decimocuarta ronda) — el juego no *emite* ninguna subida de textura (ni por la vía nativa ni por el SDK)**

- **`writeGifChain` (el helper del runtime que intenta las heurísticas nativas `tryProcessNativeGifImageUploadChain`
  y `tryProcessNativeGifPackedChain`, `ps2_runtime.cpp`≈2650) NUNCA se llama** — instrumentado el entry de la
  heurística IMAGE y el call site: **0 líneas**. ⇒ el tráfico GIF del juego entra por el camino **genérico** de
  `PS2Memory` (walk de la cadena por TADR, `mode=(chcr>>2)&3 == 1`) → `m_pendingGifTransfers` /
  `processGIFPacket` del frontend del GS, **que sí sabe manejar IMAGE** (`tryProcessNativeImageUploadPacket`) ⇒
  si el juego mandara un tag `flg=2`, lo veríamos. **No manda ninguno** (48/48 `flg=0`).
- **Los stubs de carga de imagen existen y NO son no-ops** (`sceGsExecLoadImage` en `GS.cpp:593` arma el packet
  completo con el setup A+D; `sceGifPkRefLoadImage` en `:474` también) ⇒ no es que los pisemos con un stub vacío.
- **El juego no llama al cargador del SDK**: trace sobre la región GS/DMA del SDK (`SWORD_TRACE_BRANCH=4d0000-4d4000`,
  132k líneas) ⇒ lo que llama es **sincronización** (`0x4d3190` GetThreadId ×83 363, `0x4d32e0` WaitSema
  ×43 949, `0x4d32c0` SignalSema ×3 130 — el busy-spin), algunos **DMA** (`0x4d19c8` ×62, `0x4d1a60` ×3) y
  `0x4d3730` (sceGsSyncV) ×62; **nada de image-load**.
- **Dos candidatos** para la subida que falta:
  (a) el **uploader del juego** (arma sus propios paquetes) está *gateado* (flag/caché de tmem) y no corre; o
  (b) sube por **PATH3 directo** (registros `GIF_TAG0..3 = 0x10003040+`, `GIF_CNT/P3CNT/P3TAG = 0x10003080/90/A0`
      o el **FIFO `0x10006000`**) — y el runtime **no maneja esos registros** (grep: cero referencias) ⇒ los
      guardaría en `m_ioRegisters` y los ignoraría en silencio.
  (Los literales de esas direcciones no aparecen en el generado, pero —regla conocida— una escritura por
  dirección **calculada** no aparece como literal.)

**Próximo paso (decimoquinta versión)** — decidir (a) vs (b): loguear en `PS2Runtime::Store32` las escrituras al
rango de PATH3/GIF (`0x10003000-0x10007000`, con valor y `pc`), en un run corto. Si aparece actividad ahí, el
hueco es el **FIFO/PATH3 directo** (implementarlo); si no, el uploader del juego no corre y hay que ver su gate.

**2026-10-17 (decimoquinta ronda) — el juego SÍ sube texturas, pero no el atlas PSMT8 ni el CLUT que los sprites muestrean**

- **Probe nuevo `[gs-reg]`** (toda escritura de registro GS por A+D, deduplicada): el juego escribe
  `BITBLTBUF/TRXPOS/TRXREG/TRXDIR` ⇒ **sí hace subidas** ✓ (y también `DISPFB2`/`DISPLAY2`, `TEX0`, `TEXA`,
  `FRAME`, `ZBUF`, `ALPHA`, `TEST`, `SCISSOR`, `XYOFFSET`, `PRIM`, `RGBAQ`, `ST`, `UV`, `XYZF2`…).
  `m_privRegs` **es** el mismo `gs_regs` que escribe el EE (`m_gs.init(..., &m_memory.gs())`) ⇒ no hay dos
  copias (se descarta ese bug).
- **Probe `[gs-upload]`** (cada `TRXDIR` con destino/formato/tamaño): se hacen **5 subidas**, TODAS
  `dir=0` (host→local ✓ = subidas reales) a **`dbp=10240` (page 80 = 0x280000), `dpsm=0` (PSMCT32)** con
  tamaños 32×32, 16×16, 8×8, 8×4, 16×16 ⇒ ~5,5 KB de imágenes *chicas de color directo*.
- **Y lo que dibujan los sprites**: los **12** draws texturizados (`[gs:content]`) son idénticos:
  `prim=4 tme=1 tex0(tbp0=10240 tbw=2 psm=19 tw=6 th=6) uv=(13312,15072) rgba=(0,0,0,0)` ⇒ muestrean una
  textura **PSMT8 (psm=19) de 64×64** (`tbp0=10240` = **la misma page 80**) ⇒ **leen como índices lo que se
  subió como PSMCT32**, y **no hay ninguna subida de CLUT** (ninguna a un `dbp` de paleta ni con `dpsm`
  indexado) ⇒ los texeles resuelven a negro (y el `rgba` del vértice ya es 0) ⇒ **sprites negros** ✓ = el
  síntoma.
- Resumen del eslabón: **falta la subida del atlas PSMT8 (64×64) y de su CLUT**; el resto del pipeline
  (carga de assets, tareas, encolado, VU1/GS, fade, presentación) está medido y sano.

**Próximo paso (decimosexta versión)** — ir a Gemini (v69) con esto: *¿cómo sube este motor el atlas PSMT8 y su
CLUT (qué función/recurso, p. ej. el handle `*($s0+0x1B4)` / `0x65216110`), y qué lo gatea?* En paralelo:
loguear el `TEX0` completo (`cbp`/`cpsm`/`csa`) de esos 12 draws para saber si la *paleta está declarada* pero
no subida (uploader roto) o si el juego directamente no la sube. **(RESPONDIDO en la decimosexta ronda.)**

**2026-10-17 (decimosexta ronda) — VERIFICADO POR BYTES: nuestro camino de subida es idéntico al real; falta el ATLAS PSMT8**

Artefactos: `work/teleport/GS.bin` (volcado real del menú), `work/teleport/recomp_vram_menu.bin` (nuestro, dump
tardío) y `work/teleport/diff_vram.py` (comparación reproducible).

- **`GS.bin` NO es VRAM cruda**: son **425 bytes de header + 4 MB de VRAM + 84 de cola** (4 194 813 bytes).
  Verificado por contenido: el patrón de la paleta de `CBP=10268` aparece en el archivo exactamente 425 bytes
  después de su dirección VRAM. (Sin descontar eso, toda comparación muestra un corrimiento falso de 425 y
  miles de bytes "distintos".)
- **Con el header descontado, nuestra page `0x280000` (TBP0=10240) y su CLUT (`CBP=10268`) son
  byte-idénticas al real**: `0 de 8192` y `0 de 1024` bytes distintos. ⇒ **el camino GS/A+D/DMA del runtime
  es correcto** (setup `BITBLTBUF/TRXPOS/TRXREG/TRXDIR` + payload + destino + swizzle) — el hueco NO es nuestro.
- **Lo que falta es completo y grande**: pages `0x282000`–`0x294000` (tbp 10272–10560) = **~21 KB de texeles
  PSMT8 + CLUTs** que el real tiene y nosotros **no subimos nunca**. Los draws texturizados son **2738**
  (`[gs:content] TOTAL kicks=20000 colored=133 textured=2738`) y su `TEX0` es `TBP0=10240 TBW=2 PSM=19 PSMT8
  TW=64 TH=64 TCC=1 TFX=0(MODULATE) CBP=10268 CPSM=0 PSA=0` ⇒ **el color sale 100% de la textura** (con `TCC=1`
  el `rgba=0` del vértice es irrelevante); las texturas que faltan ⇒ negro.
- **Camino del uploader (código generado + los `pc` de los kicks)**: `FUN_006efd28` (`0x6efd28`) arma el packet
  A+D (`func_4D0450`) y lo manda con `func_4D07E8` (**`$a1 = $s7-0x2600`, `$a2 = 0xD`** = los 13 qwords /
  `QWC=0xd` que ya veíamos), y espera en un bucle (`func_4D1A60`, `bnez $v0`). Su caller es **`FUN_006f0a38`**
  (`0x6f0bc4`), que **guarda los parámetros de transferencia en el nodo** (`sdr $a0,0x28($s0)`,
  `sdl/sdr $a1,0x30/0x37($s0)`) y un global en **`gp+0x654`** ⇒ **cola de subidas + rutina de flush**, no subida
  inmediata.
- **`FUN_006f0a38` no tiene ningún caller directo** (`grep` en `work/generated/*.cpp`): se invoca
  **indirectamente** por un slot de objeto/controlador (como el grafo de tareas). ⇒ para hallar el gate hay que
  trazar la *entrada* a `0x6f0a38` (su `src`), no buscar `jal`.
- **A/B del paso 4 de Gemini** (env-gateado `SWORD_NO_CRT1_DEFAULT=1`, en `gs_cpu_backend.cpp:1956`): funciona
  — `[gs:present] #830 valid1=0 valid2=1 ... vramNonZero=3119` ⇒ se evita mezclar CRT1 (default `dispfb1=0x1400`,
  page 0 vacía) sobre CRT2 y queda disponible el fallback a los frames de dibujo. Baseline: `valid1=1 valid2=1`
  (rama de mezcla). **No** queda activo por defecto.
- **Trampas nuevas de instrumento** (siguen las ya documentadas): (a) **`SWORD_TRACE_BRANCH` no flushea si hay
  pocas líneas** ⇒ un rango que matchea poco deja el log **vacío aunque el evento haya ocurrido** (el trace de
  132k líneas sí sirvió porque el buffer se vacía solo); (b) **`SWORD_DUMP_VRAM` vuelca en present
  #300/#900/#1500** y las subidas caen entre #300 y #830 ⇒ hay que usar el dump tardío; (c)
  **`SWORD_RDRAM_DUMP_LATE` (tick≥1200) no disparó** en los runs cortados con `timeout`.

**Próximo paso (decimoséptima versión)** — encontrar el gate del *driver* de texturas del juego: **(HECHO: gate identificado a nivel instrucción, ver decimoséptima ronda.)**
(1) arreglar el flush del trace (`std::unitbuf`/`flush()`) y trazar la **entrada** a `0x6f0a38` y `0x6efd28`
(capta el `src` = el `jalr` del controlador y el bucle que debería recorrer las 11 páginas); o
(2) volcar en cada subida los campos del **nodo** (`+0x28/+0x30/+0x37`) y el global **`gp+0x654`**, y compararlos
contra el descriptor real (`eeMemory.bin`, `*($s0+0x1B4)` → `0x00e89668`). Hipótesis a falsar:
(a) cola de subidas paginada esperando una confirmación de DMA/VBlank que nunca llega; (b) flag "residente en
VRAM" en el nodo que saltea las 10 páginas restantes.

**2026-10-17 (decimoséptima ronda) — el gate de la subida de texturas, identificado a nivel instrucción**
- **Arreglado el flush del trace** (`s_out.flush()` en `ps2_runtime.cpp`, junto al `<<` de `[SWORD_TRACE_BRANCH]`):
  antes un trace de pocas líneas quedaba **vacío en disco**.
- **`FUN_006efd28` (el uploader real) se entra UNA vez**, desde `src=0x6f0bc4` (dentro de `FUN_006f0a38`) ⇒ el
  packet único lleva las 5 sub-rectángulos de *esa* textura (por eso vimos 5 `TRXDIR`).
- **`FUN_006f0a38` se entra 54 veces** por llamadas **indirectas** (`kind=3`, `jalr` por slot de objeto) desde
  `0x6d54b0/0x6d5520/0x6d5590/0x6d5810/0x6d5880/0x6d5e20/0x6d5eb4` con **opcode en `a0`**:
  `0,2,4,5,6,7,0xa,0xb,0x11,0x16` (39× el 6). Es un **dispatcher por comando**, no un bucle de subida.
- **El opcode que sube es `a0=2`**: en el log temporal, la línea inmediatamente anterior a la única entrada al
  uploader es `src=0x6d5810 tgt=0x6f0a38 kind=3 a0=0x2` ⇒ **el juego emitió "subir textura" una sola vez**.
- **Cadena del emisor**: `0x6d5810` está en `FUN_006d57e8` (wrapper: `$s1 = 0x00A90000-0x7838 = 0x00A887C8`;
  `$v0 = *($s1+4); jalr $v0` con `a0=2`) ⇒ **`0x00A887C8` es el objeto gestor de texturas** y su **slot `+4`** es
  el dispatcher `FUN_006f0a38`. Su único caller directo es **`0x51f53c`, dentro de `FUN_0051f450`** (el runner de
  fase, el mismo que llama al frame-loop `FUN_00512630`).
- **EL GATE (`FUN_0051f450`)**: todo el camino de subida se toma **sólo si `func_6D5980()` devuelve != 0**:
  ```
  0x51f4d8: jal func_6D5980
  0x51f4e0: bnez $v0 -> 0x51f4f8      ; <- gate
  0x51f4e8: jal func_6D5C70 ; y sale (0x51f4f0 -> 0x51f568) sin subir
  0x51f4f8: a0=*(gp-0x7E18) a1=*(gp-0x7E14) a2=0x20 a3=0x203
  0x51f504: jal func_51EF60           ; (pinta a "pedido de bloque/asset": tamaño 0x20, flags 0x203)
  0x51f50c: jal func_6F1F90(a0=1)
  0x51f514: jal func_6D5500
  0x51f520: jal func_6D5DF8(a0=$sp+0x20, a1=$v0)
  0x51f534: *(0xA42514) = $v0
  0x51f53c: jal func_6D57E8           ; <- la subida (opcode 2)
  0x51f540: *(0xA42518) = $v0 (delay slot)
  0x51f544: bnez $v0 -> 0x51f564       ; el runner reacciona al resultado
  ```
- **Preguntas abiertas (decimoctava ronda)**: (a) ¿`FUN_0051f450` se entra una vez o por frame? (tracear
  `0x51f450`); (b) ¿qué es `func_6D5980` (el gate) y por qué devuelve != 0 sólo una vez?; (c) ¿qué pide
  `func_51EF60` con `a2=0x20/a3=0x203` y por qué no completa para las otras 10 páginas?; (d) el objeto
  `0x00A887C8` y sus globals `gp-0x7E18`/`gp-0x7E14`/`0xA42514`/`0xA42518` son el estado del gestor ⇒
  compararlos contra el real (`eeMemory.bin`) para ver en qué se diferencian.

**2026-10-17 (decimoctava ronda) — el estado del gestor de texturas es BYTE-IDÉNTICO al real**

- `func_6D5980` (el gate) también se llama **una sola vez** (desde `0x51f4d8`, dentro del runner).
- `FUN_0051f450` (el runner) se entra **una sola vez**, y su caller `FUN_00512ab0` (`0x512ab0`–`0x513160`) lo
  llama **incondicionalmente al principio** (`0x512ab8..0x512ac8`) ⇒ no hay gate en el call site: el gate es
  *cuántas veces se entra* a `FUN_00512ab0` / al runner.
- **Comparación contra el real (dos volcados de 32 MB: `/tmp/rdram_late.bin` nuestro, tick 1200, vs
  `work/teleport/eeMemory.bin` del menú real)**:
  - objeto gestor **`0x00A887C8`** ⇒ `IGUAL` (incluida su vtable: slot `+4` = `0x006f0a38`, y los métodos
    `0x006fd a80`, `0x006fa768`, …);
  - globals **`gp-0x7E18`/`gp-0x7E14`** (`0xA20258`/`0xA2025C`) ⇒ `IGUAL`;
  - **`0xA42514`/`0xA42518`** (los `sw` de `0x51f534`/`0x51f540`) ⇒ `IGUAL`;
  - ventana de 128 bytes desde `0xA887C8` ⇒ **128/128 bytes idénticos**.
- ⇒ **La lógica del juego llegó exactamente al mismo estado que el real.** El atlas que falta **no** se explica
  por un gestor roto, ni por punteros/estado desincronizados, ni por un `rgba` de vértice. Las dos hipótesis
  vivas: **(i)** en el real el atlas se subió **antes** (fase de boot/logo) y quedó en VRAM (un volcado de VRAM
  es acumulativo), y el pase que vemos es sólo el del menú — nuestro VRAM nunca tuvo esas páginas ni en el dump
  temprano (`#300`, ya con 0 en 321–330); **(ii)** el pase de subida debe **repetirse** (una textura por
  invocación) y en nuestro run se invoca una sola vez (el gestor está *idle* en ambos, así que el disparador de
  la repetición **no** está en el objeto gestor).

**Próximo paso (decimonovena ronda)** — discriminar (i) vs (ii):
1. **Dump de VRAM temprano** (p. ej. present #10) para ver si el atlas aparece *alguna vez* en nuestro run
   (si nunca aparece ⇒ (i) es falsa y el pase debe repetirse ⇒ (ii)); ya tenemos dump configurable en
   `SWORD_DUMP_VRAM=<ruta>` (hoy en #300/#900/#1500: agregar #10, o un valor de "cada N").
2. **Contar entradas a `FUN_00512ab0`** (`SWORD_TRACE_BRANCH=512ab0-512ab1`): si es 1 ⇒ su caller es el gate
   real (leer su condición) y hay que ver por qué el juego no vuelve a ejecutar el bloque de arranque.
3. Leer `func_6D5980` (qué "trabajo" consulta) y `func_51EF60` (`a2=0x20`, `a3=0x203`, dos punteros de `gp`) —
   la API del gestor — y comparar *esos* datos si el disparador no está en el objeto.
4. En paralelo: comparar por **contenido** (no por dirección, el heap está corrido +0x150) el resto de las
   estructuras del loader/task4 contra el real, para descartar que falte una cola de assets.

**2026-10-17 (decimonovena ronda) — el pase de subida es de *startup* y la cola tenía UN solo asset listo ⇒ el eslabón es el LOADER**

- **`FUN_00512ab0` (0x512ab0–0x513160) se entra UNA vez**, desde `src=0x51fee8` = la función de entrada del juego
  (`entry_0051f4f8`) ⇒ todo el camino (runner → gate → la subida) es un **pase de arranque**, no parte del lazo
  de frame (el lazo `FUN_00512630`, que hace *yield*, se entra después desde dentro de esta misma función).
- **El bloque del runner es un *bucle* sobre el gestor**: `0x51f544: bnez $v0 → 0x51f564` ⇒ la secuencia
  "consultar trabajo (`func_6D5980`) → preparar → subir (opcode 2) → reaccionar" **itera mientras el gestor
  diga que hay trabajo**. En nuestro run ejecutó **una** vez y paró ⇒ **en ese instante la cola tenía un único
  asset listo** (el de la primera textura), y como el pase es de *startup*, los que estuvieran listos *después*
  ya no se procesan.
- **Diff completo de 32 MB** (nuestro tick 1200 vs `eeMemory.bin`): 7,78% de palabras distintas, pero el
  desglose es *esperado*: (a) las zonas de **código** del juego están en cero en nuestra RAM (el runtime usa el
  código recompilado, no ejecuta el del guest) — esto explica los clusters grandes y ruidosos de la zona baja;
  (b) el **heap** corrido +0x150; (c) una **lista enlazada poblada en el real y vacía en nosotros** (nodos cada
  `0x4C` desde `0x1AD7C`, con `prev`/`next` y un auto-puntero en `+0x4C`; head autorreferente en `0x1A260`):
  patrón de **tabla de descriptores de E/S del guest** (iomanX/loader) ⇒ **artefacto de HLE** (nosotros
  interceptamos el file I/O y esas estructuras del guest quedan sin poblar), no una diferencia de estado del
  juego. **El objeto gestor de texturas sigue siendo byte-idéntico al real.**
- **Conclusión del hilo de texturas**: no es el GS (probado byte a byte), no es el estado del gestor (idéntico),
  no es el código de dibujo ⇒ **es la *readiness del loader de assets* en el momento del único pase**.
  Próximo paso natural: instrumentar **qué assets pide el juego al loader y cuáles quedan sin completar**
  (los `[ld-*]`/SIF/RPC ya existen; comparar la *cola* del loader y las respuestas del lado IOP/SIF), y en
  particular si hay un asset de *atlas de interfaz* que nunca se completa (el loader quedó en `state=3` para 6
  assets, pero puede faltar el que trae los texeles PSMT8 de las pages 321–330).

**2026-10-17 (vigésima ronda) — el gate es un flag, y en el gestor hay una LISTA que en el real tiene 6 objetos y en nosotros está en cero**

- **El gate, leído:** `func_6D5980` hace `$s2 = 0xA887B8` (base del gestor), `$v0 = *(0xA888DC)`, `$v0 ^= 1`,
  `$s0 = ($v0 < 1)` y `beqz $s0` ⇒ **"hay trabajo" se decide por el flag `*(0xA888DC)`**. Medición: vale **3 en
  ambos** (nuestro dump y el real) ⇒ **no** es la diferencia.
- **Layout del gestor `0xA887B8`**: `+0x8` = contador (`0xA887C0`), `+0x10` = vtable (`0xA887C8`, slot `+4` =
  `0x006f0a38`), `+0xBC` = **centinela de lista** (`0xA88874`), `+0x124` = flag del gate (`0xA888DC`),
  `+0x128` = `sw $s2` de `0x6d5b60`.
- **La diferencia real, comparando la ventana entera**: sólo 3 palabras difieren entre nuestro dump tardío y
  `eeMemory.bin`:
  - `0xA887C0`: **345 vs 629** (contador; muy probablemente de tiempo/frames ⇒ no concluyente),
  - **`0xA88874`/`0xA88878` (centinela de la lista): `0x00A88874`/`0x00A88874` (auto-punteros = lista vacía en
    nosotros, y además los slots `+8/+0xC/+0x10` en 0) vs `0x00CB5818`/`0x00E8C058` en el real** ⇒ en el real
    el centinela tiene **la vtable de la clase** (`+8 = 0x004c6568`, `+0xC = 0x004cb430`, `+0x10 = 0x004c6c20`)
    y una **lista doblemente enlazada con 6 nodos** (`0xE8C058 → 0xE8C2D8 → 0xE8C558 → 0xE81F18 → 0xCB6028 →
    0xCB5818`, con floats `0x3F800000` = 1.0 y `0x3F7FFFFF` en `+8`) — objetos con *transforms/floats* (UI ✓),
    no texturas.
- **El centinela nunca se escribe en nuestro run**, y eso está *medido*: el watchpoint de escritura
  (`SWORD_WP_WRITER`, implementado con `mprotect`+SIGSEGV, **no es ciego**: atrapa también `FAST_WRITE32`)
  vigiló 2 páginas que cubren `0xA88874`/`0xA888DC` durante 100 s y capturó **0 escritores**.
- **Cadena del "instalador" (para contextos)**: `FUN_006d5ad0` construye si el flag está en 0
  (`0x6d5b58: lw $v0, 0x124($s0)` → `bnez`, y en el delay slot `sw $s2, 0x128($s0)`) y llama a
  **`FUN_006d13a0`** (batch de instalación de vtables: arma `0x4c6568`, `0x4cb430`, `0x4c6c20`, `0x4c71d8`,
  `0x4c6818`, `0x4c6e70`, … con `lui 0x4C/0x6D` + `addiu`). **`FUN_006d13a0` sí corre (1 vez, desde
  `0x6d5b64`)** ⇒ instala tablas *globales*, pero **no** escribe el centinela de `0xA88874` ⇒ la
  construcción/enlace de la lista es de **otra** función que en nuestro run no se ejecuta.
- **Trampa nueva (importante para futuros watchpoints)**: `wpInstall` redondea el inicio **hacia arriba**
  (`(base + lo + 0xFFF) & ~0xFFF`), así que `SWORD_WP_WRITER=a88000-a8a000` vigila **desde `0xA89000`** y deja
  afuera la página de `0xA888DC` ⇒ **dar siempre una página de margen** (p. ej. `a87000-a8a000`).

**Próximo paso (vigesimoprimera ronda)** — encontrar quién construye/enlaza los 6 objetos de esa lista:
1. Trazar la **entrada** de las funciones del cluster de la clase (`0x6d6290`, `0x6d6310`, `0x6d6390`,
   `0x6d6410`, `0x6d6490`, `0x6d6510`, `0x6d67a8`, `0x6d68a0`, `0x6d6a80`, `0x6db0d0`) y ver cuáles **no** se
   ejecutan en nuestro run (mismo método que reveló el gate del uploader).
2. Comparar la *cadena de nodos* del real (direcciones de heap) contra nuestro dump para ver si los objetos
   existen (desenlazados) o no existen; recordar el corrimiento **+0x150** del heap, así que comparar **por
   contenido** (floats `0x3F800000`, tamaño 0x280 entre nodos) y no por dirección.
3. Con la función que *enlaza* identificada, trazar sus llamadores hacia arriba hasta el punto donde el flujo
   de nuestro run diverge del real (ahí está la causa raíz de que el menú salga sin color).



**Próximo paso (cuarta versión — SUPERSEDED por la quinta de arriba)** — el camino al menú pasa por la fase, no por el render:
1. **Watchpoint real sobre `0xA93728`** (mprotect+SIGSEGV, tipo el viejo `SWORD_WP_WRITER`): enumerar quién
   escribe el flag del objeto de fase (y quién *debería*). Un watch en `Store32` **no sirve** (artefacto 6).
2. Con eso, decidir: (a) falta el productor de esa señal (el juego espera algo que no llega) o (b) el
   runtime nunca ejecuta la ruta que la produce (comparar con savestate: `gp740/744` y la tabla de fases).
3. Comparar el **estado de fase** recomp vs savestate de la misma fase (`work/teleport/eeMemory.bin`) antes
   de encadenar más deducciones: el `0xA93728` del recomp no tiene por qué caer en la misma dirección en
   consola (el heap difiere ~`0x150`), así que comparar por **contenido/estructura**, no por dirección.

## 2026-10-18 — verificación de la respuesta v70 de Gemini + A/B que REFUTA "falta el atlas"

> Todas las mediciones de esta sección son propias (artefactos en `/tmp`), no deducciones.

### (1) Corrección de marco: `FUN_0051f450` NO es un bucle; el bucle de frame es `FUN_00512630`

- **`FUN_0051f450` (`0x51f450-0x51f578`) es estrictamente lineal** (leído el generado completo): `func_6E6D00`
  → setup `0xA42530` → `func_6D5AD0` (ctor del gestor) → `func_51F580` → **`func_6D5980` (gate)** → si hay
  trabajo: `func_51EF60`/`func_6F1F90`/`func_6D5500`/`func_6D5DF8` → **`func_6D57E8` (opcode 2 = UNA subida)**
  → `0x51f544: bnez $v0, 0x51f564` (**salto hacia adelante**, devolver 1) → `ret`. **No hay lazo.**
  ⇒ La frase de la ronda 19 ("el bloque del runner es un bucle sobre el gestor") es un **error de lectura**.
- **`SWORD_TRACE_BRANCH=51f450-51f579`** (150 s): `FUN_0051f450` entra **1 vez** (de `src=0x512ac8`) y recorre
  el camino de subida 1 vez. ⇒ **toda la corrida sube UNA textura** (las 5 sub-rect TRXDIR a `dbp=10240`).
- **`SWORD_TRACE_BRANCH=51fe00-51ff40`** (140 s): el bucle `FUN_0051fea0` llama `FUN_00512ab0` (`0x51fee8`)
  **1 vez** y `FUN_00512630` (`0x51fef0`) **1 vez**. **Y eso es CORRECTO**: `FUN_00512630` **es** el bucle de
  60 fps de la fase (verificado: contiene `jal func_51FCF0` (vsync), `func_511F60` (pad), `func_5FBB90`
  (audio), `func_51AA80` (árbol de tareas), `func_510A10` (kick GS), `func_6291A0`, `func_62B250` (flip),
  `func_51A100`). `FUN_0051fea0` es el bucle de **cambio de fase**, no el de frame.
- **Confirmado contra el savestate**: el objeto de fase `*(gp-0x358)` (real `0xA93870` / nuestro `0xA93720`,
  offset heap `0x150`) tiene **contenido idéntico**: `+0 = 0`, `+4 = 3f800000`, **`+8 = 0`**, `+0xC = 0x009f3028`.
  Y `*(gp-0x324)` = `0xC61890`/`0xC619E0` → `+0 = 4`, `+0xC = 0`. ⇒ **que `FUN_00512630` no salga es normal**
  (el menú es la 4ª tarea); NO es nuestro bug. (Cierra el "próximo paso 4ª versión".)

### (2) El centinela `0xA88874` es transitorio — línea DESCARTADA (coincide con Gemini)

- Las funciones que insertan corren a montón (`0x6d6290`=900, `0x6d6310`=902, `0x6d6390`=899, `0x6d6a80`=8694)
  y el "clear" `0x6db0d0` corre **3593** veces; los 6 nodos reales son **matrices de transform 4×4**.
- Objetos del mismo tipo existen en nuestro dump (patrón matriz-identidad+`0x00020003`: **30 vs 27**).
  ⇒ la lista se rearma/vacía por frame; la foto del `.p2s` la agarró llena y la nuestra vacía. **No explica
  nada del menú negro.**

### (3) `GS.bin` (VRAM del real en el menú): **sólo contiene el atlas**, el resto de la VRAM está en cero

- Header verificado otra vez: **425 bytes** (con `hdr=425` las pages 320–330 suman 24 293 B ≠ 0, el esperado).
- **Mapa completo**: el real tiene data **únicamente** en el bucket 10 (`0x280000–0x2C0000`): pages
  320–330 (24 293 B). **Pages 0–299 = 0** (incluida la 128 = FBP del `DISPFB1` real). Bucket 16 = 5 bytes.
- Nuestra VRAM (run normal): buckets 0–7 llenos (≈2 MB de clear **alpha-only**, `0x7F…`) + bucket 10 = 3119
  (sólo page 320). Con la inyección: `vramNonZero=24293` (sólo el atlas).

### (4) **A/B DECISIVO: inyectar la VRAM del real NO muestra el menú ⇒ "falta el atlas" queda REFUTADO**

- Herramienta: `SWORD_LOAD_GS` lee 4 MB **desde el offset 0** ⇒ con `GS.bin` mete los 425 B de header
  (bug). Workaround sin recompilar: `dd if=GS.bin of=/tmp/GS_vram.bin bs=1 skip=425 count=4194304`.
  **(Corregir el offset en `triageLoadGs` es deuda pendiente.)**
- Run `SWORD_LOAD_GS=/tmp/GS_vram.bin` (130 s, sin teleport de RDRAM): `[load-gs] VRAM 4 MB inyectada`,
  y el frame **sigue negro**: `[gs:diag] crt1 (fbp=0): rgbNZ=0 aNZ=0 | crt2 (fbp=0): rgbNZ=0 aNZ=0`,
  `vramNonZero=24293` (sólo el atlas inyectado, el juego no reescribió nada).
- ⇒ **Con el atlas presente en VRAM el menú NO aparece.** El atlas **no** es la causa del frame negro.
- **Lo que sí diverge es la PRESENTACIÓN**: nosotros presentamos **`fbp=0`** (`dispfb1=0x1400` = el *default
  del runtime*, `ps2_memory.cpp:578`; el juego **nunca** escribe `DISPFB1`/`DISPLAY1`), y el `DISPFB1` del
  real es `0x00080080` → **FBP=128**. El contexto de **dibujo** es `ctx=80/8/0` (el juego dibuja en la
  page 80 = `0x280000`). Con la VRAM inyectada, la page 80 **tiene** contenido y aun así el present sigue
  eligiendo la page 0: el fallback por contenido de `PresentFromLocalMemory` (línea ~2024) **no selecciona**
  el candidato `ctx=80/8/0` (el `[gs:diag]` sigue diciendo `crt1 (fbp=0)`).
- **Nuevo foco (reencuadre)**: el bloqueo vigente es **de presentación / `DISPFB`/`DISPLAY`**, no de subida
  de texturas. Próximo paso concreto: instrumentar `copySource`/`CopyFrameToHostRgba` para ver por qué el
  candidato `80/8/0` no gana (¿devuelve `false`? ¿`countNonBlackPixels == 0`?) y, en paralelo, por qué el
  juego nunca escribe `DISPFB1`/`DISPLAY1` (¿los escribe por DMA en un paquete que el runtime no parsea?).

### (5) Respuesta v70 de Gemini — qué quedó verificado y qué no

- ✅ **Verificado**: `FUN_00512630` es el bucle de frame (sus `jal` coinciden exactamente); el flag de fase
  `*(s1+8)=0` también en el real; el centinela es transitorio (descartar); `FUN_0051f450` es init de fase.
- ❌ **NO verificado**: *"los datos del atlas YA están en RAM en `0x00cd0000` (real) / `0x00cd04ff` (nuestro)"*.
  El bloque de `0x00cd067f`/`0x00cd04ff` es **una tabla que existe idéntica en AMBOS** dumps, y **el contenido
  de la page 321 de la VRAM no aparece en la RAM** (ni exacto ni por ventanas de 16 B). ⇒ El **Paso 3 (PoC de
  inyección desde `rdram+0xcd04ff`)** no tiene base. La inyección probada (desde `GS.bin`) **tampoco** muestra
  el menú (ver (4)).

### (6) Sondas nuevas (`[dc-probe]`, `[present-fb]`) — el "display copy" NUNCA ocurre y el dibujo cae en la page 0, que queda VACÍA

Probes temporales (NO env-gated, pocas líneas): `gs_frontend.cpp::updatePreferredDisplaySourceForDraw`
(`[dc-probe]`) y `gs_cpu_backend.cpp::PresentFromLocalMemory` (fallback: `[present-fb]`).

- **`[dc-probe]`: no hay NINGÚN sprite full-screen texturizado.** La única línea es un sprite full-screen
  **todo en cero** (`tme=0 abe=0 fst=0 ctxt=0 frame.fbp=0 tex0.tbp0=0 tw=0 th=0`). ⇒ **la heurística
  "display copy" (blit framebuffer→página de display) nunca se dispara**; el runtime no tiene
  `preferredSource` y depende **solo** de `DISPFB`. (`[gs:content]` sólo ve **13** prims `tme=1`, todos
  `tex0(tbp0=10240 tbw=2 psm=19 tw=6 th=6) uv=(13312,15072) rgba=(0,0,0,0)` — **no** son de pantalla completa.)
- **Contexto de dibujo del juego**: **cambia con el tiempo** — al principio `ctx=128/8/0`, y en la fase de
  menú **`ctx=0/8/0 0/8/0`** (ambos = page 0). `[gs:present] #590`: `valid1=1 valid2=1 dispfb1=0x1400`
  (default) `dispfb2=0x80000001000` (→ fbp=0) `vramNonZero=3119` `per256K=[10]=3119` (¡sólo la page 320!).
- **PRECEDENTE CLAVE**: **la page 0 —el contexto de dibujo— está VACÍA al final**
  (`[gs:diag] crt1 (fbp=0): rgbNZ=0 aNZ=0`) y **el resto de la VRAM también** (sólo page 320 = las 5
  sub-rects). O sea: **el juego dibuja (13 prims texturizados) pero no deja pixel en la VRAM**. Y como
  `DISPFB1` (default, page 0) y `DISPFB2` (page 0) apuntan a esa page vacía ⇒ negro.
- **Coincidencia fuerte**: la VRAM **del real** (`GS.bin`) también tiene **pages 0–299 en cero**. ⇒ La
  "página vacía" **no** es un artefacto nuestro: el real tampoco tiene framebuffer en esa zona. ⇒ El frame
  visible del real **tiene que** venir de otra parte (¿la page 128? ¿un dump incompleto de `GS.bin`?), **o**
  `GS.bin` se capturó en un momento sin frame válido.
- **Siguiente paso concreto** (probes ya montados, sólo falta extenderlos): loguear en el rasterizador de
  prims `tme=1` (a) el `fbp/fbw` de destino y (b) si el write se descarta (alpha-test/blend con
  `rgba=(0,0,0,0)`), para responder *"¿por qué 13 prims texturizados no escriben nada en la page 0?"*.
  Hipótesis viva: **el color/alpha del vértice llega 0 y el prim se descarta o se escribe transparente**
  (el dato vendría del `TEXA`/`RGBAQ` que arma el juego — comparar `TEXA`/`ALPHA` con el real).

### (7) CADENA COMPLETA LOCALIZADA (2026-10-18) — los sprites del menú se descartan porque su **UV es (0,0)**

Probes nuevos: `[tri-probe]` (DrawTriangle texturizado), `[tex-probe]` (samplePoint), `[clut-probe]`
(LookupCLUT). Cadena medida, en orden:

1. **Los prims texturizados del menú son `TRISTRIP` (`type=4`), no sprites**, y **dibujan en la page 128**
   (`dest fbp=128 fbw=8 psm=0`) — que **coincide con el `DISPFB1` del real (FBP=128)**. Nuestro `DISPFB1`
   es el default del runtime (page 0) ⇒ aun arreglando el color habría que presentar la page 128 (o el
   fallback por contenido debe elegirla).
2. **TODOS los píxeles se DESCARTAN** (`[raster-probe] DISCARD tme=1 dest fbp=128 … rgba=(0,0,0,0)
   test=0x5002b alpha=0x44`). `TEST=0x5002b` → `AXT=1`, **`ATST=5` = `alpha >= AREF`** con **`AREF=2`**,
   **`AFAIL=0` = KEEP** ⇒ con alpha 0 **se descarta cada píxel** (nada se escribe ⇒ VRAM vacía ⇒ negro).
3. **El alpha compuesto es 0 porque el TEXEL es (0,0,0,0)**, no por el vértice: `[tri-probe]`
   `v0=(0,0,0,0) shade=(0,0,0,249) texel=(0,0,0,0) out=(0,0,0,0)`. **El alpha interpolado del vértice es
   ~249** (válido). Con `TCC=1`/`TFX=0` (MODULATE) el color/alpha sale de la textura.
4. **El texel es 0 porque la COORDENADA DE MUESTREO es (0,0) en todos los píxeles**: `[tex-probe] raw=0x0
   su=0 sv=0 psm=19 tbp0=10240 tbw=2 texW=64 texH=64 cbp=10268 cpsm=0` (8/8 idénticas).
   ⇒ **la `UV`/`ST` de los vértices llega en 0** (la textura en sí no importa: siempre muestrea (0,0)).
5. **`CLUT[0]` es transparente aun en el real**: `[clut-probe] idx=0 clutIndex=0 c0=0 c256=0 csm=0 csa=0`
   y en `GS.bin` el byte 0 de `0x281C00` es `00 00 00 00`. ⇒ aun con la CLUT bien cargada, el índice 0 da
   alpha 0. **No es la CLUT.** (Se probó una hipótesis de CLD=0 y se refutó: el juego usa **`CLD=1`**,
   que sí carga el cache; el cambio se revirtió.)
6. La textura (page 320 = `0x280000`) **está presente e idéntica al real**, y el atlas (pages 321–330)
   **no cambia el resultado** (ver (4) y (6)) ⇒ **"falta el atlas" no es la causa**.

**CONCLUSIÓN**: el eslabón es el **decode de las coordenadas de textura del vértice** (UV/ST en `0`). Es un
**bug de fidelidad del runtime**, no un dato faltante ni un parche por dirección.

**Próximo paso** (una sonda más + rebuild): en el prim `tme=1` loguear `v0.u/v0.v/v0.s/v0.t/v0.q` (y `fst`)
al entrar al batch, para ver si llegan 0 desde el **decode de vértices empaquetados** (GIF `REGS`/`PACKED`)
o si el `ST`/`UV` del registro no se propaga a la cola de vértices. Comparar con PCSX2 (`tools/ps2emu/pcsx2`,
solo referencia). Nota: la sonda `[gs:prim]` sólo cubre los primeros 64 prims (todos `tme=0`, el fade/clear),
por eso no se ven ahí.

> **Probes temporales dejados puestos** (no env-gated, ~decenas de líneas): `[raster-probe]`, `[tri-probe]`,
> `[tex-probe]`, `[clut-probe]`, `[dc-probe]`, `[present-fb]`. Revertir/limpiar al cerrar el diagnóstico.

### (8) Sonda de UV/ST — el prim texturizado llega **DEGENERADO** (3 vértices idénticos) y con `ST ≈ 0`

`[uv-probe]` (en `DrawTriangle`, primeros 6 prims `tme=1`): las 6 líneas son idénticas:
```
[uv-probe] tme=1 fst=0 type=4 v0(u=0x3400 v=0x3ae0) v1(u=0x3400 v=0x3ae0) v2(u=0x3400 v=0x3ae0)
           s0=0 t0=0 q0=1 s1=0 t1=0 q1=1 s2=0 t2=0 q2=1
           xyz0=(2048,2048) xyz1=(2048,2048) xyz2=(2048,2048) texW=64 texH=64 tbp0=10240
```
Lectura:
- **`fst=0`** (modo ST) y **`s=t=0, q=1`** ⇒ `texUf = s/q*texW = 0` ⇒ `su=0 sv=0` (consistente con (7)).
- El **mismo qword** que da `u=0x3400 (13312)`/`v=0x3ae0 (15072)` da `s=0x00003400`/`t=0x00003ae0` como
  **float32** ⇒ ~1.9e-41 ≈ 0. **Ojo**: PCSX2 también guarda `ST.S/ST.T` como float (`GSState.cpp:2619`
  `v->ST.S = std::bit_cast<float>(S)`), o sea **nuestro decode de ST NO está mal**; con `FST=0` el juego
  estaría mandando ST ≈ 0. (La otra lectura, UV con `FST=1`, daría `su=0 sv=46` por wrap, no lo medido.)
- **NUEVO E INDEPENDIENTE DEL FST: el prim llega DEGENERADO** — `v0 == v1 == v2` (misma `xyz`, misma UV).
  La sonda `[gs:prim]` de los primeros 64 prims (`tme=0`) muestra lo mismo (`v2 == v0`).
  ⇒ **el armado del batch/cola de vértices está produciendo primitivas colapsadas**; un triángulo
  degenerado no cubre píxeles ⇒ no escribe nada ⇒ negro (además del descarte por alpha=0).
- `xyz=(2048,2048)` para los 3 vértices huele a **vértice no inicializado / cola mal alineada**.

**Conclusión de la sesión**: el bloqueo NO es el atlas, ni la CLUT, ni el present: es **el armado de
vértices** (prims degeneradas + ST≈0 ⇒ se muestrea siempre (0,0) ⇒ texel transparente ⇒ alpha test
descarta ⇒ VRAM vacía). Siguiente paso: bisectar el armado de la cola de vértices (`vertexKick` /
`readVertexStream` / el pasaje VU1→GIF) contra PCSX2.

> **Caveat importante de esta sonda**: los 6 prims que loguea `[uv-probe]` son **los primeros** `tme=1`
> y están **fuera de pantalla** (`xyz=(2048,2048)` con `ofx/ofy` chico ⇒ x=2048 px > 640) y degenerados.
> Los prims que **sí rasterizan** son los del `[tri-probe]` (que sí imprimió píxeles `(0,0)…(7,7)` con
> `su=sv=0`). ⇒ Falta una sonda que loguee la **UV/ST del prim que rasteriza** (dentro del lazo de
> píxeles, 1 vez por prim), no de los 6 primeros. No dar por cerrado el "ST≈0" hasta medirlo en el prim
> que dibuja.

### (9) Respuesta v71 verificada + sonda del prim real: **el alpha test es SÍNTOMA, no causa**

- ✅ **Verificado de Gemini v71**: (a) el `uv=(13312,15072)` era **artefacto del log** — `[gs:content]`
  imprime `v.u, v.v` (`gs_frontend.cpp:1661`), no `v.s, v.t`; (b) los paquetes **sí** traen ST válido:
  `[XGKICK-fin] raw=…:3f800000 | 3eae00003e000000:3f800000 | …` ⇒ **S=0x3e000000=0.125, T=0x3eae0000=0.340,
  Q=1.0**; (c) las prims degeneradas de los primeros kicks son **padding/strip-restart normales** (y la
  sonda previa sólo capturaba esas); (d) la semántica de `TEST=0x5002b` (ATST=5 GEQUAL, AREF=2, AFAIL=KEEP)
  y `A_out = A_shade*A_tex/128` es correcta.
- **Sonda `[real-tri-probe]`** (1 vez por prim que **rasteriza**, dentro del lazo de píxeles; agregada en
  `DrawTriangle`): los prims reales del menú traen
  `fst=0 type=4 fbp=128 fbw=8 tbp0=10240 texW=texH=64`,
  `v0 xyz=(2308.87,2309) st=(0.48633,0.0117187) q=1 uv=(0,0) rgba=(128,0,128,255)`,
  y el primer píxel da `px=(256,256) is=0.486327 it=0.0117187 iq=0.999999 iu=iv=0
  texUf=31.1249 texVf=0.749999`. ⇒ **ST válido y coordenada de muestreo ~(31,0)**, NO (0,0).
  (Los prims #1/#2 sí tenían `st=(0,0)` — eran el padding.)
- **PRUEBA DE FUEGO (Gemini v71 paso 2, `SWORD_NO_ALPHA_TEST=1`, env-gated): con el alpha test
  BYPASSEADO la VRAM SIGUE SIN CONTENIDO** — `[gs:present] #600 vramNonZero=3119`, `per256K=[10]=3119`
  (sólo la page 320). ⇒ **el descarte por alpha no es la causa raíz**: aunque se escriba, el color
  resultante es 0 (el texel/CLUT resuelve a 0 en la coordenada real). El alpha test es **síntoma**.
- **Paso 3 implementado (env-gated, default OFF)**: `SWORD_PRESENT_CTX=1` ⇒ si `dispfb1 == 0x1400`
  (default del runtime) presenta `contextFrames[0]` (page 128, el `DISPFB1` del real).
- **Falta cerrar**: loguear el **texel** muestreado en el prim real (la sonda actual loguea `is/it/iq`
  antes de `SampleTexture`) y compararlo con la VRAM real offline (page 320 = `GS_vram.bin[0x280000]`,
  que es **byte-idéntica** al real), para decidir si `(31,0)` da índice 0 / CLUT 0 de verdad o si el
  lookup (PSMT8/CLUT) está mal.

### (10) El lookup PSMT8 es CORRECTO: `(31,0)` → VRAM `0x280136` = `0x00` **también en el real**

- Sonda extendida (`[real-tri-probe]` ahora loguea también el **texel**). Prims reales del menú:
  `px=(256,256) is=0.486327 it=0.0117187 iq=0.999999 texUf=31.1249 texVf=0.749999 texel=0x0
  texrgba=(0,0,0,0)`, con `v0 st=(0.48633,0.0117187) rgba=(128,0,128,255) cbp=10268 cpsm=0 cld=1 csm=0
  csa=0` y `fbp=128`.
- **Verificación offline con el swizzle real del runtime** (`ps2_gs_memory.h`: `P8 PageExtent{128,64}`,
  `BlockExtent{8,4}`, `BlockTableP8`, `ColumnTable8`; `address = page*8192 + (block+bid)*256 + col`):
  - `(0,0)`  → `0x280000` → byte **0x00** (coincide con la medición),
  - **`(31,0)` → `0x280136` → byte `0x00` en `GS_vram.bin` (el REAL)** ⇒ **el índice es 0 también en
    consola** ⇒ `CLUT[0]` (que en el real es `00 00 00 00`) ⇒ texel `(0,0,0,0)`.
  ⇒ **El camino de muestreo PSMT8/CLUT del runtime es correcto.** Estos prims magenta
  (`rgba=(128,0,128,255)`) están muestreando **fondo transparente**: no dibujan nada ni en el real.
  ⇒ **Estos prims NO son el contenido del menú.**
- **Consecuencia / siguiente foco**: hay que localizar los prims que **sí** dibujan el menú (los que
  muestrean texeles con índice ≠ 0, o que no son `tme`), y ver si llegan a ejecutarse. Sonda propuesta:
  loguear (a) el **histograma de texeles** muestreados por prim (cuántos ≠ 0) y (b) cualquier prim con
  `rgba` ≠ 0 y su `tbp0`, en toda la corrida — no sólo los primeros 12.

### (11) Histograma de texeles: **0 de 600 prims texturizados muestrean un texel ≠ 0**

`[tex-hist]` (por prim, `DrawTriangle`; run 130 s, juego en el menú: `root h20=0x500490`, `count=4`):

```
[tex-hist] #1  fbp=128 tbp0=10240 psm=19 rgba0=(0,0,0,0)       px=256 texelNZ=0
[tex-hist] #5  fbp=128 tbp0=10240 psm=19 rgba0=(128,0,128,255) px=256 texelNZ=0
[tex-hist] #12 fbp=0   tbp0=10240 psm=19 rgba0=(128,0,128,255) px=256 texelNZ=0
[tex-hist] TOTAL texturedPrims=200 withNonZeroTexel=0
[tex-hist] TOTAL texturedPrims=400 withNonZeroTexel=0
[tex-hist] TOTAL texturedPrims=600 withNonZeroTexel=0
```

- **TODOS** los prims texturizados usan `tbp0=10240` (page 320) y **ninguno** muestrea un índice ≠ 0.
- **La mitad rasteriza `px=0`** (degenerados/fuera de pantalla): `#2, #4, #7, #8, #13, #14, #19, #20…`.
- `vramNonZero=3119` (sólo page 320) al final, con el juego en el menú.

⇒ **El contenido del menú no está siendo dibujado por estos prims.** O bien (a) el juego dibuja el menú con
**otro `TBP0`** (el atlas de pages 321–330 que no se sube) y esas draws no ocurren / las decodificamos mal,
o (b) el armado de `TRISTRIP`/vertex-queue está mal (mitad degenerados), o (c) el dibujo del menú va por un
camino que no es `DrawTriangle` (p. ej. `DrawSprite`), que **no** tiene histograma.

> **Nota de método**: NO se puede concluir "el runtime dibuja mal" — el lookup PSMT8/CLUT y las
> coordenadas ST están verificados. Lo que no está es el **contenido**: ninguna muestra cae en un texel
> real de glifo. Pregunta a Gemini v72.

### (12) Telemetría GLOBAL de draws (`[gs:prims]`): **el juego NUNCA emite las draws del contenido**

Sonda global en `gs_frontend.cpp` (antes de `m_backend->Submit(batch)`), independiente del tipo de prim:
cuenta prims por tipo y draws texturizados por `TBP0`. Run 130 s (juego en el menú, `f=1630`):

```
[gs:prims] draws=21360 POINT=1 LINE=0 TRI=0 TRISTRIP=2294 TRIFAN=8256 SPRITE=10809
[gs:prims]   tbp0=10240 (page 320) texturedDraws=2294
```

- **El ÚNICO `tbp0` de draws texturizados es 10240 (page 320)**; nunca `10272..10560` (el atlas).
- **`texturedDraws == TRISTRIP` (2294)**: los **8256 TRIFAN y 10809 SPRITE son `tme=0`** (sin textura).
- **A/B con el atlas inyectado** (`SWORD_LOAD_GS=/tmp/GS_vram.bin`): **idéntico** — sigue habiendo sólo
  `tbp0=10240` ⇒ **el gate NO es la VRAM** (inyectar el atlas no hace que el juego emita esas draws).
- ⇒ Confirmado de Gemini v72: page 320 = chrome/íconos; el atlas de glifos (pages 321–330, `tbp0`
  10272–10560) **nunca se usa para dibujar**. **El juego nunca emite las draws del contenido del menú**
  (texto/glifos). El bloqueo está **aguas arriba del GS**, en la emisión 2D del juego — no en el runtime
  de render.
- **Próximo foco**: por qué el emisor 2D (p. ej. `FUN_006e58b8` / el componente de texto de la Task#4)
  no produce esas draws. Consulta: `work/gemini/msg_gemini_v73.md`.

### (13) Respuesta v73 VERIFICADA BYTE A BYTE: el nodo de texto nunca recibe el bind de fuente

Comparación en los dos dumps (real `eeMemory.bin` vs nuestro `/tmp/rdram_late1.bin`), nodo de string
`String 0x130` (**real `0xE83170` / nuestro `0xE82F70`**):

| Campo | Real | Nuestro | Significado |
|---|---|---|---|
| `+0x00` | **`0x08000000`** | `0x00000000` | falta el bit 27 ("bound") |
| `+0x2C` | `0` | `0x30` | offset crudo de archivo sin resolver |
| `+0x3C` | **`0x0095F410`** | **`0x3B`** | **falta el puntero al contexto de glifos** |
| `+0x4C` | `0` | `0x2C` | offset crudo de archivo sin resolver |

Contexto estático del generador de glifos **`0x0095F410`**:
- real: `00000101 00000001 00000004 00000000 | 00000000 00000004 0095F430` (**inicializado**),
- nuestro: **todo cero** (los bytes vírgenes del ELF).

Timers del **Task#4** (real `0xE21790` / nuestro `0xE21590`): `+0x2C/+0x30/+0x34` =
real **`3/3/4`**, nuestro **`2/2/2`** (⇒ `elapsed = +0x34 − +0x2C` = 1 vs 0). `+0x38 = 0xA` y
`+0xA4 = 2` **coinciden** en ambos.

⇒ **Causa raíz localizada (medida)**: el nodo de texto se encola y `FUN_006daef0` lo recorre, pero **el
generador de glifos aborta** porque `*(node+0x3C)` no es `0x0095F410` (contiene el offset crudo `0x3B`) y el
contexto `0x0095F410` está sin inicializar. Es el flag que impide emitir los quads de texto ⇒ **no hay
draws con `tbp0 ≥ 10272`** ⇒ el menú queda sin texto (y la VRAM sin el atlas).

**PoC montada (env-gated, `SWORD_FORCE_FONT_BIND=1`)**: en `work/generated/FUN_0083e2e0_0x83e2e0.cpp`, en
`label_83e540` (donde `$v0` = el nodo de string), se loguea `[font-bind] node/+00/+2C/+3C/ctx` y —sólo con
la env— se inicializa `0x0095F410` con los bytes del real y se patchea `node+0x3C = 0x0095F410` y
`node+0x00 |= 0x08000000`. **Probe temporal en un archivo generado: se pierde al regenerar el CSV.**

**A/B pendiente**: correr con y sin `SWORD_FORCE_FONT_BIND=1` y mirar `[gs:prims]` (¿aparecen
`tbp0=10272..10560`?) y `[gs:diag] rgbNZ`.

**A/B HECHO (2026-10-18)**:
- **Baseline**: `[font-bind] node=0xe82f70 +00=0x0 +2C=0x44 +3C=0x3b ctx0=0x0` ×6 (3 nodos:
  `0xe82f70`, `0xe82db0`, `0xe82e90`) y `[gs:prims]` sólo `tbp0=10240`.
- **Con `SWORD_FORCE_FONT_BIND=1`**: **NO cambia nada** — `[gs:prims]` sigue con **sólo `tbp0=10240`**
  (2340 textured draws), `[tex-hist] withNonZeroTexel=0`, `vramNonZero=3119`. ⇒ **el bind de fuente + la
  init de `0x0095F410` NO alcanzan**: es el caso **B** que Gemini anticipó ("el corte está en una función
  hija de `FUN_006daef0`, p. ej. `FUN_00710580`").
- **Ojo**: en vivo los nodos tienen **`+0x2C = 0x44` y `+0x4C = 0x44`** (offsets crudos sin resolver),
  mientras el real los tiene en **0**. Puede faltar normalizar esos campos (además de `+0x3C`/`+0x00`).
  Ver `work/gemini/msg_gemini_v74.md`.

### (14) PoC EXTENDIDO (v74) — tampoco destraba; y la explicación del "gate +0x2C" no cierra

- **Verificado**: el contexto de material real `0x0095F430..0x0095F468` coincide **exacto** con lo que dijo
  Gemini, incluida la cadena `"PS2AllMats.cl"` (`0x41325350 0x614D6C6C 0x73632E74 0x0000006C`) y la vtable
  `0x0075FB68` en `+0x54`.
- **PERO la explicación del "gate letal de `+0x2C`" es autocontradictoria**: `0x7105c4: lw $v0, 0x2C($s3)`
  y `0x7105d0: lw $v1, 0x8($v0)`. En el **real** `node+0x2C = 0` ⇒ leería `*(0x8)`; y en la RAM real
  **la dirección `0x8` contiene `0x40196800` (código)**, no 0. O sea, poner `+0x2C = 0` **no** produce el
  "`$s0 = 0` ⇒ skip" que Gemini describe (lo produce `+0x2C = 0x44` ⇒ `0x4C`, que sí es 0). Probablemente
  el `$s3` de `FUN_00710580` es el **widget/elemento a renderizar**, no el nodo de string.
- **PoC extendido ejecutado** (`SWORD_FORCE_FONT_BIND=1`: init completa del contexto+material, y
  `node+0x00/0x2C/0x3C/0x4C` normalizados). El parche **sí se aplicó** (el log muestra `ctx0=0x101` en los
  nodos siguientes) y el juego **llegó al menú** (`f=1570`, `t3sub=10`). Resultado: **NO aparecen
  `tbp0 ≥ 10272`** — sigue sólo `tbp0=10240` (`texturedDraws=2158`), `vramNonZero=3119`, `rgbNZ=0`.
  ⇒ **Caso B confirmado también con el PoC completo.**
- **Nota de determinismo**: un run con la misma env **divergió** y se quedó en `f=180` (`t3sub=1`) sin
  llegar al menú; el re-run anduvo. ⇒ hay **no-determinismo** ocasional; un resultado negativo aislado
  debe repetirse.
- **Siguiente foco** (sugerido por Gemini): visibilidad del widget (`FUN_00805340`, bit `+0x02 |= 0x04`)
  y/o el camino de `FUN_006daef0`→`FUN_00710580`. Consulta: `work/gemini/msg_gemini_v75.md`.

### (15) ¡BREAKTHROUGH! El selector PAL/NTSC esperaba **Cross**; al confirmarlo se destraba la emisión y **se sube el atlas**

- ✅ **Verificado de v75** (`FUN_0083d990`, bloque `sub==10`): `0x83da58 jal func_51C7C0` (lectura de pad)
  → `0x83da60 andi $v0,$v0,0x40` (Cross) → `0x83da64 beqz $v0 → 0x83DC24` (si no, no hace nada).
  Si `0x40`: `*(task+0xA4)=3`, `func_510600(task,1)` (transición de salida), `func_62DD60(0x42007E)`
  (sonido de confirmación) → sale del selector. **El juego estaba esperando input, no colgado.**
- **PoC `SWORD_CONFIRM_MENU=1`** (en `work/generated/FUN_0083d990_0x83d990.cpp`, en `label_83da60`:
  `$v0 |= 0x40`): el log `[confirm-menu] forzando Cross en sub=10 (v0=0x0)` dispara **una vez** y
  **`t3sub` pasa de `10` a `0`** (f≈370) ⇒ **Task#4 sale del selector**. El juego sigue vivo (`f=1720`).
- **EFECTO MEDIDO (lo importante)**:
  - **El atlas ahora SÍ se sube**: `[gs-upload] n=6..10 dir=0 … dbp=10272` (page 321), que **nunca**
    ocurría antes.
  - **Aparecen draws con el atlas**: `[gs:prims] tbp0=10272 (page 321) texturedDraws=2647`
    (`TRISTRIP` total 4101, antes ~2300 y **0** con tbp0=10272).
  - `vramNonZero` 3119 → **6238** (page 320 + 321).
  - Con `SWORD_PRESENT_CTX=1`: `fbpDisp1=128` y `[gs:diag] crt1 (fbp=128): rgbNZ=0 aNZ=151713`.
- **Lo que sigue faltando**: `rgbNZ=0` y `[tex-hist] withNonZeroTexel=0` incluso para los prims con
  `tbp0=10272` ⇒ los texeles del atlas siguen muestreando 0 (¿la CLUT del atlas — `cbp` de esos draws —
  no se carga? ¿se muestrea una zona vacía?). **Pero el bloqueo de "no se emite el contenido" está
  resuelto**: el juego emite texto/atlas en cuanto se confirma el selector.
- **Consecuencia de producto**: el input (Cross) es **parte del flujo normal**; para el hito hace falta
  (a) que el runtime entregue el pad (ya funciona la FSM) o simular la confirmación, y (b) que los texeles
  del atlas resuelvan color. Consulta: `work/gemini/msg_gemini_v76.md`.

### (16) v76: el "bug de cache de CLUT" queda REFUTADO por medición (y el `cbp` del atlas es 10300)

- ✅ Confirmado de v76: tras forzar Cross el flujo sigue (Task#4 `sub 10 → 0`), **se sube el atlas**
  (`dbp=10272`) y hay **2424–2647 draws con `tbp0=10272`**. `FUN_0083d430` y `FUN_0083d6b0` existen
  (candidatos a Title Screen / menú).
- ❌ **Su diagnóstico de "cache de CLUT desactualizado" NO cierra**:
  - Los draws del atlas tienen **`cld=1`** (`[glyph-draw] cbp=10300 cld=1 csm=0 csa=0`), y con `cld=1`
    `LoadClut` **recarga en cada escritura de TEX0** (`case 1: break` → `LoadClutUnlocked`); el `case 4`
    que Gemini señaló **no se usa**.
  - **`m_clut` NO está vacío**: `[glyph-draw] m_clut[1]=0xf m_clut[257]=0x0 m_clut[15]=0x349
    m_clut[271]=0x502` (entrada 1 = `0x0000000F`, entrada 15 = `0x05020349`).
  - **Forzar la recarga** (`SWORD_CLUT_RELOAD=1`, que ignora el cache y llama a `LoadClutUnlocked` en cada
    TEX0) **no cambia nada**: `texel=0x0`, `rgbNZ=0`, `vramNonZero=6238`.
- **Dato nuevo**: los draws del atlas usan **`cbp=10300` → `0x283000`** (page 321 + 0x1000), distinto del
  `cbp=10268` (`0x281C00`) de la page 320. La entrada 1 de esa paleta queda `0x0000000F` (RGB casi 0,
  **alpha 0**) ⇒ el texel compuesto sigue siendo 0. En el `GS_vram.bin` real, `0x283000` tiene
  `nz=361/1024` y sus primeros bytes (`00000000 00000000 00020000 00020000 …`) **no parecen una paleta de
  colores**.
- ⇒ **Queda por explicar el muestreo del atlas**: o el `cbp=10300` no es la paleta correcta, o el índice
  muestreado es 0 (fondo), o el direccionamiento CSM1 de la CLUT está mal. Consulta:
  `work/gemini/msg_gemini_v77.md`.

### (17) CAUSA CONCRETA: la page 321 de nuestra VRAM es una **COPIA de la page 320** (no el atlas)

- ✅ **Verificado de v77**: `10300*256 = 0x283C00` (mi `0x283000` era aritmética mal); la paleta real en
  `0x283C00` tiene `entry1 = 0x000F020B`, `entry15 = 0x01000B02`.
- **Dump de nuestra VRAM** (`SWORD_DUMP_VRAM=/tmp/our_vram.bin`, present #900, con Cross forzado) vs
  `GS_vram.bin`:
  - **Page 320: byte-idéntica (8192/8192)** ✓ (`our nz=3119` = `real nz=3119`).
  - **Page 321: sólo 3196/8192 bytes iguales**, `our nz=3119` vs `real nz=3188`.
    - `0x282000` (inicio): nuestro `005a005a005a005a001c451c481c451c` = **el patrón de la page 320**;
      real `00000000000100000002000000030000` (datos de glifos).
    - `0x283C00` (CLUT de `cbp=10300`): nuestro `000000000f0000003a0202042020201c` =
      **la paleta de 10268** (`entry1=0x0000000F`, `entry15=0x05020349`, idéntica a `0x281C00`);
      real = `entry1=0x000F020B`.
  - `0x281C00` (CLUT de `cbp=10268`): **idéntica** en ambos (`entry1=0x0000000F`) ✓.
- **⇒ La causa concreta**: las subidas a `dbp=10272` (n=6..10, mismas geometrías 32×32/16×16/8×8/8×4/16×16
  que las de `dbp=10240`) llevan **el mismo payload que las de la page 320**: escriben una **copia de la
  page 320** en la page 321 (incluida su CLUT). No es un bug de CLUT ni de muestreo: **los datos del atlas
  no están llegando a VRAM**.
- **`[sample-diag] su=0 sv=0 rawIdx=0 clutVal=0x0`** (primeras 12 muestras) y `[tex-hist]
  withNonZeroTexel=0` son consistentes: se muestrea una zona que (en nuestra copia) es 0/transparente.
- **Nota**: `[clut-load] cbp=10300 vram=0x283c00 e1=0xf` — nuestro runtime **sí** lee `0x283C00`, pero el
  contenido de esa zona es la paleta de 10268 porque **la page 321 es una copia**. ⇒ `LoadClut` y el
  decode de `CBP` están **bien**.
- **Próximo paso**: por qué el upload de `dbp=10272` lleva el payload de la page 320. Consulta:
  `work/gemini/msg_gemini_v78.md`.

### (18) Inyectar la page 321 real SÍ resuelve los texeles (`withNonZeroTexel` 0 → 1521/1600), pero `rgbNZ` sigue 0

- **PoC nuevo (env-gated)**: `SWORD_INJECT_PAGE321=<GS sin header>` copia la page 321 real
  (`0x282000..0x284000`) en nuestra VRAM **antes de cada snapshot de present** (en
  `GSCpuBackend::Present`). Log: `[inject-page321] loaded=8192`.
- **EFECTO**: `[tex-hist] TOTAL texturedPrims=1600 withNonZeroTexel=1521` (antes **0**) ⇒ con el atlas real
  en VRAM **los texeles sí resuelven**.
- **PERO**: `[gs:diag] crt1 (fbp=128): rgbNZ=0 aNZ=151713` **sigue igual**, y con
  `SWORD_FORCE_VTX_RGB=1` (MODULATE con vértice RGB=1.0 para `tbp0>=10240`) **tampoco cambia**
  (`withNonZeroTexel=1289/1400`, `rgbNZ=0`). `vramNonZero=6307`. La última `[gs:present]` alterna
  `fbpDisp1=0`/`ctx=0/8/0`.
- **Dato que abre la duda**: la paleta real en `0x283C00` tiene `entry1 = 0x000F020B` ⇒ **A = 0x00**; la
  alpha test (`TEST=0x5002b`: ATST=5 `alpha>=2`) descartaría esos texeles. ¿Cómo renderiza el real?
  (¿usa otras entradas? ¿la CLUT de los glifos visibles está en otro rango?).
- **Verificado de v78**: `10300*256=0x283C00` ✓; el "descriptor table" `0x8A42F0` contiene enteros chicos
  (`0x100,0x140,0x180,0x200`), **no punteros** ⇒ su explicación del `$a3=0` **no está probada**; y la RAM
  real en `0x00E63000` está **toda en cero** (los glifos no están ahí; sí hay datos tipo índice desde
  `0xE63660`). Consulta: `work/gemini/msg_gemini_v79.md`.

### (19) v79: paleta 4-bit verificada, pero la normalización NO destraba el RGB

- ✅ **Verificada la estadística de paletas de v79**:
  - **`0x283C00` (atlas, `cbp=10300`)**: **62/256 entradas con A>0**, con **A en [1,15]** y **RGB ≤ 15**
    (p. ej. entry8 `0x07000201` = R1 G2 B0 A7; entry9 `0x0F000B00` = R0 G11 B0 A15).
  - **`0x281C00` (page 320, `cbp=10268`)**: 89/256 con A>0, **A hasta 128 y RGB hasta 236** (paleta normal).
  - ⇒ La CLUT del atlas tiene valores de 4 bits (sospechoso: ¿es realmente una paleta o datos de glifo?).
- **PoC `SWORD_UI_COLOR_FIX=1`** (en `combineTexture`, para `tbp0>=10240`: A 1..15 → ×128/15, RGB ≤15 →
  ×17, vértice RGB 0 → 128, va 0 → 128), junto con `SWORD_INJECT_PAGE321` + Cross + `SWORD_PRESENT_CTX`:
  **`rgbNZ=0` sigue** (`crt1 (fbp=128): rgbNZ=0 aNZ=151713`), `vramNonZero=6307`,
  `[tex-hist] withNonZeroTexel=1289/1400`.
- **Por qué**: las muestras del atlas resuelven a **índice 0 / fondo**:
  `[sample-diag] su=0 sv=0 rawIdx=0 clutVal=0x70202` (entry0 = `0x00070202`, **A=0**) y
  `[glyph-draw] … texel=0x70202`. Con A=0 el alpha test (`ATST=5`, `AREF=2`, `AFAIL=KEEP`) descarta el
  píxel; la normalización sólo actúa si `ta` es 1..15.
  (Caveat: `[sample-diag]` loguea las **primeras 12 muestras**, que pueden ser de prims de padding; el
  `withNonZeroTexel=1289/1400` indica que la mayoría de los prims **sí** muestrean texeles ≠ 0.)
- **Pendiente**: sonda **por píxel** en `WritePixel` para el prim que rasteriza con `tbp0=10272`:
  `rgba` final, `writesAnything()`, z-test, `fbmsk`, `fbp`; y aclarar si `0x283C00` es paleta o datos.
  Consulta: `work/gemini/msg_gemini_v80.md`.

### (20) v80: verificado que el TEX0 real del atlas usa `cbp=10336` (page 323) — **nosotros emitimos `cbp=10300`**

- ✅ **Verificado en la RAM real** (`eeMemory.bin` @ `0xA97BB0`): `20050C05DD30A820` decodifica
  `tbp0=10272 tbw=2 psm=19 tw=7 th=7 tcc=1 tfx=0 **cbp=10336** cpsm=0 csm=0 csa=0 cld=1`.
  Y `0xA97BB8` = `...06` (el A+D de TEX0). Los otros: `tbp0=10368→cbp=10432` (page 326),
  `tbp0=10464→cbp=10496` (page 328). ⇒ **el juego real NO usa `cbp=10300`**.
- **Nuestros draws del atlas**: `[glyph-draw] cbp=10300 … texel=0x70202` ⇒ pedimos la paleta en
  `0x283C00` (que en la page 321 es **datos de glifo**, no paleta) ⇒ entry0 = `0x00070202` (**A=0**) ⇒
  alpha test descarta ⇒ `rgbNZ=0`.
- **PoC de v80 implementado** (`SWORD_INJECT_UI_VRAM=<GS sin header>`): inyecta las **11 páginas**
  (`0x280000..0x296000`, **90112 B**) + invalida `m_texturePageCache`/`m_clutCbp`. Log:
  `[inject-ui-vram] loaded=90112`, `copiadas 11 paginas + caches invalidados`, `vramNonZero=24293`.
  **NO cambia el resultado**: sigue `cbp=10300`, `texel=0x70202`, `rgbNZ=0` ⇒ **inyectar VRAM no cambia el
  `CBP` que el juego pide**.
- **⇒ El objetivo ahora es el `CBP`**: nuestro motor pide `+28` bloques (10272+28=10300) donde el real pide
  `+64` (10272+64=10336, page 323). Es coherente con que **la subida a `dbp=10272` sea una copia del asset
  de la page 320** (mismo layout +28). Hay que encontrar **quién calcula el `CBP`/dónde se sube el CLUT del
  atlas**. Consulta: `work/gemini/msg_gemini_v81.md`.

### (21) v81: descriptores verificados y `CBP` forzado a 10336 — el texel pasa a 0 (índice 0), `rgbNZ` sigue 0

- ✅ **Verificado de v81 en la RAM real**:
  - Tabla `0xA95650` (registros de 12 B `{desc, vram, size}`): entry0 `desc=0xE80090, vram=0xA0000,
    size=0x800`; entry1 **`desc=0xE702E0, vram=0xA0800, size=0x1800`**; entry2 `0xE6BBE0/0xA2000`;
    entry3 `0xE76D60/0xA3800`; entry4 `0xE749E0/0xA4800`.
  - Descriptor chrome `0xE80090` `+0x3C` → `tex0 = 0x200503859930A800` (**tbp0=10240 tw=6 th=6 cbp=10268**).
  - Descriptor fuente `0xE702E0` `+0x3C` → **`0x20050C05DD30A820`** (**tbp0=10272 tw=7 th=7 cbp=10336**).
  - Magic `0x573ABCDE` presente (2530 ocurrencias).
- **PoC `SWORD_FORCE_FONT_CBP=1`** (en el handler de `TEX0`: si `tbp0==10272 && cbp==10300` → `cbp=10336`),
  junto con `SWORD_INJECT_UI_VRAM` (11 páginas) + Cross + `SWORD_PRESENT_CTX`:
  `[force-cbp] tbp0=10272 cbp 10300 -> 10336 (page 323)` ✓ aplicado; `[glyph-draw] cbp=10336 … texel=0x0`
  (antes `0x70202`). **Pero `rgbNZ=0` sigue** (`crt1 (fbp=128): rgbNZ=0 aNZ=151713`), `vramNonZero=24293`.
- **Lectura**: con la paleta correcta, el **índice muestreado es 0** → entrada 0 = transparente
  (así es también en la paleta real) ⇒ alpha test descarta. ⇒ **El problema ahora es que los draws del
  atlas muestrean índice 0** (¿coordenadas UV en zona vacía? ¿textura no en la page 321 real?).
- Consulta: `work/gemini/msg_gemini_v82.md`.

### (22) CONFIRMADO: nuestro motor usa el descriptor de CHROME (64×64) para el atlas

- **TEX0 crudo que emite nuestro juego** (`[force-tex0] raw …`): **`0x200507859930A820`** →
  `tbp0=10272 tbw=2 psm=19 **tw=6 th=6** cbp=**10300** cpsm=0 cld=1`.
  Es **el TEX0 del descriptor de chrome** (`0x200503859930A800`, tbp0=10240/tw=6/th=6/cbp=10268) **con el
  `tbp0` parcheado**. El descriptor real de la fuente (`0xE702E0`) es **`0x20050C05DD30A820`**
  (`tw=7 th=7` = 128×128, `cbp=10336`).
  ⇒ **Confirmada al 100% la explicación de v81**: el gestor de texturas no registró `fnt_on_*` y usó el
  fallback de chrome (64×64) para `tbp0=10272`.
- **PoC de v81 (`SWORD_FORCE_FONT_CBP`)**: forzando el **TEX0 completo** (`0x20050C05DD30A820`) +
  `SWORD_INJECT_UI_VRAM` (11 páginas reales) + Cross + `SWORD_PRESENT_CTX`:
  `[force-tex0]` aplicado, `[glyph-draw] cbp=10336`, pero **`texel=0x0`** y **`rgbNZ=0`** siguen
  (`crt1 (fbp=128): rgbNZ=0 aNZ=151713`).
- **Caveat**: `[glyph-draw]` loguea los **primeros 8 prims** (probablemente padding, `su=sv=0`); no sirve
  para concluir sobre los prims que dibujan. Falta la sonda **por píxel filtrada a `texUf/texVf != 0`**.
- Consulta: `work/gemini/msg_gemini_v82.md`.

### (23) Objetivo redefinido (usuario): **ver la pantalla del selector y controlarla con el pad**. Dos hallazgos

- **(a) El pad del host NO llega al juego.** Corrida con `SWORD_PAD_PRESS=cross SWORD_PAD_TOGGLE=1`
  (el harness de `ps2_pad.cpp`, el mismo camino que el teclado) **sin** `SWORD_CONFIRM_MENU`:
  `[confirm-menu]` = **0** y **`t3sub` se queda en 10** (`f=1650`). ⇒ El `PSPadBackend::readState`
  (mapeo X/Space=Cross, flechas, Enter=Start) **no es lo que lee `func_51C7C0`**; el juego lee el pad por
  **libpad/padman (IOP)**, no por el stub HLE. ⇒ **"usar el pad" todavía hay que cablearlo** (hook de
  `func_51C7C0` o el camino real de libpad).
- **(b) TODAS las prims texturizadas tienen ST variable… y NINGUNA muestrea un texel ≠ 0.**
  `[tex-hist] TOTAL texturedPrims=800 withNonZeroTexel=0 **stVaryPrims=800
  stVaryWithNonZeroTexel=0**`. O sea: las UV **sí** varían en las 800 prims, pero el lookup devuelve 0
  en todas.
  - Como la **page 320 es byte-idéntica al real** (8192/8192) y tiene 3119 bytes ≠ 0, que **miles** de
    muestras den 0 es estadísticamente imposible salvo que el **direccionamiento PSMT8 esté mal**.
  - **Nuevo sospechoso principal (bug del runtime, no de assets)**: `ReadTextureVramUnlocked(P8, …)`.
    (El de CLUT/CT32 funciona: `m_clut` coincide con `0x281C00` del real.)
- **Nota de método**: mi conclusión previa "ST degenerado" era **falsa** — venía de mirar 1 prim; el
  agregado dice `stVaryPrims=800/800`.
- **Hito del usuario**: ver el selector + controlarlo. Requiere (a) cablear el pad y (b) arreglar el
  muestreo PSMT8. **Próximo paso (nuestro, no de Gemini)**: verificar el direccionamiento PSMT8
  (`ReadTextureVramUnlocked(P8)`) contra PCSX2 (`GSLocalMemory::m_psm[PSM_T8]`) usando la page 320
  (que es byte-idéntica al real): si la fórmula difiere, es un **bug del runtime** y explicaría el
  `texelNZ=0` universal.

### (24) v82 verificado/refutado; y **el chrome (page 320 nativa) también da texel 0**

- ✅ **Verificado**: la tabla de los 16 primeros colores de la page 323 (`0x286000`) de v82 es **exacta**
  (`e0=0`, `e1=0x26000000`, `e2..e15` con A=128, `e15=0x80F3F3F3`).
- ❌ **REFUTADO su "desfase de 425 B"**: el PoC **no** lee `GS.bin` con header. Se pasa
  `SWORD_INJECT_UI_VRAM=/tmp/GS_vram.bin` = **4194304 B exactos** (header ya quitado con `dd skip=425`;
  el comentario del código dice `<GS sin header>`). `work/teleport/GS.bin` = 4194813 = 4 MB + 509
  (425 header + 84 cola). Con el archivo sin header, `fseek(pf,0x280000)` cae **exacto** en VRAM
  `0x280000` ⇒ **alineado** (`[inject-ui-vram] loaded=90112`). ⇒ **El `texel=0` no viene del desplazamiento.**
- 🔑 **Dato decisivo**: los prims de **`tbp0=10240` (page 320, byte-idéntica al real)** también dan
  `texelNZ=0` ⇒ **el problema no es la inyección ni la paleta: es la lectura de textura / el índice**.
- **Corrección de un error mío**: "ST degenerado" era **falso**; el agregado dice
  `stVaryPrims=800/800` (todas las prims texturizadas tienen ST variable) pero
  `stVaryWithNonZeroTexel=0` (ninguna muestrea ≠ 0).
- `[uv-probe]` (6 prims): `fst=0` con **`s0=s1=s2=0`** y **`u=0x3400 v=0x3ae0`** poblados. En PCSX2,
  `fst=0` ⇒ STQ (floats) — verificado en `GS/GSLzma.h:188`; nuestro decode de `fst` (bit 8,
  `GS/GSRegs.h:706-715`) es **correcto**. ⇒ muestreamos **ST=0** ⇒ texel (0,0) ⇒ índice 0 ⇒ descarte.
- **Consulta milestone-oriented**: `work/gemini/msg_gemini_v83.md` (ver el selector + cablear el pad).

### (25) v83: Resolución de `fst=0` vs STQ, auditoría PSMT8 y cableado canónico del pad host

- **Misterio de `fst=0` y `uv=0x3400/0x3ae0` resuelto**:
  - En `gs_frontend.cpp`, los campos `m_curU` y `m_curV` retienen valores residuales de arranque cuando no se emite el registro UV. Con `fst=0`, el juego usa **exclusivamente STQ** (registro 2). El valor UV residual impreso en el log era inerte.
  - La sonda `[uv-probe]` se agotó tras 6 vértices degenerados de padding `(xyz=(2048,2048), s=t=0)`. En los triángulos reales posteriores (#2, #3, #4...), los vértices traen ST de coma flotante variable ($s \approx 0.48633, t \approx 0.0117187$).
- **Por qué el chrome (page 320) dio texel=0**:
  - Para el triángulo #3, los 261 fragmentos rasterizados muestrean $(\text{sampleU}=31, \text{sampleV}=0)$ de forma mono-punto.
  - En `/tmp/GS_vram.bin` en la página 320 (`0x280136`), el índice en $(31, 0)$ es `0x00`. En la CLUT de la página 320 (`cbp=10268`), la entrada 0 es `0x00000000` (Alpha=0). Con `ATST=5, AREF=2`, el fragmento es descartado.
- **Auditoría PSMT8 vs PCSX2**:
  - `ps2_gs_psmt8.h` (`PageExtent`, `BlockExtent`, `ColumnTable8`, `BlockTableP8`, wrap/clamp) es **idéntico término a término** a `GSLocalMemory.cpp`. La lógica de direccionamiento PSMT8 del runtime es 100% fiel al hardware y a PCSX2.
- **Arquitectura de Pad y Cableado Natural**:
  - Desensamblado de `func_51C7C0` (`thunk_FUN_0051e700_0x51c7c0.cpp` / `FUN_0051e700`): el juego lee `lhu $s0, 0x2($s0)` donde `$s0 = *(0x00A42500) = 0x00A42100` (buffer de puerto 0 en `0x00A42102`) y retorna en `$v0`.
  - Los botones retornados en `$v0` son **active-high**: Cross = `0x0040`, Circle = `0x0020`, Square = `0x4000`, Triangle = `0x1000`, Up = `0x8000`, Down = `0x2000`, Left = `0x0002`, Right = `0x0008`, Start = `0x0004`, Select = `0x0001`.
  - `FUN_0083d990` (`sub=10`): línea 605 comprueba `andi $v0, $v0, 0xA000` (Up/Down para alternar 50Hz/60Hz con sonido `0x62DD60(0x7D)`), y línea 727 comprueba `andi $v0, $v0, 0x0040` (Cross para confirmar).
  - Implementación: `thunk_FUN_0051e700_0x51c7c0.cpp` llama a `runtime->padBackend().readState(0, 0, padData, sizeof(padData))`, traduce los bits active-low a la máscara del motor, actualiza `0x00A42102` y retorna en `$v0`.
- **Invalidación de caches de VRAM**:
  - Eliminado el guard `<= 3u` en `gs_cpu_backend.cpp:2237` para asegurar que `m_texturePageCache.Invalidate()` y `m_clutCbp.fill(0xFFFFFFFFu)` se ejecuten en cada present durante inyección.

### (26) v83 verificado en vivo: el **pad SÍ funciona** (control ✅), pero el "fix" de redondeo de texel es **incorrecto** (refutado con PCSX2) y `rgbNZ` sigue 0

- ✅ **CONTROL (hito) — verificado en vivo**: con `SWORD_PAD_PRESS=cross SWORD_PAD_TOGGLE=1` y **sin**
  `SWORD_CONFIRM_MENU` (count = 0): `[pad-host] port=0 buttons=0x40` y el selector
  **`t3sub` 10 → 11 → 0** (`f=270`, `f=430`). ⇒ El cableado del pad en
  `thunk_FUN_0051e700_0x51c7c0.cpp` (lee `padBackend().readState`, escribe `0xA42102`, retorna en `$v0`)
  **funciona por el camino real del motor**. **La mitad "controlar" del hito está hecha.**
- ❌ **REFUTADO el "fix" de muestreo nearest** (`floor(texUf + 0.5f)` en `gs_cpu_backend.cpp:1214`):
  en PCSX2 `GS/Renderers/SW/GSDrawScanline.cpp:835-844` el sesgo de medio texel
  (`u -= 0x8000`) se aplica **solo** bajo `if (sel.ltf)` (bilinear), y el texel se deriva con
  `uv0 = u.sra32<16>()` = **shift aritmético = truncamiento**, sin redondeo. Nuestra versión original
  (`static_cast<int>(texUf)`) era **la correcta**; sumar 0.5 = **desplazamiento de medio texel**
  (dibuja lo que el real descarta). **Revertido** con el comentario que cita a PCSX2.
- ✅ **Verificado de v83 (datos)**: la fila `y=0` de la page 320 tiene **2/64** no-cero vs **50-55/64** en
  `y=1..4`; `(31,0)=0x00` vs `(31,1)=0x45`; `CLUT(cbp=10268) e0=0x00000000, e69=0x05020376` (coincide
  exacto con lo que afirmó). Y en el log en vivo `/tmp/sword_etheria_v84_test.log`: `texelNZ=256` (×6) y
  `aNZ=246080` sí ocurrieron.
- ⚠️ **Pero su atribución causal era errónea**: tras **revertir** el redondeo, `withNonZeroTexel` volvió a
  0 y **`aNZ=246080` sigue apareciendo** ⇒ los 246080 píxeles con alpha **no** vienen del muestreo sino del
  **velo de fade** (quad sin textura, vértice RGB=0, alpha≠0 ⇒ negro con alpha). O sea: el "fix" no aportaba
  nada visible (`rgbNZ=0` en ambos casos) y sí dibujaba píxeles que el real descarta.
- **Estado del hito**: **CONTROL ✅** / **VER ❌** — bloqueado por la lista de UI vacía (ver §(27)).
- **Fragilidad a anotar**: el cableado del pad vive en `work/generated/thunk_..._0x51c7c0.cpp`, que es
  **gitignored y se regenera desde el CSV** ⇒ se pierde al regenerar. Debería moverse a un override del
  runtime (`game_overrides.cpp` / `replaceFunction`) para que sea durable.

### (27) MEDIDO: la lista de UI (`0xA88874`) está **vacía** en el selector — y también en el real está "viva"

Sonda nueva en el frame-hook (`game_overrides.cpp`, junto a `[task]`): `uiNext` (campo `+0` del centinela
`0xA88874`) y `uiCount` (recorrido de la lista doble).

```
f=1   sub=0 t3sub=0   uiNext=0xcb6418 uiCount=10
f=3   sub=0 t3sub=0   uiNext=0xa88874 uiCount=0
f=20  sub=1 t3sub=1   uiNext=0xa88874 uiCount=0
f=50  sub=2 t3sub=3   uiNext=0xe1f4b8 uiCount=1
f=90  sub=1 t3sub=1   uiNext=0xa88874 uiCount=0
f=400 sub=1 t3sub=0   uiNext=0xa88874 uiCount=0
```

- **Hecho medido**: la lista **se puebla al arrancar (10 objetos)** y luego **se vacía**; en el selector
  (`t3sub=10`) queda **vacía** (`uiCount=0` en 40 muestras). ⇒ `FUN_0083d290` itera 0 objetos ⇒ sólo se
  emite el velo (coincide con `rgbNZ=0`, `aNZ>0`).
- **En el real** (`eeMemory.bin`): centinela `0xA88874` → `next=0x00CB5818`, `prev=0x00E8C058` ⇒ **6 objetos**
  (verificado). ⇒ Los objetos del selector **no se crean/enlazan** en nuestro run.
- **CONTROL ✅ / VER ❌**: el hito queda a un solo eslabón (creación de los objetos de UI del selector).
- Consulta: `work/gemini/msg_gemini_v84.md`.

