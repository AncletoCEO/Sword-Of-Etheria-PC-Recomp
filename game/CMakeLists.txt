# Juego: Sword of Etheria (SLES_537.68) recompilado con PS2Recomp.
# Une el C++ generado (work/generated) con ps2_runtime en un binario jugable.
# Uso Linux:
#   cmake -S work/build-game -B work/build-game/out-linux -G Ninja -DCMAKE_BUILD_TYPE=Release
#   cmake --build work/build-game/out-linux --target sword_etheria -j$(nproc)
# Uso Windows:
#   cmake -S . -B out -G "Visual Studio 18 2026" -A x64
#   cmake --build out --config Release --target sword_etheria
cmake_minimum_required(VERSION 3.21)

# Raíz del repo: por defecto <este-dir>/../.. ; sobreescribible con
# -DREPO_ROOT=... (útil al migrar el build a otra máquina/SO).
if(NOT DEFINED REPO_ROOT)
    get_filename_component(REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
endif()
if(WIN32)
    file(TO_CMAKE_PATH "${REPO_ROOT}" REPO_ROOT)
endif()
set(PS2RECOMP_DIR "${REPO_ROOT}/tools/PS2Recomp")
set(GENERATED_DIR "${REPO_ROOT}/work/generated")

project(sword_etheria_recomp LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Arranca el SLES_537.68 europeo por defecto (argv[1] lo sobreescribe).
set(PS2X_DEFAULT_BOOT_ELF "${REPO_ROOT}/work/elf/SLES_537.68" CACHE STRING "" FORCE)

# Solo los submódulos necesarios (el árbol completo arrastra ps2xStudio,
# que asume ser el proyecto top-level vía CMAKE_SOURCE_DIR).
add_subdirectory("${PS2RECOMP_DIR}/ps2xIOP" "${CMAKE_BINARY_DIR}/ps2xIOP" EXCLUDE_FROM_ALL)
add_subdirectory("${PS2RECOMP_DIR}/ps2xRuntime" "${CMAKE_BINARY_DIR}/ps2xRuntime" EXCLUDE_FROM_ALL)

# PS2Recomp usa SSE4.1 en headers (smmintrin.h: _mm_extract_epi32/64,
# _mm_blendv) sin activarlo para GCC/Clang. MSVC lo emite sin flag;
# en Linux x86_64 hay que pedirlo explícito.
if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64|x86" AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(ps2_runtime PRIVATE -msse4.1)
    target_compile_options(ps2_iop PRIVATE -msse4.1)
endif()

file(GLOB GAME_SOURCES "${GENERATED_DIR}/*.cpp")

add_executable(sword_etheria
    game_main.cpp
    ${GAME_SOURCES}
)

target_include_directories(sword_etheria PRIVATE "${GENERATED_DIR}")

target_link_libraries(sword_etheria PRIVATE ps2_runtime)

# Unity build: en MSVC 17k TUs serían eternos uno por uno.
# En Linux/GCC los unity files con batch 48 revientan la RAM (cc1plus killed).
# → Unity solo en MSVC; en GCC compilamos archivo por archivo con -j$(nproc).
if(MSVC)
    set_target_properties(sword_etheria PROPERTIES
        UNITY_BUILD ON
        UNITY_BUILD_BATCH_SIZE 16
        MSVC_DEBUG_INFORMATION_FORMAT ""
    )
else()
    set_target_properties(sword_etheria PROPERTIES
        UNITY_BUILD OFF
    )
endif()
# La tabla de registro (104 MB) se compila sola para no reventar un batch...
set_source_files_properties("${GENERATED_DIR}/register_functions.cpp" PROPERTIES
    SKIP_UNITY_BUILD_INCLUSION TRUE
)
if(MSVC)
    # ...y sin optimizar: es solo un inicializador gigante de datos.
    # Con /O2 el optimizador se atasca decenas de minutos; /Od es seguro aquí.
    set_source_files_properties("${GENERATED_DIR}/register_functions.cpp" PROPERTIES
        COMPILE_FLAGS "/Od"
    )
endif()

# Funciones "monstruo": Ghidra no partió varias regiones de código (hasta 246 MB
# por función) y un batch unity que contenga una tarda decenas de minutos.
# Se excluyen de unity por tamaño (>10 MB) y se compilan solas con /Od.
# (Correctitud primero; se reparten en Fase 4 si alguna es código caliente.)
set(BIG_SOURCES "")
foreach(src IN LISTS GAME_SOURCES)
    file(SIZE "${src}" src_size)
    if(src_size GREATER 2000000)
        list(APPEND BIG_SOURCES "${src}")
    endif()
endforeach()
list(LENGTH BIG_SOURCES BIG_COUNT)
message(STATUS "Archivos >10MB fuera de unity: ${BIG_COUNT}")
set_source_files_properties(${BIG_SOURCES} PROPERTIES
    SKIP_UNITY_BUILD_INCLUSION TRUE
)

if(MSVC)
    target_compile_options(sword_etheria PRIVATE /bigobj /FS)
    # TODO(perf): reconstruir en Release-/O2 cuando el juego arranque.
    # Hoy /Od en todo el target: el build /O2 no termina en esta máquina
    # (4 cores) y para el triage de stubs/syscalls la velocidad no importa.
    target_compile_options(sword_etheria PRIVATE /Od)
    # /Ob0: sin expansión inline (con /Ob2 el inliner duplica helpers en miles
    # de call-sites y cl se queda sin heap en pass 2). TODO(perf): revertir.
    target_compile_options(sword_etheria PRIVATE /Ob0)
    # TODO(seguridad): reactivar /GS en el build final. Hoy /GS- porque el
    # análisis de flujo de los cookies en funciones de 15k+ labels multiplica
    # x10 el tiempo de compilación; para triage local no aporta.
    target_compile_options(sword_etheria PRIVATE /GS-)
    # Mapa de símbolos para triage de crashes sin PDB.
    target_link_options(sword_etheria PRIVATE /MAP)
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    # Equivalente Linux de lo de arriba: sin optimizar ni inlining (el build
    # /O2 no termina en máquinas modestas), sin stack-protector (equiv. /GS-),
    # sin debug info (equiv. sin-PDB). TODO(perf/seguridad): revertir al final.
    target_compile_options(sword_etheria PRIVATE -O0 -fno-inline -fno-stack-protector -g0)
    # SSE4.1: el C++ generado incluye los mismos headers del runtime
    # (_mm_extract_epi32/64). Sin esto GCC falla con "target specific option mismatch".
    if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64|x86")
        target_compile_options(sword_etheria PRIVATE -msse4.1)
    endif()
endif()
