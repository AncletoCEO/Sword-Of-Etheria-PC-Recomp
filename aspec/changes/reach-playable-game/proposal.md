# Proposal: reach-playable-game

> Change abierto el **2026-10-19** al archivar `reach-main-menu`. Punto de partida **medido**, no supuesto:
> la UI del selector **se construye, se enlaza y se despacha al renderizador en cada frame**, el **pad del
> host funciona**, y `rgbNZ=0` porque **lo que emiten los callbacks de render no produce color visible**.
> El estado completo y las hipótesis ya refutadas están en `decisions.md` de este change (digest) y en
> `aspec/changes/reach-main-menu/decisions.md` §(1)–(32).

## Problem

El recomp arranca, llega al **selector de video PAL/NTSC** (`t3sub=10`) y **se puede controlar**, pero la
pantalla sigue **negra** (`rgbNZ=0`). Sin ver el selector no se puede elegir, y sin eso no se avanza al
título, al menú principal ni al juego.

Lo ya descartado con medición (no volver a investigarlo):

- **No es el GS, ni el present, ni la VRAM, ni los assets**: la page 320 es byte-idéntica al real; la
  inyección de las 11 páginas reales no cambia `rgbNZ`; el present funciona (`SWORD_TEST_PATTERN` se ve).
- **No es el muestreo PSMT8/CLUT**: el direccionamiento coincide con PCSX2 y el nearest **trunca**
  (`GSDrawScanline.cpp:835-844`); el `floor(x+0.5)` que se probó era un desplazamiento de medio texel.
- **No es la maquinaria de UI**: `0x6db0d0` (flush/draw, ≈2289/corrida) llama a `0x6daef0` por widget;
  los widgets del selector están **visibles** (`flags=0xf`) y **con comandos** (`rlEmpty=0`).
- **No es el "linker" de la lista**: `0x6d6a80` hardcodea el centinela `0xA88874`; 5374 inserts/corrida.
- **`0x83D290` no es la draw**: es el **destructor** del descriptor de Task 3 (`0x9C8890+0x14`).

## Proposed change

Cerrar la brecha visual y avanzar hasta el **juego jugable**, en hitos:

1. **UI visible (hito inmediato)**: identificar los **callbacks de render** (`jalr` en `0x6daf6c` con
   `*(cmd+0x10)`), ver **qué primitivas emiten** (tipo, `tbp0`, `psm`, UV, color de vértice) y por qué no
   producen color. Corregir la causa (runtime o estado del juego) **sin inyecciones ni overrides de
   assets**. Hito: selector **visible** + navegable con pad, `rgbNZ > 0` con las sondas apagadas.
2. **Título y menú principal**: seguir la cadena después del selector (Cross) y verificar que el título y
   el menú principal se dibujan y navegan.
3. **Gameplay**: escena 3D (VU1/VIF1/XGKICK), cámara, colisiones y **ritmo** (hoy ~9 ticks/s contra 58
   VBlank — problema sistémico del scheduler/pacing, no de render).
4. **Audio, cinemáticas y guardado**: salida SPU2 verificada, reproductor de vídeo, memory card.
5. **Producto**: launcher (ISO + opciones) y release Windows/Linux por tag, con el CSV reproducible y el
   gate de validación en CI (ver `proposal.md` de `reach-main-menu` §"Producto final").

## Scope

**In**
- Callbacks de render de UI y lo que emiten hacia el GS (hito 1).
- Cadena de escenas después del selector (título/menú) y su estado (hito 2).
- Camino 3D, ritmo del scheduler y determinismo (hito 3).
- Audio/SPU2, cinemáticas y guardado (hito 4).
- Launcher, config, empaquetado y CI (hito 5).

**Out**
- Recompilar el juego / regenerar el CSV sin necesidad (ya hecho; el CSV es input de build).
- Cambiar la arquitectura del runtime (overrides por dirección en `game_overrides.cpp` es el criterio
  vigente; la revisión de fidelidad es deuda declarada).
- Cualquier contenido con copyright en el repo (ISO, ELF, assets, C++ recompilado).

## Risks

- **Arreglar un síntoma**: *mitigación*: exigir `rgbNZ > 0` con **todas** las sondas/overrides apagados.
- **Confundir "no se dibuja" con "no se ve"**: *mitigación*: la cadena de UI ya está instrumentada; medir
  los prims que emiten los callbacks antes de tocar nada.
- **Sondas que mienten** (ver `decisions.md` §Reglas): líneas concatenadas, padding en los primeros N
  prims, `replaceFunction` inerte en direcciones interiores/fallthrough, logs sin flush.
- **No-determinismo ocasional** (un run divergió a `f=180`): repetir los negativos antes de concluir.
- **Pacing**: a ~9 ticks/s la respuesta al pad es lenta; no confundir lentitud con bloqueo.
