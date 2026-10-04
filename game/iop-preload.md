# Precarga de los IRX del IOP

Fecha: 2026-10-03. Parche: `game/patches/iop-preload-irx.patch`.

## Diagnóstico

Después de implementar el HLE de `sid=0x573` (ver `tyosd-573-hle.md`), el juego
seguía igual: `gif=2`, `vramNonZero=0`, 255 polls de `rpc=0x0`. El HLE ya
respondía éxito (`v0=1`) y el wrapper de `0x627a30–0x627b48` pasaba su gate
(`gp+0x44 + gp+0x48 < 0x41`), pero el IOP nunca producía el stream: no hay
nada detrás del RPC.

La pista fuerte estaba en una línea que se pasó por alto al principio:

```
[IOP/RPC trace:unhandled] sid=0x573 rpc=0x0 ... loadedModules=[]
```

`loadedModules=[]` en **todas** las trazas. El IOP no tenía ni un módulo
cargado. En una PS2 real el CRT0 carga los IRX de `IOPRP300` antes de saltar al
juego; este recomp entra directo al juego con el IOP vacío, así que no existen
los servidores de sonido, pad ni CD, y el juego nunca llama `LoadModule` por su
cuenta (0 llamadas en toda la sesión).

## Fix

`ps2xIOP` sí tiene cargador de IRX reales (`IopSubsystem::loadModule` →
`IopModuleLoader::readWholeHostFile` con path host + fallbacks HLE), expuesto
como `PS2Runtime::loadIopModule()`. Los 11 IRX de `IOPRP300` ya estaban
extraídos en `work/elf/IOP/`:

```
SIO2MAN  SIO2D  LIBSMF2  LIBSD  SDSTR3  SD_CALL  SDRDRV  PADMAN  CDVDSTM  DBCMAN  MC2_D
```

Se precargan en orden de arranque en el stub de `sceSifInitRpc` (`0x004d6860`),
que el juego invoca una vez con el IOP ya en pie. **No** en `game_main.cpp`
antes de `run()`, porque `PS2Runtime::run()` hace `resetIop()` al arrancar y
borraría todo lo cargado.

Con esto el `sid=0x573` deja de ser un HLE adivinado: si `SDRDRV.IRX` carga y
registra su server, el HLE se desactiva solo (`g_tyosdRealModuleId > 0`) y
manda el driver real, que sí sabe leer `SD.BIN` y decodificar ADPCM.

## Verificación

```
./work/build-game/out-linux/sword_etheria work/elf/SLES_537.68 > work/build-game/coldboot-iop.log 2>&1
grep "iop-preload" work/build-game/coldboot-iop.log
```

Esperado: un `moduleId` por IRX, `TYOSD real=<n>` al final, y `loadedModules`
poblado en las trazas de RPC. Si `SDRDRV.IRX` no carga, el HLE sigue activo
como red de seguridad (y el log dice `falta` o `moduleId=-1`).

Overrides: directorio con override de `SWORD_IOP_DIR` (por defecto
`work/elf/IOP/`, derivado de `cdRoot`).

## Resultado 2026-10-04

Cadena de 5 intentos por IRX (absoluta → `nativehost:` → `host0:`+abs →
`host0:IOP/` → `cdrom0:/IOP/`). Los 11 cargan (`/tmp/test_rel2.txt`):
SIO2MAN 1073741824, SIO2D 1073741825, LIBSMF2 1, LIBSD 1073741826,
SDSTR3 2, SD_CALL 3, SDRDRV 4/start 2, PADMAN 1073741827, CDVDSTM 5/2,
DBCMAN 1073741828, MC2_D 6/2; `TYOSD real=4`. Run gateado: `tick=2880
gif=2 vram=0/4194304`, 130 frames, sin acks TYOSD. El binario requirió
relink manual vía `CMakeFiles/sword_etheria.dir/link.txt`.