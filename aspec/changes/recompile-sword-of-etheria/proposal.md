# Proposal: Recompilación nativa de Sword of Etheria (PS2) para PC

## Problem

El usuario posee una copia en formato ISO de `Sword of Etheria, The (Europe)`
ubicada en la raíz de este repositorio y quiere jugarla de forma **nativa en PC**
(es decir, como ejecutable de Windows, no en un emulador como PCSX2).

No tiene experiencia previa en recompilación de juegos ni toolchain instalado, pero
identificó como punto de partida el proyecto
[PS2Recomp](https://github.com/ran-j/PS2Recomp): un recompilador estático
experimental que traduce binarios ELF de PS2 (MIPS R5900) a C++ y provee un
runtime para ejecutarlos en PC.

Hoy no existe en este repositorio ningún setup, documentación ni proceso para
llevar adelante esa recompilación.

## Proposed change

Crear un proyecto de recompilación guiado y reproducible en este repositorio:

1. Instalar y verificar el toolchain mínimo en Windows: Git, CMake 3.20+ y un
   compilador C++20 (MSVC, que es el mejor soportado por PS2Recomp).
2. Extraer el ELF ejecutable del juego desde el ISO.
3. Clonar y compilar PS2Recomp (`ps2xAnalyzer`, `ps2xRecomp`, `ps2xRuntime`, `ps2xIOP`).
4. Generar el `config.toml` del juego con el flujo recomendado (export desde
   Ghidra) o, como alternativa rápida, con `ps2xAnalyzer`.
5. Recompilar el ELF a C++ y compilar el resultado junto a `ps2xRuntime` para
   obtener el ejecutable nativo de PC.
6. Iterar sobre stubs/syscalls faltantes (ciclo recomendado por PS2Recomp) hasta
   lograr arranque y jugabilidad básica.
7. **Estrategia de ejecución**: Priorizar ejecuciones largas (como la compilación o generación de C++) y establecer temporizadores (timers de 6 horas) para gestionar automáticamente los límites de cuota de la IA, permitiendo trabajo asíncrono sin intervención manual.

8. **Publicación y release**: preparar el repo para GitHub y generar releases reproducibles para Windows y Linux. El release NO incluye contenido del juego; el usuario aporta su propio ISO y una herramienta del repo verifica el MD5 antes de construir el ejecutable jugable.

Todo el proceso queda documentado en `design.md` y operativizado en `tasks.md`,
pensado para alguien sin experiencia previa.

## Scope

In:

- Setup del entorno en Windows (Git, CMake, MSVC, Ghidra opcional pero recomendado).
- Extracción del ELF desde el ISO existente en la raíz del repo.
- Clonado y compilación de PS2Recomp como submódulo/herramienta externa.
- Generación de `config.toml`, recompilación a C++ y build del ejecutable PC.
- Ciclo de iteración sobre stubs hasta un build jugable básico.
- Documentación del proceso en este change.
- Script `build_release.py` que verifica el MD5 del ISO del usuario y compila el ejecutable final para Windows o Linux.
- Emulación SPU2 mínima (registros + `transfer-complete`, sin audio real) necesaria para que el init de sonido complete y el juego salga del spin `0x6e4d98` (opción A elegida 2026-10-04; detalle en `design.md` Fase 4.6).
- GitHub Actions CI para compilar y publicar releases de Windows y Linux automáticamente al hacer tag.
- `README.md` con instrucciones claras de uso (el usuario aporta su ISO, el script verifica el hash y genera el juego).

Out:

- Modificar contenido, assets o lógica del juego más allá de los hooks/stubs
  necesarios para que arranque.
- Corrección de todos los bugs gráficos/sonoros o de rendimiento del runtime
  (limitación propia de PS2Recomp, fuera de nuestro control), salvo la SPU2
  mínima de arranque definida en el In.
- **Distribución del ISO, del ELF o de ningún archivo con copyright** — el release solo contiene el ejecutable compilado desde el código recompilado abierto, nunca assets del juego.

## Risks

- **PS2Recomp es experimental, con emulación de hardware parcial y muchos paths
  en stub**: el juego puede no arrancar o tener glitches graves → mitigación:
  fijar como éxito "arranque + jugabilidad básica" y usar el ciclo de iteración
  documentado (arreglar bloqueantes primero, stubs temporales solo para triage).
- **ELF retail "stripped" sin símbolos**: el análisis automático puede ser
  insuficiente → mitigación: usar el flujo Ghidra + `ExportPS2Functions.java`
  como vía principal.
- **Rendimiento pobre en VU/GS** (limitación conocida del proyecto) →
  mitigación: medir expectativas; documentar flags como `low_memory_mode` y
  `output_worker_threads` si la generación se vuelve pesada.
- **Usuario sin experiencia**: curva de aprendizaje en CMake/MSVC/Ghidra →
  mitigación: tasks pequeñas y verificables una por una, con criterio de
  "hecho" explícito.
- **Aspectos legales**: trabajar solo con la copia propia y no distribuir
  archivos del juego → mitigación: el change solo versiona configuración,
  scripts y documentación, nunca el ISO/ELF ni los binarios generados.
