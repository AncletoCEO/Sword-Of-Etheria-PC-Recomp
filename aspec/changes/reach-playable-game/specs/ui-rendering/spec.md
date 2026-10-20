# Spec: ui-rendering

> Delta de especificación para `reach-playable-game`. Idioma: español; keywords en inglés.
> Estado de partida medido en `decisions.md`.

## ADDED Requirements

### Requirement: UI del juego visible

El runtime SHALL mostrar en pantalla la UI que el juego construye y encola (selector de video, título y
menús), sin inyección de VRAM ni overrides de `TEX0`/`CBP`.

#### Scenario: Selector de video visible

- **WHEN** el juego alcanza el selector PAL/NTSC (`t3sub=10`)
- **THEN** el frame presentado muestra la ventana del selector con el texto
  `Select video format.` y **las dos opciones** `NTSC(60Hz)` / `PAL(50Hz)` y el cursor
- **AND** la verificación es visual: se decodifica la VRAM presentada a PNG
  (`game/decode_gs_frame.py`, PSMCT32) y se compara con la captura real de PCSX2
- **AND** el resultado se obtiene con todas las sondas y overrides de assets apagados
- **AND** `rgbNZ > 0` por sí solo **no** satisface el escenario: un fondo cualquiera
  también lo cumple

#### Scenario: Los gates de UI pasan y la geometría llega al GS

- **WHEN** `0x6DB0D0` despacha los widgets encolados a `0x6DAEF0`
- **THEN** los widgets del selector están visibles (`flags & 1`) y con comandos (`widget+0x90` no vacía)
- **AND** las primitivas que emiten sus callbacks llegan al GS con el `tbp0`/`psm` correctos

### Requirement: Control por pad del host

El runtime SHALL entregar el estado del pad/teclado del host al juego por su propio camino de lectura
(`0x51C7C0` → `0xA42102`), sin alterar la lógica del juego.

#### Scenario: El selector responde al input

- **WHEN** el usuario presiona arriba/abajo
- **THEN** el selector alterna PAL(50Hz)/NTSC(60Hz)
- **AND** cuando presiona Cross, el juego avanza de fase

### Requirement: Juego jugable

El runtime SHALL permitir jugar el juego completo (título → menú → gameplay) con entrada, vídeo y audio.

#### Scenario: Gameplay 3D

- **WHEN** el jugador inicia una partida
- **THEN** la escena 3D se dibuja (VU1/VIF1/XGKICK) y responde al pad

#### Scenario: Ritmo útil

- **WHEN** el juego corre en una escena jugable
- **THEN** el tick de juego es suficiente para que la respuesta al pad sea usable (hoy ~9/s vs 58 VBlank)
