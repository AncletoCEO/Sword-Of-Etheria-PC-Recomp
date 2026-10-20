# Arranque de sesión (desde cero) — Sword of Etheria (recomp PS2) → JUEGO JUGABLE

> **Pegar este archivo al inicio de la sesión nueva** y arrancar con:
>
> ```
> /cleto-apply reach-playable-game
> ```
>
> Change vigente: **`aspec/changes/reach-playable-game/`** (el anterior, `reach-main-menu`, queda
> **archivado**: su `decisions.md` §(1)–(32) es el log crudo y esta sesión **no** debe repetirlo).

---

## Qué hay que hacer

Cerrar el **hito 1**: que el **selector de video se vea**, y seguir hasta **jugar**.

Leer en este orden, antes de tocar nada:

1. `aspec/changes/reach-playable-game/decisions.md` — **digest verificado** (estado + refutaciones).
2. `aspec/changes/reach-playable-game/tasks.md` — hito 1 (§1.1–1.5) es lo primero.
3. `aspec/changes/reach-playable-game/design.md` — pipeline de UI con direcciones.
4. `aspec/changes/reach-main-menu/decisions.md` §(20)–(32) — evidencia cruda de las últimas rondas.
5. `work/gemini/README.md` — índice de consultas y su veredicto.

**Primer paso concreto (tarea 1.1/1.2):** identificar los **callbacks de render** de la UI. En
`0x6DAEF0`, el `jalr` de `0x6daf6c` invoca `*(cmd+0x10)` (`cmd = $s0-8`) tras recorrer la lista circular de
`widget+0x90`. Instrumentar la **dirección del callback** por widget, listar las distintas, y medir **qué
prims emiten** (PRIM/TEX0/UV/color) y si llegan al GS. **Ese es el eslabón.**

---

## Estado verificado al 2026-10-19 (resumen; detalle en `decisions.md`)

- El recomp **llega al selector** (`t3sub=10` desde f≈200) y el **pad del host funciona** por el camino
  real (`0x51C7C0` → `0xA42102`): `t3sub` 10 → 11 → 0 sin hacks.
- **La UI se construye, se enlaza y se dibuja**: descriptor Task 3 `0x9C8890`; ctor `0x805550` corre
  (`a2=0xa21418`); **5374 inserts** en `0xA88874` (el centinela está hardcodeado en `0x6d6a80`);
  `0x6db0d0` (flush/draw, ≈2289/corrida) llama a `0x6daef0` por widget; los gates pasan
  (`flags=0xf` visible, `rlEmpty=0`).
- **`0x83D290` es el destructor**, no la draw (sus 0 ejecuciones son correctas).
- **`rgbNZ=0`** ⇒ lo que emiten los callbacks de render no produce color visible. **No** es el GS, el
  present, la VRAM, los assets, el CLUT ni el muestreo (todo eso está medido y descartado).

**No re-investigar** (lista completa de refutaciones en `decisions.md` §2): inyección de VRAM, `TEX0`/`CBP`
forzados, redondeo del texel, alpha test, cache de CLUT, "la lista está vacía", "`0x6db0d0` es un
ClearAll", "la draw nunca corre".

---

## Flujo de trabajo con Gemini (ida y vuelta — parte del ciclo normal)

Cada hito avanza en **rondas**: nosotros medimos el runtime, Gemini lee el ELF. **No es un recurso de
emergencia**: es el flujo de trabajo. Detalle completo en `design.md` §"Flujo de trabajo con Gemini".

**Ciclo (una ronda = un `vNN`)**

1. **Disparador**: aparece una pregunta que se responde leyendo el binario (quién llama, qué offset, qué
   gate, qué instrucción) o hace falta una hipótesis nueva. **No** se consulta algo ya medido o refutado
   (`decisions.md` §2).
2. **Escribís `work/gemini/msg_gemini_vNN.md`** (el siguiente al `v85`) con: estado verificado **con
   números**, preguntas **numeradas**, foco en **análisis estático**, y **A/B** por hipótesis (dónde
   instrumentar y qué log esperar si es cierta y si es falsa).
3. **El usuario** la pega en Gemini (hace de proxy) y te trae `msg_gemini_reponsevNN.md`.
4. **Verificás cada afirmación** contra ELF/RAM/log **antes** de actuar (regla 1); anotás verificado /
   refutado con la evidencia.
5. **Implementás sólo lo verificado** (env-gated, default OFF) y **medís**.
6. **Registrás la ronda** en `decisions.md` (sección numerada) y en `work/gemini/README.md` (fila con
   veredicto); actualizás `tasks.md` si cambia el plan.
7. **Siguiente ronda** con lo recién medido. Nunca repetir una pregunta ya respondida.

**Reglas que se le exigen a Gemini**

1. **Enfoque estático**: direcciones, offsets, firmas, call sites, tablas, desensamblado, y **qué
   instrucción** produce el comportamiento. **No** afirmaciones de runtime sin log citado (archivo + línea
   completa): ya se refutaron varias así.
2. **Que declare qué archivos modifica y por qué**: sección `ARCHIVOS MODIFICADOS: <ruta> — <motivo>` (o
   "ninguno"). Está editando el repo y hay que poder verificar y no pisarse.
3. **Que no edite** runtime ni `work/generated/` salvo pedido explícito: que devuelva parches y los
   aplicamos y verificamos nosotros (hay sondas activas; el árbol debe quedar estable entre corridas).
4. Si su respuesta **contradice una medición**, gana la medición (repetir el negativo si hay
   no-determinismo). Si propone algo ya refutado, se lo señala con la evidencia.

---

## Reglas de método (obligatorias)

1. **Leer el artefacto antes de afirmar** (ELF `offset = vaddr − 0x4C0000 + 0x100`; generado en
   `work/generated/`, un `.cpp` por función con la instrucción original en comentario).
2. **`replaceFunction` sólo funciona sobre la entrada real**: es **inerte** en direcciones interiores o si
   se entra por **fallthrough** (p. ej. `0x6d51b0` se entra desde `0x6d5158`). Para el log directo, editar
   el `.cpp` generado (temporal).
3. **Los logs tienen líneas concatenadas**: `grep -c` miente; usar `grep -o` y contar ocurrencias.
4. **Las sondas limitadas a los primeros N prims suelen capturar padding** (pasó 3 veces). Filtrar por
   contenido (p. ej. `tbp0`, `texUf/texVf != 0`).
5. **Heap corrido ≈+0x150** vs el real: comparar **por contenido**, no por dirección.
6. **`GS.bin` = 425 B header + 4 MB + 84** (usar `/tmp/GS_vram.bin` o `dd skip=425`).
7. **Log vacío puede ser falta de flush**; `timeout` mata con SIGTERM (los dumps de salida pueden perderse).
8. **No-determinismo ocasional**: repetir los negativos antes de concluir.
9. **Toda instrumentación nueva nace env-gated y OFF**; apagarla al cerrar el hito.

---

## Comandos

```bash
# build (-j4; más = OOM). Binario ~382 MB.
cmake --build work/build-game/out-linux --target sword_etheria -j4

# corrida completa hasta el selector (~170 s; sin pad para quedarse en t3sub=10)
SWORD_PRESENT_CTX=1 SWORD_SIF_SEMA=1 timeout 170 ./work/build-game/out-linux/sword_etheria \
  work/elf/SLES_537.68 > /tmp/run.log 2>&1

# con pad sintético (flancos): el selector avanza solo
SWORD_PAD_PRESS=cross SWORD_PAD_TOGGLE=1 SWORD_PRESENT_CTX=1 SWORD_SIF_SEMA=1 timeout 150 \
  ./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68 > /tmp/run_pad.log 2>&1

# comparar VRAM
python3 work/teleport/diff_vram.py
```

## Entorno y estado del repo

- Repo del juego: branch `visual/advance-display-and-main-loop`. **No** push a `main` sin algo visual.
- Runtime fork (GPLv3): `tools/PS2Recomp` → `_external/PS2Recomp` (branch `diag-loader-rpc`), remoto
  `fork` = `AncletoCEO/Ps2Recomp-of-etheria`. **Hay cambios sin commitear** en `game_overrides.cpp`,
  `gs_cpu_backend.cpp` y `gs_frontend.cpp`.
- `work/` está **fuera de git** (nada con copyright: ISO, ELF, assets, C++ recompilado).
- Sondas y overrides al cierre: ver `decisions.md` §4.
- El ISO/ELF de trabajo: `work/elf/SLES_537.68` (extraído del ISO del usuario).
