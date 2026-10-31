"""SIMULAÇÃO (só no PC): como ficaria a capa 64x96 com um núcleo de FPGA novo no EverDrive, que desse
  - cor por bloco de 8x8 na camada de fundo (como o MMC5), em vez de 16x16;
  - tiles de fundo à vontade (sem o limite de 63; o cartucho entregaria o tile certo a cada busca da PPU).
O resto é o NES de verdade: as mesmas paletas (fundo 1-2 livres + a do texto do OS fixa; 4 de sprite), sprites
8x16 e 8 por linha. Gera debug/comparacao_nucleo_fpga.png.

uso: python sim_nucleo_fpga.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont
import conv_v2, sim_flicker as sf, sim_flicker_barra as sb
from build_poc import carregar_capa, rgb, BLACK, COVER_W, COVER_H
from comparar_capas import optimize, uniq, dtable
from conv_v2 import OS_PAL0, BG_NPAL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def convert_nucleo(px):
    """Conversão com cor de fundo por 8x8 e tiles livres (mesmo método do conv_v2.convert)."""
    D = dtable({p for row in px for p in row})
    bg_units = [(uniq([px[by * 8 + y][bx * 8 + x] for y in range(8) for x in range(8)]), [])
                for by in range(COVER_H // 8) for bx in range(COVER_W // 8)]
    bg_pals, bg_assign = optimize(bg_units, BG_NPAL, D, 24, fixed=[OS_PAL0])
    bgb = lambda x, y: (y // 8) * (COVER_W // 8) + x // 8
    sp_units = []
    for sy in range(COVER_H // 16):
        for sx in range(COVER_W // 8):
            # o bloco de sprite 8x16 fica sobre dois blocos de cor 8x8: as cores dos dois ficam disponíveis
            extra = sorted(set(bg_pals[bg_assign[bgb(sx * 8, sy * 16)]]) | set(bg_pals[bg_assign[bgb(sx * 8, sy * 16 + 8)]]))
            sp_units.append((uniq([px[sy * 16 + y][sx * 8 + x] for y in range(16) for x in range(8)]), extra))
    sp_pals, sp_assign = optimize(sp_units, 4, D, 32)
    prev = [[(0, 0, 0)] * COVER_W for _ in range(COVER_H)]
    for y in range(COVER_H):
        for x in range(COVER_W):
            sp = sp_pals[sp_assign[(y // 16) * 8 + x // 8]]
            bp = bg_pals[bg_assign[bgb(x, y)]]
            c = px[y][x]
            opts = [(D[c][BLACK], 0, BLACK)] + [(D[c][k], 1, k) for k in sp] + [(D[c][k], 2, k) for k in bp]
            prev[y][x] = rgb(min(opts)[2])                       # sem limite de tiles: cada pixel escolhe livre
    return prev


CAPAS = [('Super Mario Bros. 3 (USA).png', 'Mario 3'), ('contra.png', 'Contra'), ('zelda.png', 'Zelda'),
         ('kirby.png', 'Kirby'), ('metroid.png', 'Metroid'), ('tartarugas.png', 'Tartarugas'),
         ('felix.png', 'Felix'), ('double.png', 'Double Dragon')]


def main():
    S, W, H = 3, COVER_W, COVER_H
    CW, CH = W * S, H * S

    def fnt(t):
        try: return ImageFont.truetype('segoeui.ttf', t)
        except OSError: return ImageFont.load_default()
    F1, F2, F3 = fnt(24), fnt(16), fnt(14)
    cols = ['Original (64x96)', 'Hoje, sem flicker', 'Hoje, com flicker (λ 0,22)', 'Núcleo novo, sem flicker',
            'O que mudou (hoje → núcleo)']
    pad, top, left = 14, 112, 128
    im = Image.new('RGB', (left + len(cols) * (CW + pad) + pad, top + len(CAPAS) * (CH + 40) + 20), (20, 17, 15))
    d = ImageDraw.Draw(im)
    d.text((pad, 10), 'Simulação: núcleo de FPGA novo no EverDrive (cor do fundo por 8x8 + tiles à vontade)',
           fill=(217, 164, 65), font=F1)
    d.text((pad, 46), 'Mesmas paletas do NES (é a PPU do console que guarda as cores). ΔE = erro de cor em relação à '
           'original (menor = mais fiel).', fill=(141, 130, 115), font=F3)
    d.text((pad, 66), 'Última coluna: em vermelho, os pixels em que o núcleo novo difere da firmware de hoje (sem flicker).',
           fill=(141, 130, 115), font=F3)
    for j, c in enumerate(cols):
        d.text((left + j * (CW + pad), top - 24), c, fill=(236, 227, 211), font=F2)

    def img(px):
        a = Image.new('RGB', (W, H)); a.putdata([tuple(c) for row in px for c in row])
        return a.resize((CW, CH), Image.Resampling.NEAREST)
    print('%-15s %8s %8s %8s' % ('capa', 'hoje', 'flicker', 'núcleo'))
    for i, (arq, rot) in enumerate(CAPAS):
        T = carregar_capa(os.path.join(ROOT, 'imagens', arq), True)
        hoje = conv_v2.convert(T)['preview']
        flk = [[tuple(c) for c in row] for row in sb.nivel(T, 0.22)['P']]
        nuc = convert_nucleo(T)
        e = [sf.erro_medio(p, T) for p in (hoje, flk, nuc)]
        dif = [[(220, 40, 40) if hoje[y][x] != nuc[y][x] else tuple(v // 3 for v in nuc[y][x]) for x in range(W)]
               for y in range(H)]
        nd = sum(1 for y in range(H) for x in range(W) if hoje[y][x] != nuc[y][x])
        print('%-15s %8.1f %8.1f %8.1f' % (rot, *e))
        y0 = top + i * (CH + 40)
        d.text((pad, y0 + CH // 2 - 12), rot, fill=(217, 164, 65), font=F2)
        for j, (px, leg) in enumerate(((T, ''), (hoje, 'ΔE %.1f' % e[0]), (flk, 'ΔE %.1f' % e[1]),
                                       (nuc, 'ΔE %.1f' % e[2]), (dif, '%.0f%% dos pixels' % (100 * nd / (W * H))))):
            x0 = left + j * (CW + pad)
            im.paste(img(px), (x0, y0))
            d.text((x0, y0 + CH + 6), leg, fill=(141, 130, 115), font=F3)
    out = os.path.join(ROOT, 'debug', 'comparacao_nucleo_fpga.png')
    im.save(out)
    print('salvo em', out)


if __name__ == '__main__':
    main()
