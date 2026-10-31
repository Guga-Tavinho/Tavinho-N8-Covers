"""Camada de SPRITES por cima da capa grande (v5): até 62 sprites 8x16 com 4 paletas próprias (12 cores).

Os sprites ficam numa grade alinhada à capa: faixas de 16 linhas (j = 0..9, y = 16 + 16j na tela) e colunas de
8 pontos (x = 136 + 8i, i = 0..13). No máximo 8 sprites por faixa (7 na faixa 0: o sprite 0 de sincronia fica
nas linhas 16-31). Cada ponto do sprite é transparente (mostra o fundo) ou uma das 3 cores da paleta dele: só
pinta onde fica melhor que o fundo.
Otimização: paletas iniciais das células de maior erro; depois, alternando, (a) cada célula escolhe a paleta que
mais ganha, (b) escolhe as células de maior ganho respeitando o limite por faixa, (c) cada cor de cada paleta é
trocada pela que mais ganha nas células escolhidas.
"""
import numpy as np
import sim_tela_cheia as S

FAIXAS, COLS = 10, 14
X0 = 8                                  # na região de 128 colunas da capa (tela x 128-255), a imagem começa em 8
MAX_SPR = 62
MAX_FAIXA = [7] + [8] * (FAIXAS - 1)


def otimizar(tela, vista_bg, voltas=5):
    """tela: imagem alvo 160x128 RGB (float); vista_bg: o fundo convertido 160x128 RGB.
    -> (lista de sprites [(faixa, coluna, paleta, índices 16x8)], paletas [4][3] (NES), vista final RGB)"""
    L = S.lab(tela)
    errbg = ((L - S.lab(vista_bg.astype(float))) ** 2).sum(-1)
    Dc = ((L[..., None, :] - S.LAB[None, None, :, :]) ** 2).sum(-1)            # 160x128x54
    celulas = [(j, i) for j in range(FAIXAS) for i in range(COLS)]
    pix = lambda j, i: (slice(16 * j, 16 * j + 16), slice(X0 + 8 * i, X0 + 8 * i + 8))
    eb = {c: errbg[pix(*c)].ravel() for c in celulas}
    dc = {c: Dc[pix(*c)].reshape(-1, Dc.shape[-1]) for c in celulas}

    def ganho(c, pal):
        m = np.minimum(eb[c], dc[c][:, pal].min(1))
        return eb[c].sum() - m.sum()

    def gulosa(c):
        m = eb[c].copy(); esc = []
        for _ in range(3):
            k = int(np.argmin(np.minimum(m[:, None], dc[c]).sum(0))); esc.append(k); m = np.minimum(m, dc[c][:, k])
        return esc
    ordem = sorted(celulas, key=lambda c: -eb[c].sum())
    pals, usadas = [], []
    for c in ordem:                                                    # 4 paletas de células bem diferentes
        p = gulosa(c)
        if all(len(set(p) & set(q)) < 2 for q in pals): pals.append(p)
        if len(pals) == 4: break
    while len(pals) < 4: pals.append(gulosa(ordem[len(pals)]))
    escolha = {}
    for _ in range(voltas):
        g = {c: max((ganho(c, pals[q]), q) for q in range(4)) for c in celulas}
        por_faixa = [0] * FAIXAS
        escolha = {}
        for c in sorted(celulas, key=lambda c: -g[c][0]):
            if len(escolha) >= MAX_SPR or g[c][0] <= 0: break
            if por_faixa[c[0]] < MAX_FAIXA[c[0]]:
                escolha[c] = g[c][1]; por_faixa[c[0]] += 1
        for q in range(4):
            cs = [c for c, qq in escolha.items() if qq == q]
            if not cs: continue
            e = np.concatenate([eb[c] for c in cs]); d = np.concatenate([dc[c] for c in cs])
            for s in range(3):
                outras = [pals[q][k] for k in range(3) if k != s]
                m = np.minimum(e, d[:, outras].min(1))
                pals[q][s] = int(np.argmin(np.minimum(m[:, None], d).sum(0)))
    vista = vista_bg.copy()
    sprites = []
    for (j, i), q in sorted(escolha.items()):
        d = dc[(j, i)][:, pals[q]]
        k = d.argmin(1)
        usa = d.min(1) < eb[(j, i)]
        ind = np.where(usa, k + 1, 0).reshape(16, 8).astype(np.uint8)
        sprites.append((j, i, q, ind))
        bloco = vista[pix(j, i)]
        cores = S.RGB[np.array(pals[q])].astype(np.uint8)
        for yy in range(16):
            for xx in range(8):
                if ind[yy, xx]: bloco[yy, xx] = cores[ind[yy, xx] - 1]
    pals_nes = [[S.CORES[k][0] for k in p] for p in pals]
    return sprites, pals_nes, vista


# ---------------------------------------------------------------- v8: sprites com FLICKER (opcional por capa)
LAMBDA_FLK = 0.05                                  # penalidade do tremido: LAMBDA_FLK * ΔE(cor A, cor B)²


def _lin(rgb):
    c = np.asarray(rgb, float) / 255.0
    return np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)


def _lab_lin(lin):
    """RGB linear (0-1) -> CIELAB (o mesmo cálculo do sim_tela_cheia.lab, sem a curva do sRGB)."""
    xyz = lin @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _unlin(l):
    l = np.clip(l, 0, 1)
    return np.where(l > 0.0031308, 1.055 * l ** (1 / 2.4) - 0.055, l * 12.92) * 255


def otimizar_flicker(tela, vista_bg, sprites, pals, lam=LAMBDA_FLK, voltas=3, progresso=None):
    """Parte da solução sem flicker (mesmas células e paletas por sprite) e dá a cada sprite um 2º quadro (B):
    paletas de sprite próprias no quadro B e um tile B. Cada ponto vê a média (luz) das cores dos 2 quadros
    (cada uma: o fundo, se transparente, ou uma das 3 cores da paleta). Custo = ΔE² até o alvo + lam * ΔE²(A, B).
    -> (sprites [(j, i, q, indA, indB)], palsA, palsB (NES), vista RGB percebida, quadro A RGB, quadro B RGB)"""
    rgb_nes = {k: np.array(S.CORES[k][1], float) for k in range(len(S.CORES))}
    idx = {nes: k for k, (nes, _) in enumerate(S.CORES)}
    linC = _lin(np.array([c for _, c in S.CORES], float))                     # 54 x 3
    labC = _lab_lin(linC)
    cel = [(j, i, q) for j, i, q, _ in sprites]
    pix = lambda j, i: (slice(16 * j, 16 * j + 16), slice(X0 + 8 * i, X0 + 8 * i + 8))
    T = np.concatenate([S.lab(tela[pix(j, i)]).reshape(-1, 3) for j, i, q in cel])
    BG = np.concatenate([_lin(vista_bg[pix(j, i)]).reshape(-1, 3) for j, i, q in cel])
    Q = np.concatenate([np.full(128, q) for j, i, q in cel])
    A = [[idx[c] for c in p] for p in pals]
    B = [list(p) for p in A]

    def custo(qs, pa, pb):
        """Para os pontos com paleta q: melhor par (a, b) e o custo, com pa/pb = 3 cores (índices em CORES)."""
        m = Q == qs
        bg = BG[m]
        oa = np.concatenate([bg[:, None, :], np.broadcast_to(linC[pa], (len(bg), 3, 3))], 1)    # N x 4 x 3
        ob = np.concatenate([bg[:, None, :], np.broadcast_to(linC[pb], (len(bg), 3, 3))], 1)
        mix = _lab_lin((oa[:, :, None, :] + ob[:, None, :, :]) / 2)                            # N x 4 x 4 x 3
        la, lb = _lab_lin(oa), _lab_lin(ob)
        c = ((mix - T[m][:, None, None, :]) ** 2).sum(-1) + lam * ((la[:, :, None, :] - lb[:, None, :, :]) ** 2).sum(-1)
        flat = c.reshape(len(bg), 16)
        k = flat.argmin(1)
        return flat.min(1).sum(), k // 4, k % 4
    def busca(q, em_a, s):
        """Custo total de cada uma das 54 cores no espaço s da paleta q (quadro A ou B), todas de uma vez: o que
        não muda (as outras 3 opções do quadro e o outro quadro) é calculado uma vez só (antes: 54 x tudo)."""
        m = Q == q
        bg, t = BG[m], T[m]
        oa = np.concatenate([bg[:, None, :], np.broadcast_to(linC[A[q]], (len(bg), 3, 3))], 1)    # N x 4 x 3
        ob = np.concatenate([bg[:, None, :], np.broadcast_to(linC[B[q]], (len(bg), 3, 3))], 1)
        la, lb = _lab_lin(oa), _lab_lin(ob)
        c = ((_lab_lin((oa[:, :, None, :] + ob[:, None, :, :]) / 2) - t[:, None, None, :]) ** 2).sum(-1) \
            + lam * ((la[:, :, None, :] - lb[:, None, :, :]) ** 2).sum(-1)                       # N x 4 x 4
        # a mistura de cada candidata com as 4 opções do outro quadro: só a do fundo depende do ponto; as 3 da
        # paleta são iguais em todos os pontos (54 x 3, calculadas uma vez)
        outro = B[q] if em_a else A[q]
        mix = np.concatenate([_lab_lin((linC[None, :, :] + bg[:, None, :]) / 2)[:, :, None, :],
                              np.broadcast_to(_lab_lin((linC[:, None, :] + linC[outro][None, :, :]) / 2)[None],
                                              (len(bg), len(linC), 3, 3))], 2)                  # N x 54 x 4 x 3
        lo = lb if em_a else la                                                                  # Lab do outro quadro
        cand = (((mix - t[:, None, None, :]) ** 2).sum(-1)
                + lam * ((labC[None, :, None, :] - lo[:, None, :, :]) ** 2).sum(-1)).min(2)       # N x 54
        if em_a: c[:, s + 1, :] = np.inf                                                         # a opção que muda
        else: c[:, :, s + 1] = np.inf
        return np.minimum(c.reshape(len(bg), 16).min(1)[:, None], cand).sum(0)                  # 54
    passos, feitos = voltas * 6 * sum(1 for q in range(4) if (Q == q).any()), 0
    for _ in range(voltas):
        for q in range(4):
            if not (Q == q).any(): continue
            for quadro, em_a in ((A, True), (B, False)):
                for s in range(3):
                    quadro[q][s] = int(np.argmin(busca(q, em_a, s)))
                    feitos += 1
                    if progresso: progresso(feitos / passos)                # (a barra da ferramenta)
    ka = np.zeros(len(T), int); kb = np.zeros(len(T), int)
    for q in range(4):
        m = Q == q
        if m.any(): _, ka[m], kb[m] = custo(q, A[q], B[q])
    # imagens: quadro A, quadro B e a média percebida
    qa = vista_bg.astype(float).copy(); qb = vista_bg.astype(float).copy(); perc = vista_bg.astype(float).copy()
    out = []
    o = 0
    for (j, i, q) in cel:
        a = ka[o:o + 128].reshape(16, 8); b = kb[o:o + 128].reshape(16, 8)
        bg = vista_bg[pix(j, i)].astype(float)
        ca = np.where(a[..., None] > 0, linC[np.array(A[q])[np.maximum(a - 1, 0)]], _lin(bg))
        cb = np.where(b[..., None] > 0, linC[np.array(B[q])[np.maximum(b - 1, 0)]], _lin(bg))
        qa[pix(j, i)] = _unlin(ca); qb[pix(j, i)] = _unlin(cb); perc[pix(j, i)] = _unlin((ca + cb) / 2)
        out.append((j, i, q, a.astype(np.uint8), b.astype(np.uint8)))
        o += 128
    nes = lambda p: [[S.CORES[k][0] for k in x] for x in p]
    return out, nes(A), nes(B), perc.round().astype(np.uint8), qa.round().astype(np.uint8), qb.round().astype(np.uint8)
