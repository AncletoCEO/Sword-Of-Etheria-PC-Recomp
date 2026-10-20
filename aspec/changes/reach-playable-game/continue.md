# Continuar — reach-playable-game

> **Prompt de arranque vigente: `CONTINUE_PROMPT.md`** (en esta misma carpeta). Pegarlo al inicio de una
> sesión nueva y arrancar con **`/cleto-apply reach-playable-game`**.
>
> Change anterior: **`reach-main-menu`** (archivado). Su `decisions.md` §(1)–(32) es el log crudo; **no
> repetirlo**. Este change arranca con el **digest verificado** en `decisions.md`.

## En 3 líneas

- La UI del selector **se construye, se enlaza y se dibuja** (`0x6db0d0` → `0x6daef0`, gates en verde), el
  **pad funciona**, y aun así `rgbNZ=0`.
- Falta medir **qué emiten los callbacks de render** (`0x6daf6c: jalr *(cmd+0x10)`) y por qué no producen
  color visible. **Ese es el hito 1.**
- Después: título/menú, gameplay 3D + ritmo, audio/save/cinemáticas, launcher + release.
- **Flujo**: cada hito avanza en **rondas con Gemini** (`work/gemini/msg_gemini_vNN.md` → respuesta), que
  se verifican contra ELF/RAM/log antes de implementar. Ver `design.md` §"Flujo de trabajo con Gemini".

## Orden de lectura

1. `decisions.md` (digest: estado + refutaciones).
2. `tasks.md` (hito 1, §1.1–1.5).
3. `design.md` (pipeline de UI con direcciones).
4. `CONTINUE_PROMPT.md` (protocolo Gemini + reglas de método + comandos).
