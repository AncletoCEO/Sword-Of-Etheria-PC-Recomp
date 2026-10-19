# Tasks: reach-main-menu

> Estado 2026-10-09. Entrada: **`HANDOFF.md`**. Se podaron las tareas superseded para no inducir a error.
>
> ⚠️ **2026-10-17 — este archivo es un LOG POR SESIÓN (histórico).** Las mediciones de cada sesión valen
> para su fecha. En particular, las líneas que dicen **`vramNonZero=0` / "sigue negro" por falta de
> dibujo** quedaron desactualizadas: hoy `vramNonZero` sube a **368801/475456**, la geometría **llega al
> GS** (`[vif1-chain]`, `[gs:kick] drawing=1 pc=0x6e4468`) y el problema es **qué página se presenta**.
> Fuente vigente: `decisions.md` §2026-10-17 + §"Artefactos de medición".
> Lo que **sí** sigue válido de acá: el `SWORD_TEST_PATTERN` prueba que **el present funciona** (se ve un
> gradiente forzado) ⇒ si la pantalla está negra no es el display roto, sino **qué VRAM lee**.

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

---

## Sesión 2026-10-17 (noche) — TEXTURAS: el eslabón es el gestor de UI, no el GS

> Mediciones vigentes en `decisions.md` §rondas 16-20. **No re-descubrir**: el camino GS/A+D/DMA del
> runtime está **probado byte a byte** contra el real y es correcto; el estado del gestor de texturas
> (`0xA887B8`) es byte-idéntico al real salvo 3 palabras; lo que falta es la **lista de 6 objetos de UI**
> cuyo centinela vive en `0xA887B8+0xBC` (`0xA88874`), que en nuestro run está vacía y **nunca se escribe**.

- [x] **Trazar la entrada de las funciones del cluster de la clase** (`0x6d6290`, `0x6d6310`, `0x6d6390`,
      `0x6d6410`, `0x6d6490`, `0x6d6510`, `0x6d67a8`, `0x6d68a0`, `0x6d6a80`, `0x6db0d0`) y ver cuál **no** se
      ejecuta en nuestro run. Método que ya funcionó: `SWORD_TRACE_BRANCH=<entrada>-<entrada+1>` y leer
      `src=` (el caller) en `/tmp/sword_branch.log`.
      **HECHO 2026-10-18** (`SWORD_TRACE_BRANCH=6d6290-6db135`, 200 s, run completo hasta el menú):
      **7 de 10 SÍ corren** — `0x6d6290`=900, `0x6d6310`=902, `0x6d6390`=899, `0x6d6510`=29,
      `0x6d68a0`=75, `0x6d6a80`=8694, `0x6db0d0` (el "clear" de la lista)=3593.
      **Nunca corren 3**: `0x6d6410` (sólo lo llama `0x8035c0`/`0x803ed8`), `0x6d6490` (sin caller directo
      en el generado) y **`0x6d67a8`** (lo llaman ~40 sitios: `0x51b934`, `0x50a76c`, `0x50a868`,
      `0x539e04`, `0x54762c`, `0x561764`, `0x573b68`, `0x5e9fec`, `0x6d69d4`, `0x6d6b74`, `0x6d6cfc`,
      `0x7f7ba4`, `0x8034c0`… y **ningún** sitio llega). ⇒ **La premisa "el linker no corre" es FALSA**:
      las funciones que insertan corren a montón; `0x6d67a8` (el "unlink-de-árbol + insert") es la única
      del sub-grupo insert que no corre pese a tener ~40 call sites. `0x6d6410/0x6d6490/0x6d67a8` son los
      candidatos vivos.
- [x] **Identificar la función que *enlaza* la lista** (la que escribe `next`/`prev` del centinela).
      Pista: el centinela real tiene la vtable de la clase en `+8/+0xC/+0x10`
      (`0x004c6568`/`0x004cb430`/`0x004c6c20`) ⇒ el constructor de la clase instala eso; buscarlo por los
      inmediatos (`addiu …, 0x6568` = 25960, y pares `lui 0x4C`; ver `FUN_006d13a0`, que es *otro* instalador:
      corre 1 vez pero no toca el centinela).
      **HECHO 2026-10-18**: el *único* código que escribe `0xA88874` en todo el generado es el bloque insert
      **inline** que comparten `0x6d6290/6310/6390/6510/68a0/6a80` y `0x6d67a8` (grep de `A88874` en
      `work/generated` = sólo esos 10 archivos). **No hay un "linker" aparte.** Y los slots `+8/+0xC/+0x10`
      del centinela (`0x4c6568/0x4cb430/0x4c6c20`…) **coinciden byte a byte** con el real (no son la
      diferencia). El insert está gateado por `(*(node+3) & 3) == 0` (si `!=0` saltea). La única diferencia
      del objeto gestor `0xA887B8` contra `work/teleport/eeMemory.bin` es `+0x8` (345 vs 629) y el centinela.
- [x] **Comparar por contenido** (no por dirección: el heap está corrido **+0x150**) si los 6 objetos existen
      desenlazados en nuestro dump o no existen. Firma: floats `0x3F800000` (1.0) y `0x3F7FFFFF` en `+8`,
      paso de **0x280** entre nodos en el real (`0xE8C058 → 0xE8C2D8 → 0xE8C558`), más `0xE81F18`,
      `0xCB6028`, `0xCB5818`.
      **HECHO 2026-10-18** (`/tmp/rdram_late1.bin` tick 1200 vs `eeMemory.bin`): los 6 nodos reales son
      **objetos de transform** (id `0x0f`/`0x03` en `+0`, matrices identidad 4×4 en `+0x10..+0x40`, links en
      `+8`(next)/`+0xC`(prev), link-base = obj+8). **Objetos del mismo tipo SÍ existen en nuestro dump**
      (patrón de matriz identidad + `0x00020003`: **30 hits en el nuestro vs 27 en el real**; p.ej.
      `0xc780c0` con `+8 = 0x00a88874`). ⇒ **La lista no es "imposible de construir": los objetos existen;
      lo que difiere es el *enlazado* (transitorio: 3593 "clear" y ~900 insert por corrida).**
      ⇒ **El "eslabón de los 6 objetos" es, con alta probabilidad, un artefacto de comparación transitoria**
      (nuestra foto cayó con la lista vacía). NO explica la falta del atlas.
- [ ] **Si el bloqueo es de datos del motor y no se resuelve leyendo**: pedir consulta a Gemini con el
      protocolo de `work/START_NEXT_SESSION.md` §Protocolo Gemini (contexto de trabajo en el primer mensaje;
      el usuario hace de proxy). Candidata: `work/gemini/msg_gemini_v70.md`.
      **PREPARADA 2026-10-18**: `work/gemini/msg_gemini_v70.md` (reescrita con el hallazgo nuevo — ver abajo —
      que refuta el modelo del "runner en bucle"). **Pendiente: el usuario la pega en Gemini.**
- [ ] **Verificar el hito**: `[gs:diag] crt1 … rgbNZ > 0` (y, cuando ocurra, subir `main` del repo del juego).
      **Sigue rojo 2026-10-18**: `[gs:diag] crt1 (fbp=0): rgbNZ=0 aNZ=0 | crt2 … rgbNZ=0`; sólo hay
      **5 subidas TRXDIR** (todas `dbp=10240` PSMCT32) ⇒ el atlas PSMT8 (`0x282000`–`0x294000`) no llega.

## Sesión 2026-10-18 — HALLAZGO: la subida de texturas se dispara UNA sola vez (el runner NO es un bucle)

> Medido, no deducido. Cambia el marco de la sesión anterior (que hablaba de "el bloque del runner que
> itera sobre el gestor").

- **`FUN_0051f450` NO tiene ningún bucle.** Leído el generado completo: es **lineal** — `func_6E6D00` →
  setup de `0xA42530` → `func_6D5AD0` (ctor del gestor) → `func_51F580` → `func_6D5980` (el gate) →
  [si hay trabajo] `func_51EF60`/`func_6F1F90`/`func_6D5500`/`func_6D5DF8` → **`func_6D57E8` (opcode 2 =
  una subida)** → `bnez $v0, +0x1C` (salto **hacia adelante**, no un lazo) → `ret`.
  El `0x51f544: bnez $v0 → 0x51f564` de la ronda 19 es un **salto hacia adelante** (devolver 1), **no** un
  lazo del runner. ⇒ **Cada invocación sube exactamente UNA textura.**
- **Medición directa** (`SWORD_TRACE_BRANCH=51f450-51f579`, 150 s): `FUN_0051f450` se entra **1 vez** (desde
  `src=0x512ac8`) y recorre el camino de subida **1 vez** (`0x51f4d8→6d5980` ×1, `0x51f53c→6d57e8` ×1).
- **Medición directa** (`SWORD_TRACE_BRANCH=51fe00-51ff40`, 140 s): el bucle de frame `FUN_0051fea0`
  (`0x51fea0-0x51ff20`) llama `FUN_00512ab0` en `0x51fee8` **1 vez** y `FUN_00512630` en `0x51fef0` **1 vez**
  ⇒ **el cuerpo del bucle de frame corrió una sola vez**; el juego queda **dentro de `FUN_00512630`**
  (entrada = 1, nunca retorna).
- **Mientras tanto la lógica del juego SÍ avanza** (menú alcanzado, `root h20=0x500490`, `count=4`,
  Task#4 `0x83d990 sub=10`, pad `state=5/6`) porque el tick entra por el **callback** `0x51147c`→`0x50f750`
  (~3600 ticks/200 s ≈ 18/s), no por el bucle de frame. Los frames presentados son ~95 `[gs:present]`/200 s.
- **Consecuencia**: la subida del atlas depende de que el bucle de frame **itere** (1 textura por frame).
  En nuestro run itera **1** vez ⇒ sólo 1 textura. El prerequisito es que **`FUN_00512630` retorne**
  (condición de salida: `0x512a6c: beqz $v1 → 0x512674` con `$v1 = *(s1+8)`, `s1` = objeto de fase).
  Ver `work/gemini/msg_gemini_v70.md`.
- **CORRECCIÓN 2026-10-18 (respuesta v70 de Gemini, verificada)**: eso **NO es un bloqueo**. `FUN_00512630`
  **es** el bucle de 60 fps de la fase (contiene los `jal` a vsync/pad/audio/árbol de tareas/kick GS/flip), y
  `FUN_0051fea0` es el bucle de **cambio de fase**. Que itere 1 vez y quede dentro de `FUN_00512630` es lo
  correcto: el objeto de fase `*(gp-0x358)` tiene **contenido idéntico** al del menú real (`+8 = 0`, `+0 = 4`
  en `*(gp-0x324)`) ⇒ el lazo **no debe** salir. `FUN_0051f450` es el **init de texturas de la fase** (lineal,
  1 subida). ⇒ No hay bug de flujo. Detalle y verificación: `decisions.md` §2026-10-18.
- **A/B DECISIVO 2026-10-18 — "falta el atlas" REFUTADO**: se inyectó la VRAM del real (arreglado el header
  con `dd skip=425`) y el frame **sigue negro** (`rgbNZ=0`). La VRAM del real en el menú es **sólo el atlas**
  (pages 320–330, 24 293 B) y el resto está en cero. ⇒ El bloqueo **no es la subida de texturas** sino la
  **presentación**: presentamos `fbp=0` (el default del runtime, `DISPFB1=0x1400`; el juego nunca escribe
  `DISPFB1`) mientras el juego **dibuja** en `ctx=80/8/0` y el real presenta FBP=128. Nuevo foco: por qué el
  fallback por contenido del present no elige la page 80 y por qué el juego no escribe `DISPFB1`/`DISPLAY1`.
  **Deuda**: corregir el offset 425 en `triageLoadGs`.
- **CAUSA LOCALIZADA 2026-10-18**: los prims texturizados del menú (TRISTRIP, `psm=PSMT8 tbp0=10240
  tw=th=64 tcc=1 tfx=0 cld=1 csm=0 cbp=10268`) **dibujan en la page 128** y **se descartan TODOS sus
  píxeles** por el alpha test (`TEST=0x5002b`: ATST=5 `alpha>=2`, AFAIL=KEEP) porque el alpha compuesto es
  0; ese 0 viene de que **el TEXEL muestreado es (0,0,0,0)**, y eso de que **la coordenada de muestreo es
  (0,0) en todos los píxeles** (`[tex-probe] raw=0x0 su=0 sv=0` en 8/8) ⇒ **la UV/ST del vértice llega en
  0**. El alpha del vértice (interpolado ≈249) y la textura (page 320, idéntica al real) están bien; el
  atlas y la CLUT **no** son la causa. ⇒ **Bug de fidelidad del runtime en el decode de UV/ST**.
  Detalle: `decisions.md` §2026-10-18 (7).
- **CORRECCIÓN + CIERRE 2026-10-18**: la lectura "UV/ST = 0" era **artefacto de las sondas** (los primeros
  prims son **padding degenerado** y `[gs:content]` imprime `v.u/v.v`, no `v.s/v.t`). Verificado:
  los prims reales traen `st=(0.48633,0.0117187)` (y los paquetes `S=0.125,T=0.340,Q=1`), el **lookup
  PSMT8/CLUT es correcto** (`(31,0)` → `0x280136` → byte `0x00` **también en el `GS_vram.bin` real**),
  y **el alpha test es síntoma**: con `SWORD_NO_ALPHA_TEST=1` la VRAM sigue vacía. **Nuevo bloqueo medido**:
  `[tex-hist]` → **0 de 600 prims texturizados muestrean un texel ≠ 0** (todos `tbp0=10240`) y **la mitad
  rasteriza 0 píxeles**. ⇒ El contenido del menú no se está dibujando por el camino observado.
  Consulta: `work/gemini/msg_gemini_v72.md` (pendiente). Detalle: `decisions.md` §2026-10-18 (9)(10)(11).
- **CIERRE 2026-10-18 (telemetría global)**: `[gs:prims]` (todos los draws, antes de `Submit`): de 21 360
  draws — `TRISTRIP=2294, TRIFAN=8256, SPRITE=10809` — **el ÚNICO `tbp0` texturizado es 10240 (page 320)**;
  nunca `10272..10560` (atlas). `texturedDraws == TRISTRIP` ⇒ TRIFAN/SPRITE van **sin textura**.
  **A/B con el atlas inyectado: idéntico** ⇒ el gate **no es la VRAM**. ⇒ **El juego nunca emite las draws
  del contenido del menú**; el bloqueo está aguas arriba del GS (emisión 2D del juego).
  Consulta: `work/gemini/msg_gemini_v73.md` (pendiente). Detalle: `decisions.md` §2026-10-18 (12).
- **CAUSA RAÍZ LOCALIZADA Y POC 2026-10-18**: verificado byte a byte contra `eeMemory.bin` — el nodo de
  string (`String 0x130`) en el real tiene `+0x00 = 0x08000000` y `+0x3C = 0x0095F410`; el nuestro tiene
  `+0x00 = 0` y `+0x3C = 0x3B`, y el contexto de glifos `0x0095F410` está **todo en cero**. En vivo:
  `[font-bind] node=0xe82f70 +00=0x0 +2C=0x44 +3C=0x3b ctx0=0x0` (3 nodos). El PoC
  `SWORD_FORCE_FONT_BIND=1` (init del ctx + `node+0x3C`) **NO destraba la emisión**: sigue sólo
  `tbp0=10240` y `vramNonZero=3119` (caso B). Quedan `+0x2C`/`+0x4C = 0x44` vs 0 y el timer del Task#4
  (`2/2/2` vs `3/3/4`). Consulta: `work/gemini/msg_gemini_v74.md` (pendiente).
  Detalle: `decisions.md` §2026-10-18 (13).
- **PoC EXTENDIDO 2026-10-18 (v74) — NEGATIVO**: el contexto de material real `0x0095F430..0x0095F468`
  coincide exacto (`"PS2AllMats.cl"`, vtable `0x0075FB68`). Se aplicó la init completa + normalización del
  nodo (`+0x00/+0x2C/+0x3C/+0x4C`); el parche **sí** se aplicó (`[font-bind]` muestra `ctx0=0x101`) y el
  juego llegó al menú (`f=1570`), pero **siguen sin aparecer `tbp0 ≥ 10272`** (`vramNonZero=3119`,
  `rgbNZ=0`) ⇒ caso B también con el PoC completo. **Refutado** el "gate `+0x2C`" de v74: con `+0x2C = 0`
  la lectura cae en `0x8`, que en la RAM real es **código** (`0x40196800`); el "skip" lo produce
  `+0x2C = 0x44`. Además un run divergió (`f=180`) y el re-run anduvo ⇒ **no-determinismo ocasional**.
  Consulta: `work/gemini/msg_gemini_v75.md` (pendiente). Detalle: `decisions.md` §2026-10-18 (14).
- **BREAKTHROUGH 2026-10-18 (v75)**: el selector PAL/NTSC (`FUN_0083d990` `sub==10`) **esperaba Cross
  (`$v0 & 0x40`)**. PoC env-gated `SWORD_CONFIRM_MENU=1` (`$v0 |= 0x40` en `label_83da60`): `[confirm-menu]`
  dispara 1 vez y **`t3sub` pasa 10 → 0**. Efectos medidos: **se sube el atlas** (`[gs-upload] dbp=10272`,
  antes nunca), **aparecen draws con él** (`[gs:prims] tbp0=10272 texturedDraws=2647`, antes 0),
  `vramNonZero` 3119 → **6238**. Con `SWORD_PRESENT_CTX=1`: `fbpDisp1=128`,
  `[gs:diag] crt1 (fbp=128) rgbNZ=0 aNZ=151713`. **Sigue `rgbNZ=0`**: los texeles del atlas muestrean 0
  (`[tex-hist] withNonZeroTexel=0`) ⇒ falta la CLUT/mapeo del atlas. Consulta:
  `work/gemini/msg_gemini_v76.md` (pendiente). Detalle: `decisions.md` §2026-10-18 (15).
- **v76 REFUTADO EN LO CLAVE 2026-10-18**: el "cache de CLUT desactualizado" **no** es la causa —
  los draws del atlas usan **`cld=1`** (recarga en cada TEX0), **`m_clut` no está vacío**
  (`m_clut[1]=0xf`, `m_clut[15]=0x349`) y **forzar la recarga** (`SWORD_CLUT_RELOAD=1`) **no cambia nada**
  (`texel=0x0`, `rgbNZ=0`). Dato nuevo: el atlas usa **`cbp=10300` (`0x283000`)**, cuya entrada 1 es
  `0x0000000F` (**alpha 0**); el `0x283000` real no parece una paleta. Sigue por explicar el muestreo del
  atlas. Consulta: `work/gemini/msg_gemini_v77.md` (pendiente). Detalle: `decisions.md` §2026-10-18 (16).
- **CAUSA CONCRETA 2026-10-18 (dump de VRAM)**: `10300*256 = 0x283C00` (corrección de v77, verificada) y la
  paleta real allí es `entry1=0x000F020B`. **Nuestra page 321 es una COPIA de la page 320**: `0x282000`
  empieza con `005a005a…` (patrón de page 320), `0x283C00` contiene la **paleta de 10268**
  (`entry1=0x0000000F`), y sólo 3196/8192 bytes coinciden con el real (page 320 sí es 8192/8192 idéntica).
  ⇒ las subidas a `dbp=10272` (n=6..10, mismas geometrías que las de 10240) **llevan el payload de la page
  320** ⇒ **el atlas no llega a VRAM** (no es CLUT ni muestreo). Consulta:
  `work/gemini/msg_gemini_v78.md` (pendiente). Detalle: `decisions.md` §2026-10-18 (17).
- **PoC INYECCIÓN PAGE 321 2026-10-18 (v78) — PARCIAL**: `SWORD_INJECT_PAGE321=<GS sin header>` copia la
  page 321 real antes de cada present. **Los texeles YA resuelven**: `[tex-hist] withNonZeroTexel`
  **0 → 1521/1600**. **Pero `rgbNZ` sigue 0** (`crt1 (fbp=128): rgbNZ=0 aNZ=151713`) y el bypass
  `SWORD_FORCE_VTX_RGB=1` (MODULATE con vértice 1.0) **tampoco cambia** ⇒ no es sólo la multiplicación por
  cero. Dato: la paleta real `0x283C00` tiene `entry1=0x000F020B` (**A=0**) y el alpha test
  (ATST=5, AREF=2, AFAIL=KEEP) descartaría. Refutados de v78: `0x8A42F0` no es tabla de punteros y
  `0x00E63000` en RAM real está en cero. Consulta: `work/gemini/msg_gemini_v79.md` (pendiente).
  Detalle: `decisions.md` §2026-10-18 (18).
- **PALETA 4-BIT VERIFICADA + NORMALIZACIÓN NEGATIVA 2026-10-18 (v79)**: la CLUT del atlas `0x283C00` tiene
  **62/256 entradas con A>0**, con **A∈[1,15] y RGB≤15** (la de page 320, `0x281C00`, tiene A hasta 128 y
  RGB hasta 236). El PoC `SWORD_UI_COLOR_FIX=1` (expande A/RGB, vértice RGB→1.0, va→128) **NO cambia
  `rgbNZ`**: las muestras dan `su=0 sv=0 rawIdx=0 clutVal=0x70202` (**A=0**) y el alpha test descarta;
  `withNonZeroTexel` cuenta valores ≠0 **aunque A=0**, así que no prueba color. Consulta:
  `work/gemini/msg_gemini_v80.md` (pendiente). Detalle: `decisions.md` §2026-10-18 (19).
- **CBP: EL OBJETIVO 2026-10-19 (v80)**: verificado en la RAM real (`eeMemory.bin` @ `0xA97BB0`) que el TEX0
  del atlas es `20050C05DD30A820` → `tbp0=10272 … **cbp=10336**` (page 323), y también `10368→10432`,
  `10464→10496`. **Nosotros emitimos `cbp=10300`** (= tbp0+28, que en la page 321 son **datos de glifo**)
  ⇒ `texel=0x70202` (**A=0**) ⇒ alpha test descarta. El PoC `SWORD_INJECT_UI_VRAM` (11 páginas, 90112 B,
  + invalidación de caches) **funciona** (`vramNonZero=24293`) pero **no cambia el `CBP`** ⇒ `rgbNZ=0`.
  ⇒ Hay que encontrar quién calcula el `CBP`/por qué se sube el asset de la page 320 a `dbp=10272`.
  Consulta: `work/gemini/msg_gemini_v81.md` (pendiente). Detalle: `decisions.md` §2026-10-18 (20).
- **DESCRIPTOR EQUIVOCADO CONFIRMADO 2026-10-19 (v81)**: la tabla `0xA95650` (registros `{desc,vram,size}`)
  y los descriptores quedaron **verificados** (`0xE80090` chrome → `0x200503859930A800`; `0xE702E0` fuente →
  `0x20050C05DD30A820`, `tw=7/th=7/cbp=10336`). **Nuestro juego emite `0x200507859930A820`** =
  el TEX0 del **chrome (64×64)** con `tbp0` parcheado. Forzar el TEX0 completo
  (`SWORD_FORCE_FONT_CBP=1`) **sí aplica** (`cbp=10336`) pero `rgbNZ=0` sigue; los primeros 8 prims del
  log son padding (`su=sv=0`), así que la sonda no sirve para concluir. Consulta:
  `work/gemini/msg_gemini_v82.md` (pendiente). Detalle: `decisions.md` §2026-10-18 (21)(22).
- **HITO ACORDADO 2026-10-19 (usuario)**: **ver la pantalla del selector de video y controlarla con el
  pad**. Dos bloqueos medidos:
  1. **Control**: el pad del host (`ps2_pad.cpp`, X/Space=Cross) **no llega** al juego — con
     `SWORD_PAD_PRESS=cross` (sin `SWORD_CONFIRM_MENU`) el selector quedó en `t3sub=10`. El juego lee
     por libpad/padman, no por el stub HLE ⇒ hay que cablear `func_51C7C0`.
  2. **Visibilidad**: `[tex-hist] texturedPrims=800 withNonZeroTexel=0 stVaryPrims=800
     stVaryWithNonZeroTexel=0` — **el chrome (`tbp0=10240`, page 320 byte-idéntica al real) también da
     texel 0** ⇒ el sospechoso es la **lectura de textura/índice** (PSMT8 + selección ST/UV), no la
     inyección ni la paleta. Refutado el "desfase de 425 B" de v82 (pasamos un archivo sin header).
  Consulta milestone-oriented: `work/gemini/msg_gemini_v83.md` (**RESPONDIDA 2026-10-19** en `msg_gemini_reponsev83.md`). Implementado cableado de pad host en `thunk_FUN_0051e700_0x51c7c0.cpp` e invalidación continua de VRAM en `gs_cpu_backend.cpp`. Detalle: `decisions.md` §2026-10-19 (25).
  Seguimiento v84: `work/gemini/msg_gemini_v84.md` (**RESPONDIDA 2026-10-19** en `msg_gemini_reponsev84.md`):
  - **CONTROL**: Pad verificado en vivo 10 → 11 → 0 sin bypass.
  - **Durabilidad**: Pad hook migrado a `game_overrides.cpp` (`replaceFunction(0x51c7c0u, ...)`).
  - **Nearest spec**: Reversión confirmada con PCSX2 `GSDrawScanline.cpp:844`.
  - **UI Architecture**: Cadena de Task 3 (`0x009C8890`), `FUN_0083dc40` y `0x00805550` revertida con tabla `0x009C8850`. Sondas A/B inyectadas (`[ui-clear]`, `[ui-insert]`, `t3_7c`, `t3_84`).

## Plan de producto (definido 2026-10-15 — NO implementar aún)

> Estos items quedan planificados; se ejecutan al cerrar el hito del menú. Ver `proposal.md`
> §"Producto final" y `design.md` §"Producto final — arquitectura".

**Hito actual (sigue siendo lo prioritario)**

- [ ] **Frame presentado con `nonZeroRgb > 0`** con los triages apagados (menú visible).
- [ ] Cerrar los `missing-target` restantes clasificándolos con el mismo criterio
      (**referenciados** de verdad: JAL/J/branch/tabla/vtable) y NO por cercanía a un epílogo.

**Launcher (entregable propio)**

- [ ] Definir el alcance de la UI (resolución, fullscreen, escalado, vsync/FPS, audio, pad).
- [ ] Selector de ISO + validación MD5 (reutilizar `check_iso` de `build_release.py`).
- [ ] Persistencia del config (`%APPDATA%` en Windows, `~/.config` en Linux) compartido con el juego.
- [ ] Acción **Generar** (invoca `build_release.py --iso`, con progreso/log visible).
- [ ] Acción **Jugar** (lanza `sword_etheria --config <archivo>`).
- [ ] Empaquetado por plataforma (Windows + Linux) en el release por tag `v*`.

**Reproducibilidad y calidad**

- [ ] `game/generate_functions_csv.py`: reproducir el CSV desde el ELF + reglas (baseline, overrides,
      splits, clamps, filtro de referencias, altas puntuales como `FUN_006f2630`).
- [ ] Mover `work/validate_csv.py` a `game/` y agregarlo como **paso del CI** (gate antes del build).
- [ ] Documentar el modelo de contenido (el ISO se necesita **también para jugar**; el repo no lleva
      nada con copyright).

**Deuda declarada (a revisar con el juego completo)**

- [ ] Fidelidad del runtime: revisar los overrides por dirección de `game_overrides.cpp`.
- [ ] Alcance funcional completo (gameplay, audio, cinemáticas, guardado) por fases.
