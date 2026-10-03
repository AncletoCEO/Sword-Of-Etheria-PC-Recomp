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
