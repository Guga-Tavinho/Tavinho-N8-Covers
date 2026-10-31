"""Simulação: capa GRANDE dentro do navegador (junto com a lista de jogos), com as regras da PPU.

Tela do navegador: lista nas linhas 2-22 (cursor na coluna 1, nomes a partir da 2), barra cinza nas linhas 24-27
(paleta 3), nome completo nas 25-26. A capa grande: 112x160 em x=136, y=16 (linhas 2-21, colunas 17-30); os nomes
da lista ficam com 14 colunas (2-15).
Cores: a paleta 0 é do texto (preto, $10, $28) e a 3 é da barra (preto, $30, $00, $28): fixas. Só as paletas 1 e 2
ficam livres para a capa (cada bloco 16x16 da capa pode usar qualquer uma das 4).
  - sem flicker: 1 e 2 com 3 cores cada;
  - com flicker: 1 e 2 alternam entre dois conjuntos de cores a cada quadro (como a v3 faz) -> cada cor vista é a
    mistura de duas cores do NES (com penalidade para pares muito diferentes, que tremem mais).
Tiles: 280 por capa; com 63 livres por banco (a fonte do OS ocupa o resto), a troca de banco no meio da tela a
cada 3 linhas de tiles (POC de tela cheia) dá conta.

uso:  python sim_navegador_grande.py      saída: debug/comparacao_capa_grande_navegador.png
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_tela_cheia as S
from build_poc import NES_RGB, ROOT, COVER_X, COVER_Y
from sim_flicker import avg_color
from gerar_covers import cover_record

CAPAS = os.path.join(ROOT, 'imagens', 'Named_Boxarts')
OS_BIN = os.path.join(ROOT, 'firmware_base', 'EDFC', 'OS.BIN')
CX, CY, CW, CH = 136, 16, 112, 160                    # capa grande
BX, BW = 128, 128                                     # blocos 16x16 que a capa ocupa (x 128-255)
PAL0 = [0x0F, 0x10, 0x0F, 0x28]                       # texto
PAL3 = [0x0F, 0x30, 0x00, 0x28]                       # barra de baixo
NES = {i: ((c >> 16) & 255, (c >> 8) & 255, c & 255) for i, c in enumerate(NES_RGB)}
PRETO = 0x0F
LAMBDA = 0.25


def candidatos(flicker):
    """Cores possíveis por posição de paleta: NES (sem flicker) ou pares (a, b) com a cor média vista."""
    cores = [i for i, _ in S.CORES]
    if not flicker:
        return [(c, c) for c in cores], np.array([NES[c] for c in cores], float), np.zeros(len(cores))
    pares = [(a, b) for k, a in enumerate(cores) for b in cores[k:]]
    rgb = np.array([avg_color(a, b) for a, b in pares], float)
    la, lb = S.lab(np.array([NES[a] for a, _ in pares], float)), S.lab(np.array([NES[b] for _, b in pares], float))
    pen = LAMBDA * ((la - lb) ** 2).sum(1)                         # par que treme muito custa mais
    return pares, rgb, pen


def converter(img, flicker):
    """img (160x112x3) -> imagem vista (com as 4 paletas, 0 e 3 fixas) e as paletas A/B escolhidas."""
    tela = np.zeros((CH, BW, 3)); tela[:, CX - BX:CX - BX + CW] = img
    h, w = CH, BW
    pares, rgb, pen = candidatos(flicker)
    L = S.lab(tela).reshape(-1, 3)
    D = ((L[:, None, :] - S.lab(rgb)[None, :, :]) ** 2).sum(-1).astype(np.float32) + pen[None, :].astype(np.float32)
    idx = {p: k for k, p in enumerate(pares)}
    canon = {i: next(k for k, r in S.CORES if r == NES[i]) for i in NES if NES[i] in [r for _, r in S.CORES]}
    pk = lambda c: idx[(canon[c], canon[c])]                   # cores repetidas do NES (pretos) viram uma só
    bg = pk(PRETO)
    fixa = {0: [pk(c) for c in PAL0[1:]], 3: [pk(c) for c in PAL3[1:]]}
    blocos = []
    for by in range(0, h, 16):
        for bx in range(0, w, 16):
            ys, xs = np.mgrid[by:by + 16, bx:bx + 16]
            blocos.append((ys * w + xs).ravel())
    dbg = D[:, bg]
    err = lambda b, p: np.minimum(dbg[b], D[b][:, p].min(1)).sum()

    def gulosa(b):
        m = dbg[b].copy(); esc = []
        for _ in range(3):
            k = int(np.argmin(np.minimum(m[:, None], D[b]).sum(0))); esc.append(k); m = np.minimum(m, D[b, k])
        return esc
    melhor = None
    for t in range(3):
        base = np.array([min(err(b, fixa[0]), err(b, fixa[3])) for b in blocos])
        ordem = np.argsort(-base)
        ini = [ordem[0], ordem[min(len(ordem) - 1, 1 + t * 3)]]
        pals = {0: fixa[0], 1: gulosa(blocos[ini[0]]), 2: gulosa(blocos[ini[1]]), 3: fixa[3]}
        for _ in range(8):
            e = np.array([[err(b, pals[q]) for q in range(4)] for b in blocos]); esc = e.argmin(1)
            for q in (1, 2):
                sel = np.where(esc == q)[0]
                if not len(sel): continue
                ii = np.concatenate([blocos[i] for i in sel])
                for s in range(3):
                    outras = [pals[q][j] for j in range(3) if j != s]
                    m = np.minimum(dbg[ii], D[ii][:, outras].min(1))
                    pals[q][s] = int(np.argmin(np.minimum(m[:, None], D[ii]).sum(0)))
        e = np.array([[err(b, pals[q]) for q in range(4)] for b in blocos]); esc = e.argmin(1)
        tot = e.min(1).sum()
        if melhor is None or tot < melhor[0]: melhor = (tot, {q: list(p) for q, p in pals.items()}, esc)
    _, pals, esc = melhor
    vista = np.zeros((h * w, 3))
    for b, q in zip(blocos, esc):
        cores = [bg] + pals[q]
        vista[b] = rgb[np.array(cores)[D[b][:, cores].argmin(1)]]
    return vista.reshape(h, w, 3).astype(np.uint8), {q: [pares[k] for k in p] for q, p in pals.items()}


def fonte():
    b = open(OS_BIN, 'rb').read()
    return b[0:0x1000]


def tela_texto(nomes, sel, largura):
    """Tela do navegador só com o texto (índices NES), como o OS desenha."""
    chr0 = fonte()
    buf = bytearray(0x400)
    for i, n in enumerate(nomes[:21]):
        row = 2 + i
        if i == sel: buf[row * 32 + 1] = ord('>')
        for k, ch in enumerate(n[:largura]): buf[row * 32 + 2 + k] = ord(ch) + (0x80 if i == sel else 0)
    nome = nomes[sel]
    for k, ch in enumerate(nome[:30]): buf[25 * 32 + 1 + k] = ord(ch)
    for k, ch in enumerate(nome[30:60]): buf[26 * 32 + 1 + k] = ord(ch)
    img = np.zeros((240, 256, 3), np.uint8)
    for y in range(240):
        pal = PAL3 if 24 <= y // 8 <= 27 else PAL0
        for tx in range(32):
            t = buf[(y // 8) * 32 + tx]
            lo, hi = chr0[t * 16 + y % 8], chr0[t * 16 + 8 + y % 8]
            for x in range(8):
                c = ((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1)
                img[y, tx * 8 + x] = NES[pal[c] if c else pal[0]]
    return img


def main():
    try:
        nomes = sorted(os.path.splitext(f)[0] + '.nes' for f in os.listdir(os.path.join(ROOT, 'firmware_gerada', 'previews')))
    except OSError:
        nomes = ['Super Mario Bros 3 (U) (PRG 0).nes']
    jogos = [('Super Mario Bros 3 (U) (PRG 0).nes', 'Super Mario Bros. 3 (USA).png'),
             ('Mega Man 2 (U).nes', 'Mega Man 2 (USA).png'),
             ('Castlevania (U) (PRG 0).nes', 'Castlevania (USA).png')]
    try:
        f = lambda t: ImageFont.truetype('segoeui.ttf', t)
        f(10)
    except OSError:
        f = lambda t: ImageFont.load_default()
    Z, gap, topo = 2, 16, 70
    cols = ['Hoje (capa 64x96, nomes com 20 letras)', 'Grande 112x160, sem flicker (nomes com 14)',
            'Grande 112x160, com flicker']
    folha = Image.new('RGB', (3 * 512 + 4 * gap, topo + len(jogos) * (480 + gap) + 40), (24, 21, 18))
    d = ImageDraw.Draw(folha)
    d.text((gap, 10), 'Capa grande no navegador (simulação com as regras da PPU: paletas 0 e 3 são do texto e da barra; '
                      'só 1 e 2 livres para a capa)', fill=(230, 170, 60), font=f(20))
    for c, t in enumerate(cols): d.text((gap + c * (512 + gap), topo - 24), t, fill=(240, 232, 220), font=f(15))
    for j, (rom, capa) in enumerate(jogos):
        print(rom, flush=True)
        path = os.path.join(CAPAS, capa)
        sel = nomes.index(rom) if rom in nomes else 0
        ini = max(0, sel - 7)
        lista = nomes[ini:ini + 21]
        hoje = tela_texto(lista, sel - ini, 20)
        _, prev = cover_record(path, 0, v3=True, lam=0.22, nitidez=70)
        hoje[32:32 + 96, 176:176 + 64] = np.array(prev, np.uint8)
        img = S.carregar(path, CW, CH, 120)
        telas = [hoje]
        for flk in (False, True):
            v, pals = converter(img, flk)
            t = tela_texto(lista, sel - ini, 14)
            t[CY:CY + CH, BX:BX + BW] = v
            telas.append(t)
        y = topo + j * (480 + gap)
        for c, t in enumerate(telas):
            folha.paste(Image.fromarray(t).resize((512, 480), Image.Resampling.NEAREST), (gap + c * (512 + gap), y))
    saida = os.path.join(ROOT, 'debug', 'comparacao_capa_grande_navegador.png')
    folha.save(saida)
    print('imagem:', saida)


if __name__ == '__main__':
    main()
