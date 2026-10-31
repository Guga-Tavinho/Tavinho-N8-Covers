"""SIMULAÇÃO (só no PC): capas com PONTILHADO (dithering ordenado, Bayer 4x4) — sem, leve e forte.

As paletas são as mesmas que o conversor escolhe hoje; muda só a escolha de cada ponto: quando o tom original fica
entre duas cores disponíveis naquele ponto (preto, as 3 do sprite do bloco e as 3 do fundo do bloco), o ponto
alterna entre as duas num padrão regular, na proporção certa (mistura em luz linear). A camada de fundo continua
com o limite de 63 tiles (o pontilhado cria mais padrões, então isso entra na conta).
Cada capa aparece em pixels puros e numa simulação de TV de tubo (desfoque leve, que mistura os pontos).
Gera debug/comparacao_pontilhado.png.

uso: python sim_dither.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import conv_v2, sim_flicker as sf
from build_poc import carregar_capa, rgb, lab, BLACK, COVER_W, COVER_H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def lin(c): return [((v / 255 + 0.055) / 1.055) ** 2.4 if v / 255 > 0.04045 else v / 255 / 12.92 for v in c]


def d2(a, b): return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


LIN = {i: lin(rgb(i)) for i in range(64)}


def pontilhado(forca, so_sprite=False):
    """Função de escolha para o conv_v2.convert: pontilhado ordenado com a força dada (0 = cor mais próxima).
    so_sprite: só alterna entre cores da camada de sprite (e o preto); onde a melhor dupla usa o fundo, fica a mais
    próxima (o fundo tem só 63 tiles: o pontilhado lá vira blocos)."""
    cache = {}

    def escolher(x, y, cor, sp, bp):
        cands = [(BLACK, 's', 0)] + [(c, 's', k + 1) for k, c in enumerate(sp)] + [(c, 'b', k + 1) for k, c in enumerate(bp)]
        vistos, cs = set(), []
        for c in cands:                                   # mesma cor no sprite e no fundo: fica o sprite
            if c[0] not in vistos: vistos.add(c[0]); cs.append(c)
        chave = (cor, tuple(c[0] for c in cs))
        if chave not in cache:
            t, tl = lin(cor), lab(cor)
            melhor = None
            for i in range(len(cs)):
                for j in range(i, len(cs)):
                    a, b = LIN[cs[i][0]], LIN[cs[j][0]]
                    ab = [b[k] - a[k] for k in range(3)]
                    n = sum(v * v for v in ab)
                    r = 0.0 if n == 0 else max(0.0, min(1.0, sum((t[k] - a[k]) * ab[k] for k in range(3)) / n))
                    m = [a[k] + r * ab[k] for k in range(3)]
                    e = d2(lab(sf.unlin(m)), tl)
                    if melhor is None or e < melhor[0]: melhor = (e, i, j, r)
            cache[chave] = melhor
        _, i, j, r = cache[chave]
        if so_sprite and i != j and (cs[i][1] == 'b' or cs[j][1] == 'b'):
            _, camada, v = cs[j] if r > 0.5 else cs[i]
            return camada, v
        limiar = 0.5 + ((BAYER[y % 4][x % 4] + 0.5) / 16 - 0.5) * forca
        _, camada, v = cs[j] if r > limiar else cs[i]
        return camada, v
    return escolher


def tv(px, s):
    """Simulação simples de TV de tubo: amplia e desfoca um pouco (mais na horizontal, como o sinal composto)."""
    a = Image.new('RGB', (COVER_W, COVER_H)); a.putdata([tuple(c) for row in px for c in row])
    big = a.resize((COVER_W * s, COVER_H * s), Image.Resampling.NEAREST)
    big = big.filter(ImageFilter.BoxBlur(1)).filter(ImageFilter.GaussianBlur(s * 0.45))
    return big


def borrar(px):
    """A mesma mistura de pontos na escala da capa (para medir o erro como a TV mostra)."""
    a = Image.new('RGB', (COVER_W, COVER_H)); a.putdata([tuple(c) for row in px for c in row])
    b = a.filter(ImageFilter.GaussianBlur(0.8))
    d = list(b.get_flattened_data()) if hasattr(b, 'get_flattened_data') else list(b.getdata())
    return [d[y * COVER_W:(y + 1) * COVER_W] for y in range(COVER_H)]


CAPAS = [('Super Mario Bros. 3 (USA).png', 'Mario 3'), ('contra.png', 'Contra'), ('kirby.png', 'Kirby'),
         ('tartarugas.png', 'Tartarugas'), ('felix.png', 'Felix'), ('double.png', 'Double Dragon')]
NIVEIS = [(0.0, 'Sem pontilhado (hoje)', False), (1.0, 'Pontilhado (tudo)', False),
          (0.6, 'Só nos sprites, leve', True), (1.0, 'Só nos sprites, forte', True)]


def main():
    S = 3
    CW, CH = COVER_W * S, COVER_H * S

    def fnt(t):
        try: return ImageFont.truetype('segoeui.ttf', t)
        except OSError: return ImageFont.load_default()
    F1, F2, F3 = fnt(24), fnt(16), fnt(14)
    pad, top, left = 14, 116, 128
    cols = ['Original'] + [n for _, n, _ in NIVEIS]
    linha_h = CH * 2 + 70
    im = Image.new('RGB', (left + len(cols) * (CW + pad) + pad, top + len(CAPAS) * linha_h), (20, 17, 15))
    d = ImageDraw.Draw(im)
    d.text((pad, 10), 'Pontilhado (dithering) nas capas: mesmas paletas, muda só a escolha de cada ponto',
           fill=(217, 164, 65), font=F1)
    d.text((pad, 46), 'Em cima: os pixels como saem do NES. Embaixo: simulação de TV de tubo (os pontos se misturam).',
           fill=(141, 130, 115), font=F3)
    d.text((pad, 66), 'ΔE TV = erro de cor depois da mistura dos pontos (menor = mais fiel ao original visto na TV).',
           fill=(141, 130, 115), font=F3)
    for j, c in enumerate(cols):
        d.text((left + j * (CW + pad), top - 24), c, fill=(236, 227, 211), font=F2)
    print('%-14s ' % 'capa' + ' '.join('%22s' % n for _, n, _ in NIVEIS) + '   (ΔE na TV)')
    for i, (arq, rot) in enumerate(CAPAS):
        T = carregar_capa(os.path.join(ROOT, 'imagens', arq), True)
        y0 = top + i * linha_h
        d.text((pad, y0 + CH - 12), rot, fill=(217, 164, 65), font=F2)
        orig = Image.new('RGB', (COVER_W, COVER_H)); orig.putdata([tuple(c) for row in T for c in row])
        im.paste(orig.resize((CW, CH), Image.Resampling.NEAREST), (left, y0))
        im.paste(tv(T, S), (left, y0 + CH + 30))
        Tb = borrar(T)
        es = []
        for j, (forca, nome, so) in enumerate(NIVEIS):
            r = conv_v2.convert(T, escolher=None if forca == 0 else pontilhado(forca, so))
            px = r['preview']
            e = sf.erro_medio(borrar(px), Tb)
            es.append(e)
            x0 = left + (j + 1) * (CW + pad)
            a = Image.new('RGB', (COVER_W, COVER_H)); a.putdata([tuple(c) for row in px for c in row])
            im.paste(a.resize((CW, CH), Image.Resampling.NEAREST), (x0, y0))
            im.paste(tv(px, S), (x0, y0 + CH + 30))
            d.text((x0, y0 + CH + 6), 'pixels · %d tiles de fundo' % r['n_bg_tiles'], fill=(141, 130, 115), font=F3)
            d.text((x0, y0 + 2 * CH + 34), 'TV · ΔE %.1f' % e, fill=(141, 130, 115), font=F3)
        d.text((left, y0 + CH + 6), 'pixels', fill=(141, 130, 115), font=F3)
        d.text((left, y0 + 2 * CH + 34), 'TV', fill=(141, 130, 115), font=F3)
        print('%-14s ' % rot + ' '.join('%22.1f' % e for e in es))
    out = os.path.join(ROOT, 'debug', 'comparacao_pontilhado.png')
    im.save(out)
    print('salvo em', out)


if __name__ == '__main__':
    main()
