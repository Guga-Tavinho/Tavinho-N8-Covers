"""Mapeia funções de um build do OS para outro (código deslocado).
Compara a sequência de instruções de cada função, ignorando operandos absolutos >= $0200 (código e variáveis em RAM)
(que mudam quando o código se desloca).

uso: python map_funcs.py OS_antigo.BIN nomes_antigos.txt OS_novo.BIN nomes_novos.txt
"""
import sys
sys.path.insert(0, __import__('os').path.dirname(__file__))
from dis6502 import OPS, LEN


def norm(prg, addr, n=40):
    out, a = [], addr
    for _ in range(n):
        o = a - 0x8000
        if o < 0 or o >= len(prg): break
        c = prg[o]
        if c not in OPS: out.append(('db', c)); a += 1; continue
        m, mode = OPS[c]; ln = LEN[mode]; b = prg[o:o + ln]
        if mode in ('abs', 'abx', 'aby', 'ind') and len(b) == 3 and (b[1] | b[2] << 8) >= 0x0200:
            out.append((c, '*'))
        else:
            out.append(tuple(b))
        a += ln
        if m in ('RTS', 'RTI', 'JMP'): break
    return tuple(out)


def main():
    old = open(sys.argv[1], 'rb').read()[0x6000:]
    new = open(sys.argv[3], 'rb').read()[0x6000:]
    names = []
    for line in open(sys.argv[2], encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#'):
            a, n = line.split()[:2]; names.append((int(a, 16), n))
    # índice de todas as posições candidatas no novo PRG
    cache = {}
    def sig_at(a, n):
        k = (a, n)
        if k not in cache: cache[k] = norm(new, a, n)
        return cache[k]
    out, miss = [], []
    for a, n in names:
        found = None
        for ln in (40, 24, 12):
            sig = norm(old, a, ln)
            hits = [x for x in range(0x8000, 0x8000 + len(new)) if new[x - 0x8000] == old[a - 0x8000] and sig_at(x, ln) == sig]
            if len(hits) == 1: found = hits[0]; break
            if len(hits) > 1:
                # vários iguais: escolhe o mais próximo do deslocamento das vizinhas
                found = min(hits, key=lambda x: abs((x - a) - (out[-1][2] - out[-1][0] if out else 0)))
                break
        if found is None: miss.append((a, n))
        else: out.append((a, n, found))
    with open(sys.argv[4], 'w', encoding='utf-8') as f:
        f.write('# gerado por map_funcs.py a partir de %s\n' % sys.argv[2])
        for a, n, x in out: f.write('%04x %s\n' % (x, n))
    for a, n, x in out: print('%04X -> %04X  (%+5d) %s' % (a, x, x - a, n))
    print('sem correspondência:', ', '.join('%04X %s' % m for m in miss) or 'nenhuma')


if __name__ == '__main__':
    main()
