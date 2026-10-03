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
- **Fase 5 (release)**: `build_release.py` rechaza ISOs con MD5 incorrecto; acepta el ISO PAL Europa conocido y produce un binario funcional. GitHub Actions genera los artefactos de Windows y Linux sin errores. El README explica el proceso sin ambiguedades legales.
- **Cierre**: `specs/` no aplica (este change no modifica comportamiento
  especificado de ningun software del repo; produce un build externo), y los
  guardrails de `AGENTS.md` (typecheck/lint/test) no aplican por no haber codigo
  TypeScript: la validacion es la de las fases de arriba.


