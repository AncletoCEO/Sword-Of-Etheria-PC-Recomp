# Reanálisis — **OBSOLETO**

> **OBSOLETO (2026-10-09).** El planteo de este documento resultó **incorrecto**: sostenía que el HLE de SIF
> "inventa" estado y que `0xA2A9C0` era una **tabla de config/RPC a reproducir a mano**. En realidad
> `0xA2A9C0` es el **pool de paquetes SIF del juego** (lo llena `_sif_alloc_packet`, entradas de 64 B), y sus
> valores en `ss01` son **síntoma**, no causa.
>
> El plan vigente está en **`HANDOFF.md`**. Se conserva este archivo solo por historial — **no usarlo como
> guía**.
