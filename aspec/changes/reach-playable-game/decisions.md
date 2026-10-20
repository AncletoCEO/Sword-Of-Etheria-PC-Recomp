# Decisions: reach-playable-game — digest de traspaso (2026-10-19)

> Este archivo **no** repite el log completo: es el **estado verificado** al archivar `reach-main-menu`,
> con la evidencia y las hipótesis **ya refutadas**. El detalle crudo está en
> `aspec/changes/reach-main-menu/decisions.md` §(1)–(32). Si algo de acá contradice una medición nueva,
> gana la medición nueva — pero **primero repetila** (hay no-determinismo ocasional).

## 1. Estado verificado al cierre

**Juego/escena**
- El recomp arranca, corre la lógica y llega al **selector de video PAL/NTSC**: `t3sub=10` desde **f≈200**
  y se mantiene (medido hasta f=2270). Tick del task ≈ **9/s** (VBlank ~58/s).
- **Pad del host funcionando por el camino real**: override de `0x51C7C0`
  (`replaceFunction(0x51c7c0u, padHook51c7c0)`), lee `padBackend().readState`, escribe `*(0xA42500)+2`
  (`0xA42102`) y retorna la máscara **active-high** (Cross=0x40, Circle=0x20, Up=0x8000, Down=0x2000,
  Left=0x2, Right=0x8, Start=0x4, Select=0x1). Verificado: `[pad-host] buttons=0x40`,
  `t3sub` **10 → 11 → 0** sin `SWORD_CONFIRM_MENU`.

**UI: se construye, se enlaza y se dibuja (lo que NO es el problema)**
- Task 3 descriptor `0x009C8890`: `+0x10 Init = 0x83DFA0`, `+0x14 = 0x83D290`.
- **`0x83D290` es el DESTRUCTOR** (se copia a `task+0x24` al spawnear; el scheduler lo pasa a `+0x20`
  recién al matar la tarea, `0x50f4ec`). Sus **0 ejecuciones son correctas**.
- Substate 2 de `FUN_0083DC40` → `0x00805550` **corre** (`ra=0x83dd80`, **`a2=0xa21418`** = tabla
  `0x009C8850`) y **tail-call a `0x6D6C40`**. `0x00804C50` **nunca** corre.
- Inserciones: `0x006D6A80` **hardcodea el centinela `0xA88874`** (`0x6d6aa0: lw $a0,-0x778C($v1)`;
  `0x6d6ab8: sw $a1,-0x778C($v1)`), nodo = `a2+8` (`next=+0`, `prev=+4`). Medido: **5374 inserts**,
  heads `0xe81d18`, `0xe8c358`, `0xcb5e08`, `0xcb55e8`, `0xe8c0d8`, `0xe8be58`.
- **Draw de UI por frame**: `0x7569B0` (≈1/frame; `ra=0x7569e4`) → `0x006D51B0` → **`0x006DB0D0`**
  (≈2289/corrida) que **llama a `0x006DAEF0`** (`dispatchGuestBranch(..., 0x6DAEF0u, ...)`) por widget.
- Gates de `0x6DAEF0`: visibilidad `flags = *(u8*)(widget+3) & 1` y lista de comandos en `widget+0x90`
  (circular; vacía si `head == widget+0x90`). **Medido en el selector: `flags=0xf` (visible) y
  `rlEmpty=0` (con comandos)** ⇒ los gates **pasan**.
- La emisión real está en **`0x6DAF6C: jalr *(cmd+0x10)`** (`cmd = $s0-8`), tras recorrer la lista y
  luego recursar en `widget+0x98` (hijos). **Ahí hay que mirar (hito 1).**

**Texturas/GS (verificado, no es el problema)**
- Page 320 (`tbp0=10240`) **byte-idéntica** al real (8192/8192); su CLUT (`cbp=10268`) también.
- `0x00A95650` (registros `{desc, vram, size}`): entry0 `0xE80090/0xA0000`, entry1 `0xE702E0/0xA0800`,
  entry2 `0xE6BBE0/0xA2000`, entry3 `0xE76D60/0xA3800`, entry4 `0xE749E0/0xA4800`.
- Descriptores: chrome `0xE80090+0x3C` = `0x200503859930A800` (`tbp0=10240 tw=6 th=6 cbp=10268`); fuente
  `0xE702E0+0x3C` = `0x20050C05DD30A820` (**`tbp0=10272 tw=7 th=7 cbp=10336`**). **Nuestro juego emite
  `0x200507859930A820`** = el del chrome con `tbp0` parcheado.
- PSMT8 conforme a PCSX2 (`PageExtent 128×64`, `BlockExtent 8×4`, `ColumnExtent 16×16`, tablas
  `blockTable8`/`columnTable8`).
- **Nearest = TRUNCAMIENTO**: PCSX2 `GS/Renderers/SW/GSDrawScanline.cpp:835-844` aplica el sesgo de medio
  texel (`u -= 0x8000`) **sólo** bajo `if (sel.ltf)` y deriva el texel con `sra32<16>`.
- Page 323 (`0x286000`) primeras 16 CLUT: `e0=0x00000000`, `e1=0x26000000`, `e2..e15` con **A=128**,
  `e15=0x80F3F3F3`. Page 320 fila `y=0` tiene 2/64 no-cero vs 50-55/64 en `y≥1`; `(31,0)=0x00`,
  `(31,1)=0x45`; `CLUT(10268) e0=0`, `e69=0x05020376`.
- Present: el juego dibuja en `fbp=128`; `SWORD_PRESENT_CTX=1` elige ese buffer. `SWORD_TEST_PATTERN=1`
  demuestra que el present puede mostrar.

## 2. Refutado con evidencia (NO volver a investigar)

| Hipótesis | Evidencia que la refuta |
|---|---|
| "El GS / el recomp dibuja negro por un bug de prims" | Pipeline verificado fiel (incluso contra la consola); el negro es data/estado |
| "Falta la subida del atlas" | Inyectada la VRAM real (11 páginas): `rgbNZ=0` igual |
| "El present elige el buffer equivocado" | `SWORD_PRESENT_CTX=1` → `fbpDisp1=128`, `aNZ=151713`, `rgbNZ=0` |
| "El alpha test es la causa" | `SWORD_NO_ALPHA_TEST=1` no cambia nada; es síntoma |
| "El CLUT cache está desactualizado" | `cld=1` recarga siempre; `m_clut` no vacío; `SWORD_CLUT_RELOAD` sin efecto |
| "El UV/ST llega en 0" | Artefacto: los primeros prims son padding; los reales traen `st=(0.48633,0.0117187)` |
| "La page 321 es una copia de la 320" (cierto) ⇒ "por eso no pinta" | Con el atlas inyectado y el TEX0 real: `texel=0` igual |
| "El `CBP` equivocado es la causa" | Forzado el TEX0 completo (`cbp=10336`): aplica y `rgbNZ=0` sigue |
| "Redondear el texel lo arregla" | `floor(x+0.5)` es un desplazamiento de medio texel; el `aNZ=246080` viene del velo de fade |
| "El `CBP` sale de una tabla dinámica" | Está precomputado en el descriptor (`+0x3C`) |
| "La lista de UI está vacía / nunca se enlaza" | 5374 inserts, todos a `0xA88874`, heads verificados |
| "`0x6db0d0` es un ClearAll que purga" | **Llama a `0x6daef0`**: es el flush/draw |
| "La draw `0x83D290` nunca se llena ⇒ nada se dibuja" | `0x83D290` es el **destructor**; la draw es `0x6db0d0`+`0x6daef0` y corre |
| "El pad del host no llega (sólo sirve el stub HLE)" | Funciona por `0x51C7C0`; `SWORD_PAD_PRESS` ahora fluye por el camino real |
| "El loader no se completa / el runner no itera" | `FUN_0051f450` es lineal (1 subida por invocación); el loop de fase es `FUN_00512630` y **debe** quedarse adentro |
| "El atlas necesita que el bucle de frame itere" | La fase no debe salir; el init de texturas de fase es lineal |

## 3. Abierto (lo que hay que medir)

1. **`*(cmd+0x10)`**: qué callbacks de render se invocan en `0x6daf6c` y qué prims emiten (PRIM/TEX0/UV/
   color) — y por qué no producen color visible. **Es el hito 1.**
2. Si los callbacks emiten bien: ¿por qué el resultado no llega al framebuffer presentado (dst, fbp, test)?
3. ¿Los widgets del selector son los que emiten, o hay un widget raíz/canvas que no está encolado?
4. Ritmo del tick (~9/s) y determinismo.
5. Camino 3D (VU1/VIF1) — sin medir todavía.

## 4. Artefactos y sondas (estado al cierre)

- Logs: `/tmp/run_render.log` (gates de UI), `/tmp/run_link.log` (insert/clear heads), `/tmp/run_full_ui.log`
  (corrida completa), `/tmp/run_draw.log` (0 ejecuciones de `0x83D290`), `/tmp/sword_etheria_v84_test2.log`.
- `game_overrides.cpp`: `padHook51c7c0`, `[ui-clear]`, `[ui-insert]` (+`global=`, `AFTER head=`),
  `[ui-reset]`, `[ui-widget]`, `[ui-draw]`, `[ui-render]`, `[task]` (+`uiNext/uiCount/t3_7c/t3_84`).
- `work/generated/FUN_0083d290_0x83d290.cpp`: `[ui-draw-gen]` (**temporal**).
- `work/generated/thunk_FUN_0051e700_0x51c7c0.cpp`: pad (**temporal**).
- `gs_cpu_backend.cpp`: sondas de textura (`[tex-hist]` con `stvary`), nearest revertido.
- `gs_frontend.cpp`: `SWORD_FORCE_FONT_CBP` (PoC, OFF).

## 5. Medición 2026-10-19 (hito 1.1–1.3, sesión actual)

### 5.1 Callbacks de render (tarea 1.1)

Sonda `SWORD_UI_CB_LOG=1` en `dispatchGuestBranch`: en `0x6daf6c` (y los otros tres `jalr` de
`0x6daef0`) se invocan **3 callbacks distintos**:

| callback | primer widget (heap varía) | cmd |
|---|---|---|
| `0x7547a0` | `0xcb4d40` | `0xcb4e20` |
| `0x756a28` | `0xcb5e00` | `0xcb5b50` |
| `0x756ab0` | `0xca7300` | `0xca71d0` |

`0x7547a0`/`0x756ab0` se re-invocan por comando (a0 = nodos distintos); `0x756a28` >1000 veces.
Call graph medido (`[ui-cb-call]`): `0x7547a0 → 0x7476e8/0x6d6a40/0x6d5f90`;
`0x756a28 → 0x6d6a40/0x5ea770/0x6d50e8/0x754a80/0x6f2630`; `0x756ab0 → 0x7440c0`.

### 5.2 Los callbacks NO emiten prims: la geometría se difiere a VU1 (tarea 1.2)

Con `SWORD_UI_CB_PRIMS=1` (tag del callback + tag del widget en `DrawPrimitive`): **0
`[ui-cb-prim]` y 0 `[ui-widget-prim]`** en 130 s, aun con `0x756a28` >1000 invocaciones. Los callbacks
solo arman comandos; la emisión es **diferida**:

- `[gs:content]` (prims UI): `prim=4` TRIFAN, `tme=1`, `fst=0`, `tbp0=10240` (page 320), `tbw=2`,
  `psm=19` (PSMT8), `tw=6/th=6`, `uv=(13312,15072)`, `rgba=(0,0,0,0)`, `pc=0x6e433c`.
- `pc=0x6e433c` ∈ **`FUN_006e4068`** (0x6e4068–0x6e45d8, escritor de paquetes GS/GIF).
  `[vu1:mscal]` con `eePc=0x6e4468 ra=0x6e4ebc` ⇒ la geometría pasa por **VIF1/VU1 (XGKICK)**.
- `[tex-hist]` 600/600 textured prims con `texelNZ=0`; `[gs:prims]`: **todos** los texturedDraws usan
  `tbp0=10240` (ninguno 10272/atlas); `[gs:diag] crt1 (fbp=128) rgbNZ=0 aNZ=0`.
- Primer tri muestreado (`[real-tri-probe]`): `st=(0.48633,0.0117187)` → `texUf=31.1249 texVf=0.75`
  ⇒ texel `(31,0)=0x0`; `[tri-probe] out=(0,0,0,0)`.

### 5.3 Causa raíz (tarea 1.3): el gestor de texturas y el atlas de fuente NO se registran/suben

Comparación contra el savestate real del selector (`work/pcsx2_states/videoformat_menu.p2s`):

- **VRAM** (dump `SWORD_DUMP_VRAM` en present 700, ya en el selector): page 320 = **byte-idéntica** al
  real (3119/3119 bytes ≠ 0); **pages 321–330 = 0** (real: 3188, 2670, 1014, 2463, … bytes).
- Decodificada como PSMT8+CLUT, la **page 321 real es el atlas de fuente** (glifos A-Z/a-z) con CLUT
  `cbp=10336` (page 323). La page 320 real es el **chrome** (caja gris con borde blanco, emblema).
- La tabla del gestor de texturas **no está en `0xA95650` en nuestro run**: el puntero global
  `0x8A5014` vale `0xA95500` (real: `0xA95650`; es el corrimiento **-0x150** del heap, no +0x150 como se
  creía para este bloque). Comparada **por contenido**:
  - **nuestra** `0xA95500`: **1 entrada** — `desc=0xE7FE90 vram=0xA0000 size=0x800` (chrome; el
    descriptor es `0xE80090-0x150`, ✓ mismo objeto).
  - **real** `0xA95650`: **5 entradas** — chrome `0xE80090/0xA0000/0x800`,
    font `0xE702E0/0xA0800/0x1800`, y 3 más (`0xE6BBE0`, `0xE76D60`, `0xE749E0`).
  ⇒ **sólo se registró el chrome**; `fnt_on_*` y los otros 3 assets nunca se registraron.
- Consecuencia: el descriptor de fuente emitido es el **fallback del chrome con `tbp0` parcheado**
  (`0x200507859930A820`: `tw=6/th=6`, `cbp=10300`) en vez del real
  `0x20050C05DD30A820` (`tw=7/th=7`, `cbp=10336`) — ya observado en v81/v82.
- El **microprograma VU1 correcto sí se sube**: `MPG #2` (dest 0, 2048 B) empieza con
  `f303ff0187102200...` = primeros bytes de `vu1MicroMem.bin` del savestate. El VU1 no es el problema
  primario. (El primer run usa el microprograma de boot `f0072e10...`; el del selector llega después.)

**Decisión de causa raíz: (b) estado distinto del real.** El juego no registra `fnt_on_*` ni sube las
pages 321–330; el texto no puede dibujarse y el chrome que sí existe se muestrea en su fila
transparente `(31,0)`. La hipótesis (a) (muestreo en zona vacía) es **síntoma** de lo mismo; (c) es
falsa (los callbacks corren y hay prims, sólo que diferidas por VU1).

### 5.4 Sondas nuevas (env-gated, OFF por defecto)

- `SWORD_UI_CB_LOG=1`: `[ui-cb]`, `[ui-cb-enter]`, `[ui-cb-call]`; setea `g_swordUiCurWidget`/`g_swordUiCbTag`.
- `SWORD_UI_CB_PRIMS=1`: `[ui-cb-prim]`/`[ui-widget-prim]` en `GSCpuBackend::DrawPrimitive`.
- `SWORD_DUMP_VRAM_AT=<present>`: dump de VRAM en un present concreto (además de 300/900/1500).
- `SWORD_DUMP_VU1CODE=1`: dump de VU1 code/data **sólo cuando** el microprograma del selector está
  cargado (`firstWord == 0x01ff03f3`).
- `SWORD_TEXREG_WATCH=1`: `[texreg-w]` para escrituras a `0xA95650..0xA956A0` (quién registra texturas).
- Se agregó `pc=` al `[gs:content]` existente.

## 6. Verificación de la respuesta v86 (2026-10-19) — su causa raíz es **REFUTADA**

> Medición propia con `SWORD_FONT_ASSET=1` (wrappers env-gated sobre `0x4f7d40`, `0x550ad0`,
> `0x5510d0`, `0x551d60`, `0x5530f0`, `0x553f20`, `0x551250`, `0x551390`, `0x700690`, `0x6fef28`,
> `0x5507b0`, `0x6d4f78`). Todos OFF por defecto.

### 6.1 Lo que v86 acertó (estático)

- `FUN_00550ad0` sí hace `jal 0x4f7d40` (`GetAsset`) y `beqz $v0` en `0x550b5c`.
- `FUN_006fef28` es el registrador (`0x6ff2ec/0x6ff3f4/0x6ff414`) y llama al uploader `FUN_006fe618`
  en `0x6ff240`; la tabla es on-demand por textura.
- El renderizador de texto `FUN_00551d60` tiene el gate `0x551f6c` (`font_asset == 0`) y otro en
  `0x551f7c` (`count < idx`).
- La descripción de los 5 assets (chrome + 4 páginas `fnt_on_001..004`) coincide con la tabla real.

### 6.2 Lo que v86 **erró** (medido)

- **`GetAsset(0x6020800)` NO devuelve NULL**: `[font:get_asset] EXIT id=0x6020800 result=0xe20560`.
  Se llama 3 veces (widgets `0xE8BC40/0xE8BF30/0xE8C1B0`) y `font_asset=0xE20560` en los 3.
- **`FUN_005510d0` SÍ se ejecuta** (6 veces): `[font:load] EXIT ... tex_ptr=0xE85360 count=6` y las
  entradas `e0=0xE78E70 e1=0xE76AF0 e2=0xE74770 e3=0xE70070` son correctas.
- **El corte no está en `0x550b5c` ni en `0x551f6c`**: el renderizador de texto `FUN_00551d60` **nunca
  se llama** (`[text:gate]` = 0). La cadena llega hasta `FUN_005530f0` (widget de texto) con
  `a0=widget, a1=0xCB46F4`, pero éste no alcanza `0x551390`/`0x551250`.
- Gates internos de `0x5530f0` medidos:
  - `*(widget+0x10C)` = `0x009C7E50` ≠ 0 (texto presente) ✓
  - `*(widget+0x1C)` = 1 (gate `0x553198`) ✓
  - slot `+0xBC` = `FUN_005507b0` devuelve **1** (`[text:gateB]`) ✓
  - **`FUN_006D4F78` (layout/fit de línea) devuelve 0** (`[text:gateC]`, 32/32 veces) ⇒ en
    `0x55322C: beqz $v0 → 0x553EE4` **se salta todo el dibujo de texto**.
- Descriptor de fuente en RAM: `fnt_on_003` en `0xE700E0` (+0x3C = **`0x20000005DD308000`**: `tbp0=0`,
  `cbp=0`, resto `tw=7/th=7/psm=19/tcc=1`), vs real `0x20050C05DD30A820` (`tbp0=10272`, `cbp=10336`).
  La VRAM nunca se asigna porque `FUN_006fef28`/`FUN_00700690` **sólo** se invocan con el chrome
  (`[text:bind] NEW desc=0xE7FE90`, `[text:register] NEW desc=0xE7FE90`).
- Diferencia de estado del widget de texto (por contenido, real `0xE8BE40` vs nuestro `0xE8BC40`):
  `+0x100 = 0x41C00000 (24.0)` vs `0x00000000 (0.0)`; `+0x104 = 6` vs `3`. La tabla estática de estilo
  `0x876E80` es **idéntica** en ELF/real/recomp ⇒ la diferencia se produce en runtime, no en los datos.

### 6.3 Gate del layout: medido, y el estilo `+0x100/+0x104` **no** es la causa

`FUN_006D4F78` recibe `a0 = contexto UI` y `a1 = vector float`. Sonda `[text:gateC]` (primeras 8):

```
m=(0,0,-1,500) v=(0,0,0,180.992)          -> v0=0
m=(0,0,-1,500) v=(-200.002,46.0053,-105.003,284.214) -> v0=0
m=(0,0,-1,500) v=(-94.9985,-26.0006,-105.003,49.49)  -> v0=0
m=(0,0,-1,500) v=(25.0003,-26.0006,-105.003,49.49)   -> v0=0
```

La tabla de 5 filas (stride `0x14`) en `a0+0x94` es:
`r0=(0,0,-1,500)`, `r1=(0,0,1,-1)`, `r2=(0,0,0,0)`, `r3=(0,1,0,-292)`, `r4=(0,0,0,0)`,
`r5=(0,-1,0,-293.14)`. La fila que rechaza es **r3**: `f1 = v.y + 292` y devuelve 0 cuando
`v.w < f1` (p. ej. `46+292=338 > 284`). Es un chequeo de **encaje en el clip vertical**.

**A/B del estilo**: forzar `+0x100=24.0f` y `+0x104=6` (`SWORD_TEXT_STYLE_FIX=1`) **no cambia nada**:
el vector sigue `(0,0,0,180.992)`, `FUN_006D4F78` sigue devolviendo 0, `[text:gate]`=0 y no hay binds
de fuente. ⇒ `+0x100/+0x104` **no** son la causa (son consecuencia/estado no usado por este gate).

Diferencias reales del widget de texto (por contenido, real `0xE8BE40` vs nuestro `0xE8BC40`):

| offset | real | nuestro |
|---|---|---|
| `+0xE0/+0xE4` | `0x192` / `0x46` | iguales |
| `+0xFC` | `0x41100000` (9.0) | `0x0` |
| `+0x100` | `0x41C00000` (24.0) | `0x0` |
| `+0x104` | `6` | `3` |
| `+0x124` | `0x00050035` | `0x00050000` |

El sub-objeto de estilo `*(widget+0x8C)` (que llena el vector vía `FUN_005507B0`) es **idéntico**
(`+0x30/34/38 = (0,0,1)`, `+0x40/44/48 = (-200.002,46.0053,-105.003)`), y `0x5507B0` devuelve 1.
⇒ lo que decide es la **matriz/contexto UI** (`a0+0x94`, transitorio) y/o el `v.w` calculado en
`0x553224`, no el style sub-object ni `+0x100`.

### 6.4 Verificación de v87 + A/B (2026-10-19): el gate es el único bloqueo; causa = cámara reflejada

**v87 verificado (estático)**: `FUN_006d3620` construye los planos en `UIroot+0x94`, llamado en
`0x6d5110` desde `FUN_006d50e8` cuando `*(camera+0x14)==1`; `0x6d3c70: swc1 $f3, 0x48($a1)` escribe
`plane3.D` en `UIroot+0xDC`. `v.w = max(W/2,H/2)*sqrt(2)` (el `0x4000` es la parte alta de `2.0f`, no
16384). `widget+0xFC/+0x100/+0x104/+0x124` se escriben **dentro de `FUN_005530f0` después del gate**
(`0x553278/0x553288/0x5532a4/0x553314`); por eso el A/B de forzarlos no cambiaba nada.

**Test A (forzar `v0=1` en `ra=0x55322C`, `SWORD_TEXT_FORCE_FIT=1`)**: desbloquea TODO el pipeline:
- `[text:gate]` 16 (antes 0); `[text:bind]` 5 (chrome + `0xE700E0/0xE6B9E0/0xE76B60/0xE747E0`);
  `[text:register]` 10; uploads `dbp=10272/10368/10464/10528/10560`; `[gs:prims]` con
  `tbp0=10272` (224 draws), 10368, 10464, 10528. `[gs:diag]` con present default: **`crt1 (fbp=0)
  rgbNZ=22560`** (el buffer presentado es `fbp=0`, `[gs:present] fbpDisp1=0`).

**Test B (corregir `plane3.D`: `-292 -> +292` en el call site, sin forzar retorno)**:
`[frustum:fix] plane3.D -> 292`; `FUN_006D4F78` devuelve 1 para las llamadas del widget de texto
(las 6 que devuelven 0 son otros callers, no el texto). Mismo resultado que Test A: `[text:gate]` 16,
binds 5, uploads de las pages 321–330, `[gs:diag] crt1 (fbp=0) rgbNZ=22560`.

**Causa raíz afuera del gate: la cámara UI está REFLEJADA.** La matriz base en `*(UIroot+4)+0x50` es
`diag(-1, -1.142857, -1)` (det −1, reflexión) en nuestro run, y `diag(-1, +1.142857, -1)` (det +1) en
el savestate real. Solo cambia el **signo del eje Y/up**. El builder de planos refleja fielmente esa
matriz: `plane3.D = -292` vs real `+292`, y el test esfera-vs-plano rechaza el widget.
- El `smode` del disp env también difiere: nuestro `0xA8D0B8 = 2` (interlace=0, ffmode=1) vs real
  `1` (interlace=1, ffmode=0). El stub `sceGsResetGraph` **no se llama** (el libgraph del juego está
  recomplido), así que `SWORD_FORCE_PAL` sobre el stub no tuvo efecto. El escritor del env/smode del
  juego es el siguiente objetivo.
- Los screenshots del host (`PS2_SCREENSHOT_DIR`) salen **negros incluso en boot** (raylib headless);
  no sirven como validación visual en este entorno. La métrica fiable es `[gs:diag]`/VRAM.

### 6.5 Próximo paso (v88)

1. **Matriz base de la cámara UI** (`*(UIroot+4)+0x50`): en nuestro run es
   `diag(-1, -1.142857, -1)` (reflexión, det −1); en el savestate real `diag(-1, +1.142857, -1)`
   (rotación propia, det +1). **¿Qué función y qué instrucciones** escriben esa matriz? ¿El signo de Y
   sale de un flag de **interlace/ffmode** del disp env, de la altura del viewport (¿`-h`?), de un
   vector `up`, o de una constante? Dirección exacta del store de `+0x14` (Y row).
2. **Disp env `smode`** (`0xA8D0B8`): nuestro run = `2` (interlace=0, ffmode=1), real = `1`
   (interlace=1, ffmode=0). El stub `sceGsResetGraph` no se llama (libgraph del juego recomplido).
   ¿Cuál es la **función recomplida** que escribe el env/smode y con qué args? ¿El builder de la cámara
   UI lee ese flag para elegir el signo de Y?
3. **A/B para forzar PAL/interlace por el camino real**: dónde instrumentar (env writer o reset graph
   recomplido) y qué log esperar (`smode` 2→1 y la matriz `-1.142857`→`+1.142857`; el gate de culling
   pasaría natural). Si el signo **no** cambia con el modo, descartar la hipótesis.
4. Si la cámara es una reflexión, ¿también **espeja la escena 3D**? Si sí, el fix correcto es la base
   de la cámara, no el signo de los planos de culling (Test B), que sólo compensa el gate.
5. **A/B**: instrumentar el store de la matriz (`+0x14` de `*(UIroot+4)+0x50`) y el `smode`; capturar
   ambos en un frame del selector (la matriz es transitoria; el savestate en reposo no la tiene).

## 7. Verificación de v88 (2026-10-19): su explicación de modo/dirección **no se confirma** en nuestro run

> Corrida válida de **100 s**: llega al selector (`[task] f=960, t3sub=10`) y al culler
> (`[text:gateC]` 8, `[text:plane]` con p3=-292). En esa misma corrida:

- `FUN_006f0d68` (el supuesto decisor de modo de video) **nunca se llama** (`[disp:mode]` = 0).
- El `sceGsResetGraph` recomplido **sí** se llama una vez, con **args PAL**:
  `[gs:reset-recomp] mode=0 interlace=1 omode=3 ffmode=0 ra=0x6f0180` (el ra no es 0x6f0d68).
- Los flags de modo (`0xA8DAF4 = 0x203`, bit1=1) y `omode` (`0xA8DB02 = 3`) son **idénticos** en
  nuestro RAM y en el savestate real. ⇒ el flag no explica la diferencia.
- `FUN_007a7f20` (la selección de dirección que cita v88, rango generado 0x7a7f20–0x7a8374) **no se
  llama** en la corrida válida (`[cam:dir] a0=... cfg=... mode=...` = 0). Las llamadas a
  `FUN_006d0280` que sí se ven pasan `dir=(0,1,0)` con `a0` en el stack (otro subsistema).
  **Chequeo de split**: `FUN_007a7c30` (0x7a7c30–0x7a7f18) termina en `0x7a7f10: jr $ra`; el código de
  dirección `0x7a7f74` está en `FUN_007a7f20`, una entrada real separada. El camino que arranca en
  `0x7a7db0` (interior a `FUN_007a7c30`) **retorna en 0x7a7f10** y no llega a 0x7a7f74. ⇒ la ruta de
  dirección de v88 no es la que ejecuta el selector (o se entra por una dirección interior no medida).
- `FUN_006d3620` **sí** se llama, pero con `a0=0xCB5330` (node `0xCB55E0`, `localY=worldY=+0.928477`),
  **no** con el contexto del culler `0xCB5B50` (cuyos planos leen `-292`). ⇒ los planos que usa el
  culling de texto no los acaba de escribir el builder con esa cámara; el objeto/contexto es otro.
- Conclusión: la cadena “interlace/ffmode → dirección ±Z → matriz → planos” de v88 **no ocurre** en
  nuestro run. La corrección de la matriz en el wrapper del builder no se aplicó porque el nodo real
  es `0xCB55E0` con Y **positivo** (no la matriz reflejada que usa el culler).

**Estado**: el A/B de v87 sigue siendo válido y es la vía verificada para destrabar el hito:
- `SWORD_TEXT_FORCE_FIT=1` (Test A) y `SWORD_TEXT_FIX_PLANES=1` (Test B, `plane3.D -292→+292`)
  desbloquean el texto, los binds/registros de fuente y las subidas de las pages 321–330, con
  `[gs:diag] crt1 (fbp=0) rgbNZ=22560` en el buffer presentado.
- La corrección de cámara de raíz queda **abierta**: hay que identificar **qué objeto** es
  `0xCB5B50` para el culler y quién escribe **sus** planos (el builder usa `0xCB5330`).

## 8. Verificación de v89 (2026-10-19): mapeo de objetos CONFIRMADO; “el builder corre para la UI” REFUTADO

**Confirmado (RAM real vs run)**:
- `0xCB5B50` (nuestro) ≡ `0xCB5D70` (real): cámara UI 2D, `+0x14=2`, half extents **256×256**,
  node `0xCB5E00`/`0xCB6020`. `0xCB5330` ≡ `0xCB5560`: cámara 3D, `+0x14=1`, half extents
  **0.3×0.225**, `Y=+0.928477`. El corrimiento de heap es **−0x220**.
- Node de la cámara UI: nuestro `node+0x24 = node+0x64 = -1.142857`; real `= +1.142857`.
  El 3D es `+0.928477` en ambos. ⇒ la única diferencia es el signo Y del nodo de la UI.
- El loop del culler itera **5 planos** (`0x6d4f94: t0=5`); el generado es fiel. El plano 5 (`+0xF8`)
  queda afuera por diseño.

**Refutado (medido con dedupe por cámara, 100 s, selector `f=970/t3sub=10`)**:
- Con `[frustum:build]` deduplicado por `a0`, **`FUN_006d3620` sólo se llama con `0xCB5330`** (3D);
  **nunca** con `0xCB5B50`. `[cam:fix]` no se dispara (no hay nodo negativo que procesar), y los planos
  del culler siguen `p3=-292`, `p2/p4=0`. ⇒ la afirmación de v89 (“el builder SÍ corre para 0xCB5B50”)
  **no se sostiene en nuestro run**: los planos de `0xCB5B50+0x94` los escribe **otra ruta/una vez**,
  no el builder per-frame.
- `[cam:dir]` sigue mostrando sólo `dir=(0,1,0)` (3D); la dirección UI no aparece.
- `[cam:ctx]` (watch de `*(0xA887B8)` por `Store32`) = **0**: las escrituras de cámara activa
  (`0x74b040`/`0x6d7108`) usan **FAST_WRITE32** o no pasan por `Store32`; hay que instrumentarlas por la
  función contenedora o por mprotect (sin cubrir el segmento del ELF).

**Conclusión**: el culler usa el objeto correcto (`0xCB5B50`), pero **no se puede afirmar que
`FUN_006d3620` lo actualice**. Falta identificar **quién escribe los planos de `0xCB5B50+0x94`**
(probablemente setup único o una función distinta). El unblock verificado sigue siendo el Test A/B de
v87 (`plane3.D -292→+292`) y, para el arreglo de raíz, primero hay que encontrar ese writer.

## 9. CAUSA RAÍZ FINAL (2026-10-19): bug del recompilador en `COP1 sqrt.s` (usa `Fs` en vez de `Ft`)

v90 acertó el despacho por tipo (`FUN_006d50e8`: type==1 → `0x6d3ee8`/`0x6d3620`; type!=1 → `0x6d4600`/
`0x6d40c0`) y el builder ortográfico real es **`FUN_006d40c0`** (corre para `0xCB5B50`). El nodo UI se
crea en `FUN_00515d40` con rotación de 180° sobre Y (`0x515e2c → FUN_006d6310 → FUN_006cc5e0`).

**El bug**: en `FUN_006cc5e0`, la instrucción **`0x6cc628: 0x46010044`** (`sqrt.s f1, f1`, campos
`ft=f1, fs=f0, fd=f1`) fue traducida a `ctx->f[1] = FPU_SQRT_S(ctx->f[0])`. La PS2 usa **`Ft`** como
fuente de `sqrt.s` (PCSX2 `iFPUd.cpp`: `FPURECOMPILE_CONSTCODE(SQRT_S, XMMINFO_WRITED |
XMMINFO_READT)`; `_Ft_ = _Rt_`). El juego calcula `f1 = x²+y²+z²` y luego `sqrt.s f1, f1`; el generado
hizo `sqrt(f0)` (el cuadrado de Z). Con eje `(0,1,0)`, `z=0` ⇒ `f1=0` ⇒ normalización 0 ⇒ eje cero ⇒
`R(180°) = -I = diag(-1,-1,-1)` en vez de `diag(-1,+1,-1)` ⇒ `FUN_006d40c0` produce `plane3.D=-292`/
`plane5.D=-293.14` y el culling descarta el texto. **No era un problema de modo de video, de cámara ni
de assets: era el recompilador.**

**Fix (raíz)** en `tools/PS2Recomp/ps2xRecomp/src/lib/fpu_translator.cpp`:
- `COP1_S_SQRT`: fuente `ft` (era `fs`).
- `COP1_S_RSQRT`: `fd = fs / sqrt(ft)` (era `1/sqrt(fs)`), conforme a PCSX2 `recRSQRT_S_xmm`
  (`READS | READT`).
- `ABS/MOV/NEG` siguen usando `Fs` (PCSX2: `XMMINFO_READS`), correcto.

**Generado**: se parchearon **94 líneas en 61 archivos** de `work/generated/` (las demás ya tenían
`ft == fs`) decodificando la instrucción real de cada sitio (script `/tmp/patch_sqrt.py`). Una
regeneración completa con el recompilador corregido reproducirá el fix; no hay que mantener el parche
manual.

**Validación estricta (sin sondas)**: corrida de 115 s, `t3sub=10`, sin `SWORD_FONT_ASSET` ni fixes de
cámara/planos. `[gs:diag] crt1 (fbp=0): rgbNZ=260187 aNZ=264752`; `[gs:present] fbpDisp1=0` ⇒ el buffer
presentado **no es negro**. El nodo UI queda en `worldY=+1.142857`, `plane3.D=+293.143`,
`plane5.D=+292` (coincide con PCSX2).

**Pad (1.5)**: `[pad-host] buttons=0x40` (Cross) y `t3sub` 10 → 11 → 0/1/3/50; el selector avanza. El
mapeo de flechas ya está en `padHook51c7c0` (Up=0x8000, Down=0x2000, Left=0x2, Right=0x8).

**CORRECCIÓN VISUAL (2026-10-20): el Hito 1 NO está cerrado.** `rgbNZ>0` no prueba que se vea el
selector: lo cumple el fondo. Decodifiqué la VRAM real del run con el layout PSMCT32 exacto
(`GSPSMCT32::addrPSMCT32`, fbp=0, fbw=10) y comparé con la captura real
`/tmp/realstate/Screenshot.png` (caja blanca “Select video format…”, 640×480).

- present 350 (`f≈190`): casi negro (nz=3120, 32 píxeles brillantes: un triángulo rojo).
- present 450 (`f≈200-260`): fondo magenta/azul (nz=260187), sin texto.
- present 600 y 900 (`f=310`, `t3sub=10`, `fadeVal=0`): mismo fondo magenta (nz=261139, 75k píxeles
  brillantes), **sin caja ni texto**.
- El A/B con solo el fix de cámara (`SWORD_UI_CAM_FIX=1`, antes del patch global de `sqrt`) daba
  `rgbNZ=22560`, compatible con el selector real; el build con los 94 `sqrt` corregidos da 261k magenta.
  Hipótesis: los otros `sqrt` corregidos hacen visible un escenario 3D que tapa/desplaza la UI, o el draw
  de la UI sigue mal (layout/UV/depth). Pendiente aislar cuál de los 93 sitios cambia la escena y
  re-verificar **visualmente**, no por `rgbNZ`.

**Hito 1 ABIERTO**: el estado `t3sub=10` y el pad funcionan, pero el selector no se ve en el framebuffer.

## 10. Regla de cierre de hitos de UI (2026-10-20)

Un hito de pantalla se cierra **cuando la pantalla se ve y se puede operar**, no cuando el estado
interno o un contador lo sugieren. `rgbNZ > 0`, los binds/uploads de texturas y los gates en 1 son
**smoke tests**, no aceptación: los cumple un fondo cualquiera.

La verificación obligatoria es:

1. Volcar la VRAM del frame presentado (`SWORD_DUMP_VRAM`, `SWORD_DUMP_VRAM_AT=<present>`).
2. Decodificarla a PNG con `game/decode_gs_frame.py` (PSMCT32, `fbp=0`, `fbw=10`, 640×448).
3. Mirar el PNG y compararlo con la captura real de PCSX2: para el selector, deben verse la caja,
   `Select video format.`, las opciones `NTSC(60Hz)`/`PAL(50Hz)` y el cursor.
4. Operarlo con el pad real y ver el cambio en pantalla.

El Hito 1 queda bloqueado hasta que 1.6 pase con esa verificación. El primer intento (present 900,
`t3sub=10`, `fadeVal=0`) muestra un fondo magenta sin texto: **no cuenta**.

## 11. Verificación de v91 y causa directa del magenta (2026-10-20)

- **G=0: confirmado.** En el frame decodificado, `max(G)=0` y `sum(G)=0` en todos los píxeles; R=B y
  los niveles 21/241/255 coinciden con la captura real. El “magenta” es gris sin el canal verde.
- **CBP=10300: REFUTADO.** Los TEX0 que el juego escribe (registro GS 0x6) son los correctos:
  - chrome `0x200503859930A800`: TBP0=10240, TW=6, TH=6, CBP=10268.
  - fuente página 321 `0x20050C05DD30A820`: TBP0=10272, TW=7, TH=7, **CBP=10336** (idéntico al real).
  - páginas 324/327/329: CBP=10432/10496/10560.
  La paleta en `0x286000` (CBP=10336) de nuestro volcado es la real (`0x80898989, 0x80989898, …`,
  G=0x89/0x98/0xA8). El descriptor `0x200507859930A820` de v91 era una medición vieja (pre-fix de binds).
- **Causa directa del G=0: el color de vértice del path packed VU1/GIF.** En
  `GS::writeRegisterPacked`, descriptor 0x01, el paquete llega `lo=0x80`,
  `hi=0x7fffffff00000080` ⇒ `(R=128, G=0, B=128, A=255)`. El parser del engine lee cuatro lanes de
  32 bits y es correcto; el paquete **ya viene sin G**. En MODULATE (`out.g = (tg * vg) >> 7`) eso
  anula el verde aunque el texel/paleta tengan G correcto. `[tri-probe]`:
  `v0=(128,0,128,255) texel=(233,24,20,41) out=(233,0,20,81) tbp0=10240 cbp=10268`.
  El path directo `GS_REG_RGBAQ` no recibe estas escrituras (sonda = 0); van por packed VU1.
- **Microcódigo VU1**: el dump cuando `firstWord == 0x01ff03f3` cambia entre runs: run1 difiere del
  real en 12126 bytes; run100 en 3366; run1 vs run100 en 8760. Cabeceras iguales. Puede ser upload
  incompleto/prematuro, variantes del selector, o un bug de MPG/VIF1. Los dumps están en
  `/tmp/recomp_vu1code_run{1,100}.bin` y `/tmp/recomp_vu1data_run{1,100}.bin`; el real en
  `/tmp/realstate/vu1MicroMem.bin` y `vu1Memory.bin`. Consulta v92 escrita.
- **Geometría**: v91 punto 4 (no hay 3D; es UI) es consistente, pero el match posicional R/B contra la
  captura real es 0.26% y el fondo es un degradado 14–23 en vez de negro. Después de corregir el color
  hay que re-verificar layout/escala/UV.
- **v91 punto 5 (COP1)**: confirmado. Solo `SQRT_S`/`RSQRT_S` leen `Ft`; `CVT/ABS/MOV/NEG` leen `Fs`;
  `ROUND/TRUNC/CEIL/FLOOR` no existen. No tocar el traductor más.

**Hito 1 sigue ABIERTO.** Próxima consulta: `work/gemini/msg_gemini_v92.md`.

## 12. v92: bug de `PS2_PEXEW` confirmado; fix aplicado, A/B pendiente (2026-10-20)

- **Confirmado contra PCSX2**: `PEXEW` debe dar `rd = (rt2, rt1, rt0, rt3)`; el intérprete
  (`MMI.cpp:1435`) y el dynarec (`recPEXEW`, `PSHUF.D 0xc6`) lo implementan así. Nuestra macro en
  `ps2_runtime_macros.h` usaba `_MM_SHUFFLE(2,3,0,1)` = `(w1,w0,w3,w2)`.
- **Cadena del bug**: `FUN_00710580` (`0x7109fc..0x710b10`, y gemelos) arma color/escala para VU1 con
  `mfc1 / pexew / mfc1 / ppacw`. Con la shuffle rota, G queda 0 y W toma el VIFcode
  (`0x6C0103Fx`); en VU1 data `0x3FB`/`0x3FC` el W es literalmente el VIFcode, y el paquete packed
  final sale `lo=0x80`, `hi=0x7fffffff00000080` (`0x7FFFFFFF` = saturación FTOI0, no Q).
- **Fix aplicado**: `PS2_PEXEW(rs) = _mm_shuffle_epi32(rs, _MM_SHUFFLE(3,0,1,2))`. Se emite como
  macro en 16 funciones del generado; **no hace falta regenerar** `work/generated`. Full rebuild en
  curso (el header lo incluyen todos los `.cpp`).
- **VU1**: run100 es la variante legítima y coincide con `vu1MicroMem.bin` en `0x000..0x5CE`; el resto
  del real es relleno sin saltos. run1 era un dump prematuro. El upload MPG/VIF1 está bien.
- **Geometría**: se espera que el mismo bug explique XYZ saturadas; **re-medir después del fix** antes
  de tocar UNPACK V2/V3 (diferencias confirmadas en código, impacto no medido).
- **Otras MMI** (`PEXEH/PEXCH/PEXCW/PROT3W/PREVH/PINTH/PINTEH`) están mal pero sin uso actual; quedan
  como deuda latente, fuera del alcance del hito.
- **A/B de Hito 1.6**: tras el rebuild, volcar VRAM en present 900, decodificar con
  `game/decode_gs_frame.py` y exigir `max(G)>0`, `R==G==B` en la UI, match posicional R/B contra
  `Screenshot.png` y las opciones visibles. Si la geometría sigue mal, recién ahí revisar UNPACK.

## 13. A/B del fix PEXEW (2026-10-20): color y opciones restaurados; queda layout/duplicación

- **Full rebuild**: `s6xxhk2e4` terminó **exit 0** (`[100%] Built target sword_etheria`).
- **A/B** (present 1500; `SWORD_DUMP_VRAM_AT=900` fue sobrescrito por el dump automático de 1500):
  - `maxG=255`, `sumG=2.231.477` (el verde ya no es 0);
  - `R==G==B` en **59.197/60.634** píxeles no negros (97,6%);
  - `nz=60.634`, `bright=2.911`; top colors `(20,20,20)=37.760`, `(21,21,21)=8.269`,
    `(110,110,110)=1.271`, `(251,251,251)=1.007` — grises del selector real;
  - `[task] f=1780`, `t3sub=10` (el tick mejoró mucho: antes f=260 a 115 s).
- **Visual**: el PNG y el frame presentado (`work/build-game/frame_300.bmp`) muestran la caja, el
  texto `Select video format.`, `Currently display is PAL (50Hz).`, las opciones `NTSC(60Hz)` /
  `PAL(50Hz)` y el cursor rojo. **Pero** hay bandas horizontales y **copias fragmentadas del texto**
  a distintos x/y (p. ej. `Select v` arriba a la derecha, `ideo format.` a la izquierda, y la copia
  central completa pero clipeada en `50H`). El frame presentado muestra lo mismo: **no es un artefacto
  del decode PSMCT32**.
- **Conclusión**: `PEXEW` era la causa raíz del G=0 y de la geometría saturada; el selector ya se ve.
  Queda un problema de **layout/posición/duplicación de widgets o de chunks de texto** (la caja es más
  angosta que la real y el texto se parte/repite). Hito 1.6 **sigue abierto** hasta que el frame sea
  una sola caja limpia con el texto y las opciones, como `Screenshot.png`.
- **Siguiente medición local**: enumerar los widgets/nodos UI vivos en `t3sub=10` (direcciones,
  posiciones, callbacks) para ver si el texto se dibuja dos veces (widgets duplicados o chunks con
  avance/posición mal) y re-medir el ancho de la caja y `+0xFC/+0x100/+0x104`. Solo después evaluar
  UNPACK V2/V3.

## 14. Texto duplicado: el nodo temporal de escena se adjunta a la cámara 3D (2026-10-20)

- **La escena raíz es correcta**: real y nuestro recorriendo `node+8` dan **6 nodos** (cámara 3D,
  cámara UI, ventana, 3 textos); `next`/`prev` y las direcciones con shift −0x200/−0x230 coinciden.
  **No hay duplicación de escena.**
- **UI manager** (`*(gp-0x34C)`, real `0xCB50D0`, nuestro `0xCB4EA0`) coincide: `+0x08` cámara 3D,
  `+0x24` cámara UI, `+0x18/+0x1C` descriptores de escena (512×512, `+0x14=0x20/0x10`,
  `+0x24=0x05008002/0x07008001`), `+0x0C` nodo 3D. Las cámaras 3D/UI tienen `type=1/2`,
  `vfunc=0x756A28`, nodo y command list correctos.
- **Cadena del nodo temporal**: `FUN_00512630` (`0x5129B0..C0`) toma `a0=*(gp-0x34C)` (UI manager) y
  llama `FUN_0051AA80`; éste (`0x51AC64`) llama `FUN_005172C0`; éste (`0x517470`) hace
  `v0=*(UImanager+8)` (**cámara 3D**), `a0=*(v0+4)` (**nodo 3D** `0xCB55E0`) y
  `0x517474 jal 0x6D6A80` inserta el temporal `0x1FEDD80` (stack, `+0=0x00591B1C`, la task
  `pc=0x591B90`) en la lista de hermanos del nodo 3D (`mgr+8`), **después de la cámara 3D**.
  Ocurre 72 veces (≈1/frame): `[ui-insert] mgr=0xcb55e0 node=0x0 widget=0x1fedd80 ra=0x51747c`.
- Las **listas de comandos** de ambas cámaras solo tienen el nodo self de la cámara
  (`vfunc=0x756A28`, `type=1/2`); el texto no está en ellas.
- **Tres pases de texto**: `[text:chain]` con los 3 widgets se repite 3 veces/frame (n=1..3, 4..6,
  7..8); `[ui-cb-enter] 0x756A28` se invoca con UI (`a0=0xcb5b50`, n=1) y 3D (`a0=0xcb5330`, n=2).
- **Estilo**: `[text:gate]` actual `+0x100=24.0`, `+0x104=3` (real 6); el A/B
  `SWORD_TEXT_STYLE_FIX=1` cambia la copia central pero **no** elimina las copias fragmentadas.
  El problema principal es el **nodo temporal/3D**, no solo el estilo.
- **Hito 1.6 sigue abierto.** Consulta v93 escrita con estas mediciones; preguntas: qué es el
  temporal/vfunc `0x591B1C`, escena principal vs UI, orden update/draw real, fix natural (¿`+0x24`
  en vez de `+0x08`?), estilo y A/B. Falta la respuesta y el fix.

## 15. Verificación de v93 (2026-10-20): el fix propuesto no aplica

**Confirmado**:
- La lista raíz real/nuestra tiene los mismos 6 nodos (cámaras 3D/UI, ventana, 3 textos).
- Los nodos de texto tienen su command list `node+0x90` **vacía** (`next==prev==self`) en real y
  nuestro; el texto no lo dibuja el recorrido de escena, sino la cola UI de la cámara UI.
- `+0x104=3` es estado transitorio y `6` el display activo; `+0x124=(group<<16)|string_id` es
  plausible (título `0x00050035`, opciones `0x0005000A/09`).
- El sprite de clear 2D (`RGBA=(0,0,0,0)`) existe en el juego real.

**Refutado / no aplica**:
- `cam3d+0x274` es **0 en el real y en el nuestro** (`camui+0x274` sí es la cola UI:
  real `0xCB4AC0`, nuestro `0xCB4890`; las estructuras de cola coinciden: `+0=7`, `+3=2`, etc.).
  El fix “asegurar `cam3d+0x274==0`” es un **no-op**.
- `FUN_00756a28` chequea `*(camera+0xC)` (`0x756A5C: lw $s1,0xC($s0)`), **no** `+0x274`.
- `FUN_006D6A80` **sí usa `a2`** (lee `a2+3`, escribe `a2+8/+12`); el `widget=0x1FEDD80` es el `a2`
  real del callee, no un artefacto puro del hook. El `0x591B1C` puede ser el `$ra` del stack, pero
  no prueba que el argumento no exista.
- `SWORD_TEXT_FORCE_FIT` **no estaba seteado** en las corridas actuales (PEXEW/style). El
  force-fit/perspectiva aplica a corridas de diagnóstico anteriores, no a las 3 copias actuales.
- El UI manager `+0x2C` es `0xBF000000`, **no** la cola UI; la cola es `camui+0x274`.

**Dato nuevo decisivo**: con `SWORD_UI_CB_LOG=1`, el renderer del texto del selector
(`f5530f0`, widgets `0xE8BC40/0xE8BF30/0xE8C1B0`) se llama con **`cb=0x0`**: no está dentro de los
callbacks de cámara `0x756A28`/`0x7547A0`/`0x756AB0`, sino que lo llama la **task/UI** directamente.
`[text:chain] f5530f0 n=1..3` y `4..6` son **dos frames**, no dos pases; el texto del selector se
dibuja una vez por frame desde la task. Las copias con posiciones distintas son compatibles con
**acumulación entre frames** (clear/alpha test o buffer no limpiado) y/o el layout que hace scroll,
no con un doble draw de la cámara 3D.

**A/B `SWORD_NO_ALPHA_TEST=1`**: la corrida terminó en `t3sub=0` (salió del selector) y el dump
present 1500 no es comparable; el A/B fue **inconcluso** (el env afectó el flujo). Siguiente medición
local: clear/alpha test del sprite de clear y posiciones del texto por frame (dump en present donde
`t3sub=10`), o consulta v94 con estas correcciones.

**Hito 1.6 sigue abierto.** No se aplicó el fix de v93 (no-op).
