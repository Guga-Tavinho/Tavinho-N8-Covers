"""Simulação: como ficaria uma capa GRANDE num visualizador próprio (firmware nova ou modo "tela cheia").

Regras da PPU respeitadas (só fundo, sem sprites e sem flicker):
  - cada bloco de 16x16 usa 1 de 4 paletas; cada paleta = cor de fundo comum + 3 cores do NES
  - tiles: todos diferentes (possível com a troca de banco de CHR no meio da tela, já confirmada no aparelho)
  - "por faixa": as 4 paletas (e a cor de fundo) trocadas a cada 48 linhas (truque de raster; experimental)
Comparado com a capa atual 64x96 (v3 com flicker, como a ferramenta gera hoje), cada uma numa tela 256x240.

uso:  python sim_tela_cheia.py [força da nitidez, padrão 70]      saída: debug/comparacao_tela_cheia[_nitidezNNN].png
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import NES_RGB, ROOT
import conv_v3
from gerar_covers import cover_record

CAPAS = os.path.join(ROOT, 'imagens', 'Named_Boxarts')
SAIDA = os.path.join(ROOT, 'debug', 'comparacao_tela_cheia.png')
JOGOS = ['Super Mario Bros. 3 (USA).png', 'Mega Man 2 (USA).png', 'Castlevania (USA).png']

# cores do NES sem repetição (os vários pretos viram um só)
CORES = []
for i, c in enumerate(NES_RGB):
    rgb = ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    if rgb not in [x for _, x in CORES] and i != 0x0D: CORES.append((i, rgb))
RGB = np.array([c for _, c in CORES], float)


def lab(rgb):
    """sRGB (0-255) -> CIELAB, para medir diferença de cor como o olho."""
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


LAB = lab(RGB)


def carregar(path, w, h, forca=70):
    """Recorte central + Lanczos + nitidez suave (o mesmo cuidado da ferramenta, no tamanho pedido)."""
    from PIL import ImageFilter
    im = Image.open(path).convert('RGBA')
    im = Image.alpha_composite(Image.new('RGBA', im.size, (0, 0, 0, 255)), im).convert('RGB')
    W, H = im.size
    s = max(w / W, h / H); cw, ch = w / s, h / s; ox, oy = (W - cw) / 2, (H - ch) / 2
    im = im.resize((w, h), Image.Resampling.LANCZOS, box=(ox, oy, ox + cw, oy + ch))
    return np.array(im.filter(ImageFilter.UnsharpMask(radius=1.0, percent=forca, threshold=1)), float)


def otimizar(D, blocos, tentativas=4, voltas=8, fundos=None):
    """D: distância (pixels x cores). blocos: lista de índices de pixel de cada bloco 16x16.
    Escolhe cor de fundo + 4 paletas de 3 cores e a paleta de cada bloco. Devolve (erro, fundo, paletas, escolha).
    fundos: cores de fundo a testar (padrão: as 3 mais usadas + preto)."""
    melhor = None
    if fundos is None:
        uso = np.bincount(D.argmin(1), minlength=D.shape[1])
        fundos = list(np.argsort(-uso)[:3])
        preto = int(np.argmin(RGB.sum(1)))
        if preto not in fundos: fundos.append(preto)
    rng = np.random.default_rng(1)
    for bg in fundos:
        dbg = D[:, bg]
        # por bloco: as 3 melhores cores (gulosas) junto com o fundo
        def gulosa(idx):
            m = dbg[idx].copy(); esc = []
            for _ in range(3):
                k = int(np.argmin(np.minimum(m[:, None], D[idx]).sum(0)))
                esc.append(k); m = np.minimum(m, D[idx, k])
            return esc
        proprias = [gulosa(b) for b in blocos]
        for t in range(tentativas):
            ini = rng.choice(len(blocos), size=min(4, len(blocos)), replace=False) if t else \
                np.argsort([-dbg[b].sum() for b in blocos])[:4]
            pals = [list(proprias[i]) for i in ini]
            while len(pals) < 4: pals.append(list(pals[0]))
            for _ in range(voltas):
                # cada bloco escolhe a paleta que erra menos
                erros = np.array([[np.minimum(dbg[b], D[b][:, p].min(1)).sum() for p in pals] for b in blocos])
                escolha = erros.argmin(1)
                # cada paleta melhora cor por cor para os blocos que a usam
                for q in range(4):
                    idx = np.concatenate([blocos[i] for i in np.where(escolha == q)[0]]) if (escolha == q).any() else None
                    if idx is None: continue
                    for s in range(3):
                        outras = [pals[q][j] for j in range(3) if j != s]
                        m = np.minimum(dbg[idx], D[idx][:, outras].min(1))
                        pals[q][s] = int(np.argmin(np.minimum(m[:, None], D[idx]).sum(0)))
            erros = np.array([[np.minimum(dbg[b], D[b][:, p].min(1)).sum() for p in pals] for b in blocos])
            escolha = erros.argmin(1); total = erros.min(1).sum()
            if melhor is None or total < melhor[0]: melhor = (total, bg, [list(p) for p in pals], escolha)
    return melhor


def converter(img, faixa=None):
    """img (h, w, 3) -> imagem só com cores possíveis. faixa = linhas por troca de paletas (None = uma só)."""
    h, w, _ = img.shape
    L = lab(img).reshape(-1, 3)
    D = ((L[:, None, :] - LAB[None, :, :]) ** 2).sum(-1)
    out = np.zeros((h * w, 3))
    faixa = faixa or h
    for y0 in range(0, h, faixa):
        blocos = []
        for by in range(y0, min(h, y0 + faixa), 16):
            for bx in range(0, w, 16):
                ys, xs = np.mgrid[by:min(h, by + 16), bx:min(w, bx + 16)]
                blocos.append((ys * w + xs).ravel())
        _, bg, pals, escolha = otimizar(D, blocos)
        for b, q in zip(blocos, escolha):
            cores = [bg] + pals[q]
            out[b] = RGB[np.array(cores)[D[b][:, cores].argmin(1)]]
    return out.reshape(h, w, 3).astype(np.uint8), None


def tela(capa, x, y):
    """Tela de 256x240 (preta) com a capa na posição (x, y)."""
    t = np.zeros((240, 256, 3), np.uint8)
    h, w, _ = capa.shape
    t[y:y + h, x:x + w] = capa
    return t


def main(forca=70):
    saida = SAIDA if forca == 70 else SAIDA.replace('.png', '_nitidez%d.png' % forca)
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    colunas = ['Original', 'Hoje: 64x96 (com flicker)', 'Grande: 128x192', 'Tela cheia: 176x240',
               'Tela cheia + paletas por faixa']
    Z = 2
    larg, alt = 256 * Z, 240 * Z
    try:
        fonte = ImageFont.truetype('segoeui.ttf', 22); fonte_p = ImageFont.truetype('segoeui.ttf', 16)
    except OSError:
        fonte = fonte_p = ImageFont.load_default()
    topo, gap = 70, 14
    W = len(colunas) * (larg + gap) + gap
    H = topo + len(JOGOS) * (alt + gap + 30) + 60
    folha = Image.new('RGB', (W, H), (24, 21, 18))
    d = ImageDraw.Draw(folha)
    d.text((gap, 12), 'Capas maiores num visualizador próprio (simulação com as regras da PPU do NES; cada quadro = '
                      'a tela inteira da TV, 256x240) · nitidez %d%%' % forca, fill=(230, 170, 60), font=fonte)
    for c, nome in enumerate(colunas):
        d.text((gap + c * (larg + gap), topo - 26), nome, fill=(240, 232, 220), font=fonte_p)
    for j, jogo in enumerate(JOGOS):
        path = os.path.join(CAPAS, jogo)
        print(jogo, flush=True)
        orig = carregar(path, 176, 240, forca=0).astype(np.uint8)
        _, prev = cover_record(path, 0, v3=True, lam=0.22, nitidez=forca)
        hoje = np.array(prev, np.uint8)
        g128, _ = converter(carregar(path, 128, 192, forca))
        g176, _ = converter(carregar(path, 176, 240, forca))
        f176, _ = converter(carregar(path, 176, 240, forca), faixa=48)
        telas = [tela(orig, 40, 0), tela(hoje, conv_v3.X0, conv_v3.Y0), tela(g128, 64, 24), tela(g176, 40, 0),
                 tela(f176, 40, 0)]
        y = topo + j * (alt + gap + 30)
        for c, t in enumerate(telas):
            im = Image.fromarray(t).resize((larg, alt), Image.Resampling.NEAREST)
            folha.paste(im, (gap + c * (larg + gap), y))
        d.text((gap, y + alt + 4), jogo[:-4], fill=(160, 150, 140), font=fonte_p)
    d.text((gap, H - 50), '"Hoje": a capa fica no lugar dela, ao lado da lista de jogos (o resto da tela é o menu). '
                          'As outras: só fundo, 4 paletas de 3 cores + cor de fundo por quadro (ou por faixa de 48 '
                          'linhas), sem sprites e sem flicker — com flicker por cima ainda melhoraria um pouco.',
           fill=(160, 150, 140), font=fonte_p)
    folha.save(saida)
    print('imagem:', saida)


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 70)
