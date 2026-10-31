"""Partes pesadas da conversão das capas em NumPy, com resultado IDÊNTICO ao do código em Python puro.

Regras para não mudar nenhum bit:
- somas na mesma ordem do Python (`np.cumsum(...)[..., -1]`, que soma em sequência; `np.sum` não serve);
- `x ** 2` e `x ** 0.5` calculados pelo próprio Python (`quad`/`raiz`): no Windows o `pow` do Python às vezes
  difere no último bit do `x*x`/`sqrt` do NumPy;
- `min`/`max`/argmin com o mesmo critério de empate (o primeiro);
- multiplicações e subtrações (exatas em IEEE nos dois).
Conferido com `referencia_conversao.py` (código antigo x novo, várias capas e níveis).
"""
import numpy as np


def quad(a):
    """a ** 2 elemento a elemento, com o pow do Python (idêntico ao código antigo)."""
    a = np.asarray(a, dtype=np.float64)
    return np.array([x ** 2 for x in a.ravel().tolist()], dtype=np.float64).reshape(a.shape)


def soma_seq(a, eixo=-1):
    """Soma na ordem do Python (0 + a0 + a1 + ...), ao longo do eixo."""
    a = np.asarray(a, dtype=np.float64)
    if a.shape[eixo] == 0: return np.zeros(np.delete(a.shape, eixo))
    return np.take(np.cumsum(a, axis=eixo), -1, axis=eixo)


def tabela_dist(colors, lab, rgb):
    """dtable(): {cor: [dist(cor, NES i) for i in 0..63]} — a mesma fórmula do build_poc.dist."""
    cols = list(colors)
    LA = [lab(c) for c in cols]
    LB = [lab(rgb(i)) for i in range(64)]
    ca = np.array([(l[1] ** 2 + l[2] ** 2) ** 0.5 for l in LA])
    cb = np.array([(l[1] ** 2 + l[2] ** 2) ** 0.5 for l in LB])
    A, B = np.array(LA), np.array(LB)
    dl = A[:, None, 0] - B[None, :, 0]
    dc = ca[:, None] - cb[None, :]
    v = (quad(A[:, None, 1] - B[None, :, 1]) + quad(A[:, None, 2] - B[None, :, 2])) - dc * dc
    dh2 = np.where(v > 0.0, v, 0.0)                     # max(0.0, v) do Python
    D = (dl * dl + dc * dc) + 3.0 * dh2
    return {c: row for c, row in zip(cols, D.tolist())}


class Unidades:
    """Unidades do optimize() (pixels únicos com contagem + cores extras fixas) em matrizes."""

    def __init__(self, units, D, black):
        cores, idx = [], {}
        for ub, _ in units:
            for p, _ in ub:
                if p not in idx: idx[p] = len(cores); cores.append(p)
        Dm = np.array([D[c] for c in cores])
        U, L = len(units), max(1, max(len(ub) for ub, _ in units))
        ID = np.zeros((U, L), dtype=np.int64)
        self.N = np.zeros((U, L))
        self.base = np.zeros((U, L))                     # min(D[p][BLACK], D[p][extra...]) — fixo
        for k, (ub, extra) in enumerate(units):
            ids = [idx[p] for p, _ in ub]
            ID[k, :len(ids)] = ids
            self.N[k, :len(ids)] = [n for _, n in ub]
            self.base[k, :len(ids)] = Dm[ids][:, [black] + list(extra)].min(axis=1)
        self.DID = Dm[ID]                                 # (U, L, 64)

    def erros(self, pal):
        """uerr(u, pal) de todas as unidades: sum(n * min(D[p][c] for c in [BLACK]+pal+extra))."""
        m = np.minimum(self.base, self.DID[:, :, list(pal)].min(axis=2))
        return soma_seq(self.N * m, 1)


def total_min(perr):
    """sum(min(perr[q][k] for q) for k), na ordem do Python."""
    return float(soma_seq(np.asarray(perr).min(axis=0)))


def total_fixo(perr, assign):
    """sum(perr[assign[k]][k] for k), na ordem do Python."""
    perr = np.asarray(perr)
    return float(soma_seq(perr[np.asarray(assign), np.arange(perr.shape[1])]))


class CustoTiles:
    """cost(g) do conv_v2 (padrão fundido de um grupo de tiles e o custo dele), com memória:
    o mesmo grupo nunca é calculado duas vezes. pix_cost(t, i, v) é a função original."""

    def __init__(self, ntiles, tiles, pix_cost):
        self.PC = np.array([[[pix_cost(t, i, v) for v in range(4)] for i in range(64)] for t in range(ntiles)],
                           dtype=np.float64)
        self.NN = np.array([[tiles[t][i] is not None for i in range(64)] for t in range(ntiles)])
        self.memo = {}

    def __call__(self, g):
        k = tuple(g)
        r = self.memo.get(k)
        if r is None:
            arr = self.PC[list(g)]                                  # (n, 64, 4)
            S = soma_seq(arr, 0)                                    # sum(pix_cost(t,i,v) for t in g)
            best = S.argmin(axis=1)                                 # min(range(4), key=...) — o primeiro
            fixo = self.NN[list(g)].any(axis=0)
            vals = np.take_along_axis(arr, np.broadcast_to(best[None, :, None], (arr.shape[0], 64, 1)), 2)[:, :, 0]
            vals = np.where(fixo[None, :], vals, 0.0)
            c = float(soma_seq(vals.ravel()))                       # t por fora, i por dentro
            pat = [int(b) if f else None for b, f in zip(best.tolist(), fixo.tolist())]
            r = self.memo[k] = (c, pat)
        return r[0], list(r[1])
