# Tasks: reach-playable-game

> Abierto 2026-10-19. Estado de partida y evidencia: `decisions.md` de este change (digest) +
> `aspec/changes/reach-main-menu/decisions.md` §(1)–(32). Reglas de método al final (obligatorias).

## Hito 1 — Selector de video VISIBLE (lo inmediato)

- [x] **1.1 Identificar los callbacks de render de la UI.** En `0x6DAEF0`, el `jalr` de `0x6daf6c` invoca
      `*(cmd+0x10)` con `cmd = $s0-8`, tras recorrer la lista circular de `widget+0x90`. Instrumentar el
      **valor del puntero** (dirección del callback) por widget y listar las direcciones distintas.
      **Esperado**: pocas funciones (2-6) que emiten prims (quads de caja, sprites de texto, cursor).
      **MEDIDO (SWORD_UI_CB_LOG=1)**: 3 callbacks distintos, todos por `src=0x6daf6c`:
      `0x7547a0` (widget `0xcb4d40`, cmd `0xcb4e20`), `0x756a28` (widget `0xcb5e00`, cmd `0xcb5b50`) y
      `0x756ab0` (widget `0xca7300`, cmd `0xca71d0`). `0x7547a0`/`0x756ab0` se re-invocan por comando
      (a0 = distintos nodos, p. ej. `0xcb4b00`, `0xca3b00`, `0xca2260`...); `0x756a28` >1000 veces.
- [x] **1.2 Medir lo que emiten.** Para esos callbacks: qué `PRIM`/`TEX0`/`UV`/color de vértice producen y
      si esos prims aparecen en `[gs:prims]` con el `tbp0` correcto (¿10240? ¿10272? ¿sin textura?).
      Correlacionar con `[tex-hist]` (¿muestrean el borde transparente?) y con `[gs:diag]`.
      **MEDIDO (SWORD_UI_CB_LOG=1 + SWORD_UI_CB_PRIMS=1, 130 s)**: los callbacks **no emiten prims
      sincrónicamente**: 0 `[ui-cb-prim]` y 0 `[ui-widget-prim]` en toda la corrida (aun con
      `0x756a28` >1000 invocaciones). Solo encolan/arman comandos y llaman a
      `0x7476e8/0x6d6a40/0x6d5f90` (cb `0x7547a0`), `0x6d6a40/0x5ea770/0x6d50e8/0x754a80/0x6f2630`
      (cb `0x756a28`) y `0x7440c0` (cb `0x756ab0`) (`[ui-cb-call]`).
      **Emisión real (diferida)**: por VIF1/VU1 (`[vu1:mscal]` `eePc=0x6e4468 ra=0x6e4ebc`); el último
      store EE es `pc=0x6e433c` en `FUN_006e4068` (0x6e4068-0x6e45d8, escritor de paquetes GS/GIF).
      **Prims observados** (`[gs:content]`): `prim=4` (TRIFAN), `tme=1`, `fst=0`, `tbp0=10240` (page 320),
      `tbw=2`, `psm=19` (PSMT8), `tw=6/th=6` (64x64), `uv=(13312,15072)`, `rgba=(0,0,0,0)`, `pc=0x6e433c`.
      **Muestreo** (`[real-tri-probe]`): `st=(0.48633,0.0117187)` → `texUf=31.1249 texVf=0.75` ⇒ texel
      `(31,0)=0x0`; `[tri-probe] out=(0,0,0,0)`. `[tex-hist]` 600/600 textured prims `texelNZ=0`;
      `[gs:prims]` **todos** los texturedDraws son `tbp0=10240` (page 320), ninguno 10272/atlas.
      `[gs:diag] crt1 (fbp=128) rgbNZ=0 aNZ=0`. La atribución por callback **no aplica** al submit: la
      geometría se difiere al buffer/VU1 y se kickea fuera de `0x6daef0`.
- [x] **1.3 Decidir la causa raíz** entre: (a) los callbacks emiten prims correctos pero el muestreo cae
      en zona vacía; (b) emiten con un estado (TEX0/CLUT/bind de fuente) distinto del real; (c) no emiten
      (un gate distinto de visibilidad/comandos). **A/B obligatorio** para cada hipótesis.
      **DECIDIDO: (b) estado distinto del real.** Evidencia (savestate `videoformat_menu.p2s`):
      `0xA95650` (tabla del gestor de texturas) **toda en cero** en nuestro RDRAM vs **5 entradas** en el
      real (chrome `0xE80090/0xA0000/0x800`, font `0xE702E0/0xA0800/0x1800`, +3); VRAM: page 320
      **byte-idéntica** al real, **pages 321–330 en cero** (el real tiene el atlas de fuente en page 321
      y su CLUT en 323; decodificado PSMT8 se ven los glifos). El descriptor de fuente emitido es el
      fallback del chrome con `tbp0` parcheado (`0x200507859930A820`, `tw=6/th=6`, `cbp=10300`) en vez
      de `0x20050C05DD30A820` (`tw=7/th=7`, `cbp=10336`).
      **A/B**: (a) es **síntoma** — el prim muestreado da `(31,0)=0` porque el atlas/fuente no está y el
      chrome se muestrea en su fila transparente; (c) **falso** — hay prims (TRIFAN tme=1, tbp0=10240)
      emitidas por VU1 XGKICK (`[vu1:mscal] eePc=0x6e4468`), sólo que diferidas. El microprograma VU1 del
      selector **sí** se sube (MPG #2 = primeros bytes de `vu1MicroMem.bin`).
- [x] **1.4 Corregir sin hacks** (runtime si es bug nuestro; estado del juego si es data/gate) y verificar
      **`rgbNZ > 0`** con el selector visible, sin `SWORD_CONFIRM_MENU` ni `SWORD_INJECT_*`.
      **CAUSA RAÍZ ENCONTRADA, PERO VISUALMENTE NO CERRADO (2026-10-20)**: el bug del recompilador era
      real (`COP1 sqrt.s` leía `Fs` en vez de `Ft`; `FUN_006cc5e0 0x6cc628 sqrt.s f1,f1` →
      `sqrt(f0)` → normalización 0 → matriz `-I` → `p3=-292`). Corregido en `fpu_translator.cpp`
      (`SQRT`→`Ft`, `RSQRT`→`fs/sqrt(ft)`) y 94 líneas del generado. Con eso el gate pasa natural
      (`v0=1`), hay 5 binds/10 registers/uploads y `[gs:diag] fbp=0 rgbNZ=261139`. **Pero al decodificar
      la VRAM (PSMCT32, fbp=0, fbw=10) el frame es un fondo magenta 3D, no la caja blanca con texto del
      selector real** (`/tmp/realstate/Screenshot.png`). En present 350/450 no hay texto (solo 32 píxeles
      brillantes, un triángulo rojo); en present 600/900 (f=310, `fadeVal=0`) hay 75k píxeles magenta y
      ningún texto. `rgbNZ>0` lo cumple el fondo, no el selector. **Falta**: aislar si el fondo magenta es
      el escenario 3D que ahora sí dibujan los otros 93 `sqrt` corregidos y tapa/desplaza la UI, o si el
      draw de la UI sigue mal (layout/UV/depth). El A/B con solo el fix de cámara daba `rgbNZ=22560`,
      compatible con el selector; el build con todos los `sqrt` da 261k magenta.
- [x] **1.5 Cerrar el hito**: selector visible + navegable con pad (flechas alternan PAL/NTSC, Cross avanza).
      **PAD VERIFICADO + VISUAL CERRADO (2026-10-20)**: `[pad-host] buttons=0x40` (Cross) y `t3sub`
      10 → 11 → 0/1/3/50; mapeo en `padHook51c7c0` (Up=0x8000, Down=0x2000, Left=0x2, Right=0x8).
      El selector ya se ve limpio (`frame_300.bmp` 512×511: caja/texto/`NTSC`/`PAL`/cursor) y el pad
      lo opera; el Hito 1 queda cerrado.
- [x] **1.6 Verificación VISUAL de las opciones**: volcar la VRAM del frame
      presentado y decodificarla con `game/decode_gs_frame.py` (PSMCT32, fbp=0, fbw=10); confirmar en el
      PNG que se ven **la caja, `Select video format.`, las opciones `NTSC(60Hz)`/`PAL(50Hz)` y el
      cursor**, y compararlo con la captura real de PCSX2 (`/tmp/realstate/Screenshot.png`).
      **`rgbNZ > 0` no alcanza**: el run actual da `rgbNZ=261139` con un fondo magenta y ningún texto
      (present 900, f=310, `fadeVal=0`). El hito 1 se marca `[x]` recién cuando este PNG muestre las
      opciones y el pad las opere.
      **Causa directa medida (2026-10-20)**: el color de vértice del path **packed VU1/GIF** llega
      `lo=0x80`, `hi=0x7fffffff00000080` ⇒ `(128,0,128,255)`, G=0; MODULATE anula el verde. Los TEX0
      reales son correctos (fuente CBP=10336, chrome CBP=10268) y la paleta en `0x286000` es la real:
      **v91 punto 2 (CBP=10300) refutado**. **v92 confirmó la raíz**: `PS2_PEXEW` usaba
      `_MM_SHUFFLE(2,3,0,1)`; PCSX2 usa `_MM_SHUFFLE(3,0,1,2)` (`(w2,w1,w0,w3)`). Fix aplicado en
      `ps2_runtime_macros.h` (16 funciones lo usan; sin regenerar). **Full rebuild exit 0** y A/B
      (2026-10-20): `max(G)=255`, `R==G==B` en **59.197/60.634** no negros, `nz=60.634`,
      `t3sub=10`, f=1780. **El selector ya se ve** (caja, texto y opciones `NTSC(60Hz)`/`PAL(50Hz)`
      con cursor), pero el frame tiene **bandas y copias fragmentadas del texto** (también en el frame
      presentado, no solo en el decode). La caja es más angosta que la real y el texto se parte/repite.
      **Hito 1.6 SIGUE ABIERTO**: falta layout/posición/duplicación. **Medido (2026-10-20)**: la escena
      raíz real/nuestra tiene los mismos 6 nodos; el UI manager (`*(gp-0x34C)`, real `0xCB50D0`,
      nuestro `0xCB4EA0`) coincide (`+0x08` cámara 3D, `+0x24` cámara UI). La duplicación viene de un
      **nodo temporal `0x1FEDD80`** (stack, `+0=0x591B1C`, task `pc=0x591B90`) que
      `FUN_00512630 → FUN_0051AA80 → FUN_005172C0 → 0x6D6A80` inserta en la lista de la **cámara 3D**
      (`mgr+8`) ≈1/frame; las listas de comandos solo tienen el self de cada cámara; `[text:chain]` da
      3 pases/frame y `0x756A28` se invoca con UI y 3D. El estilo `+0x104=3` (real 6) es secundario
      (el A/B no elimina las copias). **v93 verificada (2026-10-20)**: confirmó escena/`node+0x90`
      vacío/cola UI/estilo, pero su fix (`cam3d+0x274==0`) es **no-op**: el campo ya es 0 en real y
      nuestro; `0x756a28` chequea `+0xC`; `0x6D6A80` sí usa `a2`; la cola es `camui+0x274`
      (real `0xCB4AC0`/nuestro `0xCB4890`, estructuras iguales). **Dato nuevo**: el texto del selector
      (`f5530f0`) se dibuja con **`cb=0x0` desde la task/UI**, no desde las cámaras; `n=1..3/4..6` son
      **dos frames**, no dos pases. Lead: acumulación entre frames (clear/alpha test) y/o scroll;
      el A/B `SWORD_NO_ALPHA_TEST=1` fue inconcluso (`t3sub=0`). Siguiente: clear/alpha test y
      posiciones del texto por frame. UNPACK V2/V3 queda después.
      **v94 VERIFICADO (2026-10-20)**: el `DISPLAY` real es **512×511** (`eeMemory 0x00A8D0C8`:
      DW=2559/MAGH=4, DH=510); los `DISPFB` son **page 0** y **page 0x80**, **FBW=8**, PSM=0. La
      lectura correcta es **512×511** (no 640×448): `frame_300.bmp` 512×511 **limpio**, sin bleed
      derecho, con caja/texto/opciones/cursor. Secuencia: selector → language (`t3sub=11`) →
      fade (`t3sub=1`) → FMV (`t3sub=0`, `movie/op.pss`). **Corrección del usuario (juego real)**:
      la pantalla de idioma **SÍ existe**; 50Hz → language (`t3sub=11`); 60Hz → confirmación
      (`t3sub=50`) → language; luego fade/FMV. El log de PCSX2 no registra los menús; el `t3sub=11`
      del log del pad es la language. La página 0x90 no existe. **Siguiente: language (t3sub=11)
      + FMV 4.2 + audio 4.1**; el stub `sceGsSetDefDispEnv` (640×448) queda como deuda de
      root-cause, compensado por la lectura 512×511 del present.

## Hito 2 — Título y menú principal

> **Dependencia:** la secuencia real es **selector → primer FMV → título/menú principal**. El menú
> principal **no** llega directo del selector: **4.2 (FMV) es prerequisito de 2.1/2.2**. El audio del
> FMV se verifica con **4.1** en la misma pasada. El orden de ejecución es 1.6 → 4.2 (+4.1) → 2.1/2.2 →
> 3.x → 4.3 → 5.x; la numeración de hitos se mantiene sólo para seguimiento.

- [ ] **2.1** Seguir la transición post-selector (`FUN_0083d990` → siguiente fase) **pasando por la
      pantalla de idioma (`t3sub=11`) y el primer FMV** y verificar que se dibuja el título/menú
      principal. 50Hz → language; 60Hz → confirmación (`t3sub=50`) → language.
      **MEDIDO (2026-10-20)**: language **visible y operable** (PNG de VRAM del present 560 con el
      texto y las 5 opciones; secuencia `10 → 11 → 50 → 0 → 1` [fade] con `SWORD_AUTOPRESS`).
      **BLOQUEADO tras el fade**: el tick se congela en f=510 y el hilo principal gira en
      `FUN_006ec8a8 0x6ec8fc` esperando `descriptor+0x34 != 1`. **v95 verificado**:
      vtable `0xA887B8+0x5C` = `FUN_006ec8a8` (`WaitForAssetSync`), `+0x11C` = bind `FUN_006d5fb8`;
      `+0x34` es un **contador de transferencias en vuelo** que incrementa `FUN_006fe618`
      (`0x6feec4..0x6feed8`) y sólo se limpia en `0x6ec92c`. En el spin: `gp5ec=0`, `gp630=0`,
      `cbgp=0` (sin callback de fin de DMA). **A/B 1 OK**: `SWORD_FORCE_ASSET_SYNC=1` destraba el
      fade (`t3sub 1→3` en f=520, handler raíz `0x4ffb40`, sin crash). Falta el fix durable de la
      finalización y el FMV/IPU (4.2). Detalle: `decisions.md` §18.
- [ ] **2.2** Verificar navegación real con pad en el menú principal (sin overrides).
- [ ] **2.3** Documentar el mapa de escenas (qué función/task por pantalla) en `decisions.md`.

## Hito 3 — Gameplay (3D) y ritmo

- [ ] **3.1** Medir el camino 3D: `VIF1` UNPACK, microcódigo VU1, `XGKICK`, texturas 3D. Confirmar que la
      escena se dibuja (no sólo la UI).
- [ ] **3.2** **Ritmo**: hoy el tick corre a **~9/s contra 58 VBlank** (`[task]`/`[tick-prof]`). Identificar
      el cuello (scheduler cooperativo, esperas, coste de las funciones recompiladas) y subirlo a un ritmo
      jugable. No confundir con bloqueos.
- [ ] **3.3** Determinismo: caracterizar el no-determinismo ocasional (un run divergió a `f=180`).
- [ ] **3.4** Save state / carga de partida si aplica al flujo.

## Hito 4 — Audio, cinemáticas y guardado

- [ ] **4.1** Verificar salida SPU2 (el driver corre; **el selector ya reproduce audio**; falta comprobar
      mezcla/salida y que el mezclador reciba datos correctos). **Incluye el audio del primer FMV**,
      verificado junto con 4.2.
- [ ] **4.2** Reproductor de vídeo/cinemáticas (si el juego las usa) verificado. **Se adelanta: es
      prerequisito de 2.1/2.2** (el menú principal llega después del primer FMV).
      **MEDIDO (2026-10-20)**: el juego no importa `sceMpeg*`; linkea **libipu estáticamente**
      (`PsIIlibipu 3000`) y todavía no escribe ningún registro IPU (`SWORD_IPU_TRACE`=0). El runtime
      sólo almacena `0x10002000..0x10002030` (`ps2_memory.cpp`), no decodifica. Antes del FMV hay que
      resolver el cuelgue del fade (2.1, `descriptor+0x34`). Consulta v95 pendiente.
- [ ] **4.3** Memory card / guardado (stubs de `libmc`): crear, leer y escribir.

## Hito 5 — Producto (launcher + release)

- [ ] **5.1** Launcher: selector de ISO + MD5 (`check_iso` de `build_release.py`), persistencia del config
      (`%APPDATA%` en Windows, `~/.config` en Linux), opciones (resolución, fullscreen, escalado, vsync/FPS,
      audio, pad).
- [ ] **5.2** Acciones **Generar** (invoca `build_release.py --iso`) y **Jugar** (`--config`).
- [ ] **5.3** Empaquetado Windows + Linux en el release por tag `v*`.
- [ ] **5.4** `game/generate_functions_csv.py` (CSV reproducible) + `validate_csv.py` como gate del CI.
- [ ] **5.5** Revisión de fidelidad del runtime (overrides por dirección) — deuda declarada.

## Deuda / higiene (hacer al tocar cada zona)

- [ ] Unificar el cableado del pad en **un solo lugar durable** (`game_overrides.cpp`) y **quitar** el
      cableado del thunk generado (`work/generated/thunk_FUN_0051e700_0x51c7c0.cpp`), que se pierde al
      regenerar el CSV.
- [ ] Quitar el log `[ui-draw-gen]` de `work/generated/FUN_0083d290_0x83d290.cpp` cuando ya no se necesite.
- [ ] Limpiar sondas viejas **no env-gated** de `gs_cpu_backend.cpp` (las primeras rondas no estaban
      gateadas) y dejar sólo las que se usan.
- [ ] Corregir el offset de 425 B en `triageLoadGs` (lee desde 0 y consume el header de `GS.bin`).
- [ ] Revisar el commit del fork del runtime (hoy hay cambios sin commitear en `game_overrides.cpp`,
      `gs_cpu_backend.cpp`, `gs_frontend.cpp`).

## Flujo de trabajo (incluye el ciclo con Gemini)

Cada hito avanza en **rondas** (`work/gemini/msg_gemini_vNN.md` → `msg_gemini_reponsevNN.md`). Es parte del
flujo normal, no un recurso de emergencia. Detalle y reglas: `design.md` §"Flujo de trabajo con Gemini".

- **Por cada bloqueo de análisis estático** (quién llama / qué offset / qué gate / qué instrucción): abrir
  una ronda con el estado medido, las preguntas **numeradas** y el **A/B**; el usuario la pega en Gemini y
  trae la respuesta.
- **Verificar la respuesta** contra ELF/RAM/log **antes** de actuar; anotar verificado/refutado.
- **Implementar sólo lo verificado** (env-gated, OFF) y medir.
- **Registrar la ronda** en `decisions.md` (sección numerada) y en `work/gemini/README.md` (fila con
  veredicto).
- **No repetir preguntas** ya respondidas ni re-abrir hipótesis refutadas (`decisions.md` §2).
- Al cerrar cada hito, una **ronda de revisión** de lo aprendido y actualización del índice.

## Reglas de método (aprendidas a golpes — obligatorias)

1. **Leer el artefacto antes de afirmar.** ELF `work/elf/SLES_537.68`
   (`offset = vaddr − 0x4C0000 + 0x100`), generado `work/generated/` (un `.cpp` por función con la
   instrucción original en comentario), savestates `work/pcsx2_states/*.p2s` (ZIP con `eeMemory.bin`).
2. **`replaceFunction` sólo funciona sobre la entrada real de la función.** Es **inerte** en direcciones
   interiores o si la entrada se alcanza por **fallthrough** desde un chunk anterior (p. ej. `0x6d51b0`
   se entra desde `0x6d5158`).
3. **Los conteos con `grep -c` sobre estos logs son mentira**: las líneas se concatenan. Usar `grep -o` y
   contar ocurrencias; desconfiar de `head -N` (los primeros N prims suelen ser **padding degenerado**).
4. **El orden de líneas del generado ≠ el orden de direcciones**; el generado no es consistente en
   mayúsculas: grepear ambas.
5. **El globo `$gp` del heap está corrido ≈+0x150** vs el real: comparar **por contenido**, no por dirección.
6. **`GS.bin` tiene 425 B de header + 4 MB + 84** (usar `/tmp/GS_vram.bin` = 4 MB exactos o `dd skip=425`).
7. **Un log vacío puede ser falta de flush**, no ausencia de evento. `timeout` mata con SIGTERM ⇒ los dumps
   de salida pueden no escribirse.
8. **No-determinismo ocasional**: repetir los negativos antes de concluir.
9. **Toda instrumentación nueva nace env-gated y OFF**; al cerrar el hito, apagarla.
