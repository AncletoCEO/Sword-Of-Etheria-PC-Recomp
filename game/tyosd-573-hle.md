# HLE mínimo: servidor SIF RPC `sid=0x573` (TYOSD / SD.BIN)

Fecha: 2026-10-03. Investigación del subagente: `sid` sin bit31 = custom del
juego; `work/elf/IOP/` trae la pila de sonido Sony (`LIBSD.IRX`, `SDRDRV.IRX`,
`SD_CALL.IRX`…); el EE abre `cdrom0:\SD.BIN;1` (`rpc=0x10000`,
`send=0xa44080/128`, `recv=0xa44900/20`), pullea (`0x20000`/`0x0`) y pide
streaming (`rpc=0x30000`, `send=0xa44100/640`, `recv=0xa44940/352`) desde
`FUN_005496c0` (`0x627ab0/0x627afc`). Sin handler, `recv` queda a cero, el
juego reintenta y la cola de render (`0xA96800/0xB16000`, spin `0x6e4d98`)
nunca recibe datos → pantalla negra.

## Qué hace el handler (en `sifCallRpcStub`, rama `sid == 0x573`)

- `rpc=0x10000`: lee el path en `send+4`, resuelve `SD.BIN` en
  `work/elf/` (683 MB, existe) y devuelve `recv[0]=1`,
  `recv[1]=tamaño en bytes`, `recv[2]=sectores`. Resto a cero.
- `rpc=0x20000`/`0x0`/`0x30000`: `recv[0]=1` (done), resto a cero.
- No cambia el flujo: después corre el `sceSifCallRpc` real + re-apply como
  antes; `v0=0` (éxito → el EE toma `bnez → 0x627b14`).
- Límite conocido: `0x30000` aún no sirve datos reales del stream (layout del
  descriptor de 640 B sin verificar). Si el juego avanza pero el audio/stream
  se atasca, el siguiente paso es parsear ese descriptor y hacer
  `sceCdRead` de `SD.BIN` al destino guest.

## Parche

`game/patches/tyosd-573-hle.patch`. Rebuild incremental `ps2_runtime` +
relink y re-test gráfico (buscar `[TYOSD]` en el log).

## Resultado 2026-10-04 (HLE siempre activo)

Se eliminó el gate `g_tyosdRealModuleId <= 0`: el HLE atiende `0x573`
aunque `SDRDRV.IRX` esté cargado (moduleId=4), porque el driver real no
responde `rpc=0x0`. `/tmp/test_hle.txt` (90s): `tick=3960 gif=2
vram=0/4194304`, `rpc=0x0` x625, `TYOSD] ack` x622, 147 frames.
`/tmp/test_hle2.txt` (150s): `tick=5280`, 864 polls, 861 acks, 164
frames. Bloqueo persiste (`0x6e4d98`, `flag5D0` oscila). Siguiente:
`rpc==0x0` debe simular contadores `gp+0x44/gp+0x48 >= 0x41` y `0x30000`
servir `SD.BIN` según descriptor.
