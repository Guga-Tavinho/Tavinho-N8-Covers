"""Teste das cores editadas à mão (painel de paletas do gerador_firmware_capas.py).

- sb.aplicar com as paletas originais reproduz o nível calculado (quadros, média, ΔE, tremido);
- record_v3 / record_v2 com uma cor trocada: só os bytes de paleta mudam, e a prévia mostra a cor nova;
- gerar_covers.py --paletas usa o arquivo salvo (e ignora se a imagem mudou).
uso: python teste_paletas_editadas.py
"""
import json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_flicker_barra as sb
import conv_v2, conv_v3

AQUI = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(sb.ROOT, 'imagens', 'Super Mario Bros. 3 (USA).png')
CHR0 = open(os.path.join(sb.ROOT, 'firmware_base', 'EDFC', 'OS.BIN'), 'rb').read()[:0x1000]
CRC = 0x60E6D5A5
ok = True


def check(c, m):
    global ok
    print(('  OK   ' if c else '  FALHA') + ' ' + m); ok &= bool(c)


def main():
    T = sb.capa(SRC)
    print('== aplicar() sem mudanças = nível calculado')
    for lam in (0.22, None):
        n = sb.nivel(T, lam)
        e = sb.aplicar(n, T, sb.paletas(n))
        check(e['A'] == n['A'] and e['B'] == n['B'] and e['P'] == n['P'] and e['erro'] == n['erro']
              and e['tremor'] == n['tremor'], 'λ=%s: quadros, média, ΔE e tremido iguais' % lam)

    print('\n== record_v3 com uma cor trocada')
    n = sb.nivel(T, 0.22)
    pals = sb.paletas(n)
    base, prev0 = conv_v3.record_v3(T, CRC, CHR0, lam=0.22)
    mesmo, _ = conv_v3.record_v3(T, CRC, CHR0, lam=0.22, pals=sb.paletas(n))
    check(mesmo == base, 'paletas originais: registro idêntico')
    velho = pals['A']['sp'][1][0]
    novo = 0x30 if velho != 0x30 else 0x16
    pals['A']['sp'][1][0] = novo
    rec, prev = conv_v3.record_v3(T, CRC, CHR0, lam=0.22, pals=pals)
    dif = [i for i in range(len(rec)) if rec[i] != base[i]]
    off = 256 + 12 + 4 * 1 + 1                     # paletas A: fundo 1-2 (8) + OS 3 (4) + sprite 1, espaço 1
    check(dif == [off] and rec[off] == novo, 'só o byte da cor muda (offset %d: $%02X -> $%02X)' % (off, velho, novo))
    e = sb.aplicar(n, T, pals)
    check([[list(c) for c in r] for r in prev] == e['P'], 'prévia do registro = o que a ferramenta mostra')

    print('\n== pontos pintados no quadro A (onde ele mostra o fundo fixo $0F)')
    e = n['est']
    pts = [(x, y) for y in range(96) for x in range(64)
           if not e['A']['spr'][y][x] and e['bg'][y][x] == 0 and e['B']['spr'][y][x]]
    check(len(pts) > 0, '%d pontos com $0F fixo no quadro A e sprite no B' % len(pts))
    pp = sb.paletas(n)
    pp['pix']['A'] = [[x, y, 2] for x, y in pts]
    rp, prp = conv_v3.record_v3(T, CRC, CHR0, lam=0.22, pals=pp)
    dif = [i for i in range(len(rp)) if rp[i] != base[i]]
    check(dif and all(512 <= i < 2048 for i in dif), 'só os tiles de sprite do quadro A mudam (%d bytes)' % len(dif))
    ep = sb.aplicar(n, T, pp)
    check(all(ep['A'][y][x] == pp['A']['sp'][e['sp_assign'][(y // 16) * 8 + x // 8]][1] for x, y in pts),
          'os pontos do quadro A ficam com a cor do espaço 2 do sprite do bloco')
    check([[list(c) for c in r] for r in prp] == ep['P'], 'prévia do registro = o que a ferramenta mostra')

    print('\n== record_v2 com uma cor trocada')
    n2 = sb.nivel(T, None)
    p2 = sb.paletas(n2)
    b2, _ = conv_v2.record_v2(T, CRC, CHR0)
    v = p2['A']['bg'][0][2]
    p2['A']['bg'][0][2] = 0x30 if v != 0x30 else 0x16
    r2, pr2 = conv_v2.record_v2(T, CRC, CHR0, p2)
    dif = [i for i in range(len(r2)) if r2[i] != b2[i]]
    check(dif == [256 + 3] and r2[259] == p2['A']['bg'][0][2], 'só o byte da cor muda (fundo 1, espaço 3)')
    check([[list(c) for c in r] for r in pr2] == sb.aplicar(n2, T, p2)['P'], 'prévia = o que a ferramenta mostra')

    print('\n== gerar_covers.py --paletas')
    with tempfile.TemporaryDirectory() as tmp:
        capas = os.path.join(tmp, 'capas'); os.makedirs(capas)
        import shutil
        shutil.copy(SRC, capas)
        pd = os.path.join(capas, 'paletas_editadas'); os.makedirs(pd)
        d = dict(nome=os.path.basename(SRC), lam=0.22, chave=conv_v3.chave_paletas(T), **pals)
        json.dump(d, open(conv_v3.arquivo_paletas(pd, 'Super Mario Bros. 3 (USA)', 0.22), 'w'))
        out = os.path.join(tmp, 'C.BIN')
        r = subprocess.run([sys.executable, os.path.join(AQUI, 'gerar_covers.py'), capas, '--v3', '--lambda', '0.22',
                            '-o', out], capture_output=True, text=True, encoding='utf-8')
        cov = open(out, 'rb').read()
        check('paletas editadas à mão: Super Mario Bros. 3 (USA).png' in r.stdout, 'gerador avisa que usou a edição')
        check(cov[256 * 512:256 * 512 + 8192] == rec, 'COVERS.BIN com a cor editada')
        d['chave'] = 'outra'
        json.dump(d, open(conv_v3.arquivo_paletas(pd, 'Super Mario Bros. 3 (USA)', 0.22), 'w'))
        r = subprocess.run([sys.executable, os.path.join(AQUI, 'gerar_covers.py'), capas, '--v3', '--lambda', '0.22',
                            '-o', out], capture_output=True, text=True, encoding='utf-8')
        cov = open(out, 'rb').read()
        check('ignoradas' in r.stdout and cov[256 * 512:256 * 512 + 8192] == base,
              'imagem mudou: edição ignorada com aviso')
    print('\nRESULTADO:', 'TUDO OK' if ok else 'HÁ FALHAS')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
