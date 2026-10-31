"""Mini-assembler 6502 de duas passagens (para patches do OS do EverDrive).

Sintaxe por linha:
  rotulo:                 define rótulo (pode vir antes de uma instrução na mesma linha)
  LDA #$10 / LDA #<rot / LDA #>rot
  LDA $12 (zp) / LDA $1234 / LDA rot / LDA rot+1 / LDA rot,X / LDA ($30),Y / JMP (rot)
  BNE rot                 desvio relativo (erro se passar de -128..127)
  .byte $01,2,'A'  .word rot,$1234  .text "ABC"  (texto sem terminador)  .asciz "ABC"
  ; comentário
Constantes: NOME = $1234 (antes do uso ou em qualquer lugar).
"""
import re
from dis6502 import OPS, LEN

BY_NAME = {}
for code, (m, mode) in OPS.items():
    BY_NAME[(m, mode)] = code
BRANCHES = {'BPL', 'BMI', 'BVC', 'BVS', 'BCC', 'BCS', 'BNE', 'BEQ'}


class AsmError(Exception):
    pass


def assemble(src, org, symbols=None, strict=True):
    """Retorna (bytes, tabela_de_simbolos). strict=False: símbolo indefinido vale $FFFF (montagem
    de vários segmentos que se referenciam; repita até a tabela estabilizar e termine com strict=True)."""
    syms = dict(symbols or {})
    lines = []
    for n, raw in enumerate(src.splitlines(), 1):
        line = re.sub(r';.*', '', raw).rstrip() if '"' not in raw else _strip_comment(raw)
        if not line.strip():
            continue
        m = re.match(r'^\s*([A-Za-z_]\w*)\s*=\s*(.+)$', line)
        if m:
            lines.append((n, 'const', m.group(1), m.group(2)))
            continue
        m = re.match(r'^\s*([A-Za-z_]\w*):(.*)$', line)
        if m:
            lines.append((n, 'label', m.group(1), None))
            line = m.group(2)
            if not line.strip():
                continue
        lines.append((n, 'ins', line.strip(), None))

    def value(expr, final):
        expr = expr.strip()
        if expr.startswith('<'): return value(expr[1:], final) & 0xFF
        if expr.startswith('>'): return (value(expr[1:], final) >> 8) & 0xFF
        total = 0
        for sign, tok in re.findall(r'([+-]?)\s*([^+-]+)', expr):
            tok = tok.strip()
            if tok.startswith('$'): v = int(tok[1:], 16)
            elif tok.startswith('%'): v = int(tok[1:], 2)
            elif re.fullmatch(r'\d+', tok): v = int(tok)
            elif re.fullmatch(r"'.'", tok): v = ord(tok[1])
            elif tok in syms: v = syms[tok]
            elif not final or not strict: return 0xFFFF  # indefinido: assume endereço absoluto
            else: raise AsmError('símbolo indefinido: ' + tok)
            total = total - v if sign == '-' else total + v
        return total & 0xFFFF

    def is_zp_literal(expr):
        e = expr.strip()
        return e.startswith('$') and len(e) <= 3 and re.fullmatch(r'\$[0-9A-Fa-f]{1,2}', e)

    def encode(text, pc, final):
        parts = text.split(None, 1)
        op = parts[0].upper(); arg = parts[1].strip() if len(parts) > 1 else ''
        if op == '.BYTE':
            return bytes(value(a, final) & 0xFF for a in _split_args(arg))
        if op == '.WORD':
            out = b''
            for a in _split_args(arg):
                v = value(a, final); out += bytes([v & 0xFF, v >> 8])
            return out
        if op in ('.TEXT', '.ASCIZ'):
            s = re.fullmatch(r'"(.*)"', arg).group(1).encode('ascii')
            return s + (b'\0' if op == '.ASCIZ' else b'')
        if op in BRANCHES:
            target = value(arg, final); off = target - (pc + 2)
            if final and not -128 <= off <= 127:
                raise AsmError('desvio longe demais: %s -> %04X' % (text, target))
            return bytes([BY_NAME[(op, 'rel')], off & 0xFF])
        if arg == '' or arg.upper() == 'A':
            mode = 'acc' if arg.upper() == 'A' and (op, 'acc') in BY_NAME else 'imp'
            if (op, mode) not in BY_NAME: mode = 'acc'
            return bytes([BY_NAME[(op, mode)]])
        if arg.startswith('#'):
            return bytes([BY_NAME[(op, 'imm')], value(arg[1:], final) & 0xFF])
        m = re.fullmatch(r'\((.+)\),\s*[Yy]', arg)
        if m: return bytes([BY_NAME[(op, 'izy')], value(m.group(1), final) & 0xFF])
        m = re.fullmatch(r'\((.+),\s*[Xx]\)', arg)
        if m: return bytes([BY_NAME[(op, 'izx')], value(m.group(1), final) & 0xFF])
        m = re.fullmatch(r'\((.+)\)', arg)
        if m:
            v = value(m.group(1), final); return bytes([BY_NAME[(op, 'ind')], v & 0xFF, v >> 8])
        m = re.fullmatch(r'(.+),\s*([XxYy])', arg)
        base, idx = (m.group(1), m.group(2).upper()) if m else (arg, None)
        v = value(base, final)
        zp = is_zp_literal(base) or v < 0x100   # rótulo ainda indefinido vale $FFFF -> absoluto
        if idx is None:
            if zp and (op, 'zp') in BY_NAME: return bytes([BY_NAME[(op, 'zp')], v])
            return bytes([BY_NAME[(op, 'abs')], v & 0xFF, v >> 8])
        if zp and (op, 'zp' + idx.lower()) in BY_NAME:
            return bytes([BY_NAME[(op, 'zp' + idx.lower())], v])
        key = (op, 'ab' + idx.lower())
        if key not in BY_NAME: raise AsmError('modo inválido: ' + text)
        return bytes([BY_NAME[key], v & 0xFF, v >> 8])

    out = b''
    for final in (False, True):
        pc = org; out = b''
        for n, kind, a, b in lines:
            try:
                if kind == 'const':
                    syms[a] = value(b, final)
                elif kind == 'label':
                    if final and syms.get(a) != pc: raise AsmError('rótulo instável: ' + a)
                    syms[a] = pc
                else:
                    enc = encode(a, pc, final); out += enc; pc += len(enc)
            except (AsmError, KeyError, AttributeError) as e:
                raise AsmError('linha %d: %s (%s)' % (n, a, e))
    return out, syms


def _split_args(s):
    return [x.strip() for x in re.findall(r"'.'|[^,]+", s) if x.strip()]


def _strip_comment(raw):
    out, q = '', False
    for ch in raw:
        if ch == '"': q = not q
        if ch == ';' and not q: break
        out += ch
    return out.rstrip()
