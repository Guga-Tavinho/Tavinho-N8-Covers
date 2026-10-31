"""Cores editáveis da capa grande (o conta-gotas da ferramenta), sem reconverter a capa.

A conversão (conv_capa_grande.converter_v8) devolve a estrutura da capa em info['est']: índices de cor do fundo
(ind, 0-3 por ponto), a paleta de cada bloco 16x16 (esc, 0-3), as paletas 1 e 2 (bg), a 3ª cor da paleta 3 (c3),
os sprites [(faixa, coluna, paleta, índices A 16x8, índices B 16x8)] e as paletas de sprite dos quadros A e B.
Trocar uma cor de paleta não muda tiles nem sprites: só os bytes de paleta do registro (setor 0: [3:9] paletas 1 e
2, [367] cor livre da paleta 3; setor 15: [256:272] paletas de sprite A, [304:320] B). A paleta 0 (texto), o
branco e o cinza da paleta 3 (barra) e o preto do fundo são da firmware: fixos.

Paletas (dict): bg = [[3], [3]], c3 = n, A = [[3] x 4], B = [[3] x 4] (cores NES). Sem flicker, B = A.
Edição salva em <capas>/paletas_editadas_grande/<capa>.F<força>.<sem | L<λ>>.json = {orig, novo}: só vale se a
conversão de agora tiver as mesmas paletas originais (senão a capa mudou e a edição é ignorada).
"""
import json, os
import numpy as np
import sim_navegador_grande as N
import conv_sprites_grande as SP

PASTA = 'paletas_editadas_grande'
CW, CH, X0 = 112, 160, 8
_LIN = SP._lin(np.array([N.NES[i] for i in range(64)], float))         # cor NES -> RGB linear


def paletas(est):
    return dict(bg=[list(p) for p in est['bg']], c3=int(est['c3']), A=[list(p) for p in est['spA']],
                B=[list(p) for p in (est['spB'] if est['flicker'] else est['spA'])])


def copia(p):
    return json.loads(json.dumps(p))


def renderizar(est, pals):
    """-> (quadro A, quadro B, percebida) RGB uint8 112x160 (CH x CW x 3), como na TV (média dos 2 quadros)."""
    tab = np.array([N.PAL0, [0x0F] + pals['bg'][0], [0x0F] + pals['bg'][1], N.PAL3[:3] + [pals['c3']]])
    esc = np.repeat(np.repeat(est['esc'], 16, 0), 16, 1)[:CH, :N.BW]
    bg = _LIN[tab[esc, est['ind']]][:, X0:X0 + CW]                       # CH x CW x 3 (linear)
    qa, qb = bg.copy(), bg.copy()
    flk = est['flicker']
    for j, i, q, a, b in est['spr']:
        ys, xs = slice(16 * j, 16 * j + 16), slice(8 * i, 8 * i + 8)
        for img, idx, pal in ((qa, a, pals['A'][q]), (qb, b if flk else a, pals['B' if flk else 'A'][q])):
            cores = _LIN[np.array([0x0F] + pal)][idx]
            img[ys, xs] = np.where(idx[..., None] > 0, cores, img[ys, xs])
    u = lambda l: SP._unlin(l).round().astype(np.uint8)
    return u(qa), u(qb), u((qa + qb) / 2)


def espaco(est, pals, quadro, x, y):
    """O que define a cor do ponto (x, y) da capa no quadro 'A'/'B': ('bg', paleta 0-1, espaço 0-2),
    ('c3',), ('sp', quadro, paleta 0-3, espaço 0-2), ou um texto (cor fixa da firmware)."""
    flk = est['flicker']
    for j, i, q, a, b in est['spr']:
        if j == y // 16 and i == x // 8:
            v = int((b if (quadro == 'B' and flk) else a)[y % 16, x % 8])
            if v: return ('sp', quadro if flk else 'A', q, v - 1)
            break
    p = int(est['esc'][y // 16, (x + X0) // 16]); c = int(est['ind'][y, x + X0])
    if c == 0: return 'preto do fundo ($0F)'
    if p == 0: return 'da paleta do texto da lista'
    if p == 3: return ('c3',) if c == 3 else 'da barra (%s)' % ('branco $30' if c == 1 else 'cinza $00')
    return ('bg', p - 1, c - 1)


def cor(pals, alvo):
    if alvo[0] == 'bg': return pals['bg'][alvo[1]][alvo[2]]
    if alvo[0] == 'c3': return pals['c3']
    return pals[alvo[1]][alvo[2]][alvo[3]]


def definir(pals, alvo, valor, flicker):
    if alvo[0] == 'bg': pals['bg'][alvo[1]][alvo[2]] = valor
    elif alvo[0] == 'c3': pals['c3'] = valor
    else:
        pals[alvo[1]][alvo[2]][alvo[3]] = valor
        if not flicker: pals['B'][alvo[2]][alvo[3]] = valor          # sem flicker os 2 quadros são iguais


def nome(alvo):
    if alvo[0] == 'bg': return 'Fundo %d, cor %d' % (alvo[1] + 1, alvo[2] + 1)
    if alvo[0] == 'c3': return 'cor livre da paleta 3 (barra)'
    return 'Sprite %d, cor %d' % (alvo[2], alvo[3] + 1)


def aplicar_reg(reg, pals):
    """Registro (64 setores) com as paletas trocadas."""
    r = bytearray(reg)
    r[3:9] = bytes(pals['bg'][0] + pals['bg'][1])
    r[367] = pals['c3']
    s = 15 * 512
    r[s + 256:s + 272] = bytes(sum(([0x0F] + p for p in pals['A']), []))
    r[s + 304:s + 320] = bytes(sum(([0x0F] + p for p in pals['B']), []))
    return bytes(r)


def arquivo(capas, png, forca, flicker, lam=SP.LAMBDA_FLK, pontilhado=False):
    stem = os.path.splitext(os.path.basename(png))[0]
    return os.path.join(capas, PASTA, '%s.F%d.%s%s.json' % (stem, forca, ('L%.3f' % lam) if flicker else 'sem',
                                                         '.P' if pontilhado else ''))


def tv(rgb):
    """Borrão aproximado de uma TV com vídeo composto (horizontal forte, vertical leve, na luz): para avaliar o
    pontilhado como ele aparece no console, não ponto a ponto."""
    l = SP._lin(np.asarray(rgb, float))
    k = np.array([1, 4, 6, 4, 1]) / 16
    p = np.pad(l, ((0, 0), (2, 2), (0, 0)), mode='edge')
    l = sum(k[i] * p[:, i:i + l.shape[1]] for i in range(5))
    p = np.pad(l, ((1, 1), (0, 0), (0, 0)), mode='edge')
    l = 0.25 * p[:-2] + 0.5 * p[1:-1] + 0.25 * p[2:]
    return SP._unlin(l).round().astype(np.uint8)


def ler(arq, orig):
    """Paletas editadas (se a edição foi feita sobre estas mesmas paletas originais) ou None."""
    try:
        d = json.load(open(arq, encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return d['novo'] if d.get('orig') == orig else None


def salvar(arq, orig, novo):
    """Grava a edição (ou apaga o arquivo, se voltou ao original)."""
    if novo == orig:
        if os.path.exists(arq): os.remove(arq)
        return
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    with open(arq, 'w', encoding='utf-8') as f: json.dump(dict(orig=orig, novo=novo), f)


def editadas(capas):
    """Nomes (sem extensão) das capas com alguma edição de cores salva."""
    d = os.path.join(capas, PASTA)
    return {f.split('.F')[0] for f in os.listdir(d) if f.endswith('.json')} if os.path.isdir(d) else set()
