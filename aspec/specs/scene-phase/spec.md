# Spec: scene-phase

> Sincronizado desde `aspec/changes/reach-main-menu` al archivarse (2026-10-19).
>
> **Estado al sincronizar**: el **avance de fase** y el **menú visible** siguen siendo el objetivo. Los
> requisitos de **semáforo 8** y **réplica de RPC** quedaron **refutados por medición** (ver
> `aspec/changes/reach-playable-game/decisions.md` §2) y se conservan acá como registro histórico; no
> guiar la implementación actual. La continuación del hito vive en `aspec/changes/reach-playable-game/`.

## Requirements

### Requirement: Avance de fase de escena

El runtime SHALL permitir que el state machine de escena del juego avance desde la fase de boot
(fase negra) hacia el título/menú, sin quedar detenido en una transición.

#### Scenario: La variable de fase avanza

- **WHEN** el juego ejecuta su loop de escena en la fase de boot
- **THEN** la variable/paso de escena avanza (cambia de valor) y el juego no permanece indefinidamente
  en la fase negra

#### Scenario: El thread principal sale del conjunto de pcs de la fase negra

- **WHEN** se perfila el thread principal (`[triage-vbprof]`)
- **THEN** su `pc` deja de concentrarse en el conjunto de funciones de la fase negra y pasa a las
  de la fase siguiente (título/menú)

### Requirement: Semáforo 8 balanceado

El runtime SHALL hacer que el semáforo `8` del juego quede balanceado, de modo que ninguna espera
quede colgada.

#### Scenario: Señales cubren las esperas

- **WHEN** el juego espera/señaliza el semáforo `8` (`0x51ee84`/`0x51eeb4`)
- **THEN** la cantidad de `SignalSema(8)` cubre las `WaitSema(8)` y ningún waiter queda bloqueado

### Requirement: RPC del juego con réplica

El runtime SHALL responder (o registrar el servidor de) las RPC del juego
(`0x80000592`/`0x8000059c`/`0x80000006`) de modo que dejen de aparecer como `unhandled`.

#### Scenario: RPC ya no queda en unhandled

- **WHEN** el juego invoca `sceSifCallRpc` a `0x80000592`/`0x8000059c`/`0x80000006`
- **THEN** la RPC se resuelve con un servidor (no `rpc=0`/`unhandled`) y el state machine que la
  espera puede continuar

### Requirement: Menú principal visible

El runtime SHALL presentar un frame con contenido (no negro) cuando el juego alcanza el título/menú,
sin parches de triage activos.

#### Scenario: Frame de menú con píxeles RGB

- **WHEN** el juego alcanza la fase de título/menú con los triages apagados
- **THEN** el frame presentado tiene `nonZeroRgb > 0`

#### Scenario: Estado del driver de sonido en la rama activa

- **WHEN** el juego consulta su estado de driver de sonido (`0x6e8870`/`0x6e8880`)
- **THEN** el estado es **2** (rama activa) y NO se fuerza `2→5` (idle)
