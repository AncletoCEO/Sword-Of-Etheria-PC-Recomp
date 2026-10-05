# Decision log: Recompilación Sword of Etheria (2026-10-03 → 2026-10-05)

Bitácora de proceso y decisiones del change `recompile-sword-of-etheria`.
Actualizar con cada decisión tomada. Estado de tareas: ver `tasks.md`
(38/44 al 2026-10-05 noche). Principios vigentes (memoria del repo):
`release-playable-first`, `autonomy-until-playable`.

## Contexto técnico (estable)

- Juego: `SLES_537.68` (entry `0x004C0008`, stripped), ISO PAL Europa
  MD5 `b9c5115b77b7f05fbf14a67df8d3f99d`.
- Sonido: stack Sony real en IOP (LIBSMF2 MIDI + SDSTR3/SD_CALL + SDRDRV +
  LIBSD) + protocolo propio TYOSD (`sid=0x573`: `0x10000` open,
  `0x20000`/`0x0` polls, `0x30000` transfer 640 B desc / 352 B recv).
- Estado estable del run: `tick` avanza (hasta 33000 en 10 min), `dma`
  fluye, `gif=2` fijo, VRAM magenta (triage), 1 comando de 16 B pendiente
  (`w0=0x1101`, `b=a+0x10`), `cb==0`, spin `0x6e4d98` + poller + worker
  girando en macro-loop sano (~2-4 rondas/s).

## Decisiones

### 2026-10-03 — Análisis vía Ghidra como ruta principal
- **Trigger**: ELF stripped, `ps2_analyzer` se cuelga >30 min.
- **Decisión**: export Ghidra (`ghidra_functions.csv`, 7672 funcs) +
  `config.toml`; degradar a analyzer solo si Ghidra bloquea.
- **Outcome**: build completo OK. Vigente.

### 2026-10-03 — Patrón triage→HLE en `game_overrides.cpp`
- **Trigger**: stubs/syscalls faltantes bloquean arranque.
- **Decisión**: handlers temporales (`ret0/ret1`, igualar contadores) solo
  para clasificar; fixes reales promovidos; hacks por juego con
  `PS2_REGISTER_GAME_OVERRIDE`; parches versionados en `game/patches/`.
- **Outcome**: patrón de todo el trabajo posterior. Vigente.

### 2026-10-03/04 — HLE TYOSD + precarga IRX
- **Trigger**: `sid=0x573` sin handler (`recv` en ceros, reintentos).
- **Decisión**: rama `sifCallRpcStub` responde `recv[0]=1`/`v0=1`;
  precargar los 11 IRX de IOPRP300 en `sceSifInitRpc` con cadena de 5
  rutas; gate `g_tyosdRealModuleId` eliminado (HLE siempre activo).
- **Outcome**: audio avanza por etapas; HLE sigue activo. Vigente.
- **Nota**: la carga físico-vs-HLE VARÍA por corrida (ej.: LIBSD físico
  `moduleId=2` algunas veces, HLE otras). No asumir determinismo.

### 2026-10-04 — Opción A (SPU2 mínima) elegida por el usuario
- **Trigger**: cola congelada, runtime sin SPU2.
- **Decisión**: emulación SPU2 mínima en vez de cazar consumidor en Ghidra.
- **Outcome**: derivó en auditoría + hallazgos (abajo). Vigente.

### 2026-10-04 — Auditoría MMIO: EE limpio, IOP con infra
- **Trigger**: tarea 4.6-1 (¿aliasing SPU2 en EE?).
- **Decisión**: escanear `work/generated/` por literales SPU2.
- **Outcome**: EE sin accesos SPU2 (solo artefactos disassembler) → sin
  stub/alias. IOP ya tiene mapa HW + auto-complete DMA SPU. Tarea 1 ✓.

### 2026-10-04 — LIBSD físico preferido sobre HLE
- **Trigger**: `libsd:*` siempre Missing aunque LIBSD.IRX tiene 34 exports
  v0x105 (parseo offline del ELF).
- **Causa raíz**: la cadena de preload se detenía en el HLE
  (id ≥ `0x40000000`) sin probar el físico.
- **Decisión**: reintentar `cdrom0:/IOP/LIBSD.IRX` físico para LIBSD;
  stub `v0=1` pasa a fallback (prefiere export registrado).
- **Outcome**: `moduleId=2`, cero Missing `libsd`, código Sony real
  corriendo. Tarea 3 ✓ (mejor que planificado).

### 2026-10-04 — Investigación comparada con etiqueta PS2/NO-PS2
- **Trigger**: pedido de ideas frescas; riesgo de contaminar con N64/Xbox.
- **Decisión**: regla de higiene — cada fuente etiquetada `[PS2]` o
  `[NO-PS2]`; el plan ejecutable sale solo de `[PS2]` (OpenGOAL-Jak,
  ps2sdk, PCSX2, FREESD). Ver sección en `design.md`.
- **Aporte clave `[PS2]`**: mapa `spu2regs.h` + valores boot PCSX2
  (`ENDX=0xFFFFFF`, `STATX=0x80`) + fuente FREESD (semántica libsd) +
  truco DMA-síncrono OpenGOAL.

### 2026-10-04 — Tests A/B ENDX/STATX (H1, H2)
- **Trigger**: modo poll-storm (484k `0x20000`, cero transfers) vs modo
  transfer.
- **H1**: con `ENDX=FULL+STATX=0x80` → poll-storm; con ceros → transfers.
  Confirmada.
- **H2**: el veneno es `STATX=0x80` (bit busy), no ENDX. Con ENDX lleno +
  STATX 0 → transfers estables. Confirmada.
- **Decisión**: boot con ENDX lleno + STATX idle (activo en el binario).
  Tarea 4.6-2 parcialmente verificada (falta cierre con menú).

### 2026-10-04 — Híbrido 0x30000 (real corre + éxito reportado)
- **Trigger**: passthrough puro reportaba fallo → tormenta 0x20000.
- **Decisión**: pre deja correr el RPC real, post fuerza `v0=1`
  (emparejados por toggle; la rama corre 2× por RPC).
- **Outcome**: driver avanza como con HLE + servidor real ve los requests.
  Vigente. Ojo: `fakePos` en `recv` es irrelevante (el wrapper EE ignora
  `recv`: solo mira `v0` + contadores `gp+0x44/0x48`).

### 2026-10-04 — Servidor 0x573 existe: SDRDRV `func=0x47be4`
- **Trigger**: ¿llegan los transfers a código real o al vacío?
- **Decisión**: loguear `sceSifRegisterRpc` (sids).
- **Outcome**: `0x573` registrado por SDRDRV físico; replies reales con
  bitmasks de voces (`ffffffff/0000ff00` ×36). El EE los ignora.
  Servidor `0x30` también existe (`func=0x41bcc`).

### 2026-10-05 — LIBSMF2 sano; mapa de ordinales Sony verificado
- **Trigger**: ¿el scan ENVX es espera o trabajo sano?
- **Decisión**: disassemblar el loop (LIBSMF2 `@0x2410c`): read-modify-write
  finito por tick (compara envelope vs esperado, escribe flags, `s4`
  countdown, retorna). SANO, no es el atasco. NO tocar ENVX a ciegas
  (rompería verificación init).
- **Decisión**: ordinales Sony `5=SetParam 6=GetParam 7=SetSwitch`
  verificados contra `exports.tab` ps2sdk + tabla de decodificación de
  Sony `GetParam` extraída del binario (offset `0x4980`, base ENVX
  `0xBF90000A`).

### 2026-10-05 — Poll de voces 18-23 por transfer (hallazgo para mañana)
- **Trigger**: correlación pre/post + args libsd.
- **Outcome**: durante cada transfer, `GetParam(ENVX)` de voces 18-23
  (ambos cores). Son las voces de streaming/BGM. El motor nunca les da
  progreso (sin KeyOn observado, envolventes en 0).
- **Siguiente**: fix quirúrgico ENVX (devolver envolvente llena en esa
  ventana, preservando valores escritos) o modelo de ciclo de voz
  KeyOn→playing→ENDX. Ver tarea 4.6-4/5.

### 2026-10-05 — Corrección de modelo: ping-pong es artefacto
- **Trigger**: `a/b` alternaban entre visitas.
- **Decisión**: es el flip (`0x6e4df4+`, lee tabla `gp+0x5F8`) republicando
  tras cada salida forzada, no drenado real. Sin triage: 1 solo comando
  pendiente desde init. Triages v6 (cero-contenido) y v7 (decremento w2)
  inertes por construcción (el productor regenera el ítem completo:
  137 visitas leyendo w2=65).
- **Consecuencia**: no más triages de contenido; solo señales externas.

### Lecciones operativas (no perder)
- El build compila `work/build-game/` (ignorado), NO `game/` (versionado):
  sincronizar a mano (`cp`) tras editar `game/`. Reconfigurar el build
  contra `game/` queda pendiente (evita rebuild total: dir nuevo = horas).
- `/tmp` es volátil entre sesiones; usar `/tmp/opencode/` para logs
  (también se limpia: no confiar a largo plazo).
- Corridas de 25-30s tienen alta varianza (tick 360-1440); para
  trayectoria usar 90-120s; 10 min confirma steady-state.
- La ventana gráfica cerrada mata el smoke (exit 0, tick ~120):
  `game/smoke_report.py` lo detecta ("ventana cerrada").
- Carga físico-vs-HLE de IRX varía por corrida (timing).
- Commits atomizados + push por cada cambio (regla 4.5).
- `game/smoke_report.py`: smoke + veredicto (TRANSFER/POLL-STORM/etc.).
  Extenderlo antes que grep manual.

## Preguntas abiertas (mañana)
1. Fix quirúrgico ENVX voces 18-23 (¿envolvente llena las desbloquea?).
2. Si no: modelo de ciclo de voz (KeyOn→ENDX) mínimo.
3. Servir `SD.BIN` en bulk cuando el layout del comando de 16 B se conozca
   (tarea 4.6-4).
4. Revertir triages al drenar (tarea 4.6-5) → menú → tag `v0.1.0`.
