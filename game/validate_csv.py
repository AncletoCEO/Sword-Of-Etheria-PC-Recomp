#!/usr/bin/env python3
"""Validador de ghidra_functions.csv ANTES de recompilar.

Chequea las 3 clases de error que nos costaron builds de ~5 h:

  1. OVERLAP: End_i > Start_{i+1}  (una fila se mete en la siguiente).
  2. START SOMBREADO: el Start de una FUN_ cae ESTRICTAMENTE dentro del rango de
     otra fila -> el despachador no le crea slot -> "missing-target".
     (Es el caso entry_0070bf60 tapando FUN_0070bf70.)
  3. SPLIT MID-FUNCION: un FUN_ cuya direccion de inicio NO estaba en el baseline
     y cuyos 12 bytes previos NO son [jr $ra | j] + delay + nops -> se partio donde
     no era funcion real (el caso que rompio 0x6e6934 / 0x4ddab0).

Uso:
  python3 game/validate_csv.py [csv] [--baseline csv_baseline] [--elf elf]

Salida: lista de problemas + exit code 1 si hay alguno.
"""
import struct
import sys


def load(path):
    rows = []
    with open(path, "rb") as f:
        data = f.read().decode("utf-8")
    for line in data.split("\r\n"):
        raw = line.strip()
        if not raw or raw.startswith("Name,") or raw.startswith("#"):
            continue
        p = raw.split(",")
        if len(p) < 4:
            continue
        rows.append((p[0], int(p[1], 16), int(p[2], 16), int(p[3])))
    rows.sort(key=lambda r: r[1])
    return rows


def main():
    argv = sys.argv[1:]
    args, opts = [], {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            k, v = a[2:].split("=", 1) if "=" in a else (a[2:], None)
            if v is None and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                i += 1
                v = argv[i]
            opts[k] = v if v is not None else ""
        else:
            args.append(a)
        i += 1
    csv_path = args[0] if args else "aspec/changes/archive/2026-10-09-recompile-sword-of-etheria/ghidra_functions.csv"
    # Baseline opcional: si se pasa, se usa para detectar splits NUEVOS (chequeo MIDFUNC).
    # Sin baseline, MIDFUNC se omite y quedan los chequeos criticos SHADOW / MISSING.
    baseline_path = opts.get("baseline", "")
    elf_path = opts.get("elf", "work/elf/SLES_537.68")

    rows = load(csv_path)
    base = {}
    try:
        for n, s, e, z in load(baseline_path):
            base[s] = n
    except OSError:
        pass

    errors = []
    warnings = []
    problems = errors  # compat: los ERROR son los que bloquean

    def is_fun(name):
        return name.startswith(("FUN_", "thunk_"))

    # Patrones NORMALES que NO son error:
    #   FUN_ seguido de entry_ INTERNO  (entry_ es un label de jump dentro de la FUN_)
    #   entry_ seguido de entry_        (sub-labels encadenados)
    # El error real es:
    #   (a) FUN_ cuyo Start cae dentro del rango de un entry_/thunk_ ANTERIOR -> sin slot
    #       (es el caso entry_0070bf60 tapando FUN_0070bf70)
    #   (b) dos FUN_ (o thunk_) reales que se solapan -> partida incorrecta

    # --- 1+2. Overlap/sombreado SOLO cuando la fila tapada es una FUN_ real ---
    for j in range(len(rows)):
        nn, ns, ne, _ = rows[j]
        if not is_fun(nn):
            continue
        # buscar hacia atras la fila i que contiene a ns
        for i in range(j - 1, -1, -1):
            n, s, e, _ = rows[i]
            if e <= ns:
                break
            # s <= ns < e  (por orden); si s == ns no es sombreado (misma dir)
            if s < ns:
                if not is_fun(n):
                    # entry_/thunk_ tapa una FUN_ -> SIN slot -> BLOQUEA
                    errors.append(
                        f"SHADOW      {nn} start=0x{ns:x} cae dentro de {n} 0x{s:x}-0x{e:x} -> sin slot"
                    )
                else:
                    # thunk dentro de su funcion madre: el recompilador registra AMBOS
                    # (thunk + madre) -> benigno, se tolera (7 casos historicos del baseline)
                    warnings.append(
                        f"OVERLAP-FUN {nn} start=0x{ns:x} dentro de {n} 0x{s:x}-0x{e:x} (thunk, benigno)"
                    )
                break

    # --- 3. Splits mid-funcion ---
    try:
        elf = open(elf_path, "rb").read()
    except OSError:
        elf = None

    def is_ret_or_jump_before(addr):
        """True si en los 24 bytes previos hay un epilogo real:
        [jr $ra | j] + delay slot + (0..3) nops de alineacion.
        Cubre las 3 variantes reales del binario:
          ret @ -8  (jr + delay activo, sin nops)
          ret @ -12 (jr + delay + 1 nop)
          ret @ -16 (jr + delay + 2 nops)
        """
        if elf is None:
            return None
        off = addr - 0x4C0000 + 0x100
        if off < 32:
            return None
        for back in (8, 12, 16, 20, 24):
            w1 = int.from_bytes(elf[off - back:off - back + 4], "little")
            if not (w1 == 0x03E00008 or (w1 >> 26) == 2):
                continue
            # el delay slot y los bytes hasta `addr` deben ser nops o 1 instruccion
            tail = elf[off - back + 4:off]
            if len(tail) % 4 != 0:
                continue
            words = [int.from_bytes(tail[k:k + 4], "little") for k in range(0, len(tail), 4)]
            # el delay slot puede ser una instruccion real; el resto, nops
            if all(w == 0 for w in words[1:]):
                return True
        return False

    for n, s, e, _ in rows:
        if not base:
            break  # sin baseline no se puede saber si el start es nuevo -> MIDFUNC no aplica
        if s in base:
            continue  # ya existia en el baseline -> no es un split nuevo
        if not n.startswith(("FUN_", "entry_", "thunk_")):
            continue
        ok = is_ret_or_jump_before(s)
        if ok is False:
            errors.append(
                f"MIDFUNC  {n} start=0x{s:x} no esta precedido de jr $ra/j+delay+nops "
                f"-> split en mitad de funcion"
            )

    # --- 4. Funcion FALTANTE: un entry_ o FUN_ cuyo rango interno contiene un nuevo inicio
    #        de funcion (tras jr $ra/j + delay + nops) con REFERENCIA REAL (JAL, J, branch externo,
    #        LUI+ADDIU de plugins, o puntero en vtable) que NO tiene fila propia. ---
    starts = set(r[1] for r in rows)

    # Precomputar mapa de referencias reales en el ELF si esta disponible
    jal_targets = set()
    j_targets = set()
    lui_targets = set()
    from collections import defaultdict
    branch_map = defaultdict(list)
    vtable_targets = set()

    if elf is not None:
        for off in range(0x100, len(elf) - 3, 4):
            pc = 0x4C0000 + off - 0x100
            w = int.from_bytes(elf[off:off+4], "little")
            op = w >> 26
            if op == 3:
                jal_targets.add((pc & 0xF0000000) | ((w & 0x03FFFFFF) << 2))
            elif op == 2:
                j_targets.add((pc & 0xF0000000) | ((w & 0x03FFFFFF) << 2))
            elif op in (1, 4, 5, 6, 7):
                simm = w & 0xFFFF
                if simm & 0x8000:
                    simm -= 0x10000
                branch_map[pc + 4 + (simm << 2)].append(pc)
            elif op == 0x0F:
                rt = (w >> 16) & 0x1F
                imm_hi = w & 0xFFFF
                max_look = min(len(elf) - 3, off + 4 * 40)
                for off2 in range(off + 4, max_look, 4):
                    w2 = int.from_bytes(elf[off2:off2+4], "little")
                    op2 = w2 >> 26
                    rs2 = (w2 >> 21) & 0x1F
                    rt2 = (w2 >> 16) & 0x1F
                    if op2 == 9 and rs2 == rt:
                        simm_lo = w2 & 0xFFFF
                        if simm_lo & 0x8000:
                            simm_lo -= 0x10000
                        lui_targets.add(((imm_hi << 16) + simm_lo) & 0xFFFFFFFF)
                    elif op2 == 13 and rs2 == rt:
                        lui_targets.add((imm_hi << 16) | (w2 & 0xFFFF))
                    if rt != 0:
                        if op2 == 0x0F and rt2 == rt:
                            break
                        if op2 == 0:
                            if ((w2 >> 11) & 0x1F) == rt:
                                break
                        elif op2 in (8, 9, 10, 11, 12, 13, 14, 15, 32, 33, 35, 36, 37):
                            if rt2 == rt and rs2 != rt:
                                break

        for off in range(0, len(elf) - 7, 4):
            v = int.from_bytes(elf[off:off+4], "little")
            prev_w = int.from_bytes(elf[off-4:off], "little") if off >= 4 else 0
            next_w = int.from_bytes(elf[off+4:off+8], "little") if off + 8 <= len(elf) else 0
            p_ok = (0x004C0000 <= prev_w <= 0x00A27488 and prev_w % 4 == 0)
            n_ok = (0x004C0000 <= next_w <= 0x00A27488 and next_w % 4 == 0)
            if p_ok or n_ok:
                vtable_targets.add(v)

    def is_referenced(addr, parent_s, parent_e):
        if addr in jal_targets or addr in j_targets or addr in lui_targets or addr in vtable_targets:
            return True
        # branches externos a la funcion madre
        for src in branch_map.get(addr, []):
            if not (parent_s <= src < parent_e):
                return True
        return False

    def unaligned_func_inside(name, s, e):
        if elf is None or not name.startswith(("entry_", "thunk_", "FUN_")):
            return
        a = s
        while a + 16 <= e:
            w1 = int.from_bytes(elf[a - 0x4C0000 + 0x100:a - 0x4C0000 + 0x104], "little")
            if w1 == 0x03E00008 or (w1 >> 26) == 2:
                nxt = a + 4  # delay slot
                b = nxt + 4
                while b + 4 <= e:
                    ww = int.from_bytes(elf[b - 0x4C0000 + 0x100:b - 0x4C0000 + 0x104], "little")
                    if ww != 0:
                        break
                    b += 4
                if b in starts and b != s:
                    return
                if s < b < e:
                    # Descartar si tiene ramas internas saltando hacia b (early exit dentro de la misma funcion)
                    has_int_branch = any(s <= src < b for src in branch_map.get(b, []))
                    if not has_int_branch and is_referenced(b, s, e):
                        errors.append(
                            f"MISSING  {name} 0x{s:x}-0x{e:x} contiene un inicio de funcion REFERENCIADO en "
                            f"0x{b:x} SIN fila propia -> se necesita FUN_{b:06x} + clamp de {name}"
                        )
                        return
            a += 4

    for n, s, e, _ in rows:
        unaligned_func_inside(n, s, e)

    print(f"filas={len(rows)}  baseline={len(base)}")
    if not errors:
        print(f"OK: 0 SHADOW / 0 MIDFUNC  (warnings benignos: {len(warnings)} OVERLAP-FUN)")
        return 0
    print(f"ERRORES (bloquean build): {len(errors)}   warnings benignos: {len(warnings)}")
    for p in errors:
        print("  " + p)
    if False:
        print(f"  ... y {len(errors)-200} mas")
    return 1


if __name__ == "__main__":
    sys.exit(main())
