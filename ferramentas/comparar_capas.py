"""Compara modos de conversão de uma capa para o NES (só visualização, não gera COVERS.BIN).

uso: python comparar_capas.py capa.png [saida.png]
Painéis: Original | Atual | Bayer | Floyd-Steinberg | Sprites+Fundo (simulação)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import progresso
import rapido
import build_poc as B
from build_poc import (png_read, png_write, resize, quantize, rgb, dist, USABLE, BLACK,
                       COVER_W, COVER_H, ROOT)

CANDS = USABLE


def dtable(colors):
    """{cor: [dist(cor, NES i) for i in 0..63]} (NumPy, resultado idêntico ao laço em Python)."""
    return rapido.tabela_dist(colors, B.lab, rgb)


def optimize(units, npal, D, cands, iters=3, fixed=()):
    """units: lista de (pixels_unicos[(cor,n)], cores_fixas_extra). Busca local de npal paletas de 3 cores.
    fixed: paletas fixas (não otimizadas) que vêm antes das livres no resultado."""
    hist = {}
    for ub, extra in units:
        for p, n in ub:
            i = min(CANDS + [BLACK], key=lambda k: D[p][k])
            if i != BLACK: hist[i] = hist.get(i, 0) + n
    common = sorted(hist, key=hist.get, reverse=True) or [0x30]
    nf = len(fixed)
    pals = [list(f) for f in fixed] + [[common[(p * 3 + k) % len(common)] for k in range(3)] for p in range(npal)]
    npal += nf
    cands = [c for c in common[:cands]]

    U = rapido.Unidades(units, D, BLACK)                 # uerr de todas as unidades de uma vez (NumPy)
    perr = [U.erros(pal) for pal in pals]
    total = lambda: rapido.total_min(perr)
    best = total()
    passos = iters * (npal - nf) * 3
    for it in range(iters):
        imp = False
        for q in range(nf, npal):
            for s in range(3):
                progresso.avancar((it * (npal - nf) * 3 + (q - nf) * 3 + s) / passos)
                for c in cands:
                    if c in pals[q]: continue
                    old, olde = pals[q][s], perr[q]
                    pals[q][s] = c; perr[q] = U.erros(pals[q])
                    e = total()
                    if e < best: best, imp = e, True
                    else: pals[q][s], perr[q] = old, olde
        if not imp: break
    assign = [int(q) for q in rapido.np.asarray(perr).argmin(axis=0)]      # o primeiro mínimo, como o min()
    return pals, assign


def uniq(pixels):
    h = {}
    for p in pixels: h[p] = h.get(p, 0) + 1
    return list(h.items())


def sprite_block_of(x, y): return (y // 16) * 8 + x // 8
def bg_block_of(x, y): return (y // 16) * 4 + x // 16


def render(px, allowed_at, mode):
    """mode: 'plain' | 'bayer' | 'fs'. allowed_at(x,y) -> lista de índices NES permitidos."""
    out = [[(0, 0, 0)] * COVER_W for _ in range(COVER_H)]
    err = [[[0.0, 0.0, 0.0] for _ in range(COVER_W + 2)] for _ in range(COVER_H + 1)]
    bayer = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
    for y in range(COVER_H):
        for x in range(COVER_W):
            c = px[y][x]
            if mode == 'fs':
                e = err[y][x]
                c = tuple(max(0, min(255, int(round(c[k] + e[k])))) for k in range(3))
            elif mode == 'bayer':
                t = (bayer[y % 4][x % 4] / 16.0 - 0.5) * 48
                c = tuple(max(0, min(255, int(c[k] + t))) for k in range(3))
            best = min(allowed_at(x, y), key=lambda i: dist(c, rgb(i)))
            out[y][x] = rgb(best)
            if mode == 'fs':
                q = rgb(best); d = [px[y][x][k] + err[y][x][k] - q[k] for k in range(3)]
                for dx, dy, w in ((1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)):
                    if 0 <= x + dx < COVER_W:
                        for k in range(3): err[y + dy][x + dx][k] += d[k] * w / 16
    return out


def main():
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + '_comparacao.png'
    w, h, big = png_read(src)
    px = resize(w, h, big, COVER_W, COVER_H)

    # atual (sprites, 4 paletas)
    pals, assign, pix_idx, atual = quantize(px)
    spr_allowed = lambda x, y: [BLACK] + pals[assign[sprite_block_of(x, y)]]
    bayer = render(px, spr_allowed, 'bayer')
    fs = render(px, spr_allowed, 'fs')

    # simulação sprites + fundo: 3 paletas de fundo (16x16) e depois 4 de sprite (8x16) por cima
    D = dtable({p for row in px for p in row})
    bg_units = []
    for by in range(COVER_H // 16):
        for bx in range(COVER_W // 16):
            bg_units.append((uniq([px[by * 16 + y][bx * 16 + x] for y in range(16) for x in range(16)]), []))
    bg_pals, bg_assign = optimize(bg_units, 3, D, 24)
    sp_units = []
    for sy in range(COVER_H // 16):
        for sx in range(COVER_W // 8):
            extra = bg_pals[bg_assign[sy * 4 + sx // 2]]
            sp_units.append((uniq([px[sy * 16 + y][sx * 8 + x] for y in range(16) for x in range(8)]), extra))
    sp_pals, sp_assign = optimize(sp_units, 4, D, 32)
    both_allowed = lambda x, y: [BLACK] + sp_pals[sp_assign[sprite_block_of(x, y)]] + bg_pals[bg_assign[bg_block_of(x, y)]]
    both = render(px, both_allowed, 'plain')
    both_fs = render(px, both_allowed, 'fs')

    panels = [('Original', px), ('Atual', atual), ('Bayer', bayer), ('Floyd', fs),
              ('Spr+Fundo', both), ('S+F+Floyd', both_fs)]
    font = open(os.path.join(ROOT, 'firmware_base', 'EDFC', 'OS.BIN'), 'rb').read()[:0x800]
    gap, top = 4, 12
    W = len(panels) * (COVER_W + gap) - gap
    H = COVER_H + top
    out = [[(32, 32, 32)] * W for _ in range(H)]
    for k, (label, im) in enumerate(panels):
        ox = k * (COVER_W + gap)
        for y in range(COVER_H):
            for x in range(COVER_W): out[top + y][ox + x] = im[y][x]
        for ci, ch in enumerate(label[:8]):
            t = ord(ch)
            for r in range(8):
                lo, hi = font[t * 16 + r], font[t * 16 + 8 + r]
                for cx in range(8):
                    if (lo >> (7 - cx)) & 1 and not (hi >> (7 - cx)) & 1 and ox + ci * 8 + cx < W:
                        out[1 + r][ox + ci * 8 + cx] = (240, 240, 240)
    png_write(dst, W, H, out, 3)
    ncol = lambda im: len({p for row in im for p in row})
    print('salvo:', dst)
    for label, im in panels: print('  %-10s %3d cores' % (label, ncol(im)))
    print('  paletas fundo :', [['%02X' % i for i in p] for p in bg_pals])
    print('  paletas sprite:', [['%02X' % i for i in p] for p in sp_pals])


if __name__ == '__main__':
    main()
