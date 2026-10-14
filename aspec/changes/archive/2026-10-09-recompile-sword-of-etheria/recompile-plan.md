# Plan de recompilación — fix del boundary (SIF dispatcher 0x4d3fe8)

Fecha: 2026-10-10. Contexto: `decisions.md` §20–21. Objetivo: eliminar el gap
`0x4d3fe8` (los `entry_*`/`FUN_*` faltantes del dispatcher SIF) y llegar al menú.

## Diagnóstico (verificado)

- `work/ps2_recomp-linux.log:1436-1438` → la generación actual usó
  **`aspec/changes/recompile-sword-of-etheria/config-linux.toml`** con
  `ghidra_output = …/ghidra_functions.csv` → **`Loaded 17768 functions from Ghidra map`**.
  ⇒ **Los límites de función vienen del CSV de Ghidra**, no del discovery del recompilador.
- CSV línea de `FUN_004d3fa0`: `0x004D3FA0,0x004D3FE8,72` → **End truncado**. La función real
  llega a `0x004D4078` (216 B): en `0x4d3fe8` arranca el **loop de dispatch SIF**.
- `elf_parser.cpp` (`loadGhidraFunctionMap` + `addOrMerge`) **hace autoritativo el `end` del mapa**
  (mantiene el mayor end); `decodeFunction` decodifica estrictamente `[start,end)` ⇒
  `0x4d3fe8..0x4d4078` queda **sin decodificar** y el runtime pega `missing-target`.
- Confirmado en runtime: `[guest-branch:missing-target] source=0x4d3fe8 target=0x4d3fe8`.

## Cambios

### (A1) Corregir el CSV de Ghidra (quirúrgico, causa directa)
- `aspec/changes/recompile-sword-of-etheria/ghidra_functions.csv`:
  `FUN_004d3fa0,0x004D3FA0,0x004D4078,216` (antes End `0x004D3FE8`, Size `72`).
- Auditar vecinos del tramo SDK (`0x4d3xxx`) y otros `end` sospechosos con el mismo patrón
  (función que termina justo en el retorno de un `jal` y a la que le sigue código no cubierto).

### (A2) Endurecer el recompilador (sistémico, opcional pero recomendado)
- `tools/PS2Recomp/ps2xRecomp/src/lib/ps2_recompiler.cpp`, en
  `PS2Recompiler::discoverAdditionalEntryPoints()` (~L1914, al construir
  `guestFallbackEntryAddresses`): sembrar **`f.end`** como entry cuando, para funciones
  consecutivas `f` y `g` (ordenadas), `f.end < g.start`, `f.end` cae en sección ejecutable y `f`
  **no** termina en terminador de control (`jr $ra` / `j` incondicional / `jr` indirecto).
  Con eso el tramo se decodifica como `entry_004d3fe8` acotado por `g.start`.
- (Opcional) `resliceEntryFunctionsImpl` (L606-618): excluir starts `entry_*` de `boundaryStarts`
  (mismo criterio ya usado en `findContainingFunction`), para no re-cortar por targets sintéticos.
- Rebuild del recompilador: `cmake --build tools/PS2Recomp/out-linux -j$(nproc) --target ps2_recomp`.

## Procedimiento (con backup y regen incremental)

1. **Backup**: copiar `work/generated` → `work/generated.pre-recompile` (o al menos los 17 archivos
   instrumentados). Nunca pisar sin red.
2. **Regenerar a un dir temporal** con el MISMO config que la última vez:
   `tools/PS2Recomp/out-linux/ps2xRecomp/ps2_recomp  aspec/changes/recompile-sword-of-etheria/config-linux.toml`
   apuntando `[general].output` a `work/generated.new`.
3. **Diff** `work/generated.new` vs `work/generated`; copiar **solo** los archivos cambiados/nuevos
   a `work/generated` (evita recompilar 18k objetos y el relink total).
   Verificar que `entry_004d3fe8_*` (o `FUN_004d3fa0` extendido) exista.
4. **Re-aplicar instrumentación**: los 17 `work/generated/*` con `fprintf` de debug
   (`[gen-audio]`, `[gen-state]`, `[TYOSD-*]`, `[triage-*]`) — preservar/reaplicar.
5. **Splitter obligatorio**: `python3 game/split_monsters.py work/generated`.
6. **Build**: `cmake --build work/build-game/out-linux --target sword_etheria -j4`
   (ojo OOM: `-j4`, no más).
7. **Verificación**:
   - Runtime sin `[guest-branch:missing-target] source=0x4d3fe8`.
   - `[triage-vbprof]` con el thread 2 recorriendo el dispatcher (`pc` en `0x4d3fe8..0x4d4078`).
   - `SWORD_SIF_SEMA=1` (mitad runtime ya lista) ⇒ sema 3 se postea y el thread 2 arranca.
   - Avance de fase: vectores TYOSD > n=2 / aparición de FMV (`MOVIE/00/*.PSS`) / imagen no negra.

## Riesgos / notas

- El "alcance" medido antes (5.285 huecos) es una **cota superior** (incluye datos). El guard de
  terminador limita (A2) a huecos reales de código.
- `work/generated_orig` está **desactualizado** (542 diffs): no usarlo como baseline.
- No hay opción de config para lista explícita de funciones / deshabilitar reslice / forzar end
  (`config_manager.cpp`): el control es por el mapa de Ghidra (A1) o por código (A2).
- La build completa (regen total + link 1.5 GB) es de horas; el paso 3 (regen a temp + copia
  incremental) es lo que la hace viable.
