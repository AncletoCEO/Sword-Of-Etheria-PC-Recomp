# Design: reach-playable-game

## Approach

**Medir la cadena completa antes de tocar código.** Cada hito se cierra con una métrica dura y con las
sondas apagadas:

1. **Hito 1 (UI visible)**: trazar los **callbacks de render** que `0x6daef0` invoca
   (`0x6daf6c: jalr $v0` con `$v0 = *(cmd+0x10)`, `cmd = $s0-8`) y correlacionar lo que emiten con lo que
   llega al GS (`[gs:prims]`, `[tex-hist]`, `[gs:diag]`). La pregunta es **qué prims/texturas emite cada
   callback del selector** y por qué no producen color, no si la UI "corre" (corre).
2. **Hito 2 (título/menú)**: con el selector visible y Cross funcionando, seguir la fase siguiente
   (`FUN_0083d990` → transición) y verificar que el título/menú se dibuja y navega.
3. **Hito 3 (gameplay)**: medir el camino 3D (VIF1/VU1/XGKICK) y el **ritmo** del tick.
4. **Hito 4 (audio/save/cine)**: verificar salida SPU2, reproductor y memory card.
5. **Hito 5 (producto)**: launcher + release + CI.

## Flujo de trabajo con Gemini (ida y vuelta)

El análisis estático del ELF se hace en **ciclos con Gemini**: nosotros medimos el runtime, Gemini lee el
binario. **Es parte del flujo normal de cada hito**, no un recurso de emergencia.

**Ciclo (una ronda = un `vNN`)**

1. **Disparador**: aparece una pregunta que se responde leyendo el ELF/generado (quién llama, qué offset,
   qué gate, qué instrucción) **o** hace falta una hipótesis nueva. **No** se consulta algo ya medido o
   refutado (`decisions.md` §2).
2. **Preparar `work/gemini/msg_gemini_vNN.md`**: estado verificado con números (no adjetivos), preguntas
   **numeradas**, foco explícito en **análisis estático**, pedido de `ARCHIVOS MODIFICADOS: <ruta> —
   <motivo>`, y para cada hipótesis el **A/B** (dónde instrumentar y qué log esperar si es cierta y si es
   falsa).
3. **El usuario** lo pega en Gemini (hace de proxy; nosotros no llamamos a la API) y trae
   `msg_gemini_reponsevNN.md`.
4. **Verificar cada afirmación** contra ELF/RAM/log **antes** de actuar (regla 1). Anotar verificado /
   refutado con la evidencia.
5. **Implementar sólo lo verificado** (env-gated, default OFF) y **medir** el efecto.
6. **Registrar la ronda**: sección numerada en `decisions.md` (evidencia + veredicto) y fila en
   `work/gemini/README.md`. Actualizar `tasks.md` si el plan cambia.
7. **Siguiente ronda** con lo recién medido. Nunca repetir una pregunta ya respondida.

**Reglas del ciclo**

- Gemini es proveedor de **análisis estático** (direcciones, offsets, call sites, desensamblado). El
  comportamiento en ejecución lo medimos nosotros: **no se aceptan afirmaciones de runtime sin log
  citado** (archivo + línea completa).
- Si Gemini propone editar runtime o `work/generated/`, se le pide **parche/instrucciones** y lo aplicamos y
  verificamos nosotros (hay sondas activas y el árbol debe quedar estable entre corridas).
- Si su respuesta contradice una medición, **gana la medición** — repitiendo el negativo si hay
  no-determinismo.
- Si propone algo ya refutado, se lo señala con la evidencia y se cierra la ronda.
- Una ronda por bloqueo; al cerrar cada hito, una ronda de revisión de lo aprendido.

## Architecture (verificada al 2026-10-19)

**Pipeline de UI (el que hay que cerrar)**

```
UI tick por frame  (0x7569B0, ra=0x7569e4)        ~1 por frame (2264 en 2240 frames)
  └─ 0x006D51B0  (flush: fija estado en 0xA887B8, llama al render de la cola, resetea 0xA88874)
       └─ 0x006DB0D0  (recorre la lista 0xA88874 y despacha cada widget)
            └─ 0x006DAEF0  (por widget)
                 ├─ gate visibilidad: flags = *(u8*)(widget+3) & 1   → medido: 0xf (visible)
                 ├─ gate comandos: lista circular en widget+0x90      → medido: rlEmpty=0
                 └─ 0x6DAF6C: jalr *(cmd+0x10)   ← ACÁ SE EMITE LA GEOMETRÍA (a investigar)
                      └─ (hijos: widget+0x98)
```

**Productores de widgets**

- Task 3 descriptor: `0x009C8890` (`+0x10 Init=0x83DFA0`, `+0x14 = 0x83D290` = **destructor**).
- Substate 2 de `FUN_0083DC40` → `0x00805550` (vtable+0x2DC): corre (`ra=0x83dd80`, `a2=0xa21418` = tabla
  `0x009C8850`), **tail-call a `0x6D6C40`** (cuenta/construye el subárbol).
- Inserciones: `0x006D6A80` **hardcodea el centinela `0xA88874`** (`0x6d6aa0`/`0x6d6ab8`), nodo en `a2+8`
  (`next=+0`, `prev=+4`). Medido: 5374 inserts, heads `0xe81d18`, `0xe8c358`, `0xcb5e08`…
- `0x006D67A8` = unlink de árbol/hermanos; no corre en nuestro run.
- `0x00804C50` **nunca** corre (no es el camino de inserción).

**Task scheduler**

- `0x5107F0(task, fn, sub)` → `task+0x20 = fn` (handler de estado), `task+0x38 = sub`, `task+0x3C = 0`.
  `0x510810(task, fn)` → `task+0x20 = fn`, `+0x38 = 0`, `+0x3C = 0`.
- `task+0x24` = destructor (copiado desde descriptor `+0x14` = `0x83D290` al spawnear); el scheduler lo
  copia a `+0x20` recién al matar la tarea (`0x50f4ec`). Por eso 0 ejecuciones es lo correcto.
- En el selector: `0x83DC1C` → `0x510810(task, 0x83D6B0)` → `0x83D990` (bucle de pad) es el handler vivo.

**GS / presentación (ya verificado, no tocar salvo bug)**

- PSMT8 conforme a PCSX2 (`PageExtent 128×64`, `BlockExtent 8×4`, `ColumnExtent 16×16`).
- Nearest = **truncamiento**; el sesgo de medio texel aplica **sólo** a bilinear.
- CLUT/CT32 y uploads conforme al real (page 320 byte-idéntica).
- Present: `SWORD_PRESENT_CTX=1` elige `fbpDisp1=128` (el juego dibuja ahí); `SWORD_TEST_PATTERN=1`
  prueba que el present puede mostrar (harness).

**Input**

- `0x51C7C0` (thunk) → `FUN_0051E700`: el juego lee `lhu` de `*(0xA42500)+2` (= `0xA42102`).
  Override durable en `game_overrides.cpp` (`replaceFunction(0x51c7c0u, padHook51c7c0)`), mapea el pad del
  host (teclado/gamepad) a las máscaras **active-high** del motor (Cross=0x40, Up=0x8000, Down=0x2000…).
  Verificado: `t3sub` 10 → 11 → 0 sin hacks.

## Validation

- **Métrica primaria del hito 1**: frame presentado con **`rgbNZ > 0`** y el selector **visible**, con
  **todas** las sondas/overrides apagados (`SWORD_CONFIRM_MENU`, `SWORD_INJECT_*`, `SWORD_FORCE_*` OFF) y
  controlado por pad.
- **Métricas de soporte**: `[gs:prims]` con `tbp0` del contenido; `[tex-hist] withNonZeroTexel > 0` en los
  prims que dibujan; `[ui-render]` coherente; `[gs:diag] crt1 (fbp=128) rgbNZ>0`.
- **No-regresión**: los conteos de referencia al cierre (2026-10-19): inserts 5374, flush 2289, resets
  2264, `t3sub=10` desde f≈200, `vramNonZero` 24293 con inyección (sin inyección ~3119).
- **Reversión**: toda instrumentación nueva nace **env-gated y OFF**; al cerrar cada hito se apaga.

## Decisión de diseño

Se **descarta** seguir por el camino de **inyectar VRAM, forzar TEX0/CBP o normalizar colores**: está
medido que no destraba `rgbNZ` y enmascara la causa. El foco pasa a **los callbacks de render de la UI**
(qué emiten) y, si el problema es de estado del juego, a **por qué ese estado está distinto del real**.
