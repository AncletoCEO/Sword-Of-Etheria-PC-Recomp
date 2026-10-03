#!/usr/bin/env python3
"""Divide monstruos del recompilado (>THRESHOLD) en partes + dispatcher.

Formato de entrada (emitido por ps2_recomp): una funcion void por .cpp con
`switch (ctx->pc) { case 0xADDRu: goto label_ADDR; ... default: break; }`
seguido de bloques `label_ADDR:` que caen por fall-through. Temporales
declarados dentro de `{ ... }`, asi que partir por labels es seguro.

Transformacion por chunk:
  - `goto label_X` mismo chunk -> se deja
  - `goto label_X` otro chunk/desconocido -> `ctx->pc = 0xX; return true;`
  - `return;` -> `return false;` (salida real de la funcion)
  - fin de chunk (no ultimo) -> `ctx->pc = FIRST_NEXT; return true;`
  - ultimo chunk -> `return false;` al final
Dispatcher (conserva nombre/firma original, loop plano sin stack growth):
  while (pc en [START, END)) rutea por rangos al chunk y repite si devuelve true.
"""
import re
import sys
from pathlib import Path

PART_BYTES = 3 * 1024 * 1024   # partes de 3 MB → ~1 GB RAM por worker, seguro con -j4
THRESHOLD = 4 * 1024 * 1024    # dividir todo >4 MB (cubre los 9 MB que sobrevivieron)
SKIP_FILES = {"register_functions.cpp"}

SIG_RE = re.compile(
    r"^void (\w+)\(uint8_t\* rdram, R5900Context\* ctx, PS2Runtime \*runtime\) \{$",
    re.M,
)
RANGE_RE = re.compile(r"^// Address: 0x([0-9a-fA-F]+) - 0x([0-9a-fA-F]+)", re.M)
CASE_RE = re.compile(r"case 0x([0-9a-fA-F]+)u?: goto label_([0-9a-fA-F]+);")
LABEL_RE = re.compile(r"^label_([0-9a-fA-F]+):", re.M)
GOTO_RE = re.compile(r"goto label_([0-9a-fA-F]+);")


def split_file(path: Path) -> list[str]:
    text = path.read_text()
    m = SIG_RE.search(text)
    if not m:
        print(f"SKIP {path.name}: sin firma reconocida")
        return []
    name = m.group(1)
    header = text[: m.start()]
    rm = RANGE_RE.search(text)
    if rm:
        start, end = int(rm.group(1), 16), int(rm.group(2), 16)
    else:
        addrs = [int(a, 16) for a, _ in CASE_RE.findall(text)]
        start, end = min(addrs), max(addrs) + 4

    labels = [(lm.start(), lm.group(1).lower()) for lm in LABEL_RE.finditer(text)]
    if not labels:
        print(f"SKIP {path.name}: sin labels")
        return []
    # Bloques: desde cada label hasta el siguiente label (o fin de funcion).
    blocks: list[tuple[str, str]] = []
    for i, (pos, addr) in enumerate(labels):
        stop = labels[i + 1][0] if i + 1 < len(labels) else len(text)
        blocks.append((addr, text[pos:stop]))
    # Quitar la llave final de funcion del ultimo bloque (queda en dispatcher/part).
    if blocks[-1][1].rstrip().endswith("}"):
        addr, body = blocks[-1]
        blocks[-1] = (addr, body.rstrip()[: -1])

    # Particion por tamanio acumulado.
    chunks: list[list[int]] = [[0]]
    acc = len(blocks[0][1])
    for i in range(1, len(blocks)):
        if acc + len(blocks[i][1]) > PART_BYTES:
            chunks.append([])
            acc = 0
        chunks[-1].append(i)
        acc += len(blocks[i][1])
    if len(chunks) < 2:
        print(f"SKIP {path.name}: una sola parte ({len(text)/2**20:.0f}MB)")
        return []
    chunk_of = {}
    for k, idxs in enumerate(chunks):
        for i in idxs:
            chunk_of[blocks[i][0]] = k

    def xform(body: str, k: int) -> str:
        def rep_goto(gm):
            tgt = gm.group(1).lower()
            if chunk_of.get(tgt, -1) == k:
                return gm.group(0)
            return f"{{ ctx->pc = 0x{tgt}u; return true; }}"
        body = GOTO_RE.sub(rep_goto, body)
        body = body.replace("return;", "return false;")
        return body

    base = path.stem  # e.g. FUN_006cc400_0x6cc400
    bounds: list[int] = []  # primera addr de cada chunk
    out_files: list[str] = []
    for k, idxs in enumerate(chunks):
        first_addr = blocks[idxs[0]][0]
        bounds.append(int(first_addr, 16))
        parts = [header, f"bool {name}_p{k}(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime) {{\n"]
        parts.append("    switch (ctx->pc) {\n")
        for i in idxs:
            a = blocks[i][0]
            parts.append(f"        case 0x{a}u: goto label_{a};\n")
        parts.append("        default: return false;\n    }\n")
        for i in idxs:
            parts.append(xform(blocks[i][1], k))
        if k + 1 < len(chunks):
            nxt = blocks[chunks[k + 1][0]][0]
            parts.append(f"\n    ctx->pc = 0x{nxt}u;\n    return true;\n}}\n")
        else:
            parts.append("\n    return false;\n}\n")
        p = path.with_name(f"{base}_p{k}.cpp")
        p.write_text("".join(parts))
        out_files.append(p.name)

    disp = [header]
    for k in range(len(chunks)):
        disp.append(f"bool {name}_p{k}(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime);\n")
    disp.append(f"void {name}(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime) {{\n")
    disp.append("#ifdef PS2_FUNCTION_LOG_TRACKER\n")
    disp.append(f'    PS_LOG_ENTRY("{name}");\n')
    disp.append("#endif\n")
    disp.append(f"    while (ctx->pc >= 0x{start:x}u && ctx->pc < 0x{end:x}u) {{\n")
    disp.append("        bool cont = false;\n")
    for k in range(len(chunks)):
        kw = "if" if k == 0 else "else if"
        if k + 1 < len(chunks):
            disp.append(f"        {kw} (ctx->pc < 0x{bounds[k+1]:x}u) {{ cont = {name}_p{k}(rdram, ctx, runtime); }}\n")
        else:
            disp.append(f"        else {{ cont = {name}_p{k}(rdram, ctx, runtime); }}\n")
    disp.append("        if (!cont) { return; }\n    }\n}\n")
    path.write_text("".join(disp))
    print(f"SPLIT {path.name}: {len(text)/2**20:.0f}MB -> {len(chunks)} partes")
    return out_files


def main() -> int:
    gendir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("work/generated")
    files = sorted(
        p for p in gendir.glob("*.cpp")
        if p.stat().st_size > THRESHOLD and p.name not in SKIP_FILES
    )
    print(f"monstruos a dividir: {len(files)}")
    total_parts = 0
    for p in files:
        total_parts += len(split_file(p))
    print(f"partes generadas: {total_parts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
