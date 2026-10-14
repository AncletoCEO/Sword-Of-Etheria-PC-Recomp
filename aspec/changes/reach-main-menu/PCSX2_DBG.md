# PCSX2 + debugger — workflow para seguir solo

Estado 2026-10-10. Complementa `decisions.md` / `HANDOFF.md`.

## 1. Levantar PCSX2 con debugger (¡hay que hacerlo así!)

El debugger de PCSX2 **se traba si arrancás el juego desde boot limpio**. Lo que **sí** funciona:

1. Config (ya está así en `~/.config/PCSX2/inis/PCSX2.ini`):
   - `[EmuCore/CPU] EnableEE = false` y `EnableIOP = false` → **intérprete** (necesario para el debugger).
   - `EnablePINE = true`.
2. `pcsx2-qt -debugger "Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso"`.
3. Hacé **shutdown** y **recargá la ISO** desde la GUI; recién ahí el breakpoint se alcanza sin trabarse.
4. Cargá el **savestate 1** (o el que necesites) y poné el breakpoint.

> El intérprete es **lento**; para jugar normal poné `EnableEE/IOP = true` de vuelta.

## 2. Panel GPR roto → leer registros del savestate

El panel **GPR del debugger NO actualiza** (queda con estado de boot: `s0..s7=0`, `gp=0`). **No confiar en él.**

Para leer los **GPRs reales** en un punto:

```bash
# parado en el breakpoint (o donde quieras), con PCSX2 corriendo:
python3 game/pine_state_gpr.py save 9     # SaveState al slot 9 + imprime GPRs
python3 game/pine_state_gpr.py read 9     # relee el slot 9 ya guardado
```

Layout: array de 32 GPRs, stride `0x10`, `r0` en el offset `0x162` del
`PCSX2 Internal Structures.dat` (dentro del `.p2s`; se extrae con `bsdtar`).

## 2b. Rotar los 9 slots: guardar/restaurar por nombre

PCSX2 sólo tiene 9 slots, pero podés guardar muchos estados con nombre en
`work/pcsx2_states/` (gitignored):

```bash
python3 game/pcsx2_state.py save <slot> <nombre>       # slot -> carpeta
python3 game/pcsx2_state.py restore <nombre> <slot>    # carpeta -> slot
python3 game/pcsx2_state.py list                       # estados guardados
python3 game/pcsx2_state.py slots                      # slots actuales en PCSX2
```

Ej.: `save 6 draw_vif1kick_006E4468` → después `restore draw_vif1kick_006E4468 3`
y en el debugger cargás el slot 3.

Guardados hoy: `videoformat_menu`, `draw_vif1kick_006E4468`,
`menu_sceGsSyncV_004D3730`, `menu_sceGsSetDefDispEnv_004D0DF8`,
`menu_sceGsSetDefDrawEnv_004D12F8`, `menu_sceGsSetDefClear_004D25D0`,
`scenebuild_0074A3D4`.

## 3. Breakpoints y Memory

- **Breakpoints**: funcionan (con intérprete). Se ponen por dirección (p.ej. `0x74A3D4`).
- **Memory**: la pestaña Memory sí sirve. Escribí la dirección absoluta (p.ej. `00C803E0`).
- **Disassembly**: aparece **corrido ~+8 bytes** respecto del ELF real (**ignorar** ese offset).

## 4. Qué NO hace falta re-verificar (ya está probado)

- Código de `0x74A3C0..0x74A3EC` **idéntico** en ELF == s01 == s02 == recomp → **no hay overlay/mala recompilación**.
- El **armado de escena** (`FUN_006cba48` p10) llega con **los mismos** `s0/s2/s7/gp` que el recomp;
  sólo difieren punteros de heap por **offset constante `0x150`**. ⇒ **no es la divergencia.**
- Display OK: `SWORD_TEST_PATTERN=1` en el recomp muestra "HELLO WORLD".
- El gate del loader se cruza (`gp+0x58=1`).

## 5. Foco actual: **render / GS**

El recomp emite **prims negros sin textura** (`tme=0`, `rgba=(0,0,0,*)`) ⇒ no dibuja escena/menú.
Comparar entre **real y recomp** en el punto del menú:
- Registros GS (`gs:reg` en los logs del recomp; y el estado GS del real).
- Paquetes GS (`gs:prim`, `gs:gif`) → ¿hay prims con `tme=1` / colores ≠ 0 en el real?
- VRAM: ¿qué textura/framebuffer tiene el real que el recomp no?

Herramientas recomp: logs `[gs:prim]`, `[gs:gif]`, `[triage-vbprof]` (incluye `gp50/54/58`, `burst_nz`,
`burst_maxdst`), y `SWORD_TEST_PATTERN` para validar que el present sigue andando.

## 6. Recomp lado: datos de referencia (para comparar)

- Probe temporal `[build]` en `work/generated/FUN_006cba48_0x6cba48_p10.cpp` (`0x74A3E0`), imprime
  `s2/s4/a2/v0/s0/fp` por ítem. Se pierde al regenerar el generado.
- `SWORD_LOAD_RDRAM=<eeMemory.bin>` (+ `<file>.ranges`): teleporta RAM real al recomp (diagnóstico).
- `SWORD_SEED_TAIL=1`: marca `0xDEADBEEF` en `0xCF0000-0xDB0000` para ver si algo lo escribe.
- `SWORD_DUMP_LATE=1`: vuelca la RAM del recomp a `/tmp/sword_recomp_late.bin` (vb≥4000).
