# Design: Recompilación nativa de Sword of Etheria (PS2) para PC

## Approach

Seguimos el flujo oficial de PS2Recomp (módulos `ps2xAnalyzer` → `ps2xRecomp` →
`ps2xRuntime` + `ps2xIOP`), adaptado a un usuario sin experiencia en Windows. El
trabajo se organiza en 5 fases secuenciales, cada una con un criterio de salida
verificable antes de avanzar:

1. **Entorno (fase 0)**: instalar Git, CMake 3.20+, Visual Studio (MSVC C++20) y
   verificar versiones desde terminal. Ghidra se instala en esta fase porque el
   flujo recomendado de análisis depende de él, pero su uso intensivo llega en
   fase 2.
2. **Extracción (fase 1)**: obtener el ELF ejecutable (`SLUS/SLES/SLPM_*.XX`,
   típicamente en la raíz del ISO) desde
   `Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso` con una herramienta de
   extracción (p. ej. 7-Zip) hacia `work/elf/` — directorio de trabajo local que
   **nunca se versiona** (ver `.gitignore` en tasks).
3. **Análisis y configuración (fase 2)**: vía principal = abrir el ELF en
   Ghidra, ejecutar `ps2xRecomp/tools/ghidra/ExportPS2Functions.java` y obtener
   el TOML + CSV de funciones. Vía alternativa (rápida, solo si el ELF conserva
   símbolos): `./ps2_analyzer juego.elf config.toml`. El resultado es
   `config.toml` versionado en este change, con `general.input` apuntando al ELF
   local y `general.output` al directorio de C++ generado.
4. **Recompilación y build (fase 3)**: clonar PS2Recomp con submódulos
   (`git clone --recurse-submodules`), compilarlo con CMake, correr
   `./ps2_recomp config.toml` y compilar el C++ generado enlazado con
   `ps2xRuntime` hasta obtener el `.exe`.
5. **Iteración (fase 4)**: ciclo recomendado por PS2Recomp — arrancar con config
   mínima sin skips agresivos, corregir bloqueantes (`function not found`,
   syscalls TODO, stubs críticos de IO), usar handlers temporales
   (`ret0`/`ret1`/`reta0`) solo para clasificar importancia, promover fixes
   reales y mover hacks por juego a módulos de game override
   (`PS2_REGISTER_GAME_OVERRIDE`, clave por metadata del ELF). Re-testear desde
   arranque en frío tras cada tanda.

Si la vía Ghidra se vuelve un bloqueo, se degrada a la vía `ps2xAnalyzer` y se
compensa con bindings manuales `handler@0xADDRESS` en `general.stubs` (válidos
solo para este build concreto del juego; no son portables entre regiones).

**Estrategia de Ejecución Asíncrona**: Para optimizar el uso de cuota de la IA y minimizar bloqueos:
- Las tareas pesadas (como `cmake --build` o la generación de código con `ps2_recomp`) se enviarán a segundo plano.
- El agente configurará un temporizador periódico o de 6 horas (`/schedule`) para despertarse automáticamente, revisar el estado de la tarea en background y continuar iterando si la cuota lo permite, evitando que el usuario tenga que reactivar manualmente el proceso.

**Gestión de memoria en el build (lección 2026-10-01)**:
- Ciertos `.cpp` generados por `ps2_recomp` (`FUN_004eb8d0_0x4eb8d0.cpp` y similares) no fueron cubiertos por el splitter original y consumen 5+ GB de RAM solos al compilar con GCC. El splitter debe aplicarse a **todos** los archivos >8 MB, sin excepción.
- Antes de cada build, verificar con `ps aux | grep cc1plus` que no haya workers zombies de builds anteriores. Matarlos con `kill -9 <PID>` antes de arrancar.
- Solo después de confirmar que ningún archivo supera ~8 MB se puede usar `-j$(nproc)`. Mientras haya monstruos, usar `-j1` es seguro pero muy lento; la solución real es el re-split.
- El generador **Ninja** se traba con globbing sobre los 18k archivos generados; usar siempre `-G "Unix Makefiles"` para este proyecto.

## Architecture

Layout de trabajo propuesto dentro del repo (solo config, scripts y docs se
versionan; el ISO, el ELF y el código/binarios generados, no):

```text
Sword of etheria recomp/
  Sword of Etheria, The (Europe) (...).iso   # copia del usuario (no tocar)
  tools/
    PS2Recomp/                               # clon externo --recurse-submodules (no tocar)
  work/                                      # TODO: ignorar vía .gitignore
    elf/                                     # ELF extraído del ISO
    generated/                               # C++ emitido por ps2x_recomp
    build/                                   # build del runtime + juego
  aspec/changes/recompile-sword-of-etheria/
    proposal.md
    design.md (este archivo)
    tasks.md
    config.toml                              # config versionada del juego
```

Roles de los módulos PS2Recomp en este flujo:

- `ps2xAnalyzer`: escanea ELF/funciones y escribe el TOML base (`stubs`, `skip`,
  patches de instrucciones). Solo para la vía alternativa.
- `ps2xRecomp`: lee TOML + ELF, decodifica R5900 (+ MMI/VU0 macro) y genera el C++.
- `ps2xRuntime`: memoria guest, tabla de dispatch, syscalls, stubs GS/VU/archivo;
  es contra lo que se enlaza el juego. Aquí viven también los game overrides.
- `ps2xIOP`: ejecuta módulos IRX originales con kernel IOP virtual y fallbacks HLE.

Contratos de configuración (`config.toml`): `general.input` (ELF),
`general.ghidra_output` (CSV de Ghidra), `general.output` (carpeta C++),
`general.single_file_output`, `general.low_memory_mode` y
`general.output_worker_threads` (para generaciones pesadas),
`general.patch_syscalls = false` (recomendado), `general.stubs` (incluye
`handler@0xADDRESS` y temporales `ret0/ret1/reta0`), `general.skip` y
`patches.instructions` (reemplazos crudos por dirección).

**Arquitectura del release (Fase 5)**:

El modelo de distribución es idéntico al de otros recompiladores legales (Ship of Harkinian, 2ship2harkinian, etc.): el repo distribuye solo código; el usuario aporta su propio ISO original.

```
Flujo del usuario final:
  1. Descarga el release de GitHub (Windows .zip o Linux .tar.gz)
  2. Coloca su ISO en la carpeta indicada
  3. Ejecuta: python build_release.py --iso "Sword of Etheria...iso"
  4. El script verifica MD5 del ISO (debe coincidir con el hash conocido)
  5. Extrae el ELF, compila con los artefactos del repo y genera el ejecutable
  6. Lanza el juego con: ./sword_etheria  (o sword_etheria.exe en Windows)
```

Componentes del release:
- `build_release.py` — script Python multiplataforma: verifica MD5 del ISO, extrae el ELF y compila el ejecutable final.
- `.github/workflows/release.yml` — GitHub Actions: al hacer push de un tag `v*.*.*` compila en `ubuntu-latest` y `windows-latest` y publica ambos como assets del release.
- `README.md` — instrucciones de uso con requisitos, MD5 esperado del ISO y pasos de build.

MD5 del ISO (`Sword of Etheria, The (Europe) (En,Fr,De,Es,It).iso`) se determina en Fase 5 con `md5sum` y se hardcodea en `build_release.py`.

## SPU2 mínima (Fase 4.6 — opción A, elegida 2026-10-04)

Estado verificado que motiva esta fase (smokes 25–120s, `tick` hasta 5520):

- Pipeline GS probado: triage negro→magenta, `vramNonZero=2093058/4194304`,
  ventana magenta confirmada por el usuario.
- Audio encadenado por HLE: `libsd:6` (2300+ polls) → `libsd:5/7` → `done`;
  hilo IOP deja de girar; `TYOSD rpc` 43→6 por corrida.
- Spin `0x6e4d98` sale con triage v2 (condición real: `0x638==0x63C` **y**
  byte `gp+0x630==0`) pero macro-gira: la cola nunca se drena.
- Anatomía de la cola (dump `[triage-buf]`, ver `game/tyosd-573-hle.md`):
  un solo comando de sonido de 16 B (`00001101 <ptr> <count 0x40/0x41> <ptr>`,
  familia `0x11xx`), `b = a+0x10`, `B` en ceros, callback `*(gp-0x7A30)==0`
  (consumidor jamás instalado), productor re-encola con retry.
- Auditoría del runtime: **sin emulación SPU2** (sin MMIO `0x1F8014xx` /
  `0x1F900xxx`; `ps2_audio.cpp` solo arma WAV para host). Accesos EE directos
  a registros SPU2 aún no auditados en el mapa de memoria del runtime
  (verificar riesgo de aliasing silencioso a RDRAM antes de codificar).

Plan mínimo (sin audio real; solo completar el init de sonido):

1. Auditar `Load/Store` EE para `0x1F8xxxxx`: loguear accesos SPU2 del juego
   y decidir stub (aceptar + estado plausible) vs alias (corregir mapa).
2. Modelo SPU2 mínimo: registros core/voice + `transfer-complete`, sin
   síntesis; el estado debe mostrar "done" para que SDRDRV complete.
3. Semántica real de `libsd:4/5/7/9/11/23` desde los exports de
   `work/elf/IOP/LIBSD.IRX` (reemplaza los `v0=1` de triage uno por uno).
4. Servir `SD.BIN` (683 MB en `work/elf/`) según el comando de 16 B una vez
   conocido su layout (destino guest + tamaño; hoy sin verificar).
5. Drenar la cola (`gif>2` sostenido, VRAM con escena sin `triage-vis`),
   revertir triages y cerrar hito con menú.

## Investigación comparada (2026-10-04, previa a codificar SPU2)

Regla de higiene (2026-10-04): cada fuente va etiquetada `[PS2]` o `[NO-PS2]`.
Lo `[NO-PS2]` solo aporta patrones abstractos; NUNCA detalles técnicos
(XMA≠VAG, RSP≠SPU2, XAudio≠libsd, mesg-queues≠SIF-RPC). El plan ejecutable
sale solo de fuentes `[PS2]`.

Fuentes `[PS2]`: OpenGOAL Jak (docs + PR #3804, IOP/OVERLORD), ps2sdk
(`spu2regs.h`, FREESD, sdrdrv), PCSX2 (`SPU2/spu2sys.cpp`, `regs.h`),
Parappa2 (`wavep2`/`tapctrl`, solo arquitectura — es decomp, no runtime),
PS2Tek (mapa IO).
Fuentes `[NO-PS2]` (solo patrón): UnleashedRecomp Xbox 360 (`apu/`),
Zelda64Recomp N64 (`RECOMP_PATCH` + API bridge), lista
awesome-game-decompilations (metas; PS2 casi ausente).

Ideas aplicables, en orden de coste:

1. **[PS2] Completitud síncrona (OpenGOAL PR #3804)**: correr el handler de
   interrupción DMA "inmediatamente", para que desde el juego siempre haya
   otro buffer SPU disponible y el grueso del código de streaming nunca tenga
   que correr. Equivalente nuestro: el auto-complete DMA ya existe en
   `IopMemory::writeHardware32`; falta que el DMA **arranque** (cero
   arranques observados) o que su IRQ llegue al waiter.
2. **[NO-PS2: patrón] HLE a nivel frame (UnleashedRecomp `apu/`)**: la única
   idea que se importa es "decodificar con libs existentes y entregar frames".
   Nada de XMA/FFmpeg/XAudio aplica aquí. Equivalente nuestro (ya PS2): el
   runtime YA tiene `ps2_audio_vag.cpp` (decode VAG→PCM) +
   `PS2AudioBackend::play`; solo falta alimentar `SD.BIN` → decode → `play`
   (hoy nadie llama a esa cadena).
3. **[NO-PS2: patrón] Parche mínimo no invasivo (Zelda64Recomp)**: solo valida
   el patrón `game_overrides.cpp` + `game/patches/` (no reescribir sistemas).
   Nada de RSP/mesg-queues/ultramodern aplica a PS2.
4. **[PS2] Mapa SPU2 exacto (ps2sdk `spu2regs.h`)**: base IOP `0xBF900000`
   (física `0x1F900000`), cores a `0x400`; `ENDX` en `0x340+core*0x400`,
   `STATX` en `0x344+core*0x400`; DMA `0xBF8010C0+ch*1088`, start bit 24.
   Nuestras direcciones observadas calzan (`0x1F900004` voces,
   `0x1F900344` status, `0x1F9007C0/7C8` SPDIF).
5. **[PS2] Valores de boot HW ("PS2 confirmed", PCSX2 `spu2sys.cpp`)**:
   `ENDX=0xFFFFFF` y `STATX=0x80` por core al arrancar. Nuestro stub
   devolvía 0 en todo → las voces "nunca terminan". Fix inmediato:
   pre-poblar esos 4 registros en `IopMemory::reset()` (hecho 2026-10-04;
   verificar en smoke si LIBSD avanza; si el init los pone a cero y espera
   al HW, endurecer a lectura-siempre-`0xFFFFFF` estilo PCSX2).
6. **[PS2] FREESD (ps2sdk, driver compatible con LIBSD + fuente)**: si algún
   ordinal `libsd` necesita semántica exacta, su fuente es la referencia
   (antes que adivinar valores de retorno). Verificado contra esto el mapa
   de ordinales (`5=SetParam`, `6=GetParam`, `7=SetSwitch`, …).
7. **[PS2, solo arquitectura] Parappa2 (`wavep2` streaming + `tapctrl`
   voces)**: confirma el split en dos módulos (feeder + voces), igual que
   CDVDSTM vs SDRDRV/LIBSD aquí. Al ser decomp (código C equivalente, no
   runtime HLE), no aporta patrón ejecutable: el atasco vive del lado
   feeder/dato, no del consumidor EE.

### 8. Arquitectura de Suspensión y Preemption en Syscalls (`EeScheduler`) (2026-10-07)

- **Problema de excepción C++ vs context.pc**: Los stubs recompiled de syscalls en `ps2_runtime` (`FUN_004d31c0` SleepThread, `FUN_004d31d0` WakeupThread, `FUN_004d32a0` WaitSema, etc.) ejecutan `handleSyscall()` y posteriormente asignan `ctx->pc = jumpTarget;` ($ra). Si el syscall invoca `blockCurrent()` o `transferIfRequested()`, se lanza la excepción `EeDispatcherTransfer{}` para ceder el control al loop del scheduler (`step()`).
- **Consecuencia previa**: El desenrollado de la pila de C++ abortaba la función recompiled antes de que pudiera asignar `ctx->pc = $ra`. El contexto guardado del hilo retenía el PC del cuerpo del syscall (`0x4d31c0` / `0x4d31d0`). Al reactivarse, el scheduler reanudaba ejecutando nuevamente el syscall desde el inicio, causando un bloqueo infinito de re-invocación.
- **Regla arquitectónica**: En `blockCurrent()` y `transferIfRequested()`, si el registro de retorno `$ra` (`getRegU32(&self->activeContext(), 31)`) es distinto de cero, debe asignarse inmediatamente `self->activeContext().pc = ra`. Esto emula con precisión la semántica de hardware de la CPU MIPS R5900, donde cualquier hilo suspendido en un syscall reanuda en su dirección de retorno `$ra`.

### 9. Desbloqueo del Render Loop y Presentación (2026-10-07)

- Al reanudarse correctamente Thread 1 y Thread 3, se desbloqueó el despacho SIF RPC (`sceSifCheckStatRpc` / `0x628950` / `0x628980`).
- Thread 1 alcanzó el bucle principal de renderizado (`0x6d6a6c`), logrando la activación del **Double Buffering Flip a 60 FPS** (`dispfb1` alternando dinámicamente entre `0x1000` y `0x1080`).
- Por primera vez se escribió contenido gráfico en la memoria de video de GS: **`vramNonZero = 262144 / 4194304` (256 KB)**, con resolución configurada por el motor a 512x512.

### 10.1 Análisis de arriba a abajo (datos del savestate vs recomp) — 2026-10-08

> Pedido del usuario: recorrer **todo** lo que tenemos sin dejar nada afuera.

**Inventario de datos disponibles** (todo del `.p2s`; **no hace falta debugger**):

| artefacto | contenido | ¿analizado? |
|---|---|---|
| `eeMemory.bin` | RDRAM 32 MB | ✅ diff vs recomp (`rdram_diff.py`, 8–13 %) |
| `GS.bin` | VRAM 4 MB + 509 B | ✅ conteo por bloque |
| `PCSX2 Internal Structures.dat` | `cpuRegs` (GPR, 16 B c/u), `EE-Subsystems`, `vuMicroRegs`, `VIF1dma`, `Gif Unit`, … | ✅ GPR (32) extraídos; ⏳ subsistemas |
| `vu1Memory/vu1MicroMem.bin` | data + micro del VU1 | ⏳ pendiente |
| `iopMemory.bin` | RAM del IOP | ⏳ pendiente |
| `Screenshot.png` | frame real | ✅ referencia visual |
| dumps/logs del recomp | RDRAM, VRAM, regs, counters | ✅ |

**Resultado firme: el hilo principal del real y el del recomp están en el MISMO loop**
(el spin `0x6e4d98`, dentro de `0x6e4848`), pero **en puntos distintos**: el real en
`pc=0x6E4CDC` (tras el `jal 0x6e4848`), el recomp en `0x6E4B14`/`0x6E4468`.
**Ojo**: `0x6E4CDC` y `0x6E4F08` son el **mismo bloque duplicado** en el binario ⇒ no
es divergencia de lógica.

**Registros del real (slot 6/7)**: `v0`/`v1`/`s1` apuntan al **ring** (`0xA96800`),
`s1 = gp+0x5F8`, `a2=3`, `a3=0x44`, `sp=0x1FFDBA0`, `ra=0x6E4CDC`, `gp=0xA28070`.
⇒ el real está **vivo en el motor** (coincide con que el ring se llena).

**Pendiente (para "no dejar nada afuera")**:
1. Histograma de `pc` del recomp (¿pasa por `0x6E4CDC`? ¿por cuáles no?).
2. A/B **GPR por GPR** (loguear los del recomp en el mismo pc).
3. Barrer `vu1Memory`/`vu1MicroMem`/`iopMemory` del savestate contra el recomp.
4. Comparar `Screenshot.png` vs la VRAM del recomp por fase.

### 10. A/B con PCSX2 y estado real del bloqueo (2026-10-07)

- **Método (sin BIOS ni emulador en CI: es referencia local)**: PCSX2 2.8.2 +
  BIOS `ps2-0220e-20060210.bin`, lanzado `-batch -fullscreen -fastboot` con el
  ISO del repo (usuario pasa el diálogo inicial a mano); capturas con
  `spectacle` cada 10 s. Config/evidencia en `/tmp/opencode/pcsx2{,b}/`.
- **Secuencia real del juego**:
  1. ~20 s — **primera pantalla**: diálogo **"Select video format — NTSC(60Hz)
     / PAL(50Hz)"**, dibujado por el juego, esperando input (Cross).
  2. ~70 s — **título**: logo *THE SWORD OF ETHERIA* sobre nubes +
     **New Game / Load Game**.
  3. ~120 s+ — **menú principal**: logo + arte de los 3 personajes +
     **Quit Game / Save / Story Mode / ?????? / ??????**, ©2006 KONAMI.
- **El juego renderiza desde el arranque**: el log muestra `microVU1: Cached
  Prog` + `GL: Compiling vertex/pixel shader` desde ~10 s (VU1 + GS activos).
- **Estado del recomp (mismo ISO, mismo ELF)**: arranca, carga todo el disco
  (OL/CHARA/BG/EFFECT/INTER/EED..EEU.BIN) y presenta con double-buffer
  (`dispfb1` alternando), pero **`gif=2` / `gsw=0` / `vif=6`**: **cero
  geometría**, VRAM con un único clear alpha (`crt1 fbp=128: rgbNZ=0
  aNZ=262144`). 10 min sin avanzar ⇒ **diverge antes del primer render**, o
  sea el gate es temprano (no un state machine profundo).
- **Hipótesis descartadas (2026-10-07)**:
  - **Semáforo 3 / hilo 2**: `_init_sys` → `FUN_004d4078` crea el semáforo (id
    3) + el hilo 2 (entry `0x4d3fa0`); los que lo señalan son
    `FUN_004d4168/4200/4280` (`iSignalSema`) y **nunca se invocan** ⇒ es el
    **thread de comandos SIF** del SDK, **idle por diseño** (nuestro HLE de
    `sceSifCallRpc` puentéa el camino SIF del SDK). No es el gate.
  - **Pad**: la primera pantalla pide input, pero el recomp **nunca llama
    `scePadRead`** (solo `scePadInit`+`scePadPortOpen`) ⇒ no está esperando
    input.
- **Gap abierto**: `PADMAN`/`SIO2MAN`/`SIO2D`/`DBCMAN` cargan como **HLE**
  ("physical IRX unavailable") aunque los `.IRX` están extraídos en
  `work/elf/IOP/`; solo `LIBSD`/`SDRDRV`/`SDSTR3`/`SD_CALL`/`CDVDSTM`/`MC2_D`
  cargan físicos. PCSX2 sí completa el intercambio de config del pad.
- **Plan inmediato**: (1) diff de la secuencia de init (cargas CD, IRX, binds
  SIF/RPC) PCSX2 vs recomp para ubicar la divergencia; (2) reparar la carga
  física de `PADMAN`.

## Validation

- **Fase 0**: `git --version`, `cmake --version` (>= 3.20), `cl` (MSVC C++20)
  responden correctamente; CPU con SSE4/AVX.
- **Fase 1**: existe un ELF valido en `work/elf/` (tamano > 0, cabecera ELF MIPS).
- **Fase 2**: `config.toml` existe, referencia al ELF real y lista funciones
  (via Ghidra: TOML + CSV exportados; via analyzer: TOML generado sin errores).
- **Fase 3**: PS2Recomp compila (`cmake --build` OK); `ps2_recomp` emite C++ en
  `work/generated/`; el binario del juego enlaza sin errores.
- **Fase 4 (jugabilidad basica)**: el ejecutable arranca el juego desde frio y
  alcanza jugabilidad basica (menu + inicio de partida). Glitches menores de
  graficos/audio no bloquean el cierre; se registran como limitaciones conocidas.
- **Fase 4.6 (SPU2 mínima)**: `gif>2` sostenido en smoke 30s, VRAM con escena
  sin `triage-vis`, cola de sonido drenada (`a==b` estable con callback
  instalado o completitud señalada) y triages de audio revertidos a HLE real.
- **Fase 5 (release)**: `build_release.py` rechaza ISOs con MD5 incorrecto; acepta el ISO PAL Europa conocido y produce un binario funcional. GitHub Actions genera los artefactos de Windows y Linux sin errores. El README explica el proceso sin ambiguedades legales.
- **Cierre**: `specs/` no aplica (este change no modifica comportamiento
  especificado de ningun software del repo; produce un build externo), y los
  guardrails de `AGENTS.md` (typecheck/lint/test) no aplican por no haber codigo
  TypeScript: la validacion es la de las fases de arriba.


