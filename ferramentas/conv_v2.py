"""Conversor v2 (EXPERIMENTAL): capa 64x96 com sprites 8x16 (4 paletas) + camada de fundo
(2 paletas: 1 e 2 — a 3 é a da barra de baixo do OS; atributos 16x16, no máximo 63 tiles únicos nos slots $01-$1F e $80-$9F da tabela 0).

convert(px) -> dict com tudo que a firmware v2 precisa + prévia renderizada.
Geometria da firmware v2: capa na coluna de tiles 22 (x=176), linhas 4-15 (y=32).
"""
import os, sys
import progresso
sys.path.insert(0, os.path.dirname(__file__))
from build_poc import rgb, dist, BLACK, COVER_W, COVER_H
from comparar_capas import optimize, uniq, dtable
import rapido

COLS8, ROWS8 = COVER_W // 8, COVER_H // 8          # 8 x 12 tiles de fundo
BG_SLOTS = list(range(0x01, 0x20)) + list(range(0x80, 0xA0))   # 63 slots
X0, Y0 = 176, 32                                    # posição na tela (alinhada à grade de atributos)
BG_NPAL = 2                                         # paletas de fundo livres: 1 e 2
OS_PAL0 = [0x10, 0x0F, 0x28]                        # paleta 0 do texto (cinza, preto, amarelo): usável como está
OS_PAL3 = bytes([0x0F, 0x30, 0x00, 0x28])           # paleta 3 original (barra de baixo do OS)


PESOS_CONV = dict(bg=(0.0, 0.15), sp=(0.15, 0.85), tiles=(0.85, 1.0))      # fração do tempo de cada parte (NumPy)


def _fundir_tiles(groups, pats, gcost, cost, max_bg_tiles, g0):
    """Enquanto passar do limite, funde o par de tiles que menos piora (o trabalho cai com o quadrado)."""
    while len(groups) > max_bg_tiles:
        n = len(groups)
        if g0 > max_bg_tiles: progresso.avancar(1 - (n * n - max_bg_tiles ** 2) / (g0 * g0 - max_bg_tiles ** 2))
        best = None
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                c, pat = cost(groups[a] + groups[b])
                d = c - gcost[a] - gcost[b]
                if best is None or d < best[0]: best = (d, a, b, c, pat)
        d, a, b, c, pat = best
        groups[a] += groups[b]; pats[a] = pat; gcost[a] = c
        del groups[b], pats[b], gcost[b]


def convert(px, max_bg_tiles=len(BG_SLOTS), use_pal0=True, escolher=None):
    """escolher(x, y, cor, sp, bp) -> (camada, valor): troca a escolha de cada ponto (ex.: pontilhado); None = a mais próxima."""
    D = dtable({p for row in px for p in row})
    bg_units = [(uniq([px[by * 16 + y][bx * 16 + x] for y in range(16) for x in range(16)]), [])
                for by in range(COVER_H // 16) for bx in range(COVER_W // 16)]
    # paletas de fundo: [0] = paleta 0 do OS (fixa, atributo 0), [1..2] = livres (atributos 1-2)
    with progresso.etapa(*PESOS_CONV['bg']):
        bg_pals, bg_assign = optimize(bg_units, BG_NPAL, D, 24, fixed=[OS_PAL0] if use_pal0 else ())
    if not use_pal0:
        bg_pals = [OS_PAL0] + bg_pals; bg_assign = [a + 1 for a in bg_assign]
    sp_units = []
    for sy in range(COVER_H // 16):
        for sx in range(COVER_W // 8):
            extra = bg_pals[bg_assign[sy * 4 + sx // 2]]
            sp_units.append((uniq([px[sy * 16 + y][sx * 8 + x] for y in range(16) for x in range(8)]), extra))
    with progresso.etapa(*PESOS_CONV['sp']):
        sp_pals, sp_assign = optimize(sp_units, 4, D, 32)

    # decomposição por pixel: sprite (1-3) ou fundo (0-3); None = fundo "tanto faz" (coberto pelo sprite)
    spr = [[0] * COVER_W for _ in range(COVER_H)]
    bg = [[None] * COVER_W for _ in range(COVER_H)]
    for y in range(COVER_H):
        for x in range(COVER_W):
            sp = sp_pals[sp_assign[(y // 16) * 8 + x // 8]]
            bp = bg_pals[bg_assign[(y // 16) * 4 + x // 16]]
            if escolher:
                layer, v = escolher(x, y, px[y][x], sp, bp)
            else:
                opts = [(D[px[y][x]][BLACK], 0, 's', 0)]
                opts += [(D[px[y][x]][c], 1, 's', k + 1) for k, c in enumerate(sp)]      # empate: sprite
                opts += [(D[px[y][x]][c], 2, 'b', k + 1) for k, c in enumerate(bp)]
                _, _, layer, v = min(opts)
            if layer == 's' and v: spr[y][x] = v
            elif layer == 'b': bg[y][x] = v
            else: bg[y][x] = 0                                                    # preto: fundo 0

    # tiles de fundo 8x8 com "tanto faz"; agrupa compatíveis e depois funde os mais parecidos
    tiles = []
    for ty in range(ROWS8):
        for tx in range(COLS8):
            tiles.append([bg[ty * 8 + y][tx * 8 + x] for y in range(8) for x in range(8)])
    pal_of_tile = [bg_assign[(t // COLS8) // 2 * 4 + (t % COLS8) // 2] for t in range(len(tiles))]

    def pix_cost(t, i, v):
        """custo de o tile t mostrar o valor v no pixel i (0 se 'tanto faz')."""
        if tiles[t][i] is None or tiles[t][i] == v: return 0
        y, x = (t // COLS8) * 8 + i // 8, (t % COLS8) * 8 + i % 8
        pal = [BLACK] + bg_pals[pal_of_tile[t]]
        return D[px[y][x]][pal[v]] - D[px[y][x]][pal[tiles[t][i]]] + 1

    groups = [[t] for t in range(len(tiles))]

    def merged_pattern(g):
        pat = []
        for i in range(64):
            best = min(range(4), key=lambda v: sum(pix_cost(t, i, v) for t in g))
            fixed = [tiles[t][i] for t in g if tiles[t][i] is not None]
            pat.append(best if fixed else None)
        return pat

    def cost(g):
        pat = merged_pattern(g)
        return sum(pix_cost(t, i, pat[i]) for t in g for i in range(64) if pat[i] is not None), pat

    pats = [tiles[g[0]] for g in groups]
    gcost = [0] * len(groups)
    # 1) funde sem perda (compatíveis)
    changed = True
    while changed:
        changed = False
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                if all(x is None or y is None or x == y for x, y in zip(pats[a], pats[b])):
                    groups[a] += groups[b]
                    pats[a] = [x if x is not None else y for x, y in zip(pats[a], pats[b])]
                    del groups[b], pats[b], gcost[b]
                    changed = True; break
            if changed: break
    # 2) enquanto passar do limite, funde o par que menos piora
    g0 = len(groups)
    with progresso.etapa(*PESOS_CONV['tiles']):
        _fundir_tiles(groups, pats, gcost, rapido.CustoTiles(len(tiles), tiles, pix_cost), max_bg_tiles, g0)

    tile_slot = [0] * len(tiles)
    bg_chr = {}
    for gi, g in enumerate(groups):
        pat = [v if v is not None else 0 for v in pats[gi]]
        slot = BG_SLOTS[gi] if gi < len(BG_SLOTS) else 0x100 + gi   # >63 só para comparação
        lo = bytearray(8); hi = bytearray(8)
        for i, v in enumerate(pat):
            lo[i // 8] |= (v & 1) << (7 - i % 8); hi[i // 8] |= (v >> 1) << (7 - i % 8)
        bg_chr[slot] = bytes(lo + hi)
        for t in g:
            tile_slot[t] = slot
            for i in range(64):
                bg[(t // COLS8) * 8 + i // 8][(t % COLS8) * 8 + i % 8] = pat[i]

    preview = [[(0, 0, 0)] * COVER_W for _ in range(COVER_H)]
    for y in range(COVER_H):
        for x in range(COVER_W):
            if spr[y][x]:
                preview[y][x] = rgb(sp_pals[sp_assign[(y // 16) * 8 + x // 8]][spr[y][x] - 1])
            else:
                v = bg[y][x]
                preview[y][x] = rgb(BLACK if v == 0 else bg_pals[bg_assign[(y // 16) * 4 + x // 16]][v - 1])
    return dict(sp_pals=sp_pals, sp_assign=sp_assign, spr=spr, bg_pals=bg_pals, bg_assign=bg_assign,
                tile_slot=tile_slot, bg_chr=bg_chr, n_bg_tiles=len(groups), preview=preview, bg=bg)


if __name__ == '__main__':
    import time
    from build_poc import png_read, png_write, resize
    w, h, big = png_read(sys.argv[1])
    px = resize(w, h, big, COVER_W, COVER_H)
    t = time.time()
    r = convert(px)
    print('tiles de fundo: %d | %.1fs' % (r['n_bg_tiles'], time.time() - t))
    r_free = convert(px, 96)
    print('sem limite: %d tiles' % r_free['n_bg_tiles'])
    gap = 4
    ims = [px, r_free['preview'], r['preview']]
    W = len(ims) * (COVER_W + gap) - gap
    out = [[(32, 32, 32)] * W for _ in range(COVER_H)]
    for k, im in enumerate(ims):
        for y in range(COVER_H):
            for x in range(COVER_W): out[y][k * (COVER_W + gap) + x] = im[y][x]
    png_write(sys.argv[2], W, COVER_H, out, 3)
    print('salvo', sys.argv[2])


def com_paletas(r, pals):
    """Resultado do convert() com as paletas editadas à mão (fundo 1-2 e sprites 0-3); refaz a prévia."""
    import conv_v3
    r = dict(r, bg_pals=[r['bg_pals'][0]] + pals['A']['bg'], sp_pals=pals['A']['sp'],
             spr=conv_v3.com_pontos(r['spr'], (pals.get('pix') or {}).get('A')))
    r['preview'] = [[rgb(r['sp_pals'][r['sp_assign'][(y // 16) * 8 + x // 8]][r['spr'][y][x] - 1]) if r['spr'][y][x]
                     else rgb(BLACK if r['bg'][y][x] == 0 else
                              r['bg_pals'][r['bg_assign'][(y // 16) * 4 + x // 16]][r['bg'][y][x] - 1])
                     for x in range(COVER_W)] for y in range(COVER_H)]
    return r


def record_v2(px, crc, chr0, pals=None):
    """Registro de 8 setores (4096 bytes) para o COVERS.BIN v2. chr0 = tabela 0 original (4096 B).
    pals: paletas editadas à mão (conv_v3.ler_paletas)."""
    r = convert(px)
    if pals: r = com_paletas(r, pals)
    meta = bytearray(512)
    oam = bytearray([0xFF] * 256)
    for k in range(48):
        row, col = divmod(k, 8)
        oam[k * 4:k * 4 + 4] = bytes([Y0 + row * 16 - 1, (k * 2) | 1, r['sp_assign'][k], X0 + col * 8])
    meta[0:256] = oam
    pals = bytearray()
    for p in r['bg_pals'][1:]: pals += bytes([BLACK] + p)          # $3F04-$3F0B: fundo 1-2
    pals += OS_PAL3                                                 # $3F0C-$3F0F: paleta 3 do OS intacta
    for p in r['sp_pals']: pals += bytes([BLACK] + p)              # $3F10-$3F1F: sprites
    meta[256:284] = pals
    meta[284:287] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
    meta[288:384] = bytes(r['tile_slot'])                           # nametable 12 x 8
    attr = bytearray(24)                                            # linhas 1-3 x colunas 0-7
    for by in range(COVER_H // 16):
        for bx in range(COVER_W // 16):
            tc, tr = 22 + bx * 2, 4 + by * 2
            shift = (2 if tc % 4 >= 2 else 0) + (4 if tr % 4 >= 2 else 0)
            attr[(tr // 4 - 1) * 8 + tc // 4] |= r['bg_assign'][by * 4 + bx] << shift   # 0 = paleta do texto
    meta[384:403] = attr[5:24]                                      # $63CD-$63DF
    spr_chr = bytearray()
    for row in range(COVER_H // 16):
        for col in range(COVER_W // 8):
            for half in range(2):
                lo = bytearray(8); hi = bytearray(8)
                for y in range(8):
                    for x in range(8):
                        v = r['spr'][row * 16 + half * 8 + y][col * 8 + x]
                        lo[y] |= (v & 1) << (7 - x); hi[y] |= (v >> 1) << (7 - x)
                spr_chr += lo + hi
    bga = bytearray(chr0[0x000:0x200])                              # tiles $00-$1F (0 = vazio original)
    bgb = bytearray(chr0[0x800:0xA00])                              # tiles $80-$9F
    for slot, data in r['bg_chr'].items():
        if slot < 0x20: bga[slot * 16:slot * 16 + 16] = data
        else: bgb[(slot - 0x80) * 16:(slot - 0x80) * 16 + 16] = data
    rec = bytes(meta) + bytes(spr_chr) + bytes(bga) + bytes(bgb) + bytes(1024)
    assert len(rec) == 4096
    return rec, r['preview']
