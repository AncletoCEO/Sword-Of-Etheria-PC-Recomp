# Decision log: Recompilación Sword of Etheria (2026-10-03 → 2026-10-05)

Bitácora de proceso y decisiones del change `recompile-sword-of-etheria`.
Actualizar con cada decisión tomada. Estado de tareas: ver `tasks.md`
(38/44 al 2026-10-05 noche). Principios vigentes (memoria del repo):
`release-playable-first`, `autonomy-until-playable`.

> **LEER PRIMERO — Auditoría externa 2026-10-05 (sección al final del archivo).**
> Análisis de solo-lectura del repo versionado. Enfoques a corregir; bloquea
> cierre / release `v0.1.0` hasta resolver **A1** (runtime no versionado),
> **A2** (dos builds divergentes) y **A6** (release/CI no valida). No ejecutar
> nada sobre `work/` sin leerla.

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

## Auditoría externa (2026-10-05) — enfoques a corregir

Análisis de solo-lectura del repo versionado (36 commits). Ordenado por
gravedad. **Bloquea cierre / release `v0.1.0` hasta resolver al menos A1, A2 y
A6.** Ninguna acción de esta sección se ejecutó.

### A1 — Reproducibilidad rota: el runtime real no está versionado (crítico)

- El trabajo que hace avanzar el juego (162 syscall stubs, redirect
  `fullRenderFunc`, HLE TYOSD, precarga IRX, híbridos y triages) vive en
  `tools/PS2Recomp/ps2xRuntime/src/lib/game_overrides.cpp`, y `tools/` está en
  `.gitignore`.
- En el repo solo quedan fragmentos narrativos en `game/patches/*.patch`:
  **ningún script los aplica** (no hay `git apply`/`patch -p1` en
  `build_release.py` ni en `.github/workflows/release.yml`).
- `README.md` afirma que el runtime "incluye `game_overrides.cpp` (162 syscall
  stubs + hooks)": eso no está en el repo.
- **Consecuencia**: un clon limpio + `build_release.py` compila un runtime
  stock, sin nada del avance reciente.
- **Acción**: versionar como parches aplicables (`git format-patch` del
  submódulo o fork de `ps2xRuntime` dentro del repo) y que
  `build_release.py`/CI los apliquen ANTES de cualquier validación.

### A2 — Dos builds divergentes (`game/` vs `work/build-game/`)

- El flujo de dev compila `work/build-game/` (ignorado) y exige `cp` manual
  desde `game/` (ver "Lecciones operativas"); `build_release.py:120` compila
  `game/`. Son dos `CMakeLists.txt`/`game_main.cpp` que divergen.
- **Acción**: una sola fuente de verdad. O `game/` es el build (dev y release),
  o `work/build-game/` se genera por script desde `game/`.

### A3 — Paths duros y stale (portabilidad)

- `game/game_main.cpp:89` → `/home/lubonch/repos/.../sword_etheria.log`: el tee
  de log corre siempre en Linux; si el dir no existe, **el log a archivo se
  pierde en silencio**.
- `game/game_main.cpp:250` → default boot ELF con path duro `/home/lubonch/...`.
- `config-linux.toml:10-12` → `/home/lubonch/Repos/...` (mayúscula; no existe).
- `continue-on-arch.md`/`README.md` afirman "sin paths duros": falso.
- **Acción**: derivar de `argv`/CMake/env; sin paths absolutos de máquina en
  código versionado.

### A4 — Estrategia: parchear síntomas en vez de completar el entorno

- Regla de la skill PS2Recomp: "95% de los casos es el entorno" y "nunca
  parchear síntomas". Acá se encadenaron triages (v1/v2/v3/v6,
  `poll-progress`, `triage-vis`, híbrido `0x30000`) y varios se reconocen
  "inertes por construcción" (ver "Corrección de modelo" arriba).
- `smoke_report.py` reporta "TRANSFER (estable)" como progreso aunque la cola
  siga sin drenar.
- **Acción**: no sumar más triages. Decidir el consumidor real vía A/B con
  PCSX2 (DebugServer) o modelar el ciclo de voz SPU2 completo
  (KeyOn→playing→ENDX); no forzar ENVX a ciegas ni `v0=1`.

### A5 — `replaceFunction` a mitad de función

- `game/patches/6e4d98-triage.patch` engancha `0x6e4d98` (mitad de `0x6e4cc0`)
  y admite que "puede corromper registros/stack". El fix real va por el
  productor/entorno, no por reemplazo de instrucciones sueltas.

### A6 — El release/CI no valida nada (crítico para el hito)

- `release.yml` solo compila PS2Recomp, corre `py_compile`/`--help` y empaqueta
  tools + 4 archivos. No compila el juego, no aplica patches, no corre smoke.
  El asset de `v0.1.0` no arranca el juego.
- `build_release.py:107` y `config-linux.toml` inyectan un parche de
  instrucción crudo en `0x4c008c` (`j 0x4c0218`) para saltar el spin del
  bootstrap: hack de arranque atado a este ELF, no entorno.
- **Acción**: no taggear `v0.1.0` hasta menú visible; el CI debe fallar si el
  asset no es ejecutable/funcional.

### A7 — Menores

- `build_release.py:121` pasa `-DCMAKE_BUILD_TYPE=Release`, pero
  `game/CMakeLists.txt:116` fuerza `-O0 -fno-inline -fno-stack-protector -g0`
  (`/Od /GS-` en MSVC): "Release" nominal.
- `game/CMakeLists.txt:92` imprime "Archivos >10MB fuera de unity" pero el
  umbral real es 2 MB (`src_size GREATER 2000000`).
- `split_monsters.py` transforma C++ generado con regex, sin tests: frágil ante
  cambios de `ps2_recomp`.
- `decisions.md` dice "38/44" y `tasks.md` tiene el hito sin cerrar: bitácora y
  tasks no coinciden.
- `searchMemory` no devuelve nada y `.ancleto/memory.db` está vacío: los
  principios citados ("release-playable-first") no están en la memoria del repo.
- No hay evidencia de A/B con PCSX2.

### Lo que está bien (preservar)

- Diagnóstico del IOP vacío → precarga de IRX (arreglar el entorno, no síntoma).
- Regla "splitter siempre tras `ps2_recomp`", implementada en
  `build_release.py:118`.
- Higiene `[PS2]`/`[NO-PS2]`; `smoke_report.py` estandarizado.

## Preguntas abiertas (actualizado 2026-10-06)
1. Fix quirúrgico ENVX voces 18-23 (¿envolvente llena las desbloquea?).
2. Si no: modelo de ciclo de voz (KeyOn→ENDX) mínimo.
3. Servir `SD.BIN` en bulk cuando el layout del comando de 16 B se conozca
   (tarea 4.6-4).
4. Revertir triages al drenar (tarea 4.6-5) → menú → tag `v0.1.0`.

## Respuestas a la auditoría 2026-10-05 (2026-10-06)
- **A7 memoria: refutado.** `searchMemory("playable release autonomy")`
  devuelve la regla `release-playable-first` (scope project, 2026-10-04).
  La memoria no está vacía; la query de la auditoría no matcheó.
- **A1 hecho y validado**: 14 parches aplicables + applier idempotente;
  `build_release.py` pinea (`75d729c`) y aplica. Prueba desde cero OK.
  Commit `d6e0150`.
- **A2 hecho**: `game/sync_work.py` (fuente única `game/`); divergencias=0
  verificado; `build_release.py` lo ejecuta.
- **A6 hecho**: `release.yml` actualizado para reproducibilidad: triggers ampliados a main/PR, checkout pineado (`75d729c`), aplicación de parches con `apply_patches.py`, validación de scripts/smoke, empaquetado preservando estructura `game/` completa y assets de release solo en tags `v*.*.*`. Tag `v0.1.0` continúa condicionado a menú visible.
- **A4 (no sumar triages)**: de acuerdo en espíritu; el fix ENVX propuesto
  queda supeditado a no romper verificación init (solo valores no escritos
  o con justificación). Sin adivinanzas.
- **Conteo 38/44**: incluye tareas de tooling (smoke_report, Fase 5.1);
  el hito sigue abierto y visible como tal. Sin discrepancia real.
  (Nota 2026-10-06: el conteo quedó en 40/47 tras Fase 5.1 + tooling.)

## Progresión lenta, no estancamiento (2026-10-06)
- Comparando pc-sets: corrida 10 min toca 15 pcs que la de 60s jamás toca
  (`0x6e4dd0` salida del spin, worker `0x6e4068` vía poller, `0x5129e4`,
  `0x534568`, etc.). Primeras apariciones repartidas hasta tick 25440:
  el juego sigue explorando código nuevo a los ~9 min, sin asíntota.
- Hipótesis operativa: el avance existe pero es glacial (transfers 2-4/s).
  En marcha corrida de 30 min (background) para ver si llega a menú o a
  nueva fase (`gif>2`). Si a los 30 min sigue `gif=2` sin novedad,
  volver al fix quirúrgico (waiter SDRDRV / ciclo de voz).

## Layout del comando 16B + bulk-serve (2026-10-06, tarde)
- Corrección: el servidor `0x573` vive en `SD_CALL.IRX` (base `0x47500`,
  handler `0x47be4` = entry real). `SDRDRV.IRX` sí carga físico (id=5,
  base `0x80b00`); el disasm previo apuntaba al archivo equivocado. El
  dispatcher `0x47be4` sí atiende `0x10000/0x20000/0x30000` (comparación
  directa con `a0`, no `0x81xx`).
- Comando 16B completo (log IOP): constante
  `[0x11050000, 0x00020000, 0, 0]` — el productor reintenta el bloque 1
  eternamente. Primer 16B tras el descriptor 640B vino en ceros (n=2).
- Descriptor 640B (EE `sendBuf=0xa44100`): array de 40 entradas de 16B
  `[0x11050000, bloque++, 0, 0]` con bloques `0x20000, 0x30000, ...`.
  `recv` 352B = 32 + 40x8 (status por bloque). `rsize=352`, `mode=1`.
- Experimento en curso: POST de `0x30000` rellena recv con todo-unos
  (hipótesis: el EE espera status-done por bloque). Si avanza → breakthrough;
  si crashea → el pc revela el layout esperado; si igual → no lee recv.

## Protocolo 44/48 del wrapper + posible iatrogenia (2026-10-06, noche)
- Wrapper `0x627a10` (región fullGame): `sum = *(gp+0x44)+*(gp+0x48)`;
  `sum<0x41 → return 1`, `sum>=0x41 → return 2`. Caller `0x627b84` ramifica
  en `v0==2 / ==1 / ==0`.
- Caller `0x627bc0` (s2==0): si `44>0`, copia `44` bloques de 16B
  (`0xA44100 → 0xA44500+(48+i)*16`), luego `48 += 44; 44 = 0`.
  O sea: **44 = bloques recién llegados (solo lo escribe el completado
  IOP), 48 = total acumulado (solo lo escribe el secuenciador)**.
- Nuestro triage 2026-10-04 incrementaba 44 Y 48 por poll → finge llegadas
  infinitas → el caller re-somete eternamente. Livelock auto-infligido
  candidato. Experimento 2026-10-06e: incremento DESACTIVADO (reversible);
  si vuelve la tormenta `0x20000`, revertir.
- Resultado bulk todo-unos (2026-10-06b): SIN cambio (tick=3240, sin crash).
  Conclusión: el EE **no decide por `v0`/`recv`** del RPC sino por el estado
  de cola (a/b/tabla/w2), que solo avanza el worker con completado real.
- IATROGENIA CONFIRMADA (2026-10-06e): sin incremento 44/48,
  `transfers_30000=3` (vs 80) y `hybrid_pre=1` (vs 73). El incremento
  causaba el resubmit; el secuenciador ahora está quieto en el spin.
- Experimento F en curso (2026-10-06f): `44 = 40` UNA vez en el primer POST
  (simula "los 40 bloques llegaron") para que el copy-loop real consuma
  (`48 += 44; 44 = 0`) y los polls vean `44 = 0` → rama done.
- Corrección (2026-10-06f2): el POST nunca corre sin 2do submit (el juego
  somete el descriptor UNA vez y luego solo polls `rpc=0`). One-shot movido
  al PRE. Experimento G: `fakePos` salta a 64KB del fin de SD.BIN sin wrap
  (si el gate de los polls es posición, completa en pocos polls).
- Resultado F+G (2026-10-06, noche): ambos dispararon (`44 40->40`,
  `fakePos=715278336`) SIN efecto. `44=40` es preset REAL del EE (sin triage
  que lo toque). El secuenciador de transfers no vuelve a correr; todo el
  ciclo vivo está en worker/spin/poller/6E4068 con a/b congelados.
- Nuevo foco (2026-10-06h): el handler muere en su primer helper (import
  `libsd`, jal sin relocar `0x1210`). Instrumentación: log de llamadas
  anidadas a rangos Sony (`0x39f00-0x47500`, `0x80b00-0x8a000`) con args —
  nombra al waiter exacto sin adivinar.
- Corrección (2026-10-06, noche): el sweep `libsd:6` (`a0=0x500+k`,
  `a1=1<<k`) viene de LIBSMF2 (`ra=0x22dcc`, hilo 14), NO del handler:
  es polling de fondo, no el gate. El helper#1 del handler (SD_CALL
  `0x48710`) lee un global y retorna; helper#2 (`0x48748`) llama a un
  IMPORT y ramifica por códigos negativos (`-0x1A2` etc.). En curso
  (2026-10-06i): log genérico de TODO import anidado (`depth>=1`) durante
  transfers para nombrar ese import.
- Resultado NESTED (2026-10-06, noche): CERO imports anidados. El `jal
  0xa85c` de helper#2 es hoja local (`jr ra`, `.text` termina en `0xa890`),
  no import: **todo el handler 0x30000 es código local + globales**, sin
  llamadas externas. El gate es un GLOBAL.
- Helper#1 (SD_CALL `0x48710`) lee el word absoluto IOP `0xC560` (lui 1 +
  lw -0x3AA0, sin reloc en su posición): 0 = rama éxito (helper#2 con
  count, helper#3 copia buffer→tabla driver, status 0), !=0 = ramas busy.
  En curso (2026-10-06j): peek de `0xC560` + status `0xC0FE` en el triage de
  reply para saber qué rama toma.
- Resultado peek: `gC560=0` (rama éxito: el handler SÍ copia buffer→tabla,
  status 0) y reply con patrón `ffffffff/0000ff00` (no ceros). El IOP
  completa localmente; el EE no se entera porque el secuenciador de
  transfers no vuelve a correr y `44` queda en 40.
- Decisión playable-first (2026-10-06i2): completar al total 65 (`0x41`,
  umbral del wrapper) por la vía real: `44 = 65-48` una vez en PRE, el
  copy-loop calcula `48 = 65`. Si el caller llega a menú silencioso →
  breakthrough v0.1.0.
- Resultado to65: `44 40->65 (48=0)` SIN efecto. `48=0` prueba que el
  copy-loop NUNCA corrió: el secuenciador `0x627b50` no vuelve a correr.
- Hipótesis aliasing (2026-10-06k): `recv+4 == gp+0x44` (recv=`0xA44940`
  → gp=`0xA44900`). El word1 del reply sería A LA VEZ pos (streaming) y 44
  (llegadas): nuestro fakePos (MBs) lleva corrompiendo 44 desde el 04/10.
  En curso: log `recv/rsize/gp/ra` del primer poll para confirmar o matar.
- Resultado aliasing: MUERTO (`gp+0x44=0xA280B4` ≠ `recv+4=0xA44944`;
  `gp=0xA28070` es el gp del overlay, `ra=0x627afc` confirma polls desde
  el wrapper s2==0). Hallazgo mayor: el wrapper retorna 1/2 por suma pero
  el copy (`48+=44`) solo corre con `v0==1` (sum<0x41); mi `44=65` lo
  impedía (sum≥41 → 2 → return). Decisión (2026-10-06i3): goteo
  incremental `44=1` por poll (si `44==0` y `48<65`) hasta `48=65`.
- Resultado goteo: `44=1, 48=0` + resubmits de vuelta (91 PREs): `v0==1`
  = "otra vez" para el caller de polls; el copy nunca corre (el batch
  `0x627b50` no vuelve). El worker no consume el ítem.
- En curso (2026-10-06l): BYPASS de `6E4ED8` (submitter SPU del loop;
  sus callers ignoran `v0` → retorno 0 inmediato seguro). Si avanza → el
  waiter vive dentro (bypass silencioso candidato v0.1.0).
- Resultado bypass: SIN efecto + `6E4ED8` NUNCA se llama (el worker no
  tiene nada que someter: ítems con `w1<=0` se saltean). Hallazgo: con
  goteo, submits 16B SÍ fluyen (bloque `0x20000` repetido, `cmd` constante)
  y `44` baja 40→1 (restantes de un presupuesto de 40). Al llegar a 0,
  cambia de fase (nuevo stall o avance). En curso: log denso + corrida
  larga para ver qué sigue a `44=0`.
- Resultado 3min (2026-10-06, noche): `44=1, 48=0` FIJOS, cola DRENADA
  (`a==b==11623056`, flags 0), pc nuevo `0x511510` (tick 9600), transfers
  216 (reintentos 16B). Sin menú.
- En curso (2026-10-06m): `48=65` directo (el copy es irrelevante en
  silencio). Si el caller mira 48 → menú; si crash → info de layout; si
  nada → el gate es otro (w2/tabla/Status-wait).
- Resultado 48=65: SIN efecto. Baseline 06v: `44=0, 48=0` naturales (el 40
  era polución de mis incrementos). El `44++` vive en `0x627f50` SIN
  callers directos en fullGame → candidato a callback SIF async. En curso
  (2026-10-06w): log `endFunction` por rpc (¿callback que nunca corre?).
- Resultado 48=65: SIN efecto (spin vuelve a a≠b según timing). El gate es
  conjunción con `w2` (ítem+8).
- Resultado ítem (2026-10-06n): `{cmd=0x1101, dst=0xB15B00, count=0x40,
  flags=0xA8D0B0}`, `table=[0xA96680, 0xB15A80]`, `61c=0xA96690`. `w2`
  pristine = 64.
- En curso (2026-10-06o): completar el ítem (`w2=0` + 64 flags en 1) cada
  visita del spin. Si el worker avanza b → breakthrough.
- Resultado item-complete: SIN efecto.
- En curso (2026-10-06p): contadores dinámicos spin/flip/productor
  (flip: log+skip sb; prod: log+emulación exacta del sw). Si flips=0 con
  spins creciendo → la salida forzada no llega al flip (atorado entre
  `0x6e4dac-0x6e4e00`, i.e., en el cb). Si flips crecen pero `a` no alterna
  → el productor/tabla re-escribe.
- Resultado flow: flip=0, prod=0 (nunca corren); `sp` ESTABLE (sin
  recursión infinita: todo retorna). Pinpoint 06q: ningún hook corre (ni
  salida ni flip); `cb` siempre nuestro poller → el poller no retorna (o la
  salida desvía antes del call).
- En curso (2026-10-06s/t): log `ra` cada visita + salto DIRECTO a
  `0x6e4dd8` (post-loop) en vez de `0x6e4dac`. Dirime: si flips corren →
  el cb era el agujero; si ni así → falla el mecanismo de salto.
- Resultado salto: la SALIDA corre (hook dispara) → el salto funciona y el
  cb era el agujero. Pero el flip jamás (ni `0x6e4df4`): muere entre
  `0x6e4ddc-0x6e4df4` cada vez, sin colgar el host. Switch con cases por pc:
  los `goto` internos bypassean hooks → el flip podría correr invisible;
  pero `a` nunca alterna → no corre (o toggle re-escrito).
- Resultado callback (2026-10-06y): `endfn-6279D0` CORRE (n=1..5+). El SIF
  async vive; el completado `4C38D8`+`ei` se ejecuta. El stall está aguas
  abajo del callback.
- Modelo huevo-gallina (2026-10-06z2): `627B50` salta el submit si `48<=0`
  (blez→`0x627C48`); el consumo necesita `44>0`; los arrivals no existen.
  Todo en 0 = idle estable. Kickstart: `48=1` UNA vez en PRE; si el ciclo
  se autosostiene (real) → WIN.
- Resultado kickstart: consumido (`48→0` por rama `v0==0`) sin progreso;
  transfers 11, VRAM igual. El ciclo no se autosostiene.
- Nuevo hilo (2026-10-06z3): `0x627F50` (44++) tiene callers en
  `entry_006b16b0/1d0/8f4/9a4` (`0x6b16b0: si a1>0 → 627F50(a0=0x10060000,
  a1=t0, a2=1)`), sin callers directos (¿handler de interrupción?
  ¿vsync?). En curso: hooks exactos en `0x6b16b0` y `0x627f50`.
- Varianza entre corridas: sin spin (worker estacionado en `0x6e4cdc`,
  dentro de 6E4848 que no retorna y no llega al spin). Candidatos: loops
  `bc0f` (`0x6e4d24`, `0x6e4ac4`, flag C0 que nada pone). En curso
  (2026-10-06z): fallthrough forzado en ambos (equivalencia exacta con DMA
  síncrono). Si el worker avanza → era ese wait.
- BREAKTHROUGH (2026-10-06, noche): con el build bc0f+cb9d0, ¡SIN SPIN
  (`spin_hits=0`) y VRAM CON DATOS REALES creciendo
  (`262144→306048→524288`)! El juego pasó a render. Hipótesis: el hook del
  callback `0x6279D0` (o varianza de corrida) lo desbloqueó; los hooks bc0f
  nunca dispararon. En curso: corrida 5min + BMPs para ver si llega a menú.
  Si menú → v0.1.0 (revertir triages después, A6 gate).
- Giro de paradigma (2026-10-07): el audio puede estar TERMINADO (`spin=0`).
  Con pmode=0x8067 + dispfb1 alternando (0x1000/0x1080/0x1400) hay double-
  buffer real, pero frames negros (shot_1/shot_241 = 0px). El park es otro
  bloqueo. En curso: hook exacto en `0x4c1970` (dispatch worker thread).

### 2026-10-07 — Corrida 10 min: sin avance; ico-pc evaluado
- **Trigger**: hito = llegar al menú; corrida desatendida de 620s del build
  actual (binario 20:28) con capturas cada ~10s.
- **Resultado**: **REFUTADA** la hipótesis de "progresión lenta". En 10 min:
  `tick` ~6240, `gif=2` / `gsw=0` / `vif=6` **constantes** (cero geometría),
  VRAM siempre `262144/4194304` y **solo alpha** (`crt1 fbp=128: rgbNZ=0
  aNZ=262144`), ~10 fps, sin crash. Frames negros. El juego nunca emite
  VIF/GIF ⇒ el bloqueo está **aguas arriba del render**, no en el GS.
- **Anatomía de hilos (vbprof, 37k muestras)**: hilo 1 (main, pri 25) corre
  en `0x6279d0` (callback SIF `entry_00627994`), `0x628970` (cola del cliente
  RPC `FUN_00628640` = `WakeupThread`), `0x51e7xx`/`0x6d51xx`; hilo 2
  (`FUN_004d3fa0`, espera sema 3, st=2) y hilo 3 (`FUN_00628640+0x308`,
  poll loop RPC con `SleepThread`, st=2) parkeados. Solo 3 hilos: main + 2.
- **Corrección de dos lecturas previas**:
  1. El hook de dispatch `0x4c1970`/`0x4c1900` (`mainGameLoopDispatch`) **NO
     dispara** en la corrida (0 trazas); el main ya no pasa por ahí.
  2. Forzar el estado del driver de sonido `2→5` en `0x6e8870` es **callejón
     sin salida**: verificado en el C++ generado, `state&7==2` es la rama
     **activa** (`0x6e88d8`, arma/encola comandos de sonido en `gp+0x5C0`) y
     `==5` es la rama **idle** que retorna 0. Forzar apaga el trabajo. No
     reintentar.
- **ico-pc (nathanialf/ico-pc)**: es un **port de decompilación** de ICO
  (corre C del juego), con **renderer Vulkan propio** (`port/render/rd_*.c`)
  y scheduler de fibras (`port/platform/sched.c`); **no es HLE** como
  PS2Recomp, así que su render no transfiere. Aprovechable solo como
  **semántica de referencia** de SDK en `sce/libkernl/` (thread.c,
  sifrpc.c) ante una duda puntual. No aporta fix directo a este blocker.
- **Siguiente (a dirimir)**: el gate espera una condición que el runtime no
  satisface. Dos candidatos: (a) el state machine de escena principal no
  avanza; (b) el semáforo 3 (1 waiter, idle) nunca se postea y strandea un
  paso. Instrumentar el escalón de escena + el semáforo 3.

### 2026-10-07 — Traza de semáforos: hilo 2 = thread de comandos SIF (no es el gate)
- **Instrumentación** (`swordOfEtheriaSyscallStub`, TRIAGE-sema): log de
  TODA op 64..70 con el `ra` del que llama + id de CreateSema. Rebuild
  runtime + relink OK (4m39s).
- **Resultado (smoke 90s)**: secuencia de creación `CreateSema -> id=1,2`
  (CRT0), `id=3` (SDK), `id=4..7` (CDVD), `id=8` (pad), `id=9`.
  `op=68 sema=3 ra=0x4d3fe8` **una vez** (hilo 2, WaitSema) y **cero
  señales a sema 3** (ningún `op=-67 sema=3`).
- **Identificación**: `FUN_004d4078` (llamado por `_init_sys` = `0x4dd618`)
  crea `CreateSema(maxCount=255, init=0)` → id 3 + `CreateThread(entry=
  0x4d3fa0)` + `StartThread`. El hilo 2 hace `WaitSema(3)`. Los que
  **señalan** sema 3 son `FUN_004d4168/4200/4280` vía `iSignalSema`
  (`0x4d32d0`, syscall -67) — **ninguno se invoca**: es el **thread de
  comandos SIF del SDK** y está **idle por diseño** (nuestro HLE de
  `sceSifCallRpc` puentéa el camino SIF del SDK, así que nunca se encola un
  comando). **Descartado como gate.**
- **Bug latente real (no bloqueante hoy)**: el cuerpo del hilo 2 en
  **`0x4d3fe8–0x4d4078` NO está recompilado** (Ghidra cerró `FUN_004d3fa0`
  en el `jal` de `0x4d3fe0`; el hueco de 36 instrucciones es código real
  —loop worker que lee una cola y despacha). Si algún día se señalara sema 3,
  el hilo resumiría en `0x4d3fe8` → función inexistente. Anotado para el día
  que se toque el thread SIF.
- **Estado**: el gate sigue siendo **aguas arriba del render** (main corre en
  `0x51xxxx`/`0x6d5xxx` y solo pollea `sid=0x573 rpc=0`). No descartar el
  audio/streaming. Próximo: A/B con PCSX2 (comportamiento esperado en este
  punto) o instrumentar el state machine de escena.

### 2026-10-07 — A/B con PCSX2 (referencia real del arranque) ✅
- **Setup**: PCSX2 2.8.2 (`pacman -S pcsx2`), BIOS `ps2-0220e-20060210.bin`,
  FastBoot. Lanzado `-batch -fullscreen -fastboot` con el ISO del repo;
  capturas con `spectacle` cada 10s. Config: `/tmp/opencode/pcsx2{,b}/`.
- **Secuencia real observada**:
  1. **~20s: primera pantalla del juego** = diálogo **"Select video format —
     NTSC(60Hz) / PAL(50Hz)"** (lo dibuja el juego), esperando input.
  2. **~70s (tras apretar Cross): título** = logo *THE SWORD OF ETHERIA*
     sobre nubes + menú **New Game / Load Game**.
  3. **~120s+: menú principal** = logo + arte de los 3 personajes +
     **Quit Game / Save / Story Mode / ?????? / ??????**, ©2006 KONAMI.
- **Rendering**: el log de PCSX2 muestra `microVU1: Cached Prog` + `GL:
  Compiling vertex/pixel shader` desde ~10s ⇒ **el juego renderiza 2D/3D
  real desde el arranque** (VU1 + GS). Nuestro recomp no emite nada.
- **Implicancia**: el hito "llegar al menú" = **esas dos pantallas**
  (título + menú principal). Nuestro recomp diverge **antes del primer
  render**; el gate no es profundo (es un juego que dibuja ya en boot).
- **Descartado también (este turno)**: el **pad**. La primera pantalla
  requiere input, pero en nuestro recomp el juego **nunca llama
  `scePadRead`** (0 líneas; solo `scePadInit`+`scePadPortOpen`) ⇒ no está
  esperando input.
- **Gap detectado (no necesariamente el gate)**: `PADMAN`/`SIO2MAN`/`SIO2D`/
  `DBCMAN` cargan como **HLE** ("physical IRX unavailable") aunque los
  `.IRX` están extraídos en `work/elf/IOP/`; solo LIBSD/SDRDRV/SDSTR3/
  SD_CALL/CDVDSTM/MC2_D cargan físicos. PCSX2 sí hace el intercambio de
  config del pad ("DS2 Config Finished").
- **Próximo**: diff de la **secuencia de init** (CD/SIF/IOP) PCSX2 vs
  recomp para ubicar el punto de divergencia; y/o reparar la carga física de
  PADMAN (el único core en HLE).

### 2026-10-07/08 — Diff de init PCSX2 vs recomp: **el juego carga los IRX él mismo**
- **Método**: PCSX2 con `EnableVerbose/EnableEEConsole/EnableIOPConsole = true`
  + `-logfile`; corrida de 45s (config del usuario respaldada y restaurada).
- **Secuencia real (PCSX2)**: `ELF executing` a `t=4.01s`; **`loadmodule` ×11 a
  t=4.48–5.79s** (0.47s tras la entrada), en este orden: `SIO2MAN, PADMAN,
  SIO2D, DBCMAN, MC2_D, CDVDSTM, LIBSD, SDRDRV, LIBSMF2, SDSTR3, SD_CALL`,
  todos `ret 0/2` (OK). Además RPC registrados por los IRX (`80000592/59a/593/
  597/595/59c/80000006/...`).
- **Nuestro recomp**: **0 llamadas a `SifLoadModule`** (0 líneas
  `load-emulated`); el recomp **precarga** los IRX en `sceSifInitRpc`
  (`[iop-preload]`) y **saltea** el camino real.
- **Verificación**: desensamblé el CRT0 que salteamos (`0x4c008c→0x4c0218`):
  es exactamente el startup que los overrides ya emulan (clear FPU `mtc1`,
  clear BSS `0xA27C80–0xA93700`, gp/sp, `syscall 60` SetupThread, `syscall 61`
  SetupHeap, `jal 0x4dd618` `_init_sys`, `jal 0x4d3520`, `ei`, argc
  `0xA31D00`, `jal 0x51FEA0`, `j 0x4c1900`). **No** contiene LoadModule ⇒ el
  loader vive en otra parte (init del SDK / código no ejecutado).
- **Dónde está el loader**: tabla de nombres de módulos en el ELF
  `0x51B0A8` (`sio2man.irx`, `padman.irx`, `sio2d.irx`, `dbcman.irx`,
  `mc2/mc2_d.irx`, `cdvdstm.irx`, `libsd.irx`, `sdrdrv.irx`, …) y
  **`0x51B130` = `cdrom0:\IOP\IOPRP300.IMG`** ⇒ el juego carga el **bundle
  IOPRP300.IMG** + módulos por nombre. Los `.IRX`/`IOPRP300.IMG` están en
  `work/elf/IOP/`.
- **Conclusión**: divergimos en el **arranque del sistema de IOP** — la
  sustitución (preload propio, orden distinto, 4 módulos a HLE) reemplaza el
  camino real del juego. **Próximo**: ubicar/re-habilitar el loader propio del
  juego (o hacer el preload fiel: IOPRP300.IMG + orden de PCSX2 + carga
  física) y ver si con eso el juego pasa al primer render.

### 2026-10-08 — Preload fiel: los 11 IRX cargan físicos (pero el render sigue en cero)
- **Cambio** (`game_overrides.cpp::preloadIopBootModules`): orden **real de
  PCSX2** (SIO2MAN, PADMAN, SIO2D, DBCMAN, MC2_D, CDVDSTM, LIBSD, SDRDRV,
  LIBSMF2, SDSTR3, SD_CALL) y se intenta **primero** `cdrom0:/IOP/<name>`
  (físico) para **todos**, con fallback a host/HLE. Comentario obsoleto
  corregido (el juego **sí** llama LoadModule).
- **Resultado (smoke 90s)**: **los 11 cargan físicos** (`via=cdrom0`):
  SIO2MAN 1, PADMAN 2, SIO2D 3, DBCMAN 4, MC2_D 5, CDVDSTM 6, LIBSD 7,
  **SDRDRV 8** (`[IOP Kprintf] SDR driver version 4.0.1 (C) SCEI`),
  LIBSMF2 9, SDSTR3 10, SD_CALL 11; `TYOSD real=8`. **Cero HLE** para
  PADMAN/SIO2MAN/SIO2D/DBCMAN (antes 0x40000000+).
- **Pero**: geometría **sigue en cero** — `gif=2`, `gsw=0`, `vif=6`,
  `vramNonZero=262144` (solo alpha), `activeThreads=3`. El IOP correcto era
  **necesario pero no suficiente**: el gate está en otro lado.
- **Nota de toolchain**: `cmake` desapareció del sistema (no está en
  `/usr/bin` ni en pacman; `make`/`gcc`/`ninja` sí). Build puenteado con
  `make CMAKE_COMMAND=/bin/true` + `ar`/`c++` desde los `link.txt`. **Pedir al
  usuario `sudo pacman -S cmake`** para builds normales.
- **Próximo**: probar el camino **IOPRP300.IMG** real (el juego referencia
  `cdrom0:\IOP\IOPRP300.IMG` en `0x51B130`) y/o atacar el gate del render
  (state machine de escena / handshake de audio).

### 2026-10-08 — Datos del CD: **válidos** (hipótesis "escena corrupta" refutada)
- **Instrumentación** (`cdReadStub` 0x4cfa80, TRIAGE-CD): volcado de los
  primeros 32 B del destino tras cada `sceCdRead`.
- **Resultado**: los reads devuelven datos **correctos** — cabeceras `SIMB`
  (formato KONAMI, p.ej. `53 49 4d 42`, size `0x19`) y nombres reales
  (`mission16.bin`, `mission01.bin`, `str01000201.bin`, `str03011000.bin`,
  `str07010000.bin`). El subsistema de CD/load **está bien**.
- **Nota**: `cmake` reinstalado por el usuario (4.4.4); el build normal
  (`cmake --build`) vuelve a funcionar.
- **Descartados hasta ahora**: hilos/semáforo 3 (SIF cmd thread idle),
  pad (`scePadRead` nunca se llama), módulos IOP (ahora físicos), datos del
  CD (válidos), `loadedModules=[]` (campo de diagnóstico, red herring).
- **Único comportamiento anómalo persistente**: el **macro-spin de audio**
  (TYOSD `rpc=0` ×2693 + `FLIP` ×2680 + `libsd:6` ×692 en 60s), **igual que
  antes** del fix de IOP. El main loop corre y hace flip, pero **no emite
  draws** (`gif=2`, `gsw=0`, `vif=6`).
- **Triages activos a revertir cuando se cierre**: `triage-sema`,
  `cdread-data`, `[gen-*]`.

### 2026-10-08 — Audio descartado como gate (HLE de TYOSD desactivable)
- **Cambio**: `SWORD_TYOSD_HLE=0` en `sifCallRpcStub` desactiva el HLE de
  `sid=0x573` y deja pasar el **RPC real** (ahora que SD_CALL/SDRDRV cargan
  físicos). Reversible, sin recompilar.
- **A/B (65s)**: con HLE off el **poll-storm desaparece** — 34 `rpc=0` vs
  **2693** con HLE, y aparece `rpc=0x30000` real. O sea: **el HLE causaba el
  macro-spin del audio (iatrogenia)**. La actividad se normaliza.
- **Pero**: geometría **sigue en cero** (`gif=2`, `gsw=0`, `vif=6`, VRAM solo
  alpha) y no hay draws ⇒ **el audio NO es el gate del render**. Descartado
  "en el peor caso" (era el objetivo).
- Nota: con HLE off los tags `[TYOSD-*]`/`FLIP` no se emiten (están dentro de
  la rama HLE), así que no sirven para comparar progreso.
- **Dato extra**: el texto del juego ("Select video format", "Story Mode", …)
  **no está en el ELF** ⇒ viene en los datos (comprimido); no se puede ubicar
  el renderer del diálogo por strings.
- **Estado**: el gate sigue en la **lógica EE del juego** (corre main loop y
  regs de display, pero no arma/envía draws).

### 2026-10-08 — REENCUADRE: el juego **SÍ dibuja** (sprites), pero salen negros
- **Corrección de una lectura previa**: "cero geometría" era **falso**. El
  contador `gif`/`gsw` no captura este camino. El GS **recibe kicks**:
  `[gs:kick] drawing=1 prim=6 vtxCount=1/2` (prim=6 = **sprite**, 2 vértices).
- **El log está CAPEADO** (`gs_frontend.cpp:1534`, `debugIndex < 96u`) ⇒ el
  "96 kicks" (idéntico en 65s y en 10min) **no es el total**; no sabemos
  cuántos dibuja de verdad sin instrumentar.
- **El juego además hace setup GS real**: `sceGsSetDefDispEnv`,
  `sceGsResetPath`, `sceDmaReset`, `GsPutIMR` (new=0x65280), y
  `sceDmaSend chain kick: chan=0x10009000`.
- **Pero** VRAM queda con **RGB=0** (`crt1: rgbNZ=0 aNZ=262144`) y `gsw=0` ⇒
  los sprites se emiten y **se rasterizan en negro**: el problema probable
  está en el **backend GS** (color de vértice / muestreo de textura / destino
  de rasterizado), **no** en la lógica del juego.
- **Próximo**: (a) sacar el cap / loguear el total de kicks periódicamente;
  (b) loguear color y posición de los vértices del sprite para ver por qué no
  aporta RGB (¿RGBAQ/PRIM sin llegar? ¿TEX0 muestreada negra?).

### 2026-10-08 — El **backend GS funciona**; el juego **nunca dibuja contenido**
- **Prueba del backend**: forzando `rgba=(255,0,0,255)` en los kick de vértice,
  los sprites **se rasterizan** (pantalla roja a pantalla completa; VRAM pasa
  de 262144 a **2093058/4194304**). El problema **no** es el rasterizador.
- **Estado real de los draws** (instrumentado en `gs_frontend.cpp`):
  - `[gs:rgbaq] write#N rgba=(0,0,0,0)` — el juego **escribe RGBAQ siempre en
    (0,0,0,0)**.
  - `[gs:triage] kick#N prim=6 tme=0 abe=0 ctxt=0 uv=(0,0) tex0(tbp0=0 tbw=0
    psm=0 tw=0 th=0)` — todos los picks son **sprite sin textura**.
  - Contadores (sin cap, 60s): `gs:content` **vacío** ⇒ **cero** kicks con
    color ≠ 0 y **cero** con `tme=1`.
- **Conclusión**: el juego emite un patrón de sprites negro-transparente sin
  textura (fade/clear de presentación) y **nunca llega a dibujar el contenido**
  (texto/imágenes del diálogo, que irían con `tme=1`). Es decir: **el backend
  GS no es el gate**; el juego **no genera la lista de dibujo real** (o no la
  envía por el camino que llega a `vertexKick`).
- **Próximo**: como el juego en PCSX2 sí dibuja texto (texturas), falta
  determinar si (a) el juego está en un fade y no avanza de escena (gate
  lógico), o (b) los draws reales viajan por **VU1/path3** y no llegan a
  `vertexKick` (nuestro `vif=6` sugiere casi nulo tráfico VIF1).

### 2026-10-08 — El pipeline VU1 SÍ está activo; el color sale 0 (sospecha: VU1 core)
- **Histograma DMAC** (`[dma:chans]`, agregado en `ps2_memory.cpp`): en ~60s
  **ch9 (VIF1) ≈ 1933**, **ch10 (GIF) = 2**, **ch13 (SPR_FROM/scratchpad) ≈ 3065**.
  ⇒ el juego **sí sube datos a VIF1** y hace **mucho DMA desde scratchpad**
  (patrón típico de **VU1 volcando resultados**). `m_vifWriteCount` (MMIO) no
  lo capturaba: el tráfico va por **DMA**, no por registros.
- **Atajo probado**: forzar un color visible en **todos** los kicks ⇒ la
  pantalla se pinta **full-screen** (blanco/rojo) ⇒ los draws que llegan son
  **fades/clears de pantalla completa**, no geometría del diálogo. El atajo
  **no reveló contenido**; ya revertido.
- **Conclusión**: el camino **VIF1 → VU1 → XGKICK → GS** está activo; los
  vértices llegan al GS con **RGBAQ=(0,0,0,0)** y `tme=0`. El color/estado se
  **calcula en VU1**, así que el sospechoso principal es la **emulación de
  VU1** (microcódigo del juego que produce color 0 / no llega a la escena).
- **PRECAUCIÓN**: el mapa DMAC de este runtime trata `0x10009000` como VIF1 y
  `0x1000A000` como GIF; `0x1000D000` = SPR_FROM. Verificar contra el mapa
  canónico del EE DMAC antes de sacar conclusiones de canal.
- **Próximo**: instrumentar el **VU1** (¿se carga/ejecuta el microcódigo del
  juego? ¿instrucciones no soportadas que dején el color en 0?) y/o comparar
  con un **GS dump de PCSX2** del primer frame real.

### 2026-10-08 — El VU1 ejecuta bien; el juego **casi no lo arranca** (3 MSCAL en 60s)
- **Instrumentado** `setVu1MscalCallback`/`setVu1MscntCallback`
  (`ps2_runtime.cpp`): `[vu1:mscal]/[vu1:mscnt]` con startPc/endPc/cycles/stopD/stopT.
- **Resultado (60s)**:
  - El VU1 **sí ejecuta**: `endPc=0x168`, `stopD=0 stopT=0` (termina solo),
    **0 instrucciones reservadas** (`reportReservedInstruction` nunca dispara y
    detendría el VU1 con `RUNTIME_ERROR`).
  - **Genera paquetes GIF**: `[gs:gif] idx=N size=2576/1136 nreg=3
    ctx0fbp=128 ctx1fbp=128` ⇒ **VIF1 → VU1 → XGKICK → GS funciona**.
  - **Pero**: solo **3 MSCAL + 5 MSCNT en 60s** ⇒ el juego **no tiene un loop de
    render** (serían miles/frame). Los draws vistos (sprites pantalla-completa
    con color 0) son esos pocos arranques.
- **Conclusión (la más fuerte hasta ahora)**: **todo el pipeline de rendering
  funciona** (GS rasteriza, VU1 ejecuta, XGKICK entrega) y **el gate es lógico**:
  el juego corre su main loop (miles de iteraciones) pero **no llega a emitir la
  escena** (no llama a renderizar). Se descartan VU1/GS/DMA/VIF como causa.
- **Próximo**: atacar el **estado del juego** (¿en qué fase se queda?) —
  comparar con PCSX2 y/o instrumentar el scene/state manager. Ya no queda
  hardware por descartar.

### 2026-10-08 — El kick del render sale de `0x6e4468` y se ejecuta **3 veces en 60s**
- **Instrumentado**: agregado `eePc`/`eeRa` al log de `[vu1:mscal]`
  (`ps2_runtime.cpp`). Las 3 MSCAL salen **siempre** de
  **`eePc=0x6e4468`, `eeRa=0x6e4ebc`**.
- **Qué es `0x6e4468`** (leído en `work/generated/FUN_004eb8d0_0x4eb8d0_p41.cpp`):
  ```
  0x6e4460  srl  $v0,$v0,6
  0x6e4464  ori  $v0,$v0,0x101
  0x6e4468  sw   $v0,0($s1)   ; <-- CHCR del DMA VIF1 (0x101 = start)
  ```
  ⇒ es el **kick del DMA a VIF1** (el que lleva el paquete con el MSCAL). La
  región `0x6e4xxx` (que el team había rotulado "audio") es en realidad parte
  del **envío de render**.
- **Dato decisivo**: ese kick se ejecuta **3 veces en 60s** (el juego real
  haría miles). ⇒ **el juego no está ejecutando su loop de render**; corre un
  loop (miles de iteraciones de `0x6e4cc0`) pero **se saltea/estanca antes de
  mandar el paquete VIF1**. (Nota: los 1933 DMA a "ch9=VIF1" del histograma
  deben ser de otro camino/contabilidad del runtime; el kick del juego es raro.)
- **Conclusión**: **todo el hardware/emulación está descartado**. El gate es la
  **lógica del juego**: no llega a la fase que manda el paquete de render.
- **Próximo**: instrumentar la condición que gobierna el path hacia
  `0x6e4468` (`0x6e4438`/`0x6e4444`: ramas por `$v1 & 0x300` y `$a1`) para ver
  por qué casi nunca se toma.

### 2026-10-08 — CORRECCIÓN: `eePc` del MSCAL es engañoso; `0x6e4440` **nunca** se ejecuta
- **Instrumentado** en el **generado** (`FUN_004eb8d0_0x4eb8d0_p41.cpp`,
  `label_6e4440`, `fprintf`): contaba visitas + condición `v1 & 0x300`.
- **Resultado**: **cero** líneas `[triage-6e44]` en 60s (verificado que el
  string está en el binario y en el `.o`: la instrumentación **sí** está viva).
  ⇒ **`0x6e4440` (y por lo tanto los dos paths a `0x6e4468`/`0x6e448c`) nunca se
  ejecutan**.
- **Corrección de la entrada anterior**: como el DMA se **procesa diferido**,
  `cpuContext->pc` en el callback MSCAL **no es el sitio del kick** (es sólo
  dónde estaba el EE cuando el runtime drenó la transferencia pendiente).
  `eePc=0x6e4468` **no** implica que ese `sw` haya corrido.
- **Conclusión**: **no sabemos todavía de dónde sale el kick del VIF1**. Lo que
  sí queda firme: el render se dispara poquísimas veces (3) ⇒ el juego no está
  renderizando frames.
- **Próximo (opciones)**: (a) instrumentar el **enqueue del DMA VIF1** con el
  pc del EE (requiere plumbing de `ctx` a `writeRegister`, o loguear en el
  `Store32` de `PS2Runtime` cuando `addr` ∈ canal VIF1); (b) buscar la función
  que arma los paquetes GIF del juego por otra vía (p.ej. hooks en las
  funciones `sceDmaSend`/`sceGs*` del juego con su caller).

### 2026-10-08 — Sitio REAL del kick de render: `pc=0x6e4468` (32 kicks/60s)
- **Instrumentado** `PS2Runtime::Store32` (`ps2_runtime.cpp`): si
  `vaddr == 0x10009000` (CHCR VIF1) y bit de start (`0x100`) ⇒ log `pc`/`ra`
  del EE. **Este sí es el sitio real** (no diferido).
- **Resultado (60s)**:
  - `n=1`: `pc=0x4d07a8` (el `sceDmaSend` del SDK, arranque).
  - `n=2..`: **`pc=0x6e4468`**, `ra=0x6e4ebc`/`0x6e481c`, `CHCR=0x145`,
    `madr=0x0 qwc=0`, con `[gs:gif] size=32 nloop=1 nreg=1` (paquetes chicos =
    clears/rects).
  - Total: **32 kicks en 60s** ⇒ el juego **casi no renderiza** (confirmado).
- **Contradicción a aclarar**: `pc=0x6e4468` se ejecuta, pero `0x6e4440`
  (que lo precede en el flujo) **nunca** ⇒ o el código salta directo a
  `0x6e444c/0x6e4460`, o **la copia ejecutada no es la del archivo p41**
  (los "monsters" `FUN_004eb8d0`/`FUN_006cba48`/`FUN_006cc380`/`FUN_006cc400`
  contienen el mismo rango y pueden estar duplicados). Verificar antes de
  instrumentar el generado otra vez.
- **Próximo**: inspeccionar la función en **`ra=0x6e481c`** (la que llama al
  path del kick) y su condición; es ahí donde vive el gate del render.

### 2026-10-08 — El kick sale del **handler de DMAC del juego** (`0x6e4068`)
- **Confirmado: hay 4 copias** del rango `0x6e4xxx` (mismo código en
  `FUN_004eb8d0_p41` / `FUN_006cba48_p2` / `FUN_006cc380_p2` /
  `FUN_006cc400_p2`) ⇒ **instrumentar el generado es frágil** (mi edición en
  `p41` no era la copia ejecutada). De ahora en más: preferir **`Store32`** (que
  da el `pc` real) o **desensamblar el ELF**.
- **Desensamblado del ELF** en `0x6e47c0..0x6e4844`: la función del kick es
  **`0x6e4068`** — y el propio log la marca como **handler de interrupción
  DMAC** (`[ee-irq] add dmac cause=1/2 handler=0x6e4068`). Su lógica:
  `lw $v1,0x3C0($v0)` → `beq $v1,0 → 0x6e4814` (rama alternativa) o kick GIF
  (`sw` a `0x1000A030/0x1000A020/0x1000A000`).
- **IRQ de DMAC** (`EeScheduler::dispatchIrq(dmac,cause)`): en 60s
  **`dispatch dmac cause=1` ≈ 1200** (canal **VIF1**) y **`cause=2` = 0**
  (canal **GIF**). El runtime **sí** encola `cause=2` al completar un DMA GIF
  (`ps2_memory.cpp` `hadGif → queueCompletedDmacCause(2)`) ⇒ nunca completa un
  DMA GIF porque **el juego casi no usa ese canal** (solo 2 DMA al GIF).
- **Conclusión**: el juego manda sus paquetes por **VIF1** (XGKICK) y su kick
  es parte del **handler de DMA** — pero lo ejecuta **32 veces/60s** ⇒ **el
  juego no está renderizando frames**. El gate está en la **lógica de la
  aplicación**, no en el DMAC/IRQ.
- **Próximo**: dado que hardware, IRQ y emulación están descartados, volver al
  **estado del juego**: comparar con PCSX2 (qué debería estar pasando a los
  ~20s) o instrumentar el scene/state manager del juego.

### 2026-10-08 — **GATE ENCONTRADO**: el handler de DMA sale por `gp+0x638 == gp+0x63C`
- **Desensamblado del ELF** (`0x6e4068`, el handler de DMAC del juego):
  ```
  0x6e4074  addiu $v0,$0,-1
  0x6e40e8  lw    $a1,0x638($gp)
  0x6e40ec  lw    $v0,0x63C($gp)
  0x6e40f0  beq   $a1,$v0,0x6e4590   ; <-- si 638==63C -> EPILOGO (no procesa DMA)
  0x6e40fc  bne   *(gp+0x5CF),0,0x6e4590
  ```
  (`0x6e4590` es el epílogo: restore + `jr $ra`.)
- **Evidencia del log**: `[TYOSD-ab] ... 638=0xb15a90 63c=0xb15a90` ⇒ **son
  iguales** ⇒ el handler de DMA del juego **retorna sin procesar nada** ⇒ no
  manda paquetes ⇒ **no renderiza**. (Coincide con los 32 kicks/60s.)
- **REINTERPRETACIÓN CLAVE**: los campos `gp+0x638/0x63C` (y `0x630`, `0x5CF`)
  que el equipo venía instrumentando bajo la etiqueta **"TYOSD/audio"** son en
  realidad la **cola de DMA/render del juego** (los lee su handler de DMAC).
  Toda la saga de "la cola de audio no drena" era, en realidad, **la cola de
  DMA del motor**.
- **Próximo**: entender qué llena `gp+0x638/0x63C` (el productor de la cola de
  DMA) y por qué quedan iguales; y qué es `gp+0x5CF` (flag que también frena).
  Ese es el camino directo al primer frame.

### 2026-10-08 — El ciclo productor/consumidor del DMA del motor
- **Escaneo del ELF** (`gp`=r28, escrituras/lecturas de `0x638/0x63C/0x630/0x5CF`):
  - **Productor** `0x6e4348` (`sw $v0,0x638($gp)`), con `0x6e433c: sw 0x145 →
    (VIF1 CHCR)` ⇒ **el kick del VIF1 lo hace el productor** y **avanza
    `head += 8`** (`0x6e4340/0x6e4348`) + `gp+0x630 += 2`.
  - **Consumidor/spin** `0x6e4d98`: `lw 0x638` (head) vs `lw 0x63C` (tail);
    `bne` → procesar; si iguales llama al callback **`*(gp-0x7A30)` (cb)** y
    **gira** (`bne $s0,0 → 0x6e4d98`). El log muestra **`cb=0x0`** ⇒ gira sin
    llamar nada (macro-spin).
  - **Tail** se actualiza en `0x6e4e04: sw $a0,0x63C($gp)`.
  - `0x630` se incrementa en el productor y **decrementa** en el handler
    (`0x6e40d8`) ⇒ es el contador de "DMA en vuelo".
- **Lectura del sistema**: `gp+0x638/0x63C` = **head/tail de la cola de
  comandos DMA/render del motor** (no audio). El handler de DMAC la mira
  (`beq head,tail → salir`) y el spin la espera. `gp+0x5CF` es otro flag que
  también frena el handler.
- **Próximo**: con esto claro, instrumentar **head/tail/cb/630/5CF en el
  momento del handler de DMA** (no en el harness viejo) para ver si el
  productor deja `head != tail` y el handler lo ve; y por qué `cb == 0`.

### 2026-10-08 — Estado de la cola en el dispatch del handler de DMA
- **Instrumentado** `PS2Runtime::drainCompletedDmacHandlers`
  (`[dmairq] n=.. cause=.. head=.. tail=.. EMPTY|WORK f630=.. f5cf=.. cb=..`),
  leyendo `gp+0x638/0x63C/0x630/0x5CF` y `gp-0x7A30` (cb) del RDRAM **justo
  antes** de despachar.
- **Resultados (60s)**:
  - El handler se despacha muchas veces (`cause=1` dominante, también `2` y `8`).
  - La cola **se mueve**: hay despachos `WORK` (`head != tail`, p.ej.
    `head=0xa96680 tail=0xa96690`) y `EMPTY` (`head == tail`).
  - **`cb=0x0` en TODOS** ⇒ el callback que el spin (`0x6e4d98`) invoca nunca
    está instalado ⇒ el spin gira sin consumir.
  - El flag **`gp+0x5CF` aparece en 1** en varios despachos ⇒ el handler sale
    también por `0x6e40fc: bne *(gp+0x5CF),0 → epílogo`.
- **Lectura**: el motor **sí** encola/despacha DMA (head/tail avanzan, y hay
  kicks), pero (a) el **callback nunca se instala** y (b) el flag `5CF` frena
  el handler a menudo. Y el volumen es bajísimo (32 kicks/60s).
- **Próximo**: ver quién debería instalar `cb` (`gp-0x7A30`) y quién pone
  `gp+0x5CF = 1` (escritores detectados: `0x511ef4`, `0x511f44`, `0x6e44e4`,
  `0x6e44fc`, `0x6e4644`, `0x6e690c`) — ahí está el freno real.

### 2026-10-08 — `cb` nunca se instala y `5CF` nunca se resetea
- **Escaneo del ELF** de escritores:
  - **`cb`** (`gp-0x7A30`): **instalador `0x6e6934`** (`sw $a0,-0x7A30($gp)`) y
    **desinstalador `0x6e6cf0`** (`sw $zero,-0x7A30($gp)`). Como en runtime
    `cb=0` siempre ⇒ **el instalador no corre** (o se desinstala al toque).
  - **`f5cf`** (`gp+0x5CF`): se **resetea a 0** en `0x6e690c`, dentro de una
    función de **reset del motor de DMA** (`0x6e68e0..0x6e692c`: pone
    `f630=0`, `f5cf=0`, `5dc/5e0/5e4/5e8/5ec=0`, `640=0`, tras `jal 0x4d3b98`).
    Como seguimos viendo `f5cf=1`, **ese reset no corre**.
- **Lectura**: el motor de DMA del juego **nunca se inicializa**
  (`cb` sin instalar + `5CF` en 1 de fábrica) ⇒ el handler de DMA sale y el spin
  gira sin consumidor. Eso explica los 32 kicks/60s.
- **Próximo**: encontrar **quién llama** a `0x6e6934` (instalador de `cb`) y a
  la función de reset `0x6e68e0`; si esas llamadas no ocurren, el gate son sus
  condiciones/callers.
- **Entorno (2026-10-08)**: se movieron los clones externos fuera del repo con
  **symlinks** (el build los necesita en su ruta):
  `tools/PS2Recomp → /home/lubonch/repos/_external/PS2Recomp`,
  `ghidra-mcp → /home/lubonch/repos/_external/ghidra-mcp`; sus `.git` quedan
  como `.git-off`. VS Code ya no los ve como repos.

### 2026-10-08 — Watchpoints: nadie escribe la cola vía `Store32/8` (fast-write)
- **Búsqueda de callers** del instalador de `cb` (`0x6e6934`) y del reset
  (`0x6e68e0`): **0 callers** (ni `jal`/`j` ni punteros literales en el ELF) ⇒
  ni reachable estáticamente.
- **Watchpoints** en `PS2Runtime::Store8/Store32` sobre `gp+0x5CF`, `gp+0x630`,
  `gp+0x638`, `gp+0x63C` y `gp-0x7A30` (comparando **relativo al gp del ctx** y
  también **absoluto** con `gp=0xA28070`): **0 hits en 60s**.
- **Pero** `[dmairq]` confirma que `head`/`tail` **cambian**
  (`0xa96680/0xa96690 → 0xb15a80/0xb15a90`) con `gp=0xa28070`.
- **Conclusión**: el juego escribe esos campos por un camino que **no pasa por
  `Store32/Store8`** ⇒ el generado usa **`FAST_WRITE*`** (escritura directa a
  RDRAM) o `Store128`. Por eso los watchpoints del runtime no sirven para estos
  campos.
- **Próximo**: para instrumentar el productor hay que usar
  **`runtime.replaceFunction(0x6e4348u, …)`** (funciona, el equipo ya lo hizo
  como `triageProd`) o editar el generado en las **4 copias**; o probar
  watchpoints en `Store128/Store64`.

### 2026-10-08 — El productor `0x6e4348` **nunca se ejecuta** (motor sin arrancar)
- **Extendido `triageProd`** (`replaceFunction(0x6e4348u, …)`, que sí funciona
  aunque el `sw` lo emule el hook) para loguear `head/tail/630/5CF/cb` antes de
  encolar: `[prod] n=… headPrev=… newHead=… tail=… f630=… f5cf=… cb=…`.
- **Resultado**: **cero líneas `[prod]` en 55s** ⇒ el juego **nunca ejecuta
  `0x6e4348`** ⇒ la cola **nunca se llena** por el productor.
  (Los 32 kicks/60s salen del **otro** camino, `pc=0x6e4468`, no del productor.)
- **Círculo vicioso confirmado**: el handler de DMAC (`0x6e4068`) sale temprano
  (`head==tail` y/o `f5cf!=0`) → no llega al productor → la cola no se llena →
  el handler sigue viéndola vacía. Y el **arranque del motor** (instalar `cb`
  en `0x6e6934` + resetear `5CF` en `0x6e68e0`) **nunca ocurre** (0 callers
  estáticos y `cb=0` en runtime).
- **Conclusión**: el juego **no inicializa su motor de DMA/render**. El gate es
  el **init del motor** — hay que ver si `0x6e68e0`/`0x6e6934` se ejecutan
  (hookearlos con `replaceFunction`) y quién debería llamarlos.
- **Próximo**: `replaceFunction(0x6e68e0, log)` y `replaceFunction(0x6e6934, log)`
  para confirmar si el init corre en runtime (independiente de callers
  estáticos), y si no, rastrear su caller por otras vías (jalr / tablas).

### 2026-10-08 — El init del motor de DMA **nunca corre** (confirmado en runtime)
- **Hookeado** `0x6e68e0` (reset motor) y `0x6e6934` (instala `cb`) con
  `replaceFunction` + `g_orig*` (loguea `ra`/`a0` y llama al original).
- **Resultado**: `[motorinit] lookup 0x6e68e0=OK 0x6e6934=OK` (ambas
  **registradas** en la tabla de funciones) pero **cero disparos** ⇒ ni el reset
  ni el instalador se ejecutan.
- **Salvedad**: son direcciones **interiores** a sus funciones; si el runtime
  consultara overrides sólo al entrar a la función (no en cada instrucción), el
  hook podría no dispararse aunque la función corriera. A verificar hookeando el
  **próemio real** (encontrar el inicio de esas funciones).
- **Estado**: el cuadro queda coherente y cerrado a nivel motor — **el juego no
  inicializa su motor de DMA/render** (`cb=0`, `f5cf=1` de fábrica), el handler
  de DMAC sale temprano, el productor nunca corre, la cola nunca se llena, no
  hay frames (32 kicks/60s).
- **Próximo**: o bien encontrar el **inicio real** de `0x6e68e0`/`0x6e6934` y
  hookearlo, o subir un nivel: buscar **quién debería llamar al init del motor**
  (jalr/tabla) — es el último eslabón antes del primer frame.

### 2026-10-08 — El init del motor no tiene camino (código sin referencias)
- **Prólogo real** (escaneo hacia atrás):
  - `0x6e68e0` (reset motor) y `0x6e6934` (instala `cb`): **sin `addiu sp,sp,-N`
    cercano** (≤0x200) ⇒ no hay prólogo propio localizable.
  - `0x6e6cf0` (desinstala `cb`): prólogo en **`0x6e6cb8`** (`addiu sp,sp,-16`).
- **Referencias**: **ninguna** en todo el ELF — ni punteros literales, ni
  `lui 0x6e + addiu 0x68e0/0x6934`, ni `jal`/`j`. ⇒ **no se llaman por
  dirección**; sólo podrían alcanzarse por **fallthrough**, y el código previo
  termina en `jr $ra` (`0x6e6930`), así que tampoco.
- **Conclusión**: en el desensamblado actual esas entradas **no tienen camino**.
  Como el rango `0x6e4xxx` está cubierto por **4 "monsters" solapados**
  (`FUN_004eb8d0`/`FUN_006cba48`/`FUN_006cc380`/`FUN_006cc400`), es probable que
  **la estructura real esté mal** en esa zona (funciones partidas/inline).
- **Próximo**: dejar el análisis estático de esa zona (poco confiable) y **A/B con
  PCSX2**: ver *cuándo/dónde* el juego real inicializa su motor de DMA (primer
  frame) y comparar contra nuestro recomp; o re-desensamblar esa zona con una
  herramienta real (Ghidra interactivo / objdump) antes de seguir.

### 2026-10-08 — **GATE REAL**: spin de DMA antes del init del motor (`0x6f0920`)
- **Corrección del desensamblado** (búsqueda de prólogo ampliada a 0x1000):
  - `0x6e68e0` **NO es función**: es código **interior** de la función que
    empieza en **`0x6e6640`** (`addiu sp,sp,-64`). El `jr $ra` de `0x6e6928`
    es un early return. (Por eso el hook en `0x6e68e0` no disparaba: era
    interior.)
  - `0x6e6934` **sí** es función hoja (`sw $a0,-0x7A30($gp); jr $ra`).
- **Hookeado `0x6e6640`** (entrada real, `lookup=OK`): **cero disparos** ⇒
  **la función de reset del motor nunca corre**. Y `0x6e6934` tampoco.
- **Caller de `0x6e6640`**: **uno solo** en todo el ELF — **`0x6f0950`**.
  Desensamblado de su función:
  ```
  0x6f0920  jal 0x4d1a60 (a0=1)
  0x6f0928  bne $v0, 0 -> 0x6f0920      ; <-- SPIN mientras v0 != 0
  0x6f0938  ori $v0,0x1000,0xE010        ; 0x1000E010 = D_STAT (DMAC)
  0x6f0940  sw 4 -> D_STAT               ; reset DMAC
  0x6f0944  sw $zero, 0x3CC($s0) ... 0x3C0($s0)   ; limpia el campo 0x3C0
  0x6f0950  jal 0x6e6640                 ; <-- init del motor (NUNCA se llega)
  ```
- **Qué es `0x4d1a60`**: **espera de DMA** — con `a0==0` lee el **CHCR de VIF1**
  (`0x10009000`) y espera a que se limpie el bit de start; con `a0!=0`
  (`0x4d21d4`) hace `ld 0x12001000` y espera el **bit 1** (con timeout por
  `sltu`/contador).
- **CONCLUSIÓN**: el juego queda **girando en un sync de DMA (`0x6f0920`)**
  **antes** de inicializar el motor ⇒ no instala `cb`, no resetea `5CF`, el
  handler de DMAC sale, el productor nunca corre, **no hay frames**. **Ese es el
  gate real**, y es donde hay que mirar: por qué nuestro runtime no satisface esa
  espera (`0x12001000` bit 1 / CHCR de VIF1/GIF).

### 2026-10-08 — CORRECCIÓN: el spin `0x6f0920` **sí sale** (no es el gate)
- **Hookeado `0x4d1a60`** (`lookup=OK`; log `[dmasync] a0/ret/ra`).
- **Resultado (45s)**: **solo 3 llamadas**, todas con `a0=1` y **`ret=0x0 (ZERO)`**
  ⇒ `0x4d1a60` devuelve 0 ⇒ el spin `0x6f0920` (`bne $v0,0 → loop`) **NO repite**:
  **sale**. `ra` = `0x6f01e8`, `0x6f07d8`, `0x6f0928` (3 call sites distintos).
- ⇒ **Mi conclusión anterior era incorrecta**: el juego **no** está atascado en
  ese sync (si lo estuviera, habría miles de llamadas).
- **Sigue en pie**: el hook de `0x6e6640` (init del motor) **no dispara** — pero
  ahora no se explica por el spin. Hipótesis: (a) `replaceFunction(0x6e6640)` no
  surte efecto en esa dirección (aunque `lookup=OK`), o (b) el bloque
  `0x6f0930..0x6f0950` (tras el spin) no se ejecuta / salta antes.
- **Próximo**: hookear/loguear `0x6f0940`/`0x6f0950` (justo antes del `jal`) para
  ver si el flujo llega ahí, y verificar que el override de `0x6e6640` se aplique
  (p.ej. hookear una dirección vecina conocida como control).

### 2026-10-08 — ⚠️ CORRECCIÓN METODOLÓGICA: los `replaceFunction` no disparan en esa zona
- **Prólogo real**: las 4 call-sites de `0x4d1a60` (`0x6f01e8`, `0x6f07d8`,
  `0x6f0928`, `0x6f0950`) están **todas dentro de una misma función** cuyo prólogo
  es **`0x6efd28`** (`addiu sp,sp,-160`).
- **Hookeado `0x6efd28`** (`lookup=OK`): **cero disparos**. **PERO** el código de
  `0x6f0920` (dentro de `0x6efd28`) **sí corre** — probado por el `ra=0x6f0928`
  con que `0x4d1a60` fue llamada.
- ⇒ **Los overrides de `replaceFunction` NO se aplican en las direcciones de esa
  zona**: el código generado de los "monsters" usa **`goto label_X` internos que
  bypassean el check de overrides** (limitación ya anotada por el equipo:
  "los `goto` internos bypassean hooks"). `lookupFunction` devuelve algo
  (`lookup=OK`) pero el override **nunca se consulta** en esas direcciones.
- ⚠️ **Consecuencia**: quedan **inválidas** las conclusiones basadas en
  "el hook de `0x6e6640`/`0x6e6934` no dispara ⇒ no corre". NO sabemos si el init
  del motor corre o no — hay que instrumentarlo **editando el generado**
  (`fprintf`), que es la vía que sí funciona en esa zona (el equipo lo hacía así).
- **Próximo**: instrumentar en el **generado** (`0x6f0950` → ¿llega al `jal`? y
  `0x6e6640` → ¿corre el reset?), en las **4 copias** si hace falta.

### 2026-10-08 — Instrumentado el generado: **el init del motor SÍ corre**; y la copia que ejecuta es `FUN_006cba48`
- **Instrumenté las 4 copias** del generado (`label_6f0950` en los `*_p42/p3`,
  `label_6e6640` en los `*_p41/p2`) con `fprintf` + tag por archivo
  (`A41/B2/C2/D2/A42/B3/C3/D3`).
- **Resultado**: exactamente **2 líneas**:
  ```
  [GEN-B3] 6f0950-jal  n=1        (copia FUN_006cba48_p3)
  [GEN-B2] 6e6640-init n=1        (copia FUN_006cba48_p2)
  ```
- **Conclusiones**:
  1. **El init del motor SÍ se ejecuta** (1 vez): el `jal 0x6e6640` **llega** y la
     función corre. La conclusión anterior ("nunca corre") era **falsa** (era
     consecuencia del override que no aplicaba).
  2. ⚠️ **La copia EJECUTADA es `FUN_006cba48` (tag B)**, NO `FUN_004eb8d0`
     (tag A). ⇒ el runtime **registra una copia y ejecuta otra**: por eso los
     `replaceFunction` en ese rango **no surten efecto** (registran bajo A pero
     corre B). **Regla nueva: instrumentar/parchear `FUN_006cba48`** (y verificar
     por tag cuál corre) — no `FUN_004eb8d0`.
  3. El reset corre **1 sola vez** y aun así `f5cf=1`/`cb=0` en runtime ⇒ o sale
     antes de `0x6e690c` (early return), o algo lo vuelve a poner en 1 después.
- **Próximo**: instrumentar dentro de **`FUN_006cba48`** el tramo del reset
  (`0x6e68e8..0x6e6914`: `sb 0x630`, `sw 0x5dc/5e0/5e4/5e8/5ec`, `sb 0x5cf`,
  `sb 0x640`) para ver **dónde sale** y con qué deja `f5cf`/`cb`.

### 2026-10-08 — El reset completa; `f5cf` vuelve a 1 después; forzarlo no alcanza
- **Instrumentado** el tramo del reset en `FUN_006cba48_p2` (`fprintf` en
  `0x6e690c`, `0x6e6914`, `0x6e6918`, `0x6e6928`):
  ```
  [GEN-B2] 6e6640-init    n=1
  [GEN-B2] after-sb5cf    n=1 f5cf=0 f630=0
  [GEN-B2] after-sb640    n=1 f5cf=0 f630=0
  [GEN-B2] reset-epilogue n=1 f5cf=0 f630=0
  [GEN-B2] jr-ra          n=1 f5cf=0 f630=0
  ```
  ⇒ **el reset COMPLETA** (deja `f5cf=0`) y llega al `jr $ra`.
- **Pero** en runtime `f5cf` vuelve a **1** después: los otros escritores de
  `5CF` (`0x6e44e4`, `0x6e44fc`, `0x6e4644`) están **dentro del handler de DMAC**
  ⇒ el handler lo pone en 1 (busy) y nadie lo baja.
- **Atajo probado** (`SWORD_FORCE_F5CF=1` en `drainCompletedDmacHandlers`: fuerza
  `gp+0x5CF=0` antes de despachar): **sin efecto** — el handler ya no sale por
  `f5cf`, pero **sigue saliendo por `head == tail`** (`EMPTY`): la cola está
  vacía ⇒ no hay nada que procesar. `gif=2`, VRAM 262144.
- **Estado**: el freno efectivo pasó a ser **la cola vacía** (el productor
  `0x6e4348` no encola). Y recordar que ese hook vive en la copia equivocada
  (`FUN_004eb8d0`) — hay que instrumentarlo en **`FUN_006cba48`**.
- **Próximo**: instrumentar `0x6e44e4/0x6e44fc/0x6e4644` (quién deja `f5cf=1`) y
  el productor **en `FUN_006cba48`**.

### 2026-10-08 — Iteración sobre el motor de DMA (sin resultado visual todavía)
- **Productor/consumidor instrumentados en la copia correcta** (`FUN_006cba48_p2`):
  - `prod` (`0x6e4348`): **0 ejecuciones** ⇒ el productor **nunca corre** (ni en la
    copia que ejecuta: el `triageProd` del equipo vive en `FUN_004eb8d0`, copia
    equivocada).
  - `tail` (`0x6e4e04`) y `spin` (`0x6e4d98`): **corren** (head/tail = offsets
    `0x80`/`0x90` alternando ⇒ el "ping-pong" histórico).
- **Atajo probado — neutralizar los 3 early-returns del handler** (`0x6e40e0`,
  `0x6e40f0`, `0x6e40fc` → editar el generado): **sí cambia algo** (`gif=3`
  aparece por primera vez, `head/tail` pasan a `WORK`), **pero corrompe**
  (`head=0x4c01a0`, un puntero de código; VRAM cae a 0). Demasiado agresivo ⇒
  **revertido** (`if (false && …)` → `if (…)`), build OK.
- **Estado del gate** (sin cambios respecto de antes): el handler de DMAC sale
  temprano (cola vacía / `f5cf`); el productor nunca corre ⇒ el motor no encola
  ⇒ no genera frames con contenido. El bypass demuestra que **el handler SÍ
  puede procesar** cuando no sale, así que el camino está ahí — falta que el
  **estado de la cola sea coherente** (hoy `head`/`tail` son offsets `0x80/0x90`
  y el handler los compara; hay que entender **quién** los pone a `0x90`).
- **Nota de higiene**: el generado quedó **limpio** de este atajo (revertido);
  siguen los `fprintf` de instrumentación (`GEN-*`, `[dmairq]`, `[motorinit]`,
  `[dmasync]`, `[prod]`, `[wp*]`, `[f5cf-force]`) como triages a limpiar al
  cerrar el hito.

### 2026-10-08 — Todo el motor de DMA vive DENTRO del handler (sin entradas externas)
- **Escaneo estático** de `0x6e4348` (productor), `0x6e4564` (2º escritor de
  `head`), `0x6e44e4/44fc/4644` (escritores de `f5cf`): **cero referencias** en
  todo el ELF — ni `jal`/`j`, ni punteros literales, ni `lui 0x6e + addiu`.
- ⇒ Son **código interior** del handler de DMAC (`0x6e4068..0x6e4840`). **Todo
  el "motor de DMA" está auto-contenido ahí**: productor, escritores de
  `head`/`tail`/`f5cf`, consumidor.
- **Consecuencia**: como el handler **sale si `head == tail`** (`0x6e40f0`) y
  **nadie encola desde afuera** (los únicos escritores de `head` son internos),
  el **círculo nunca se rompe**: `head==tail` ⇒ sale ⇒ no produce ⇒ `head==tail`…
- ⇒ En una PS2 real, algo debe dejar `head != tail` **antes** del primer
  dispatch (el setup `0x6efd28` limpia `0x3C0..0x3CC` y llama al reset, pero **no
  escribe `head`**). **Ahí está la pregunta**: qué estado inicial de la cola
  espera el juego y por qué el nuestro arranca en `head==tail`.
- **Próximo**: instrumentar el **setup `0x6efd28`** (en el generado, copia
  `FUN_006cba48_p3`), sobre todo después del `jal 0x6e6640` (`0x6f0958+`), y ver
  qué deja en la cola / si debería llamar al productor.

### 2026-10-08 — El setup corre pero **no encola** (`head == tail == 0`)
- **Instrumentado** el setup en `FUN_006cba48_p3` (`post-reset` 0x6f0958, `sp1`
  0x6f0964, `sp2` 0x6f0974, `sp3` 0x6f09e0, `sp4` 0x6f0a08):
  ```
  [GEN-B3] post-reset n=1 head=0x0 tail=0x0 f5cf=0
  [GEN-B3] sp2        n=1 head=0x0 tail=0x0 f5cf=0
  [GEN-B3] sp4        n=1 head=0x0 tail=0x0 f5cf=0
  ```
  (`sp1`/`sp3` **no** se ejecutan: el flujo toma otra rama.)
- ⇒ El setup **corre** (post-reset → sp2 → sp4) y **deja la cola en
  `head == tail == 0`**: **no encola**, y el productor sigue sin correr.
- **Conclusión del hilo "motor de DMA"**: en nuestro recomp, **nadie llena la
  cola** (`head == tail` desde el arranque; el setup no encola y el productor
  sólo se alcanza desde el handler, que sale por `head == tail`). El motor
  **nunca arranca** ⇒ no se generan frames con contenido (32 kicks/60s, todos
  "clear" full-screen).
- **Pregunta abierta (la que separa de la PS2 real)**: qué hace que en la
  consola la cola tenga trabajo en el primer dispatch. Hipótesis: un DMA de
  arranque (carga) que en nuestro recomp no deja el mismo estado, o un `head`
  inicial distinto. `head` pasa a `0x80/0x90` recién **después** del setup
  (escritor `0x6e4564`, interno del handler).

### 2026-10-08 — Atajo `cb = productor`: el spin no llega a invocarlo
- **Hipótesis**: el spin (`0x6e4d98`) llama a `cb` (`gp-0x7A30`) cuando
  `head==tail` para **producir**; `cb=0` ⇒ nunca llena la cola. Experimento:
  instalar `cb = 0x6e4348` (el productor) en runtime (`SWORD_CB_PRODUCER=1`).
- **Resultado**: el `cb` **se instala** (`[cb-install] cb = 0x6e4348`) pero
  `prod` sigue en **0** ⇒ **el spin no llega a invocar `cb`** (o no corre tras
  instalarlo). Sin cambio: `gif=2`, `vramNonZero=0`.
- **Estado**: el atajo quedó **detrás de env** (`SWORD_CB_PRODUCER`, OFF por
  defecto ⇒ inocuo) como experimento revertible; anotado como triage.
- **Balance del día**: pese a ~40 ciclos build+run **no se alcanzó imagen con
  contenido**. El cuadro es coherente y está bien acotado (todo el motor de DMA
  vive en el handler de DMAC; nadie llena la cola; el handler sale por
  `head==tail`), pero **la causa raíz de por qué la cola arranca vacía en el
  recomp y no en la consola sigue sin determinarse**.
- **Siguientes candidatos**: (a) A/B fino con PCSX2 del estado de la cola en el
  primer frame (requiere ver RDRAM en PCSX2 — p.ej. via debugger/savestate);
  (b) revisar si el runtime **genera las IRQ de DMAC** con la misma cadencia que
  la consola (el handler procesa según IRQ); (c) revisar el arranque `0x4c008c`
  → por si un paso de init del DMAC (que la consola hace) se está salteando.

### 2026-10-08 — **A/B con savestates de PCSX2: la cola SÍ está viva en la consola**
- **Método**: el `.p2s` de PCSX2 2.x es un **ZIP** con `eeMemory.bin` (RDRAM de
  32 MB) + registros + `Screenshot.png`. Se parsea con `zipfile` de Python.
  Slots: **01 = diálogo de formato**, **02 = título/menú**.
- **Resultado (gp = 0x00A28070 en ambos)**:
  | campo | PCSX2 slot1 | PCSX2 slot2 | recomp |
  |---|---|---|---|
  | `head` (gp+0x638) | **0x00A96800** | **0x00A96800** | 0x80/0x90 |
  | `tail` (gp+0x63C) | **0x00A96830** | **0x00A9E0E8** | 0x80/0x90 |
  | estado | **WORK** | **WORK** | EMPTY |
  | `cb` (gp-0x7A30) | **0** | **0** | 0 |
  | `f5cf` | **1** | **1** | 1 |
  | `f630` | 0 | 0 | 0 |
- **Conclusiones (corrigen hipótesis previas)**:
  1. **`cb=0` y `f5cf=1` son idénticos en la consola** ⇒ **NO eran la causa**.
     Se descartan como gate (el juego real funciona así).
  2. **La cola difiere radicalmente**: en la consola `head`/`tail` son **punteros
     reales** (`0x00A96800`, WORK ⇒ el motor está procesando); en el recomp son
     **0x80/0x90** (offsets chicos ⇒ EMPTY ⇒ el handler sale siempre).
- ⇒ **El gate real es la inicialización de `head`/`tail`**: en el recomp quedan
  con valores inválidos (no el puntero al ring `0xA96xxx`), así que el handler de
  DMAC siempre ve `head == tail` y nunca procesa.
- **Próximo**: encontrar **quién inicializa `head`/`tail` con el puntero del ring
  (`0xA96800`)** y por qué en el recomp no ocurre (o queda sobrescrito). Candidato
  claro y acotado.

### 2026-10-08 — Formato del ring (leído del savestate): comandos de 16 B
- **Contenido del ring `0xA96800` (consola)** — entradas de **16 B** = dos pares
  `[u32 tag][u32 addr]`:
  ```
  0xa96800: 00001101 00a96880 | 00001042 00b96898
  0xa96810: 00001042 00b97738 | 00001042 00b96d78
  ...
  ```
  Tags vistos: **`0x1101`** (1er comando, apunta a `0xA96880` = ring+0x80, o sea una
  cabecera/estructura) y **`0x1042`** (mayoría; apunta a buffers `0xB9xxxx`).
- **Ocupación**: slot1 (diálogo) `head→tail` = 3 entradas; **slot2 (título) =
  1934 entradas** ⇒ la cola está **llena** en la consola.
- **Coincidencia notable**: **1934 entradas ≈ los `ch9 (VIF1) = 1933` DMA**
  medidos en el recomp ⇒ fuerte indicio de que *ese* es el mecanismo de render
  (la cola alimenta los DMA de VIF1) y que en el recomp el vínculo
  cola→DMA no está cerrándose por los `head`/`tail` inválidos.
- **Próximo**: ver **quién escribe los comandos** en el ring (`0xA96800+`) y quién
  fija `head`/`tail`; comparar con el recomp (donde la cola nunca se llena).

### 2026-10-08 — El ring no es data del ELF: se llena en runtime
- **Segmentos del ELF**: `[0x4C0000, 0xA93700)` (5.8 MB) y `[0x100000, 0x154000)`;
  BSS vacío.
- El **ring `0xA96800` cae justo ARRIBA** del final del segmento (`0xA93700`) ⇒
  **NO es data inicializada**: es **RAM que el juego llena en runtime**. (El `gp`
  `0xA28070` sí está dentro del segmento cargado.)
- ⇒ **Gate final**: existe una función que **arma y escribe los comandos del ring**
  (`[tag][addr]` de 16 B) que en el recomp **no corre** (o corre mal) ⇒ la cola
  queda sin llenar ⇒ `head==tail` ⇒ el handler de DMAC sale ⇒ sin render.
- **Balance del día**: avance de diagnóstico **grande** (A/B con savestates
  funcional; formato de la cola; `cb`/`f5cf` descartados por A/B), aunque **sin
  imagen con contenido todavía**. Próximo paso bien acotado: hallar al
  **escritor del ring** y por qué no corre en el recomp.

### 2026-10-08 — **Decisivo**: el ring está VACÍO en el recomp; escritor localizado
- **Volcado del ring en el recomp** (`[ring] 0xa96800`): **48 bytes en 0x00** ⇒
  **el juego NUNCA escribe los comandos del ring**. En la consola está lleno.
- **Corrección** de la medición previa de `head`/`tail`: los `[dmairq]` muestran
  `head=0xA96680 tail=0xA96690 **WORK**` y `head=0xB15A80 … WORK` ⇒ son
  **punteros válidos y a veces WORK** (mi lectura anterior de `0x80/0x90` era
  mala). El handler **no** sale siempre; el problema es que **el ring está vacío**.
- **Escritor del motor localizado**: buscando la constante del tag (`addiu
  $rt,$0,0x1101`) apareció en **`0x6e58fc`**, **`0x6e5cf0`** y `0x6dd49c`.
  Desensamblado `0x6e5cec..0x6e5d20` — **arma el comando del motor**:
  ```
  0x6e5cec  lw  $v0,0x5DC($gp)
  0x6e5cf0  addiu $v1,$0,0x1101        ; tag
  0x6e5cf8  sw  $v0,0x5C0($gp)
  0x6e5cfc  sw  $v1,0x62C($gp)         ; tag 0x1101
  0x6e5d00  sw  $a0,0x620($gp)
  0x6e5d14  ori $v0,$v0,0x1101         ; 0x80001101 (tag con bit 31)
  0x6e5d1c  sw  $v0,0x62C($gp)
  ```
  Es de la **misma zona del handler** (`0x6e5xxx`) ⇒ el handler debe **procesar**
  para llegar acá y encolar.
- **Próximo (decisivo)**: instrumentar **`0x6e5cf0`** en el generado (copia
  `FUN_006cba48`) para ver si corre en el recomp; si no, ver qué rama del handler
  lo está evitando.

### 2026-10-08 — El motor arma el comando pero el ring sigue vacío
- Instrumentado `0x6e5cf0` en el generado (las 4 copias): **corre 20+ veces** en
  el recomp ⇒ el motor **sí arma** el comando (escribe `gp+0x5C0`/`0x62C`/…).
- **Pero el ring `0xA96800` sigue en 0x00** (volcado sigue vacío) ⇒ lo que el
  juego arma **no llega a `0xA96800`**.
- **Diferencia de `head`**: consola `0xA96800` (justo el ring) vs recomp
  `0xA96680` / `0xB15A80` (otros buffers) ⇒ el recomp apunta a **otro** buffer.
- ⇒ Hipótesis afinada: el "ring" del motor **no es `0xA96800`** sino lo apuntado
  por su propio estado (`gp+0x5C0`/`gp+0x5DC`…), o el **commit** del comando
  (publicar `head`) no está ocurriendo. Hay que mapear la estructura real del
  motor (`gp+0x5C0`, `0x5DC`, `0x5E0`, `0x614`, `0x620`, `0x628`, `0x62C`) y
  comparar **campo por campo** contra el savestate del PCSX2.
- **Plan inmediato**: volcar en el recomp ese bloque (`gp+0x5C0`..`gp+0x640`) y
  los buffers que apuntan, y comparar 1:1 con el savestate — el A/B ya demostró
  que funciona para acotar diferencias.

### 2026-10-08 — **A/B de estado 1:1 del motor (diferencias concretas)**
- Volcado del bloque `gp+0x5C0..0x650` en el recomp, la **primera vez que
  `head != 0`** (post-init), comparado con los savestates:
  | campo | consola | recomp |
  |---|---|---|
  | `gp+0x5CC` | `0x01020000` | `0x00010000` |
  | `gp+0x5DC` | `0x70002000` | `0x70002000` ✓ |
  | `gp+0x5E0` | `0x00B1D3B0` | `0x00A9C0C0` |
  | `gp+0x5F8` (ptr ring) | **`0x00A96800`** | **`0x00A96680`** |
  | `gp+0x600/0x604` | `0x0007F400` / `1` | igual ✓ |
  | `gp+0x60C` | `0x30B88D00` | **`0`** |
  | `gp+0x638` head | **`0x00A96800`** | **`0x00A96680`** |
  | `gp+0x63C` tail | `0x00A9E0E8` | `0x00A96690` |
  | `gp+0x640` / `0x64C` | `0x100` / `0x00A28070` | igual ✓ |
- ⇒ El motor del recomp **apunta a un buffer desplazado** (`0xA96680`, −0x180 del
  real `0xA96800`) y le **faltan** `gp+0x5CC` (`0x01020000`) y `gp+0x60C`
  (`0x30B88D00`). Eso explica que el ring "real" (`0xA96800`) quede vacío: el
  motor **nunca escribe ahí**.
- **Próximo**: hallar de dónde salen `gp+0x5CC`/`0x60C` (¿valores leídos del
  disco/tabla?) y por qué el recomp los tiene en 0/otro — con eso el motor
  apuntaría al ring correcto y los comandos llegarían a `0xA96800`.

### 2026-10-08 — Escritores de los campos del motor y cálculo del ring ptr
- **Escritores hallados (por offset de `gp`)**:
  - `gp+0x5F8` (**ring ptr**) ← **`0x6e66ec`** (dentro del reset `0x6e6640`).
  - `gp+0x60C` ← **`0x6e61b4`** (`sw`).
  - `gp+0x5CC` ← `0x6f09dc` / `0x6f09e0` (`sb`, en el **setup `0x6efd28`**).
  - `gp+0x638` (head) ← `0x6e4348`, `0x6e4564`, `0x6e4e0c`.
- **Cálculo del ring ptr** (`0x6e66c0..0x6e66ec`, dentro del reset del motor):
  ```
  0x6e66c0  lui  $v1, 0x00A9
  0x6e66c4  lw   $v0, 0x88C4($v1)     ; v0 = *(0xA988C4)  <-- puntero a función
  0x6e66c8  jalr $v0                  ; callback (OPCIONAL: en consola vale 0)
  0x6e66d8  addiu $v1,$s2,-0x800
  0x6e66e0  sll  $v0,$v0,2
  0x6e66e4  addiu $s0,$s0,0x800       ; base + 0x800
  0x6e66e8  subu $s2,$v1,$v0
  0x6e66ec  sw   $s0,0x5F8($gp)       ; ring ptr
  0x6e66f4  sb   $s0,0x604($gp)
  0x6e66fc  sw   $v0,0x648($gp)
  ```
- **A/B del puntero**: `0xA988C4` = **0 en la consola** (callback vacío, ambos
  slots) ⇒ no es la causa. Y `0xA96800` tiene los comandos en la consola;
  `0xA96680` (el buffer que usa el recomp) tiene `… 0000007f …` en la consola.
- ⇒ El recomp calcula una **base desplazada** (ring ptr `0xA96680` vs `0xA96800`,
  −0x180). Hay que mirar **más arriba** en `0x6e6640` de dónde salen `s0`/`s2`
  (la base del buffer) — ahí está la diferencia.—

### 2026-10-08 — **Base del motor: la clave del desplazamiento (−0x100)**
- Inicio del reset (`0x6e6640`): `ring ptr = align128(*(gp-0x7A28)) + 0x800`
  (`0x6e6694..0x6e66a8` alinea a 0x80; `0x6e66e4` suma 0x800).
- **La BASE `*(gp-0x7A28)` la devuelve una llamada indirecta `jalr *(0xA988C0)`**
  (`0x6e6678`, args `a0=0x1080`, `a1=0x00040411`) — una **función de asignación**.
- **A/B de la base (savestates)**:
  | campo | consola |
  |---|---|
  | `gp-0x7A28` (BASE) | `0x00A95FA0` |
  | `align128(BASE)+0x800` | `0x00A96780` |
  | `gp-0x7A34` (inicio) | `0x00A96000` |
  | `gp-0x7A2C` | `0x04000000` |
  | `0xA988C0` (fn) | `0x1000000F` (slot2) / `0` (slot1) |
- **Diferencia**: el recomp tiene ring ptr `0xA96680` ⇒ su `align128(BASE)` =
  `0xA95E80` vs **`0xA95F80`** de la consola ⇒ **la BASE está `0x100` más abajo**.
  El origen es la **función de asignación llamada por `jalr`** (`*(0xA988C0)`).
- **Próximo**: entender qué es/hace `*(0xA988C0)` (ptr `0x1000000F`) y por qué en el
  recomp la asignación devuelve `0x100` menos — ahí está la causa raíz del corrido.

### 2026-10-08 — **BLOQUEANTE NUEVO**: la base viene de un `jalr` a `0x1000000F`
- La BASE del motor (`*(gp-0x7A28)`) la devuelve `jalr *(0xA988C0)` (`0x6e6678`,
  args `a0=0x100080`, `a1=0x00040411`).
- **`*(0xA988C0)` = `0x1000000F`** en la consola (slot 2), `0` en slot 1. Esa
  dirección cae en la región **`0x10000000` = registros MMIO del EE**, NO en
  código ⇒ **saltar ahí no es ejecutable** de la forma esperada. Es un
  **trampoline/handle** de un mecanismo que no estamos replicando.
- **No se encuentra el escritor**: no existe ningún `sw`/`sd`/`sq` a `0xA988C0`
  con base `0xA9` en el ELF (el único hit, `0x73c8c0`, es `sw $a1,-0x7740($gp)`
  — base `gp`, falso positivo). ⇒ `0xA988C0` se puebla por una vía no hallada
  (¿`jalr`/tabla construida en runtime? ¿mecanismo del kernel/libs?).
- **Por qué es bloqueante**: sin entender ese mecanismo no puedo reproducir la
  asignación de la base (ni el offset `0x100`) — y toda la cadena del motor
  (ring → head/tail → handler) depende de eso.
- **Opciones**: (a) A/B con el **debugger de PCSX2** poniendo un breakpoint en
  `0x6e6678` y viendo quién/para qué se llama (y con qué devuelve); (b) buscar
  `0x1000000F` / la convención `0x10000000+` en el binario y en el código del
  recomp; (c) revisar si el runtime define trampolines ahí.

### 2026-10-08 — **Diff de RDRAM: el heap está corrido `+0x150` (pista fuerte)**
- El debugger de PCSX2 se queda en el entry (`0x4C0008`) ⇒ se descartó; se usó
  **A/B por RDRAM**.
- Herramienta nueva: **`game/rdram_diff.py`** (diff entre el dump del recomp y
  `eeMemory.bin` del savestate). El recomp volca 512 KB desde `0xA20000` con
  `SWORD_RDRAM_DUMP`.
- **Resultado**: `8.0 %` de words distintos (10479/131072), concentrados en el
  **heap** (`0xa94000..0xa9f000`). Y el patrón es **sistemático**:
  ```
  deltas (consola − recomp) en punteros del heap: { 336 (0x150): 9,
                                                     384 (0x180): 5,
                                                     416 (0x1A0): 1, ... }
  ```
  ⇒ **todos los punteros del heap están ~`0x150` más bajos en el recomp**.
- Otras diferencias relevantes: campos que en el recomp son **0** y en la consola
  son punteros (`0xA20248`: `0` vs `0x00E20DD0`; `0xA20A04`: `0` vs `0x00B83000`)
  ⇒ **asignaciones que en el recomp no ocurren**; y contadores distintos
  (`0xA206F4`: `2` vs `0x1DB`; `0xA20730`: `8` vs `0x28`).
- **Salvedad metodológica**: el dump del recomp es de una fase temprana
  (`primer head!=0`) y el savestate del **diálogo** ⇒ parte del ruido es de fase.
  Pero el corrimiento `+0x150` de los punteros es del **estado del allocator**.
- **Conclusión**: el allocator del juego (CRT/libc propio) **reparte ~0x150
  menos** en el recomp ⇒ el motor apunta a buffers corridos ⇒ el ring real queda
  vacío. Ahí está la causa raíz.
- **Próximo**: rastrear el **allocator del juego** (¿una cabecera/bloque de
  inicialización de ~0x150 que no se crea?) — o afinar el A/B con un dump en una
  fase más comparable.

### 2026-10-08 — Allocator del motor identificado (init / set-base / free)
- Escritores de la BASE (`gp-0x7A28`): `0x6e6684` (reset, camino del `jalr`),
  **`0x6e6ce8`** y **`0x6e6d2c`**. Desensamblados:
  - **`0x6e6d00` = "set-base"**: `sw $a2,-0x7A28($gp)` (guarda la base que le
    pasan, con alineación a 0x80 vía el bucle `andi $v0,$a2,0x7F`).
  - **`0x6e6cb8` = "free del motor"**: `jalr *(0xA988C4)` con `a0=BASE` y luego
    `BASE=0`, `cb=0`, `inicio=0`.
- **Callers**: `set-base` ← **`0x51f468`**; `free` ← `0x6f0bd4`; `reset` ←
  `0x6f0950`.
- **`0x51f450` = init del heap del juego** (región `0x51xxxx`):
  ```
  0x51f454  addiu a1,$0,0x400        ; align 0x400
  0x51f45c  daddu a2,$0,$0           ; base 0
  0x51f468  jal   0x6e6d00           ; set-base(0x100000, 0x400, 0)
  0x51f46c  lui   a0,0x0010          ; tamaño 1 MB
  0x51f480  sw    $0,-0x78FC($gp)
  0x51f488  sw    v1,0x14(a1)        ; tabla de punteros en 0xA42530
  ```
- **Dato del A/B**: `inicio` (`gp-0x7A34`) = `0xA96000` (consola) vs `0xA95E80`
  (recomp) ⇒ el **heap del juego arranca ~`0x180` más abajo** en el recomp.
- **Próximo**: instrumentar `set-base`/los `allocs` en el recomp (cargar el
  dump/A-B ya montado) para ver **dónde** se pierden los `0x150`.

### 2026-10-08 — El `jalr` es el allocator: devuelve `0x150` menos (con basura en el puntero)
- Instrumenté en el generado `0x6e6d00` (set-base) y `0x6e6684` (asignación de la
  base). Secuencia real en el recomp:
  ```
  [GEN] 6e6d00-setbase a2=00000000            ; set-base(0)  => BASE = 0
  [GEN] 6e6684-base=v0=00a95e50 gp=00a28070   ; BASE = 0xA95E50  (v0 del jalr)
  ```
  ⇒ **el `jalr *(0xA988C0)` SÍ se ejecuta** en el recomp y **devuelve la base**:
  `0xA95E50` (recomp) vs `0xA95FA0` (consola) ⇒ **`+0x150`**.
- **El init del heap** (`0x51f450`) se llama con **`a0=0`** (`0x512ab0..0x512ac8`)
  ⇒ sólo resetea (`set-base(0x100000,0x400,0)`).
- **Estado del puntero del allocator** (`0xA988C0`):
  | | recomp | consola slot1 | consola slot2 |
  |---|---|---|---|
  | `0xA988C0` | **`0x43400000`** | `0` | **`0x1000000F`** |
  | `0xA988C4` | `0x432E0000` | `0` | `0` |
  | `0xA988B8/BC` | **`0x55555555`** | `0` | `0` |
  ⇒ en el recomp esa zona tiene **basura** (`0x55555555`/`0x43400000`), no los
  punteros del juego. (`0x55555555` **no** lo pone el runtime: grep vacío.)
- **Pista del mecanismo**: en el savestate hay **muchas** entradas con valores
  `0x10000000..0x1000004C` (`0xA938xx`, `0xA8D1xx`, …) ⇒ el juego usa una
  **tabla de "handles" en la región `0x10000000+`** (que en el EE es MMIO) como
  punteros a funciones/servicios. Es el mecanismo que **no estamos replicando**.
- **Conclusión**: el gate es la **instalación/uso de esa tabla `0x10000000+`**
  (los punteros de alloc/free del motor salen de ahí y en el recomp están sin
  inicializar/basura) ⇒ la asignación devuelve `0x150` menos ⇒ sin frames.

### 2026-10-08 — Búsqueda en el ELF del mecanismo `0x100000xx` (no concluyente)
- Escaneo del ELF por construcciones `0x10000000+` (`lui 0x1000`+`ori/addiu`): 52
  sitios (p.ej. `0x6e61e4` → `0x10000040`, `0x6e525c` → `0x10000017`).
- Los valores `0x100000xx` aparecen **muchísimo** en el ELF (`0x10000002`×2123,
  `0x10000008`×1563, `0x1000000F`×330…). **PERO** al mirar el contexto
  (`0x4c03d4`) se ve que son **instrucciones**, no datos: `0x10000004` = `beq
  $0,$0,+4` (op=4), en medio de `sw` y un `jal` ⇒ **falso positivo**.
- Por lo tanto: **la "tabla de handles en el ELF" NO existe** como tal. Los
  valores `0x100000xx` que sí son datos están en el **savestate** (en `0xA938xx`,
  `0xA8D1xx`, escritos por el juego en runtime) — no en el binario.
- **Lo que queda firme** (evidencia dura):
  1. **`jalr *(0xA988C0)`** es el allocator del motor; devuelve `0xA95E50` en el
     recomp vs `0xA95FA0` en consola ⇒ **`+0x150`**.
  2. `0xA988C0` en el recomp = **`0x43400000`** (+vecinas `0x55555555`); en la
     consola = `0`/`0x1000000F` ⇒ **la zona está sin inicializar/basura**.
- **Próximo**: (a) averiguar **qué escribe `0xA988C0`** con el valor correcto
  (¿un `jalr`/tabla construida en runtime? ¿copia de stub?); (b) A/B del bloque
  `0xA988B8..0xA988C8` en varias fases; (c) revisar si el runtime deja esa zona
  con `0x55555555` (patrón) — aunque el grep no lo encontró en el código.

### 2026-10-08 — Descartado: la RDRAM del recomp arranca en **0** (no un patrón)
- `ps2_memory.cpp:340`: `std::memset(m_rdram, 0, ramSize)` ⇒ la RDRAM del recomp
  arranca en **cero, igual que PCSX2**. ⇒ el **`0x55555555`** de `0xA988B8/BC`
  **no** es un patrón de relleno del runtime (grep en `tools/PS2Recomp` sin
  coincidencias fuera de tests) — **lo escribe el juego/copia**, y por el
  corrimiento `+0x150` cae en otro lado que en la consola.
- **Estado consolidado del bloqueo** (lo único firme):
  1. El **heap/allocator del motor** reparte `~0x150` menos en el recomp.
  2. El puntero del allocator (`0xA988C0`) está **sin inicializar** en el recomp.
  3. La RDRAM arranca en 0 en ambos ⇒ no es un problema de inicialización global.
- **Siguiente vía (requiere datos que no tengo sin vos)**: A/B del bloque
  `0xA988B0..0xA988D0` **en la misma fase** (el recomp no llega al diálogo, así que
  parte del ruido es de fase) o un breakpoint en `0x6e6678`/`0x51f468` en PCSX2.
- **Nota de mantenimiento**: quedan **4 triages activos** para limpiar al cerrar:
  `[motor]`+`SWORD_RDRAM_DUMP`, `cb-install`/`SWORD_CB_PRODUCER`, `[cdread-data]`,
  y los `fprintf` `[GEN]`/`[triage-*]` del generado.

### 2026-10-08 — Búsqueda agotada (ELF + runtime + generado)
- El **generado** (2.1 GB) **tampoco** contiene `0x55555555` (grep con `-l`/`-c`
  sin coincidencias) ⇒ ese valor lo **escribe el juego en runtime** (y por el
  corrimiento `+0x150` cae en otro offset que en la consola).
- **Búsqueda cerrada**: el mecanismo detrás de `0xA988C0`/el corrimiento **no se
  resuelve más por análisis estático** — hace falta un breakpoint (PCSX2) o un
  A/B en **fase idéntica** (que hoy no es posible porque el recomp no llega al
  diálogo).
- **Todo commiteado y pusheado** (ver `git log`); artifacts al día
  (`design.md` §10, `tasks.md` Fase 4.8, `decisions.md`).

### 2026-10-08 — **A/B fase por fase (8 savestates) + el motor FUNCIONA**
- Savestates del arranque completo (gracias al usuario): 1=negro, 2=formato,
  3=conf60, 4=idioma, 5=konami, 6=press-start, 7=newgame, 8=menú.
- **Evolución en la consola**: slot 1 (negro) tiene **todo en 0** (motor sin
  inicializar); en el **slot 2** (formato) la **base pasa a `0xA95FA0`** y el
  **ring `0xA96800` ya tiene 1773 comandos** ⇒ **la ventana de divergencia es el
  init del motor (slot 1→2)**.
- **Descartado**: `alloc` (`0xA988C0`) **también tiene "basura" en la consola**
  (`0x3F009A34`, `0x43C00000`, …) en las fases 3-7 ⇒ el `0x43400000` del recomp
  **no es una anomalía**; el bloqueante anterior queda **anulado**.
- **🎯 EL MOTOR FUNCIONA**: comparando buffers,
  ```
  0xA96680 recomp : 00001101 00a96700 | 00000041 00a8d0b0   <- comandos validos
  0xA96800 consola: 00001101 00a96880 | 00000041 00a8d0b0   <- idem
  ```
  ⇒ el recomp **genera exactamente la misma estructura de comandos**, sólo que
  apuntando al buffer **corrido `0x180`**. Los dos buffers tienen ~170 comandos.
- **Conclusión**: el motor está **vivo y correcto**; el único problema es el
  **offset del heap (~0x150/0x180)** ⇒ el render no aparece porque el motor
  trabaja sobre buffers corridos.
- **Próximo (directo al fix)**: encontrar por qué el **heap del juego** arranca
  `~0x180` más abajo (`inicio` = `0xA96000` consola vs `0xA95E80` recomp) — el
  `SetupHeap`/`sbrk` o el primer `alloc`. Con eso, el motor apuntaría al ring real
  y debería aparecer imagen.

### 2026-10-08 — Atajo `SWORD_HEAP_PAD` sin efecto (el buffer no viene del kernel)
- Se agregó `SWORD_HEAP_PAD=N` en `SetupHeap` (syscall 0x3D) para desplazar el
  heap base y compensar el `0x180`. Corrida con `SWORD_HEAP_PAD=0x180`:
  **sin cambios** — `gp+0x5F8` sigue en `0xA96680`.
- ⇒ **el buffer del motor no sale del heap del kernel** (`SetupHeap`); lo asigna
  su propio allocator (`0x51f450` + el `jalr`), así que el pad no lo toca.
- **Estado del fix**: el motor está **vivo y correcto** (genera comandos
  idénticos), sólo desplazado `0x180`. El desplazamiento nace en el **allocator
  del juego** (`jalr *(0xA988C0)` devuelve `0xA95E50` vs `0xA95FA0`).
- **Próximo concreto**: ver **cómo `0x51f450` obtiene su buffer** (¿`sbrk`?
  ¿`malloc` interno?) y por qué sale `0x180` más abajo — o compensar en el punto
  donde el motor guarda su base (`0x6e6684`/`set-base`), que sí está localizado.
- **Atajo quedó detrás de env** (`SWORD_HEAP_PAD`, OFF por defecto ⇒ inocuo).

### 2026-10-08 — `SWORD_MOTOR_PAD` alinea el ring con la consola (pero sin imagen aún)
- Atajo en el generado: en `0x6e66dc` (el `sw $s0, inicio`) sumar `0x180` a `s0`
  cuando `SWORD_MOTOR_PAD=1`. (El de `0x6e6684`, la base, quedó como
  `SWORD_MOTOR_PAD_V0` porque compensar **ambos** daba `+0x300`.)
- **Resultado** — el motor ahora apunta **al ring de la consola**:
  ```
  recomp (pad): ring=0xA96800 head=0xA96800 tail=0xA96810
  consola slot2: ring=0xA96800 head=0xB15C00 tail=0xB15C30
  ```
  ⇒ ring/head/tail **coinciden en el rango correcto** (antes `0xA96680`).
- **PERO** `gif=2`, `gsw=0`, `vramNonZero` sin cambio (0/262144) ⇒ **sin imagen
  todavía**: alinear el offset **no era suficiente**. El motor apunta al ring real
  pero el render sigue sin emitirse.
- **Conclusión**: el corrimiento `0x180` **era real y se corrige con el pad**, pero
  hay **al menos un problema adicional** (el motor en el recomp, aun con el ring
  correcto, no emite GIF).
- **Nota**: el pad vive en el **generado** (se pierde al regenerar) y está detrás
  de env (`SWORD_MOTOR_PAD`), anotado como triage.
- **Próximo**: con el ring ya alineado, comparar `[dmairq]`/los comandos del ring
  contra la consola para ver **qué falta** en la cadena hasta el GIF.

### 2026-10-08 — Con `SWORD_MOTOR_PAD` el ring coincide (primer comando idéntico)
- Diff del ring con el pad activo vs savestate del menú (slot 8):
  ```
  0xA96800: recomp=00001101 00A96880   consola=00001101 00A96880   <- IDENTICO
  0xA96808: recomp=00000041 00A8D0B0   consola=00001042 00BA1D18   (otra fase)
  comandos en ring: recomp=347  consola=330
  ```
  ⇒ **el motor alineado genera los comandos correctos** (mismo `0x1101` + self
  pointer `0xA96880`).
- **Pero** `gif=2` sigue ⇒ el ring se llena pero **no se traduce en GIF/render**.
  Hipótesis nueva: los comandos del ring son de **transferencia DMA** (tags
  `0x1101`/`0x41`/`0x1042`), no de *draw*; el camino al XGKICK/GS debe estar en
  otro lado (o el handler procesa pero no llega a emitir).
- **Estado**: motor alineado y correcto; falta el eslabón ring → GIF.

### 2026-10-08 — Traza de la cadena del ring: falta el kick GIF
- Instrumentados en un solo build: `spin`(0x6e4d98), `cons1101`(0x6e58d0),
  `kick-vif1`(0x6e433c), `kick2`(0x6e4468), `kick-gif`(0x6e47e4).
- Resultado (con `SWORD_MOTOR_PAD=1`):
  `cons1101 ✓`, `spin ✓`, `kick2(4468) ✓` — pero **`kick-vif1(433c)=0` y
  `kick-gif(47e4)=0`** ⇒ **el recomp NUNCA hace el DMA del framebuffer al GIF**.
  Eso explica `gif=2` (los 2 del arranque).
- **El motor está alineado**: con el pad, `[dmairq]` muestra los **mismos
  buffers que la consola** (`head=0xB15C00 tail=0xB15C10`, y `0xA96800`).
- **Atajos probados sin efecto** sobre `kick-gif`: `SWORD_FORCE_F5CF=1` y
  `SWORD_FORCE_3C0=0x104` (la condición `*(v0+0x3C0)!=0` del tramo) ⇒ **hay otra
  rama** que evita el tramo `0x6e47c0..0x6e47f8` del handler.
- **Próximo**: instrumentar el tramo `0x6e4494..0x6e47c0` del handler para ver
  **dónde** se desvía antes del kick GIF (ese es el último eslabón al primer
  frame con contenido).

### 2026-10-08 — Corrección: el kick GIF NO es el camino (recomp y consola iguales)
- Traza del handler: el flujo **sí pasa los 3 checks** (`PASS-checks` ✓) y **llega
  al tramo `0x6e47c0`** (`tramo-GIF` ✓) — pero en `0x6e47d0` hace
  `beq $v1,$0 -> 0x6e4814` con **`v1 = 0`** ⇒ salta el kick.
- **El valor**: `v0 = *(gp+0x64C)`, y `v1 = *(v0+0x3C0)`. En la **consola**, en
  **todas** las fases (2..8): `*(gp+0x64C) = 0x00A28070` (gp) y
  `*(gp+0x3C0) = 0` ⇒ **la consola también salta el kick GIF**.
- ⇒ **el recomp y la consola se comportan IGUAL** en ese tramo: **el kick GIF NO
  es el camino del render**. Hipótesis anterior **descartada**.
- **Nota**: mi atajo `SWORD_FORCE_3C0` apuntaba a `gp+0x3C0` (y además el recomp
  tenía `*(gp+0x64C) = 0xA8D0B4`, no `gp`) ⇒ quedó mal dirigido (y de todos modos
  la consola no lo usa).
- **Próximo**: el render debe llegar por **otra ruta** (¿el XGKICK de VU1 que ya
  vimos? ¿otro DMA?). Revisar `[dma:start]`/canales con el pad activo y comparar
  con el esperado; o trazar el camino que **sí** produce los `[gs:kick]`.

### 2026-10-08 — Plan aprobado: "llegar a imagen visible" (anclado a los artifacts)
- **Evaluación honesta**: comprensión del bloqueo **~90%** (cadena del motor de DMA
  trazada de punta a punta y gate localizado por eslabón); **imagen visible 0%**;
  **5 atajos** activos que no son fixes (`SWORD_MOTOR_PAD`, `SWORD_HEAP_PAD`,
  `SWORD_FORCE_3C0`, `SWORD_CB_PRODUCER`, `SWORD_RDRAM_DUMP`).
- **Plan** (aprobado): `~/.commandcode/plans/llegar-al-menu-visual.md` ⇒ volcado a
  **`tasks.md` → Fase 4.9** (4.9.1 acelerar ciclo, 4.9.2 ruta real del render,
  4.9.3 fix del `+0x180`, 4.9.4 A/B del GS/VRAM, 4.9.5 limpieza).
- **Seguimiento por artifacts**: cada hallazgo ⇒ entrada acá; cada avance ⇒ checkbox
  en `tasks.md`; diseño confirmado ⇒ `design.md` §11; cada cambio ⇒ commit + push.

### 2026-10-08 — La consola renderiza en los bloques 2/3 de VRAM (FBP 0x100/0x180)
- Leído `GS.bin` del savestate (VRAM 4 MB + 509 B): contenido por bloque de 1 MB:
  ```
  bloque 0 (0x000000):    55 px
  bloque 1 (0x100000):     0 px
  bloque 2 (0x200000): 64670 px  (64498 con RGB)   <- render real
  bloque 3 (0x300000): 31773 px  (31733 con RGB)
  ```
- El **recomp** presenta desde **FBP=128 (0x80 → offset 0x100000 = bloque 1)**, que
  en la consola está **vacío**, y sólo tiene el **clear alpha** (`rgbNZ=0`).
- ⇒ **El framebuffer de render de la consola es `0x100`/`0x180`** (bloques 2/3),
  distinto del que hoy usa el recomp (`0x80`). **Hipótesis fuerte**: el `dispfb`/
  `fbp` del recomp está corrido (igual que el motor con el `+0x180`), así que el
  *present* lee un buffer vacío mientras el render escribe en otro.
- Generadas `/tmp/opencode/vram_consola_b{2,3}.png` (volcado lineal de la VRAM de
  la consola) — **para inspección visual del render real**.
- **Próximo**: volcar la **VRAM del recomp** (con `SWORD_MOTOR_PAD=1`) y comparar
  bloque por bloque contra estos números ⇒ confirmar en qué FBP renderiza.

### 2026-10-08 — 4.9.4: el recomp no tiene NINGÚN píxel con RGB en VRAM
- Instrumentado un conteo por bloque de VRAM en el recomp (`[gsblk]`, en el drain
  de DMAC): **`b0=0 b1=0 b2=0 b3=0`** ⇒ **cero píxeles con RGB en toda la VRAM**.
- Referencia (savestate, consola): `b2=64670`, `b3=31773` (**96k px con RGB**).
- ⇒ El recomp **no rasteriza contenido en ninguna parte** (sólo el clear alpha, como
  ya sabíamos). Y el VU1 hace **3 MSCAL/60 s** ⇒ **el juego no arranca su renderer**.
- **Esto reencuadra 4.9.2**: no es (sólo) que el present lea el FBP equivocado — es
  que **no hay nada dibujado**. La ruta a atacar es **por qué el juego no llega a
  renderizar** (VU1/XGKICK), no el `dispfb`.
- **Próximo**: trazar el **arranque del renderer** (los MSCAL/XGKICK) y compararlo
  con la consola (que renderiza desde ~10 s) — ¿qué condición debería dispararlos?

### 2026-10-08 — El VU1/XGKICK SÍ corre; el render sale a FBP 0x80 y con color 0
- Con `SWORD_MOTOR_PAD=1`, el VU1 **funciona y emite GIF**:
  ```
  [vu1:mscal] startPc=0x0 endPc=0x168 stopD=0 stopT=0  eePc=0x6e4468 eeRa=0x6e4ebc
  [gs:gif] idx=4 size=2576 nloop=3 nreg=3 ctx0fbp=128 ctx1fbp=128
  ```
  ⇒ el replay al problema **no es el VIF1/VU1/XGKICK** (están vivos).
- **Dos defectos concretos**:
  1. **`ctx0fbp=128`** ⇒ el juego dibuja a **FBP `0x80`**, mientras la **consola
     renderiza en `0x100`/`0x180`** ⇒ **el FBP está corrido** (mismo patrón que el
     `+0x180` del motor).
  2. La VRAM queda **sin RGB** ⇒ **el color de los vértices es 0** (el `RGBAQ=(0,0,0,0)`
     que ya habíamos visto) ⇒ aunque se rasteriza, no pinta nada.
- **En ELF**: no existe ningún `MSCAL` construido (`lui 0x1400`/literales, 0 hits) ⇒
  el microcódigo VU1 se arranca por otro camino (¿los paquetes del ring?).
- **Próximo**: (a) por qué el color es 0 (¿microcódigo VU1 incompleto / datos no
  cargados?), (b) corregir el FBP `0x80`→`0x100` (el *mismo* corrimiento a matar).

### 2026-10-08 — BLOQUEO: todo el pipeline VU1/GS funciona, pero el juego no dibuja
- **El microcódigo VU1 SÍ se carga**: `[MPG] #1 dest=0x0 bytes=376 first=102e07f0`
  (un único MPG de 376 B), y el VU1 lo ejecuta entero (`endPc=0x168`).
- Con esto **queda descartado el microcódigo** y, sumando lo anterior, **todo el
  pipeline está verificado sano**: VIF1 → VU1 → XGKICK → GIF → GS rasteriza.
- **El síntoma es aguas arriba**: el juego **no emite geometría con contenido**
  (color 0, pocos draws) ⇒ VRAM sin RGB ⇒ sin imagen. Es decir, **el juego no está
  renderizando frames**.
- **Por qué es bloqueo**: no queda nada de la cadena por descartar; lo que falta es
  **por qué el juego no llega a dibujar**. El análisis estático y los triages
  locales ya no lo responden.
- **Opciones para destrabar**:
  1. **Debugger de PCSX2 con el juego corriendo** (`Boot ISO (fast)` + abrir el
     debugger ya con el juego andando) para ver **qué hace el real** en el momento
     del render (qué función, qué estado).
  2. **A/B de estado en la MISMA fase** (hoy imposible: el recomp no llega al
     diálogo) — o comparar el `Screenshot.png`/`GS.bin` de fases tempranas.
  3. Revisar si el juego usa **otro camino de draw** (p.ej. un `sceGs...` del
     kernel) que el recomp esté stubeando como no-op.

### 2026-10-08 — Del savestate salen los pc del real: MISMO spin que el recomp
- El `.p2s` trae `PCSX2 Internal Structures.dat` con secciones (`cpuRegs`, `Cycles`,
  `EE-Subsystems`, `vuMicroRegs`, `VIF1dma`, `Gif Unit`, …) ⇒ **no hace falta el
  debugger**: los datos del real están todos en el savestate.
- Usando el **`gp` (0x00A28070) como firma** para ubicar los registros del EE, los
  `pc`/`ra` del hilo principal del real son, **en las 8 fases**:
  `0x6e4cdc`, **`0x6e4d98`** (¡el spin!), `0x6e4dbc`.
- ⇒ **El recomp está en la MISMA fase y el MISMO loop que el real** (el spin
  `0x6e4d98`, que ya conocíamos). La divergencia **no es "dónde está"** sino **qué
  produce ese loop** (refuerza el cuadro: color 0 / Datos).
- **Próximo**: A/B de **registros/estado** (no sólo el pc) entre el real (del blob)
  y el recomp, en la misma fase — para ver el campo exacto que difiere.

### 2026-10-08 — Registros del real extraídos del savestate (A/B directo posible)
- Alrededor del `gp` en `cpuRegs` (blob del slot 7 = newgame):
  ```
  gp = 0x00A28070
  sp = 0x01FFDBA0     <- NO es el 0x1FEE000 del CRT0 (es el sp vivo del hilo)
  pc = 0x006E4CDC     <- el spin
  ra = 0x007FE000     <- quien llama al spin
  ```
- ⇒ **Ya hay A/B de registros posible sin debugger**: loguear los GPR del recomp
  (en el drain) y comparar contra estos valores del real.
- El `ra = 0x7FE000` es nuevo y concreto: el spin del **real** se invoca desde ahí.

### 2026-10-08 — Análisis de registros del real (A/B): método y cuidado con los falsos positivos
- **Tabla (8 fases)**: el hilo principal del real está en **todas** las fases (2..8) en
  `pc=0x006E4CDC`, `ra=0x007FE000`, `sp=0x01FFDBA0`, `gp=0x00A28070` (slot 1 negro:
  `pc=0x004d3764`).
- **Cuidado (falso positivo)**: `0x6E4CDC` (real) y `0x6E4F08` (el `ra` del recomp son
  **el MISMO bloque duplicado**: ambos `jal 0x6e4848` (¡el handler/spin!) y siguen con
  `lw $v0,0x5ec($gp)`. ⇒ **no es divergencia de lógica**, es código duplicado en el
  binario. Y el `ra=0x7FE000` puede ser un falso positivo de la heurística de offset
  (por eso hace falta validarla).
- **Lo que SÍ es firme**: el pc del real (`0x6E4CDC`) llama a **`0x6e4848`** — o sea
  **el spin/handler `0x6e4d98` vive dentro de `0x6e4848`**.
- **Pendiente (análisis de arriba a abajo pedido por el usuario)**: validar el offset
  de registros en el blob; comparar **GPR por GPR**; y barrer el resto de artefactos
  (no sólo pc/ra/sp).

### 2026-10-08 — 🎯 La memoria del VU1 difiere (micro y data) — candidato al color 0
- Comparado el `.p2s` (real) contra el recomp:
  | | real (savestate) | recomp |
  |---|---|---|
  | `vu1MicroMem` | **2048 words (16 KB, llena)**; empieza `f303ff0187102200…` | **376 B**; empieza `102e07f0` |
  | `vu1Memory` (data) | **709 words con datos** | sin carga observada |
- ⇒ **el microcódigo del real es otro y mucho más grande**, y la **data del VU1**
  (donde viven vértices/colores) tiene **709 entradas** que el recomp **no carga**.
- **Hipótesis fuerte (y la mejor hasta ahora)**: sin data en el VU1, el XGKICK emite
  paquetes sin color/geometría real ⇒ **VRAM sin RGB** (encaja con el `RGBAQ=0`).
- **Próximo**: instrumentar el **UNPACK a VU1 data** en el VIF1 interpreter (¿el
  recomp lo hace?) y comparar el micro/data del real contra el recomp en la misma fase.

### 2026-10-08 — 🎯 El microcódigo VU1 del recomp es 1 MPG de 376 B; el real tiene 16 KB
- El recomp **SÍ hace UNPACK a `m_vu1Data`** (`[UNPACK] #2 vuAddr=0x0 bytes=3072
  vecs=192`) ⇒ **la geometría se carga** (corrige la hipótesis previa).
- **Pero** sólo se cargan **1 MPG (376 B)** de microcódigo y hay **3 MSCAL / 11
  UNPACK** en 35 s ⇒ el VU1 **no procesa** los 192 vectores (termina en 771 ciclos).
- **Real**: `vu1MicroMem` = **2048 words (16 KB)**, empieza `f303ff0187102200…`;
  el recomp empieza `102e07f0` ⇒ **microcódigo incompleto y/o distinto**.
- **Hipótesis (la más fuerte hasta ahora)**: el recomp **no carga el microcódigo VU1
  completo** (1 MPG de 376 B vs 16 KB) ⇒ el VU1 no rasteriza la geometría ⇒ **VRAM
  sin RGB**. Posible causa: **corrimiento** (`+0x180`) ⇒ el juego lee el microcódigo
  de la dirección equivocada, o el DMA/VIF1 se corta tras el 1er MPG.
- **Próximo**: ver **por qué** sólo llega 1 MPG (¿DMA a VIF1 truncado? ¿dirección
  corrida?) y comparar el microcódigo del real (`f303ff01…`) contra el que carga el
  recomp (`102e07f0`).

### 2026-10-08 — 🎯🎯 El microcódigo VU1 que carga el recomp NO es el del juego
- Comparación contra el ELF:
  | bytes | apariciones en el ELF |
  |---|---|
  | `0x102E07F0` (1er word que carga el recomp) | 2 |
  | `f303ff0187102200` (≥8 B del micro del **real**) | **30** ⇒ **es un microcódigo del juego** |
- ⇒ El recomp **carga un microcódigo que no es el del juego**, y como el micro se
  envía por **VIF1 desde un buffer del juego**, significa que **el recomp lee el
  buffer del micro desde la dirección equivocada** ⇒ **el corrimiento (`+0x180`)**.
- **Todo converge al corrimiento**: el mismo desplazamiento que mueve el heap y el
  motor hace que **el microcódigo VU1 salga mal** ⇒ VU1 no procesa la geometría ⇒
  **VRAM sin RGB**.
- **Consecuencia para el fix**: no alcanza con `SWORD_MOTOR_PAD` (alinea el motor
  *tarde*); hay que **corregir el corrimiento en origen** (la asignación del heap/el
  primer `alloc`), que es la **Fase 4.9.3**.

### 2026-10-08 — El pad es necesario pero insuficiente (el micro sale de otro buffer)
- A/B sin/con `SWORD_MOTOR_PAD`:
  ```
  SIN pad : 0 MPG, 0 mscal   <- el VU1 nunca se arranca
  CON pad : 1 MPG (376 B), 3 mscal, 11 UNPACK
  ```
- ⇒ **el pad es imprescindible** (sin él el motor no arranca el VU1) pero **corrige
  sólo una parte**: el **microcódigo sigue viniendo de un buffer corrido** (empieza
  `102e07f0` en vez de `f303ff01…`).
- ⇒ **hay más de un puntero afectado por el corrimiento**: el pad arregla `s0`
  (inicio/ring) pero **no los buffers internos del motor** (`gp+0x5E0`, `0x608`,
  `0x610`, `0x614`, …), de donde sale el micro/la geometría.
- **Consecuencia**: el fix completo es (a) **corregir el corrimiento en origen**, o
  (b) compensar **todos** los punteros del motor, no sólo `s0`.

### 2026-10-08 — Fix (b) no alcanza; (a) apunta a `0x6e58b8` (el "handle" 0x1000000F)
- **Fix (b)** (`SWORD_FIX_SHIFT`: compensar `+0x180` los buffers del motor en
  `0x6e5cf0`): **sin efecto** — el micro sigue `102e07f0` y `gif=2`. ⇒ el buffer del
  micro **no** sale por ahí.
- **(a)**: el valor `0x1000000F` (el que la consola escribe en `0xA988C0`) se
  construye en **4 sitios** (`0x70deb0`, `0x711a5c`, `0x71ad84`, `0x75c7a0`), y los
  tres primeros tienen la misma forma:
  ```
  jal 0x6e58b8            <- funcion del MOTOR (0x6e5xxx)
  lui $v1,0x1000 ; ori $v1,$v1,0xF    ; v1 = 0x1000000F  (el "handle")
  lw  $v0,0x5C0($gp) ; addiu ; sw $v0,0x5C0($gp)  ; avanza la cola interna
  ```
  ⇒ **`0x6e58b8` es la funcion clave** que precede al "handle" `0x1000000F`.
- **Próximo (a)**: desensamblar `0x6e58b8` (y su relación con `0xA988C0`) para
  encontrar la **primera asignación** y por qué reparte `0x180` menos.

### 2026-10-08 — (a): `SetSyscall` existe pero el escritor de `0xA988C0` no aparece
- El runtime **sí implementa `SetSyscall`** (`System.cpp:462`) y escribe la tabla de
  syscall handlers en **`0x80011F80 + n*4`** (no en `0x100000xx`).
- **No existe ningún `sw` literal a `0xA988C0`** en el ELF (sólo el falso positivo
  `0x73c8c0` con base `gp`). ⇒ el puntero se puebla con un **store calculado** (base
  en registro) o **desde el kernel**.
- **Estado**: el mecanismo de `0x1000000F` (los "handles") **no es el syscall-handler
  table** (esa está en `0x80011F80`); probablemente es el **mecanismo de
  `SetSyscallHandler` del EE (exception handler)** al ejecutar en región MMIO.
- **Queda para retomar**: buscar el `sw` calculado (o instrumentar el recomp para
  loguear **quién escribe `0xA988C0`**, con watchpoint en el runtime).

### 2026-10-08 — Watchpoint de `0xA988C0`: acota el escritor a la zona del motor
- Watchpoint en el runtime (detecta cambios de `*(0xA988C0)` en el drain):
  ```
  [wp-A988C0] #1 v=0x0         pc=0x4d0818
  [wp-A988C0] #2 v=0x43400000  pc=0x6e59e4   <- cambia entre n=1 y n=5
  ```
- **Cuidado**: el `pc` que loguea es **el del momento del drain**, no el de la
  escritura (misma limitación que antes) ⇒ `0x6e59e4` NO es necesariamente el
  escritor (de hecho, `0x6e59e4` es `sw $a0,0x1000D000` = SPR_FROM).
- Aun así, **acota la ventana**: `0xA988C0` pasa de `0` a **`0x43400000`** dentro de
  la zona del motor (`0x6e5xxx`), que es donde vive el "handle".
- **Real**: `0x1000000F`; **recomp**: `0x43400000` ⇒ **el juego calcula ese valor
  distinto** (o no lo calcula y queda basura).
- **Próximo**: capturar el **pc exacto** del store ⇒ requiere interceptar el
  **fast-write** (el macro del generado; recompila todo, costoso) o barrer la
  **zona `0x6e5900..0x6e5d00`** en busca del `sw` calculado a `0xA988C0`.

### 2026-10-08 — Corrección: `0xA988C0/C4` NO son punteros (son handles/floats) — cae el hilo del jalr
- Barrido de `0x6e5900..0x6e5d00` + los 4 sitios del "handle": el `0x1000000F` se
  guarda en **`gp+0x668`** (`sw $v1,0x668($gp)` en `0x70df10`/`0x711ab8`/`0x75c800`).
  **y `gp+0x668` = `1` en real y recomp** (coincide ✓).
- **A/B de `0xA988C0`/`C4`** (real vs recomp):
  ```
  real:   slot1=0, slot2=0, slot3=0x3F009A34, slot4=0x3F004000,
          slot5=0x43C00000, slot6=0x3F600000, slot7=0x45000000, slot8=0x1000000F
  recomp: 0x43400000 / 0x432E0000
  ```
  Son **magnitudes tipo float/ID** (`0x3F800000`=1.0f, `0x43C00000`=384.0f, `0x45000000`=2048.0f)
  ⇒ **no son punteros a función**; y en las fases tempranas del **real valen `0`** ⇒ el
  `jalr *(0xA988C4)` va a **0** y **el kernel lo intercepta** (handler de syscall/excepción).
- ⇒ **el hilo "el jalr del allocator va a basura" es un FALSO PROBLEMA** (el jalr no es
  un allocator): ese `0x6e6640` no asigna memoria. **Corregido.**
- **Lo que queda firme del corrimiento**: la BASE `0xA95FA0` (consola) vs `0xA95E50`
  (recomp) y el **microcódigo VU1** equivocado — esas dos sí son divergencias reales.
