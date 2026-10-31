"""Conversão da capa GRANDE do navegador (POC v4): 112x160 ao lado da lista + a tela cheia (conv_tela_cheia).

Região da capa na tela: linhas de tiles 2-21, colunas 16-31 (x 128-255, y 16-175); a imagem fica em x 136-247
(colunas 16 e 31 pretas). A paleta 0 (texto) e a 3 (barra) são fixas; 1 e 2 são da capa. Só fundo, sem flicker.
Tiles: os slots livres da fonte ($01-$1F e $80-$9F, 63 por bloco) em 7 blocos de 4 KB (bancos 1-7 do
registrador $82), um grupo de linhas por bloco: 0-3, 3-6, 6-9, 9-12, 12-15, 15-18, 18-19. A linha compartilhada
(3, 6, ...) existe nos dois blocos vizinhos com os mesmos slots: a troca de banco pode cair em qualquer ponto dela.
O bloco 2 (grupo 1) guarda também o sprite de sincronia: slots $1E (pixel 0,0 opaco) e $1F (vazio).

Registro de uma capa no COVERS.BIN v4 (64 setores, a partir do setor 512 + 64*idx):
  setor 0      verificação (crc>>8, crc>>16, crc>>24), paletas 1 e 2 (6), atributos (6 linhas x 4: $23C4.. de 8 em 8),
               nametable (20 linhas x 16: $2050.. de 32 em 32)
  setores 1-14 grupos 0-6: 2 setores cada (PPU $0000-$01FF e $0800-$09FF do banco g+1)
  setores 15-41 a tela cheia (conv_tela_cheia, começando com "TELA")
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_tela_cheia as S
import sim_navegador_grande as N
import conv_tela_cheia as TC

CW, CH = 112, 160
LINHAS = 20
GRUPOS = [(0, 3), (3, 6), (6, 9), (9, 12), (12, 15), (15, 18), (18, 19)]       # (primeira, última) linha
SLOTS = list(range(0x01, 0x20)) + list(range(0x80, 0xA0))
SYNC = 0x1E                                                                    # grupo 1: $1E/$1F
SETORES = 64
FONTE0 = None


def fonte0():
    global FONTE0
    if FONTE0 is None:                                                   # tile $00 da fonte (cor 2 sólida)
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'firmwares', 'OS_v15.BIN')   # (no .exe)
        FONTE0 = open(N.OS_BIN if os.path.exists(N.OS_BIN) else alt, 'rb').read()[0:16]
    return FONTE0


def quantizar(img, cor3=False):
    """img 160x112 -> (índices 0-3 por pixel na região 160x128, paleta de cada bloco 16x16 (10x8), pal1, pal2).
    cor3: a 3ª cor da paleta 3 (o amarelo da barra, $28) também é escolhida para a capa (v9); devolve ela no fim."""
    tela = np.zeros((CH, N.BW, 3)); tela[:, N.CX - N.BX:N.CX - N.BX + CW] = img
    h, w = CH, N.BW
    pares, rgb, pen = N.candidatos(False)
    L = S.lab(tela).reshape(-1, 3)
    D = ((L[:, None, :] - S.lab(rgb)[None, :, :]) ** 2).sum(-1).astype(np.float32)
    idx = {p: k for k, p in enumerate(pares)}
    canon = {i: next(k for k, r in S.CORES if r == N.NES[i]) for i in N.NES if N.NES[i] in [r for _, r in S.CORES]}
    pk = lambda c: idx[(canon[c], canon[c])]
    bg = pk(N.PRETO)
    fixa = {0: [pk(c) for c in N.PAL0[1:]], 3: [pk(c) for c in N.PAL3[1:]]}
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
    base = np.array([min(err(b, fixa[0]), err(b, fixa[3])) for b in blocos])
    ordem = np.argsort(-base)
    for t in range(3):
        ini = [ordem[0], ordem[min(len(ordem) - 1, 1 + t * 3)]]
        pals = {0: fixa[0], 1: gulosa(blocos[ini[0]]), 2: gulosa(blocos[ini[1]]), 3: list(fixa[3])}
        for _ in range(8):
            e = np.array([[err(b, pals[q]) for q in range(4)] for b in blocos]); esc = e.argmin(1)
            for q in ((1, 2, 3) if cor3 else (1, 2)):
                sel = np.where(esc == q)[0]
                if not len(sel): continue
                ii = np.concatenate([blocos[i] for i in sel])
                for s in ((2,) if q == 3 else range(3)):
                    outras = [pals[q][j] for j in range(3) if j != s]
                    m = np.minimum(dbg[ii], D[ii][:, outras].min(1))
                    pals[q][s] = int(np.argmin(np.minimum(m[:, None], D[ii]).sum(0)))
        e = np.array([[err(b, pals[q]) for q in range(4)] for b in blocos]); esc = e.argmin(1)
        tot = e.min(1).sum()
        if melhor is None or tot < melhor[0]: melhor = (tot, {q: list(p) for q, p in pals.items()}, esc)
    _, pals, esc = melhor
    ind = np.zeros(h * w, np.uint8)
    for b, q in zip(blocos, esc):
        ind[b] = D[b][:, [bg] + pals[q]].argmin(1)
    nes = lambda k: pares[k][0]
    if cor3:
        return ind.reshape(h, w), esc.reshape(h // 16, w // 16), [nes(k) for k in pals[1]], [nes(k) for k in pals[2]], \
            nes(pals[3][2])
    return ind.reshape(h, w), esc.reshape(h // 16, w // 16), [nes(k) for k in pals[1]], [nes(k) for k in pals[2]]


# ---------------------------------------------------------------- pontilhado (dithering) ordenado, por bloco
BAYER2 = np.array([[0, 2], [3, 1]]) / 4 + 1 / 8                  # limiares do xadrez 2x2
NIVEIS_PONT = (0.0, 0.25, 0.5, 0.75, 1.0)
PEN_PONT = 0.05                                                  # penalidade de misturar cores distantes (medida)


def pontilhar(tela, esc, pal, pen=PEN_PONT):
    """Pontilhado ordenado: cada ponto vira a mistura (na luz) de 2 das 4 cores da paleta do bloco, em 0-100% de
    25 em 25%, desenhada com o xadrez 2x2 (Bayer). Custo = ΔE²(mistura, alvo) + pen * ΔE²(cor1, cor2) * 4t(1-t):
    misturar cores distantes custa caro, então contornos e letras ficam limpos e o pontilhado vai para degradês.
    tela: alvo CH x BW RGB; esc: paleta de cada bloco 16x16; pal: [4 paletas][4 cores NES].
    -> (índices 0-3 por ponto, cor percebida RGB CH x BW (a mistura que a TV mostra))"""
    import conv_sprites_grande as SP
    h, w = tela.shape[:2]
    T = S.lab(tela)
    linN = {c: SP._lin(np.array(N.NES[c], float)) for p in pal for c in p}
    ind = np.zeros((h, w), np.uint8)
    perc = np.zeros((h, w, 3))
    lim = np.tile(BAYER2, (h // 2, w // 2))
    for by in range(0, h, 16):
        for bx in range(0, w, 16):
            cores = pal[int(esc[by // 16, bx // 16])]
            lin = np.array([linN[c] for c in cores])
            lab = SP._lab_lin(lin)
            combos = []                                          # (i, j, t)
            for i in range(4):
                for j in range(i, 4):
                    for t in (NIVEIS_PONT if j > i else (0.0,)):
                        if j > i and t in (0.0, 1.0): continue
                        combos.append((i, j, t))
            mix = np.array([(1 - t) * lin[i] + t * lin[j] for i, j, t in combos])
            pena = np.array([pen * ((lab[i] - lab[j]) ** 2).sum() * 4 * t * (1 - t) for i, j, t in combos])
            alvo = T[by:by + 16, bx:bx + 16].reshape(-1, 3)
            custo = ((alvo[:, None, :] - SP._lab_lin(mix)[None, :, :]) ** 2).sum(-1) + pena[None, :]
            k = custo.argmin(1).reshape(16, 16)
            for yy in range(16):
                for xx in range(16):
                    i, j, t = combos[k[yy, xx]]
                    ind[by + yy, bx + xx] = j if lim[by + yy, bx + xx] < t else i
                    perc[by + yy, bx + xx] = mix[k[yy, xx]]
    return ind, SP._unlin(perc)


def padroes(ind):
    """20x16 células -> padrões de 16 bytes."""
    out = []
    for ty in range(LINHAS):
        linha = []
        for tx in range(16):
            t = ind[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
            p0 = bytes(int(''.join(str(v & 1) for v in r), 2) for r in t)
            p1 = bytes(int(''.join(str(v >> 1) for v in r), 2) for r in t)
            linha.append(p0 + p1)
        out.append(linha)
    return out


def alocar(pad, sync=True):
    """Slot de cada célula; dados de CHR de cada grupo (2 x 512 bytes)."""
    mapa = [dict() for _ in GRUPOS]
    livre = [[s for s in SLOTS if not (sync and g == 1 and s in (SYNC, SYNC + 1))] for g in range(len(GRUPOS))]

    def pegar(g, p, slot=None):
        if p in mapa[g]: return mapa[g][p]
        if slot is None:
            assert livre[g], 'grupo %d sem slots livres' % g
            slot = livre[g][0]
        assert slot in livre[g], 'slot %02X ocupado no grupo %d' % (slot, g)
        livre[g].remove(slot); mapa[g][p] = slot
        return slot
    for g, (a, b) in enumerate(GRUPOS):                                 # linhas compartilhadas primeiro
        if g + 1 < len(GRUPOS):
            for p in pad[b]:
                if p in mapa[g] and p in mapa[g + 1]: continue
                s = mapa[g].get(p, mapa[g + 1].get(p))
                if s is None:
                    s = next(x for x in livre[g] if x in livre[g + 1])
                if p not in mapa[g]: pegar(g, p, s)
                if p not in mapa[g + 1]: pegar(g + 1, p, s)
    nt = bytearray(LINHAS * 16)
    for g, (a, b) in enumerate(GRUPOS):
        for r in range(a, b + 1):
            for c in range(16):
                s = pegar(g, pad[r][c])
                dono = next(k for k, (x, y) in enumerate(GRUPOS) if x <= r <= y)     # 1º grupo que tem a linha
                if dono == g: nt[r * 16 + c] = s
    for r in range(LINHAS):                                            # a linha compartilhada: mesmo slot nos 2
        gs = [g for g, (a, b) in enumerate(GRUPOS) if a <= r <= b]
        for c in range(16):
            assert len({mapa[g][pad[r][c]] for g in gs}) == 1
    chr_ = []
    for g in range(len(GRUPOS)):
        lo, hi = bytearray(512), bytearray(512)
        lo[0:16] = fonte0()
        for p, s in mapa[g].items():
            if s < 0x20: lo[s * 16:s * 16 + 16] = p
            else: hi[(s - 0x80) * 16:(s - 0x80) * 16 + 16] = p
        if sync and g == 1: lo[SYNC * 16] = 0x80; lo[(SYNC + 1) * 16:(SYNC + 2) * 16] = bytes(16)
        chr_.append(bytes(lo) + bytes(hi))
    return nt, chr_, [len(m) for m in mapa]


def atributos(esc):
    """24 bytes: linhas de atributo 0-5, colunas 4-7. Blocos 16x16 da linha 0 (y 0-15) e 11 (y 176-191) = paleta 0."""
    blocos = np.zeros((12, 8), np.uint8); blocos[1:11] = esc
    out = bytearray()
    for ar in range(6):
        for ac in range(4):
            v = 0
            for dy in range(2):
                for dx in range(2):
                    v |= int(blocos[ar * 2 + dy, ac * 2 + dx]) << (dx * 2 + dy * 4)
            out.append(v)
    return bytes(out)


def converter(path, crc, forca=180):
    """-> (registro de 64 setores, imagem vista da capa 160x128 RGB, info)."""
    img = S.carregar(path, CW, CH, forca)
    ind, esc, p1, p2 = quantizar(img)
    nt, chr_, usados = alocar(padroes(ind))
    meta = bytearray(512)
    meta[0:3] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
    meta[3:9] = bytes(p1 + p2)
    meta[9:33] = atributos(esc)
    meta[33:353] = nt
    tc = TC.converter(path, forca)
    cheia = bytearray(tc['setores']); cheia[0:4] = b'TELA'
    reg = bytes(meta) + b''.join(chr_) + bytes(cheia)
    reg += bytes(SETORES * 512 - len(reg))
    pal = [N.PAL0, [0x0F] + p1, [0x0F] + p2, N.PAL3]
    vista = np.zeros((CH, N.BW, 3), np.uint8)
    for y in range(CH):
        for x in range(N.BW):
            vista[y, x] = N.NES[pal[esc[y // 16, x // 16]][ind[y, x]]]
    return reg, vista, dict(tiles=usados, tela_cheia=tc)


# ---------------------------------------------------------------- v5: fundo + sprites
JANELAS = [(8 * (2 + 3 * k) - 1, 8 * (2 + 3 * k) + 7) for k in range(1, 7)]     # trocas para os grupos 1..6


def grupos_possiveis(l0, l1):
    """Grupos que podem estar ativos (banco 2g+1) em alguma linha de l0..l1."""
    out = set()
    for g in range(7):
        ini = JANELAS[g - 1][0] if g > 0 else -10
        fim = JANELAS[g][1] if g < 6 else 999
        if l0 <= fim and l1 >= ini: out.add(g)
    return out


SETORES_V5 = 32
SETOR_SPR = 15


def converter_v5(path, crc, forca=180):
    """Registro v5 (32 setores, sem a tela cheia): setor 0 e grupos de fundo (1-14) como a v4, sem o sprite de
    sincronia no bloco de fundo, + a camada de sprites:
      setor 15: OAM (256: [0] = sincronia, tile $01), paletas de sprite (16, $3F10-$3F1F), máscaras (63: bit g =
                o par vai para o bloco de sprites do grupo g = bloco 2g+2)
      setores 16-19: os 63 pares de tiles 8x16 (32 bytes cada; par 0 = sincronia)"""
    import conv_sprites_grande as SP
    img = S.carregar(path, CW, CH, forca)
    ind, esc, p1, p2 = quantizar(img)
    nt, chr_, usados = alocar(padroes(ind), sync=False)
    meta = bytearray(512)
    meta[0:3] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
    meta[3:9] = bytes(p1 + p2)
    meta[9:33] = atributos(esc)
    meta[33:353] = nt
    pal = [N.PAL0, [0x0F] + p1, [0x0F] + p2, N.PAL3]
    vista_bg = np.zeros((CH, N.BW, 3), np.uint8)
    for y in range(CH):
        for x in range(N.BW):
            vista_bg[y, x] = N.NES[pal[esc[y // 16, x // 16]][ind[y, x]]]
    tela = np.zeros((CH, N.BW, 3)); tela[:, N.CX - N.BX:N.CX - N.BX + CW] = img
    sprites, spal, vista = SP.otimizar(tela, vista_bg)
    oam = bytearray([0xF0] * 256)
    oam[0:4] = bytes([15, 0x01, 0x20, 0])
    pares = bytearray(63 * 32)
    pares[0] = 0x80                                                   # sincronia: pixel (0,0)
    mascaras = bytearray(63)
    mascaras[0] = sum(1 << g for g in grupos_possiveis(15, 30))
    for k, (j, i, q, sp) in enumerate(sprites):
        par = k + 1
        y = 16 + 16 * j
        oam[par * 4:par * 4 + 4] = bytes([y - 1, 2 * par + 1, q, N.BX + SP.X0 + 8 * i])
        for t in range(2):                                            # tile de cima e de baixo
            for r in range(8):
                linha = sp[t * 8 + r]
                pares[par * 32 + t * 16 + r] = int(''.join(str(v & 1) for v in linha), 2)
                pares[par * 32 + t * 16 + 8 + r] = int(''.join(str(v >> 1) for v in linha), 2)
        mascaras[par] = sum(1 << g for g in grupos_possiveis(y - 1, y + 14))
    s42 = bytearray(512)
    s42[0:256] = oam
    s42[256:272] = bytes(sum(([0x0F] + p for p in spal), []))
    s42[272:335] = mascaras
    reg = bytes(meta) + b''.join(chr_) + bytes(s42) + bytes(pares).ljust(4 * 512, b'\0')
    reg += bytes(SETORES_V5 * 512 - len(reg))
    assert len(reg) == SETORES_V5 * 512
    return reg, vista, dict(tiles=usados, sprites=len(sprites), vista_bg=vista_bg)


# ---------------------------------------------------------------- v6: o mesmo conteúdo da v5, organizado para carregar rápido
def v6_de_v5(reg5):
    """Registro v6 (32 setores) a partir do v5 (mesma imagem, mesmos tiles):
      setor 0     o da v5 + [353:367] quantos pedaços de 128 bytes enviar de cada grupo de fundo (A = $0000.., B =
                  $0800..), contados pelos slots que a nametable do grupo usa (o resto não precisa ir)
      setores 1-14 grupos de fundo (iguais)
      setor 15    OAM (256), paletas de sprite (16), tabela dos blocos de sprite [272:300]: 7 x (setor relativo,
                  pedaços de 128, destino lo, destino hi) — os pares de cada bloco formam uma faixa contínua
      setores 16+ a faixa de pares de cada bloco, em sequência (cada uma começando num setor)"""
    meta = bytearray(reg5[0:512])
    nt = reg5[33:353]
    for g, (a, b) in enumerate(GRUPOS):
        slots = {nt[r * 16 + c] for r in range(a, b + 1) for c in range(16)}
        lo = [s for s in slots if s < 0x20]
        hi = [s - 0x80 for s in slots if s >= 0x80]
        meta[353 + 2 * g] = -(-(max(lo) + 1) * 16 // 128) if lo else 0
        meta[354 + 2 * g] = -(-(max(hi) + 1) * 16 // 128) if hi else 0
    s15 = reg5[15 * 512:16 * 512]
    pares = reg5[16 * 512:16 * 512 + 63 * 32]
    mascaras = s15[272:335]
    cab = bytearray(512)
    cab[0:272] = s15[0:272]
    fluxos, setor = b'', 16
    for g in range(7):
        ps = [p for p in range(63) if mascaras[p] >> g & 1]
        if not ps:
            continue
        a, b = min(ps), max(ps)
        assert ps == list(range(a, b + 1)), 'pares do bloco %d não são contínuos' % g
        dados = pares[a * 32:(b + 1) * 32]
        nch = -(-len(dados) // 128)
        dst = 0x1000 + a * 32
        cab[272 + 4 * g:276 + 4 * g] = bytes([setor, nch, dst & 255, dst >> 8])
        bloco = dados.ljust(-(-len(dados) // 512) * 512, b'\0')
        fluxos += bloco
        setor += len(bloco) // 512
    reg = bytes(meta) + reg5[512:15 * 512] + bytes(cab) + fluxos
    assert len(reg) <= SETORES_V5 * 512, 'registro v6 com %d setores' % (len(reg) // 512)
    return reg + bytes(SETORES_V5 * 512 - len(reg))


def converter_v6(path, crc, forca=180):
    reg5, vista, info = converter_v5(path, crc, forca)
    return v6_de_v5(reg5), vista, info


# ---------------------------------------------------------------- v8: v6/v7 + flicker opcional nos sprites
SETORES_V8 = 64                                   # registro de 64 setores (com flicker os tiles de sprite dobram)


def converter_v8(path, crc, forca=180, flicker=False, cor3=False, lam=None, pontilhado=False, progresso=None):
    """Registro v8 (64 setores). Igual ao v6 (setor 0 com a tabela de pedaços do fundo, grupos 1-14), e o setor
    15 do cabeçalho dos sprites:
      [0:256] OAM (quadro A: tile do par p = 2p+1; o quadro B usa 2p+1 EOR $80 = par p+64), [256:272] paletas de
      sprite A, [272:300] faixas A (7 x setor, pedaços, destino lo, hi), [300] 1 = com flicker,
      [304:320] paletas de sprite B, [320:348] faixas B (pares p+64, mesmos blocos)
    setores 16+: as faixas (A, depois B), cada uma começando num setor."""
    import conv_sprites_grande as SP
    img = S.carregar(path, CW, CH, forca)
    if cor3:
        ind, esc, p1, p2, c3 = quantizar(img, cor3=True)
    else:
        (ind, esc, p1, p2), c3 = quantizar(img), N.PAL3[3]
    pal = [N.PAL0, [0x0F] + p1, [0x0F] + p2, N.PAL3[:3] + [c3]]
    tela = np.zeros((CH, N.BW, 3)); tela[:, N.CX - N.BX:N.CX - N.BX + CW] = img
    perc_bg = None
    if pontilhado: ind, perc_bg = pontilhar(tela, esc, pal)            # o fundo que a TV mostra (as misturas)
    nt, chr_, usados = alocar(padroes(ind), sync=False)
    meta = bytearray(512)
    meta[0:3] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
    meta[3:9] = bytes(p1 + p2)
    meta[9:33] = atributos(esc)
    meta[33:353] = nt
    for g, (a, b) in enumerate(GRUPOS):
        slots = {nt[r * 16 + c] for r in range(a, b + 1) for c in range(16)}
        lo = [s for s in slots if s < 0x20]
        hi = [s - 0x80 for s in slots if s >= 0x80]
        meta[353 + 2 * g] = -(-(max(lo) + 1) * 16 // 128) if lo else 0
        meta[354 + 2 * g] = -(-(max(hi) + 1) * 16 // 128) if hi else 0
    meta[367] = c3                                                    # v9: 3ª cor da paleta 3 enquanto a capa aparece
    vista_bg = np.zeros((CH, N.BW, 3), np.uint8)
    for y in range(CH):
        for x in range(N.BW):
            vista_bg[y, x] = N.NES[pal[esc[y // 16, x // 16]][ind[y, x]]]
    if perc_bg is not None: vista_bg = perc_bg.round().astype(np.uint8)   # sprites corrigem o percebido
    sprites, spal, vista = SP.otimizar(tela, vista_bg)
    if flicker:
        sf, spal, spal_b, vista, qa, qb = SP.otimizar_flicker(tela, vista_bg, sprites, spal,
                                                              lam=SP.LAMBDA_FLK if lam is None else lam,
                                                              progresso=progresso)
        ind_a = [a for j, i, q, a, b in sf]; ind_b = [b for j, i, q, a, b in sf]
    else:
        spal_b, qa, qb = spal, vista, vista
        ind_a = ind_b = [sp for j, i, q, sp in sprites]
    oam = bytearray([0xF0] * 256)
    oam[0:4] = bytes([15, 0x01, 0x20, 0])
    pares = bytearray(128 * 32)                                      # pares 0-62 (A) e 64-126 (B)
    pares[0] = 0x80                                                   # sincronia: pixel (0,0)
    mascaras = [0] * 63
    mascaras[0] = sum(1 << g for g in grupos_possiveis(15, 30))

    def tile(par, sp):
        for t in range(2):
            for r in range(8):
                linha = sp[t * 8 + r]
                pares[par * 32 + t * 16 + r] = int(''.join(str(v & 1) for v in linha), 2)
                pares[par * 32 + t * 16 + 8 + r] = int(''.join(str(v >> 1) for v in linha), 2)
    for k, (j, i, q, _) in enumerate(sprites):
        par = k + 1
        y = 16 + 16 * j
        oam[par * 4:par * 4 + 4] = bytes([y - 1, 2 * par + 1, q, N.BX + SP.X0 + 8 * i])
        tile(par, ind_a[k])
        tile(par + 64, ind_b[k])
        mascaras[par] = sum(1 << g for g in grupos_possiveis(y - 1, y + 14))
    cab = bytearray(512)
    cab[0:256] = oam
    cab[256:272] = bytes(sum(([0x0F] + p for p in spal), []))
    cab[300] = 1 if flicker else 0
    cab[304:320] = bytes(sum(([0x0F] + p for p in spal_b), []))
    fluxos, setor = b'', 16
    for quadro, base_cab, desloc in ((0, 272, 0), (1, 320, 64)):
        if quadro == 1 and not flicker: break
        for g in range(7):
            ps = [p for p in range(63) if mascaras[p] >> g & 1 and (quadro == 0 or p > 0)]
            if not ps: continue
            a, b = min(ps), max(ps)
            assert ps == list(range(a, b + 1)), 'pares do bloco %d não são contínuos' % g
            dados = bytes(pares[(a + desloc) * 32:(b + desloc + 1) * 32])
            nch = -(-len(dados) // 128)
            dst = 0x1000 + (a + desloc) * 32
            cab[base_cab + 4 * g:base_cab + 4 * g + 4] = bytes([setor, nch, dst & 255, dst >> 8])
            bloco = dados.ljust(-(-len(dados) // 512) * 512, b'\0')
            fluxos += bloco
            setor += len(bloco) // 512
    reg = bytes(meta) + b''.join(chr_) + bytes(cab) + fluxos
    assert len(reg) <= SETORES_V8 * 512, 'registro v8 com %d setores' % (len(reg) // 512)
    reg += bytes(SETORES_V8 * 512 - len(reg))
    usa3 = int(((esc == 3)).sum())
    # estrutura para recolorir sem reconverter (editor de cores da ferramenta: capa_grande_cores)
    spr = [(j, i, q, np.asarray(ind_a[k], np.uint8), np.asarray(ind_b[k], np.uint8))
           for k, (j, i, q, _) in enumerate(sprites)]
    est = dict(ind=np.asarray(ind, np.uint8), esc=np.asarray(esc, np.uint8), bg=[list(p1), list(p2)], c3=int(c3),
               spr=spr, spA=[list(p) for p in spal], spB=[list(p) for p in spal_b], flicker=flicker,
               pontilhado=pontilhado)
    return reg, vista, dict(tiles=usados, sprites=len(sprites), vista_bg=vista_bg, quadro_a=qa, quadro_b=qb,
                            flicker=flicker, cor3=c3, blocos_pal3=usa3, est=est)


def converter_v9(path, crc, forca=180, flicker=False, lam=None, pontilhado=False, progresso=None):
    """v9: converte com e sem a cor livre da paleta 3 e fica com a que erra menos (nunca piora).
    progresso(fração 0-1): andamento (só a parte demorada, a do flicker), para a barra da ferramenta."""
    alvo = np.zeros((CH, N.BW, 3)); alvo[:, N.CX - N.BX:N.CX - N.BX + CW] = S.carregar(path, CW, CH, forca)
    L = S.lab(alvo)[:, N.CX - N.BX:N.CX - N.BX + CW]
    melhor = None
    for k, c3 in enumerate((False, True)):
        prog = (lambda f, k=k: progresso((k + f) / 2)) if progresso else None
        reg, vista, info = converter_v8(path, crc, forca, flicker=flicker, cor3=c3, lam=lam, pontilhado=pontilhado,
                                        progresso=prog)
        e = float(np.sqrt(((L - S.lab(vista.astype(float))[:, N.CX - N.BX:N.CX - N.BX + CW]) ** 2).sum(-1)).mean())
        info['erro'] = e
        if melhor is None or e < melhor[2]['erro'] - 1e-9: melhor = (reg, vista, info)
    return melhor
