# Proposal: reach-main-menu

> ⚠️ **HISTÓRICO (2026-10-15).** Para el estado vigente: **`decisions.md` §2026-10-15** y el bloque
> "ESTADO ACTUAL" de `HANDOFF.md`. Resumen: el **arranque y el render están desbloqueados** (VRAM ~475 KB,
> `dma` ~1.700, `activeThreads=3`, CI en verde); el bloqueo restante es que el **frame presentado sigue
> negro** (el juego dibuja el fade/clear). Las hipótesis de foco del texto de abajo (`sema 8`, RPC sin
> réplica, state machine, watchpoint) están **superseded**; ver `decisions.md` ("Descartado").
>
> **ENTRADA VIGENTE: `HANDOFF.md`** (con su bloque de estado actual). Este proposal se conserva como
> registro; sus hipótesis de foco quedaron **superseded**. El gate real (2026-10-09) fue un **wait
> cruzado** en la fase de carga: ver `HANDOFF.md` §7–§8. La afirmación de abajo de que "el juego ejecuta
> su lógica, no gira en un loop" resultó **incorrecta** (ver `decisions.md`).

## Problem

Tras la recompilación (change `recompile-sword-of-etheria`, archivado) el recomp llega
**más lejos** —el gap del dispatcher SIF `0x4d3fe8` quedó cerrado y el thread 2 se desbloqueó—
pero **sigue en la fase negra** y **no aparece el menú**. El baseline (180 s, estado natural
`SWORD_FORCE_STATE=0`) da: `vbprof n=10681` (~60 fps), `nonZeroRgb=0`, vectores TYOSD **n=2**.

**Hipótesis descartada con evidencia (audio/SPU2 NO es el bloqueo):**

- El `[gen-audio] 6e4dd8 SPIN-EXIT` **no es un hack de rescate**: es un `fprintf` contador en la
  etiqueta. La sección crítica (`di`/`sync.p`/`mfc0 Status`/loop/`ei`) **sale naturalmente**
  (la recompilada limpia IE con `di`).
- El audio corre **normal**: ~551 llamadas en 180 s; el mezclador `0x6e4068` se ejecuta.
- El **thread principal NO está clavado en el audio**: su pc más frecuente (`0x6e4ebc`) tiene
  **1.2%** de las muestras; el resto se reparte por todo el código del juego ⇒ **el juego ejecuta
  su lógica**, no gira en un loop.

**Lo que sí queda como bloqueo (candidatos con evidencia):**

1. **El state machine de escena no avanza** (el juego corre pero no transiciona de la fase negra
   al título/menú). Es el residuo "lógico" tras descartar render (pipeline OK) y SIF (arreglado).
2. **`sema 8` desbalanceado**: 17 `WaitSema(8)` vs 9 `SignalSema(8)` en el baseline ⇒ ~8 esperas
   colgadas (`0x51ee84`/`0x51eeb4`).
3. **Las RPC del juego no reciben réplica**: `sid=0x80000592`/`0x8000059c`/`0x80000006` con
   `rpc=0` (los servidores que la consola registra y el IOP emulado no); el state machine puede
   depender de su respuesta.

Además hay **parches que enmascaran**: `SWORD_FORCE_STATE` (por default) fuerza el estado del
driver de sonido **2→5**, pero **5 = idle** (la rama activa es **2**).

## Proposed change

Desbloquear el **avance de fase** para llegar al **menú**:

1. **Trazar el `sema 8`**: quién espera, quién debería señalizar (`0x51ee84`/`0x51eeb4`), y por
   qué quedan 8 esperas sin cubrir.
2. **Instrumentar el state machine de escena**: identificar la variable de escena/paso que no
   avanza y la condición que la frena (comparando con el real, que sí llega al menú).
3. **Dar réplica a las RPC del juego** (`0x80000592`/`0x8000059c`/`0x80000006`) — o cargar/registrar
   el servidor que corresponda — para que el state machine no se trabe esperando.
4. **Verificar el avance de fase** sin parches (estado natural 2, triages apagados).
5. **Hito de cierre**: título + **menú principal visibles** en el recomp (frame con `nonZeroRgb>0`).

## Scope

**In of scope**
- **State machine de escena** del juego (variable/paso de fase; instrumentación y corrección).
- **`sema 8`** (`0x51ee84`/`0x51eeb4`): diagnóstico del desbalance y su señal.
- **RPC del juego** `0x80000592`/`0x8000059c`/`0x80000006`: réplica/registro de servidor.
- Corrección del default de `SWORD_FORCE_STATE` (no forzar 2→5).
- Verificación con las trazas existentes (`[triage-vbprof]`, `[triage-sema]`, `[gen-audio]`,
  `[TYOSD-*]`, `frame:upload`).

**Out of scope**
- Recompilar el juego (ya hecho; CSV de Ghidra corregido).
- El pipeline de render/GS (verificado funcionando).
- **Modelo SPU2/audio**: hipótesis descartada con evidencia; sólo se retoma si el trazado de fase
  lo vuelve a señalar.
- La preparación de GitHub / tag `v0.1.0` (change posterior).

## Risks

- **Instrumentar de más**: *mitigación*: un `env` por experimento, revertir al cerrar.
- **Reducir el `sema 8` a un síntoma**: *mitigación*: primero trazar el waiter y su señalador
  antes de tocar código.
- **Réplica trivial de las RPC** no cambia nada (ya se probó `SWORD_RPC_FILL` sin efecto en su
  momento): *mitigación*: confirmar primero que el state machine depende de esa respuesta.
- **Falsa señal de éxito** (avanzar por un parche): *mitigación*: exigir avance con los triages
  apagados y `nonZeroRgb>0` en el frame.

## Producto final (definido 2026-10-15, planificación — no implementado)

Objetivo de producto: **el juego completo**, jugable en **Windows y Linux**, distribuido por
**GitHub Releases**, y que **cualquiera con su ISO** pueda generarlo sin vueltas. Puntos acordados:

1. **Juego completo** (no sólo el menú). El alcance por fases se define cuando se cierre el hito del
   menú; la fase actual sigue siendo llegar al menú.
2. **Fidelidad vs. parches**: se mantiene el criterio actual (overrides por dirección en
   `game_overrides.cpp`). La revisión de fidelidad queda **declarada como deuda** para cuando el juego
   esté completo.
3. **Plataformas**: Windows + Linux. CI ya compila las tools en ambos.
4. **Distribución**: GitHub Releases por tag `v*`, con el launcher, las tools y `build_release.py`.
5. **Modelo de contenido (sin copyright en el repo)**: el repo **no** distribuye ISO, ELF, assets ni el
   C++ recompilado (todo en `.gitignore`). El usuario aporta su ISO, validado por MD5
   (`b9c5115b77b7f05fbf14a67df8d3f99d`). **El ISO es necesario también en runtime** (los assets se leen
   del CD): el launcher debe persistir su ruta y usarla para *generar* y para *jugar*.
6. **Launcher** (entregable propio): pide el ISO una vez, expone **opciones configurables**
   (resolución, escalado, vsync, audio, pad), escribe el config y lanza el juego. Flujo:
   `elegir ISO → validar MD5 → (generar si falta) → jugar`.
7. **Reproducibilidad**: el CSV de funciones es un **input de build**; se versiona, pero con un
   **generador reproducible** en `game/` (reglas: overrides, splits, clamps, filtro de referencias) para
   que los cambios sean revisables en diff y sin depender de Ghidra.
8. **Calidad**: mover `validate_csv.py` a `game/` y correrlo como **paso del CI** (gate
   `0 SHADOW / 0 MIDFUNC / 0 MISSING`) antes de cualquier build.

**Out of scope ahora**: implementar el launcher, el generador o el gate (se hace al cerrar el hito del
menú). Este apartado fija el **qué** para no re-decidirlo después.
