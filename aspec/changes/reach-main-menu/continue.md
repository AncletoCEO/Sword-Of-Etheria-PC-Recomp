# Continuar — reach-main-menu

> **Punto de entrada vigente: `HANDOFF.md`** (estado definitivo, herramientas, descartado y próximo paso).
>
> Este archivo antes acumulaba el log de sesiones. Se consolidó el 2026-10-09 para evitar ruido: el detalle
> por sesión quedó en git, el resumen en `HANDOFF.md` y el detalle por evidencia en `decisions.md`.

## En 3 líneas

> ⚠️ **CORREGIDO 2026-10-17.** Estas líneas eran del 2026-10-09/11 y dos de ellas hoy son falsas:
> el recomp **no** corre a 58 fps de lógica (VBlank ~58/s pero el *task update* del juego a **~9/s**) y
> **la geometría sí llega al GS** (`[vif1-chain]`, `[gs:kick] drawing=1 pc=0x6e4468`) con VRAM ocupada
> (`vramNonZero` hasta 475456). La brecha actual es **qué página se presenta**. Fuente vigente:
> `decisions.md` §2026-10-17 + §"Artefactos de medición".

- El recomp arranca, presenta frames, pero la pantalla sale **negra** (`nonZeroRgb=0`).
- El pipeline gráfico **está verificado fiel** (display, GS, parseo GIF, VIF1-UNPACK, VU1, XGKICK, geometría
  y color — incluso contra la consola). El negro **es data del juego** (quads `[0,0,0,255]`).
- ~~La brecha es **estado de escena/runtime**: el recomp se queda antes de generar el contenido.~~
  ⇒ hoy: el contenido **se dibuja** (llega al GS y a VRAM); falta **presentarlo** (la página presentada
  es la del clear/fade).

## Actualización 2026-10-10 (sesión color/VU1/staging) — DÓNDE SEGUIR

**Hallazgo principal (A/B RDRAM real↔recomp):**
- El recomp coincide con la consola en **~93.6 % de las páginas** (6.4 % vs state del draw, 12.7 % vs menú).
- La divergencia dominante: **`0xC80000–0xE50000` (~2 MB) = CERO en el recomp** y con data tipo
  **textura/staging** en el real. **Ese es el lead.**
- Verificado que **no** viene de un `sceCdRead` (los 30 reads aterrizan en `0xA4xxxx–0xA8xxxx` y **sí traen
  data real**), ni de stores literales en `work/generated` ⇒ se llena por **puntero calculado o DMA**.

**Próximo paso concreto (elegir uno):**
1. **Hook en el path de DMA del runtime** (1 archivo) para ver quién escribe `0xC80000+`.
2. Dump a **2 ticks** (early vs late) y ver qué páginas de `0xC80000+` cambian alguna vez.
3. Rebuild completo activando `ps2TraceGuestWrite` (header que incluyen 18 311 .cpp → caro).

**Herramientas nuevas de esta sesión** (todas env-gated, baseline intacto):
- `SWORD_RDRAM_DUMP_LATE=<path>` → dump de los 32 MB a `tick≥1200` (⚠ `tick` vive dentro de
  `PS2_IF_AGRESSIVE_LOGS`; hay que esperar ~130 s).
- `SWORD_DUMP_VU1CODE=1` → `/tmp/recomp_vu1code.bin` + `/tmp/recomp_vu1data.bin`.
- Probes: `[UNPACK]`, `[VIF1-chain] data=`, `[VU1-store]`, `[VU1-color]`, `[XGKICK-fin] raw=`.
- Scripts (scratchpad): `classify.py`, `full_ab.py`, `vu1dis.py`.
- Savestates reales: `.p2s` = ZIP con `eeMemory.bin` (32 MB RDRAM) — usable con `zipfile`.

**Pendiente de limpieza**: el probe temporal `[build]` (no env-gated) en
`work/generated/FUN_006cba48_0x6cba48_p10.cpp`.
