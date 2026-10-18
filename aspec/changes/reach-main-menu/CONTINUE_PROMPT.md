# Arranque de sesión — Sword of Etheria (recomp PS2) → MENÚ VISIBLE

> Pegar este archivo al inicio de la sesión nueva y arrancar con:
>
> ```
> /cleto-apply reach-main-menu
> ```

---

## Prompt (esto es lo que hay que hacer)

Seguí el hito **"menú principal visible"** de la change `reach-main-menu` con `/cleto-apply reach-main-menu`.
Las tareas pendientes vigentes están en `aspec/changes/reach-main-menu/tasks.md`
§ **"Sesión 2026-10-17 (noche) — TEXTURAS"** — empezá por ahí, e implementalas en orden.

Antes de tocar nada, leé en este orden:

1. `aspec/changes/reach-main-menu/tasks.md` §Sesión 2026-10-17 (noche) — las 5 tareas pendientes.
2. `aspec/changes/reach-main-menu/decisions.md` §**rondas 16 a 20** (2026-10-17) — las mediciones vigentes.
3. `work/gemini/README.md` §CAMINOS MUERTOS — hipótesis ya refutadas con evidencia; **no repetirlas**.

**Si te trabás, pedime que consulte a Gemini** (protocolo al final). Yo hago de proxy: yo pego la consulta
en Gemini y te traigo la respuesta. Vos no llamás a Gemini directamente.

**No re-descubras** lo que ya está medido (resumen abajo): el camino GS/DMA del runtime está **probado byte a
byte** contra la consola y es correcto; el problema **no** es el GS, ni el present, ni el estado del gestor de
texturas.

---

## Estado verificado al 2026-10-17 (noche)

**1. El runtime NO es la causa (probado por bytes).**
Nuestra VRAM del menú coincide **byte a byte** con la del real en lo que sí subimos:
page `0x280000` (TBP0=10240) → **0 de 8192** bytes distintos; su CLUT (`CBP=10268`) → **0 de 1024**.
Ojo con el artefacto: **`work/teleport/GS.bin` NO es VRAM cruda** — son **425 bytes de header + 4 MB de VRAM
+ 84 de cola** (verificado por contenido). Comparación reproducible: `python3 work/teleport/diff_vram.py`
(usa `work/teleport/recomp_vram_menu.bin`, que es nuestro dump).

**2. Lo que falta es el atlas de interfaz.**
Pages `0x282000`–`0x294000` (tbp 10272–10560): el real tiene **~21 KB de texeles PSMT8 + CLUTs**, nosotros
**0**. Hay **2738** draws texturizados y su `TEX0` es `TBP0=10240 TBW=2 PSM=19(PSMT8) TW=64 TH=64
TCC=1 TFX=0(MODULATE) CBP=10268 CPSM=0` ⇒ **con `TCC=1` el color sale 100% de la textura** (el `rgba=0` del
vértice no importa). Sin esas texturas: negro con alpha ⇒ `[gs:diag] crt1 … rgbNZ=0, aNZ≈286720`.

**3. La subida de texturas es un pase ÚNICO de arranque** (contado con `SWORD_TRACE_BRANCH`):
`entry_0051f4f8` → `FUN_00512ab0` (**1 vez**) → `FUN_0051f450` runner (**1**) → gate `func_6D5980` (**1**) →
`func_51EF60(a2=0x20,a3=0x203)`/`func_6F1F90(1)`/`func_6D5500`/`func_6D5DF8` → wrapper `FUN_006d57e8`
(**opcode 2**, 1 vez) → dispatcher `FUN_006f0a38` (54 llamadas por opcode) → uploader `FUN_006efd28` (**1**).
El bloque del runner **itera sobre el gestor** (`0x51f544: bnez $v0 → 0x51f564`) y ejecutó **una vez**: en ese
instante la cola tenía **un solo asset listo**.

**4. El estado del gestor es byte-idéntico al real… salvo 3 palabras.**
Gestor en `0xA887B8`: `+0x8` contador, `+0x10` vtable (`0xA887C8`, slot `+4` = `0x006f0a38`), **`+0xBC`
centinela de lista (`0xA88874`)**, `+0x124` flag del gate (`0xA888DC`), `+0x128`.
Diferencias contra `work/teleport/eeMemory.bin`:
- `0xA887C0`: **345 vs 629** (contador; probablemente de tiempo ⇒ no concluyente),
- **`0xA88874`/`0xA88878`: en nosotros auto-punteros (lista vacía) y los slots `+8/+0xC/+0x10` en 0; en el real
  vtable de la clase (`0x004c6568`/`0x004cb430`/`0x004c6c20`) + lista doblemente enlazada con 6 nodos**
  (`0xE8C058 → 0xE8C2D8 → 0xE8C558 → 0xE81F18 → 0xCB6028 → 0xCB5818`, paso 0x280, floats `0x3F800000` = 1.0
  y `0x3F7FFFFF`) — objetos de **UI/transforms**, no texturas.

**5. Ese centinela NUNCA se escribe en nuestro run** — medido con watchpoint de escritura
(`SWORD_WP_WRITER=a87000-a8a000`, 100 s, **0 capturas**). El instalador en lote `FUN_006d13a0` **sí** corre
(1 vez, desde `0x6d5b64` = `FUN_006d5ad0`) pero escribe otras tablas, no el centinela.

⇒ **El eslabón**: el juego nunca *construye/enlaza* esa lista de 6 objetos de UI (y por eso tampoco llega el
atlas). Hay que encontrar la función que la enlaza y el gate que impide que corra.

---

## Protocolo Gemini (cuando me lo pidas)

1. **Vos me pedís la consulta y yo la paso** (nunca llamás a Gemini vos).
2. Escribí la consulta en `work/gemini/msg_gemini_v70.md` (v71, v72… sucesivos). **El primer mensaje debe
   incluir el contexto de trabajo**: objetivo del hito, artefactos y rutas, las mediciones verificadas (las
   de arriba), las preguntas **numeradas**, y las reglas del proyecto (leer el artefacto antes de afirmar;
   A/B: qué esperar si la hipótesis es cierta **y** si es falsa; el ISO/ELF está en `work/elf/SLES_537.68`,
   offset = `vaddr − 0x4C0000 + 0x100`; el generado en `work/generated/`; PCSX2 local en `tools/ps2emu/pcsx2/`
   sólo como referencia, **no copiar código** porque el repo del juego es MIT y PCSX2 es GPL-3.0).
3. Yo pego la respuesta en `work/gemini/msg_gemini_Responsev70.md` y seguimos desde ahí.
4. **Pregunta candidata para el v70**: *"¿Qué función de este motor construye/enlaza la lista de objetos de
   UI cuyo centinela está en `0xA887B8+0xBC` (clase con vtable `0x004c6568`/`0x004cb430`/`0x004c6c20`)? ¿Qué
   la gatea para que no corra? ¿Y por qué el atlas de interfaz (pages `0x282000`–`0x294000`) nunca se sube si
   el estado del gestor coincide byte a byte con el de la consola?"* — acompañado de: el pase único de startup,
   las direcciones y conteos de arriba, y la evidencia de que el centinela nunca se escribe.

---

## Reglas de método (todas aprendidas a golpes — respetarlas)

1. **LEER EL ARTEFACTO ANTES DE AFIRMAR.** ELF en `work/elf/SLES_537.68`; generado en `work/generated/`
   (un `.cpp` por función, con la instrucción original en comentario). Ya hubo >10 conclusiones falsas por
   inferir de un grep o de un número de línea.
2. **Hooks `replaceFunction`: sólo sobre funciones COMPLETAS**; sobre una dirección interna son **inertes**.
3. **El orden de líneas del generado ≠ el orden de direcciones** (el `goto label_` va al final del label).
4. **Los conteos con `grep -c` sobre estos logs son mentira** (las líneas se concatenan): usar `grep -o` o `sed`.
5. **El generado no es consistente en mayúsculas**: grepear direcciones en ambos casos.
6. **Un log vacío puede ser falta de flush**, no ausencia de evento. `SWORD_TRACE_BRANCH` ahora **sí** flushea
   (fix del 2026-10-17 en el fork), pero cualquier otro `ofstream` propio puede no hacerlo.
7. **Trampas de artefactos ya conocidas**: `GS.bin` tiene 425 B de header; `SWORD_DUMP_VRAM` vuelca en present
   #300/#900/#1500 (las subidas caen entre #300 y #830 ⇒ usar el dump tardío); `timeout` mata con SIGTERM ⇒
   los dumps a la salida pueden no escribirse; el heap del recomp está corrido **+0x150** (comparar *por
   contenido*, no por dirección); `qwc=0` en un kick **no** significa "sin geometría" (modo cadena por `TADR`).
8. **Watchpoints**: `SWORD_WP_WRITER=<lo>-<hi>` (hex) activa el hook por `mprotect`+SIGSEGV (atrapa también
   `FAST_WRITE32`). Ojo: `wpInstall` **redondea el inicio hacia arriba** ⇒ dar **una página de margen**
   (`a87000-a8a000` para vigilar `0xA88874`/`0xA888DC`).
9. **Medir contra savestate antes de encadenar deducciones**: `work/pcsx2_states/*.p2s` (son ZIP con
   `eeMemory.bin` de 32 MB) y la RAM de consola en `work/teleport/eeMemory.bin`.

---

## Comandos

```bash
# build (-j4; más = OOM). El binario es ~382 MB.
cmake --build work/build-game/out-linux --target sword_etheria -j4

# corrida baseline (75 s alcanza para llegar al dibujo; 180 s para ver fases)
SWORD_SIF_SEMA=1 timeout 75 ./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68 > /tmp/run.log 2>&1

# trace de control de flujo -> /tmp/sword_branch.log (tid/src/tgt/kind/a0/a1)
SWORD_TRACE_BRANCH=<lo>-<hi> SWORD_SIF_SEMA=1 timeout 90 ./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68

# dumps
SWORD_DUMP_VRAM=/tmp/vram.bin SWORD_RDRAM_DUMP_LATE=/tmp/rdram.bin SWORD_SIF_SEMA=1 timeout 155 ./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68
python3 work/teleport/diff_vram.py          # nuestro VRAM vs GS.bin real, page por page

# watchpoint de escritores (¡con una página de margen!)
SWORD_WP_WRITER=a87000-a8a000 SWORD_SIF_SEMA=1 timeout 100 ./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68

# A/B del present (paso 4 de Gemini): ignora CRT1 si dispfb1 quedó en el default
SWORD_NO_CRT1_DEFAULT=1 SWORD_SIF_SEMA=1 timeout 75 ./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68
```

## Git y remotos

- Repo del juego: branch `visual/advance-display-and-main-loop`, push a `origin`
  (`git@github.com:AncletoCEO/Sword-Of-Etheria-PC-Recomp.git`). **`main` se sube cuando haya algo visual.**
- Runtime (fork GPLv3): `_external/PS2Recomp`, branch **`diag-loader-rpc`**, único remoto `fork`
  (`AncletoCEO/Ps2Recomp-of-etheria`). `remote.upstream` (ran-j) fue eliminado: **todo push va a AncletoCEO**.
  El repo del juego lo ve por el symlink `tools/PS2Recomp`.
- El CI de release pinea un **commit** (`7364cc6`), no un branch: lo que no esté commiteado/pusheado no entra.
- `work/` está **fuera de git** (no versiona nada con copyright).

## Instrumentación que quedó puesta

**Runtime** (`game_overrides.cpp`): `[frame-loop]` (ENTER/YIELD/RETURN con `pcIn/pcOut/raIn/raOut/spIn/spOut/dsp`),
`[pad-*]`, `[dma:kick]`, `[dma-reg]`, `[tick-prof]`, `[task]`, `[ld-enqueue]`, `[phase-flag]`, `[rpc-*]`.
**GS** (`gs_frontend.cpp`/`gs_cpu_backend.cpp`): `[gs:reg]` (toda escritura A+D, deduplicada), `[gs-upload]`
(cada `TRXDIR` con destino/formato/tamaño), `[gs:content]` (prims texturizados), `[gs:present]`/`[gs:diag]`
(valid1/valid2, dispfb, `vramNonZero`, `rgbNZ`/`aNZ`), dump de VRAM configurable, A/B `SWORD_NO_CRT1_DEFAULT`.
**Memoria** (`ps2_memory.cpp`): `[gif-img]`/`[gif-chain]` (forma de las cadenas GIF), `SWORD_WP_WRITER` con
rango configurable.
**Temporal (se pierde al regenerar el CSV)**: probes en `work/generated/FUN_00512630_0x512630.cpp` y
`FUN_00500490_0x500490.cpp`.
