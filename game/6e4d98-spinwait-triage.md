# Triage: spin-wait en `0x6e4d98` (pantalla negra)

Fecha: 2026-10-03. Log: `work/build-game/coldboot-negro.log` (ignorado por git, solo local).

## Hallazgo

- El juego avanza hasta tick 5400 (`dma 3589`, 2 threads, sin crash) pero la
  pantalla queda negra: `vramNonZero=0/4194304`, todos los `gs:prim`
  con `rgba=(0,0,0,128)` y `tex0 tbp0=0`, `frame:upload 512x512` alternando
  `displayFbp 128/0` con el mismo contenido.
- `gif=2` clavado desde tick ~360: no hay nuevos paquetes GS, la lógica del
  juego no emite más escena.
- Histograma de `run:tick`: `pc=0x6e4d98` x33 (dominante), `ra=0x6e4cdc`.
- `0x6e4d98` vive en `work/generated/FUN_006cba48_0x6cba48_p2.cpp:26163`
  (dispatcher `0x6cba48-0x9cbd34`, código recompilado real, no stub):

```
0x6e4d98: lw  v1, 0x638(gp)     # contador A (gp=0xa28070 -> 0xa286a8)
0x6e4da0: lw  v0, 0x63C(gp)     # contador B (             -> 0xa286ac)
0x6e4da4: bnel v1, v0, +0x18    # si difieren, s0=1 y sigue esperando
... jalr v0 / bnez s0 -> vuelve al loop
```

Es un spin-wait sobre dos contadores que otro hilo/interrupción (VSync/DMA)
debería igualar. Loop hermano en `0x6e4684` (`p2.cpp:23295`) pullea
`gp+0x5D0` vía `FUN_004d1170`.

## Snippet propuesto (TRIAGE, no fix real)

Seguir el ciclo de `design.md`: handler temporal solo para clasificar
importancia. Insertar en `applySwordOfEtheriaOverrides()`, junto a los
bloqueantes #1-#4 en
`tools/PS2Recomp/ps2xRuntime/src/lib/game_overrides.cpp`
(archivo ignorado por git: este `.md` es la copia versionada del hack):

```cpp
// TRIAGE pantalla negra: iguala contadores del spin 0x6e4d98 para
// clasificar si el juego sale del loop. NO es fix real.
static auto triage6e4d98 = [](uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime) {
    (void)runtime;
    const uint32_t gp = static_cast<uint32_t>(_mm_cvtsi128_si32(ctx->r[28]));
    uint32_t a = 0, b = 0;
    std::memcpy(&a, rdram + ((gp + 0x638u) & 0x01FFFFFFu), 4);
    std::memcpy(&b, rdram + ((gp + 0x63Cu) & 0x01FFFFFFu), 4);
    RUNTIME_LOG("[triage] 0x6e4d98 counters a=" << a << " b=" << b);
    std::memcpy(rdram + ((gp + 0x638u) & 0x01FFFFFFu), &b, 4); // fuerza salida
    ctx->pc = 0x6e4dacu; // reanuda tras el bnel con s0=0
};
runtime.replaceFunction(0x6e4d98u, triage6e4d98);
```

Nota: `0x6e4d98` es mitad de función (`0x6e4cc0`), así que el override
puede corromper estado de registros/stack. Si el test sale del loop pero
crashea, igual clasifica el bloqueante como "señal VSync/DMA faltante" y el
fix real va por `sceGsSyncV` (`0x4d3730`) / `sceDmaSync` (`0x4d02f8`) o el
handler de interrupción, no por este parche.

## Resultado triage (2026-10-03, `coldboot-triage2.log`)

- Override enganchó: 229 líneas `[triage]`, `a/b` son punteros que difieren en
  16 (`0xA96800/0xB16000…`), a veces iguales naturalmente; `flag5D0` 1→0.
- NO desbloquea render: `gif=2` clavado, `vramNonZero=0`, frames negros.
  Histograma cambia de `pc=0x6e4d98` a `pc=0x6e4cdc` x23: sale del spin
  interno pero vuelve (cola consumidora hambrienta).
- Solo 1 `sceDmaSend` en todo el run; RPCs `sid=0x573` (`rpc=0x20000/0x30000`,
  `pc=0x627ab0/0x627afc`) sin handler (`IOP/RPC trace:unhandled`).
- Clasificación: la espera es síntoma; falta el **productor** (streaming vía
  RPC `0x573`, probable IRX propio del juego). Forzar el consumidor no crea
  datos. Fix real: identificar el servidor `0x573` (módulo IRX en disco,
  `sceSifBindRpc client=0xa44020`), no este parche. Triage cumplido.

## Análisis del loop (2026-10-04, código generado `FUN_006cba48_p2.cpp`)

Leído el dispatcher completo `0x6e4d98–0x6e4dd8`:

- `0x6e4d98/0x6e4da0`: `v1=gp+0x638`, `v0=gp+0x63C` (punteros de cola).
- `0x6e4da4 bnel`: si difieren → `s0=1`, salta a `0x6e4dbc`.
- `0x6e4dac`: `lbu v0, gp+0x630` (flag); si `!=0` → `s0=1`.
- `0x6e4dc0`: si callback (`gp-0x7A30`) `==0` → sin llamada; si no,
  `jalr callback(a0=s0, a1=s2)`.
- `0x6e4dd0 bnez s0` → vuelve a `0x6e4d98`. **Salida solo si:
  `0x638==0x63C` Y `byte gp+0x630==0`** (cae a `0x6e4dd8 di`, sección crítica).
- Productores que escriben `0x638/0x63C/0x630`: fragmentos
  `entry_006e6ac4/0x6e6ac8/0x6e6ad4`, `FUN_006e6a58`, `FUN_006cc380/0x6cc400`
  (posibles handlers de interrupción que en el recomp nunca se disparan).

Conclusión: el triage v1 (igualar `a=b`) es insuficiente — falta limpiar
`gp+0x630`. Siguiente triage v2: igualar + `gp+0x630=0` antes de saltar a
`0x6e4dac`, loguear `flag630` por poll. Si sale del loop: o avanza a nueva
funcionalidad (nuevos `gif`, VRAM con escena) o crashea (pc del crash dice
dónde). Si crashea, el fix real va por el productor (VSync/DMA/SPU).

## Poller hambriento (2026-10-04, `FUN_006e6a58`)

El poller `0x6e6a58-0x6e6b2c` retorna de entrada si `byte gp+0x640==0`
(`0x6e6a5c beqz` hacia `0x6e6b28`), sin llamar jamas al worker `0x6e4cc0`.
Medido `flag640=0` estable: worker hambriento, 1 item pendiente eterno.
Triage v3: el override del spin levanta tambien `gp+0x640=1` (igual que
se hizo con `0x630`). Verificar en smoke: presencia del poller en el
histograma pc, drenado de cola (`a/b` cambian), `gif>2`.

## Correccion de modelo (2026-10-05): el ping-pong es artefacto del triage

- El poller SI es llamado desde el flujo principal (`jal func_6E6A58`
  en `0x6e7ec8`, chequea flag en `0x6e7ed0` tras volver). Corre por
  iteracion pero retorna al instante (`flag640==0`).
- La salida del spin (`0x6e4df4+`) lee una TABLA (`s1=gp+0x5F8`,
  indice `gp+0x604`) y republica `0x63C/0x638` desde ella: la alternancia
  `a/b` entre visitas es el flip normal, NO drenado real. Sin triage el
  spin se queda en el PRIMER item.
- Triage v6 (poner en cero los 16 B del item): sin efecto - el flip
  republica desde la tabla de todos modos; el productor re-escribe el
  item cada ronda independiente del contenido.
- Conclusion: UN solo comando de audio pendiente desde el init, cuyo
  productor espera senal de completitud SPU (no contenido). El consumidor
  (`cb==0`) jamas se instala porque esa senal nunca llega. Siguiente:
  waiter exacto de SDRDRV o trazar escrituras a `gp+0x63C` con pc.
