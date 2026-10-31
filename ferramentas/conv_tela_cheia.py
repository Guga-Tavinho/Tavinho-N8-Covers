"""Conversão de uma capa para o visualizador em TELA CHEIA (POC): 176x240, só fundo, 4 paletas.

Tela: 32x30 tiles; a capa nas colunas 6-27 (x = 48, alinhada à grade de atributos 16x16). Os tiles vêm de 3 blocos
de 4 KB da CHR, trocados no meio do quadro pelo registrador $82 do cartucho:
  bloco 2 (banco 2, topo):   linhas de tiles 0-9
  bloco 3 (banco 3):         linhas 9-19   (+ tiles $FE/$FF: sprite de sincronia, usado com o banco 2 no topo)
  bloco 4 (banco 4):         linhas 19-29
As linhas 9 e 19 existem nos dois blocos vizinhos com os MESMOS números de tile: a troca pode acontecer em
qualquer ponto dessas 8 linhas de pixels (não precisa acertar o fim exato de uma linha).

Dados de uma capa (27 setores):
  setor 0      verificação (CRC do nome, 4 bytes = 'cur' do OS), paletas 16, sprite 0 (Y, tile, atributo, X),
               esperas (Y1, A1, Y2, A2)
  setores 1-2  nametable $2000 (960 tiles + 64 atributos)
  setores 3-18 blocos 2 e 3 (PPU $0000-$1FFF com o banco 2)
  setores 19-26 bloco 4 (PPU $1000-$1FFF com o banco 3)
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_tela_cheia as S

W, H, X0 = 176, 240, 48
LINHA_1, LINHA_2 = 75, 155               # meio das janelas de troca (linhas de pixels 71-79 e 151-159)
TILE_SYNC = 0xFE                          # bloco 3: $FE = pixel (0,0) opaco, $FF = vazio (sprite 8x16 $FF)
SETORES = 27


def quantizar(img, preto=True):
    """img (240x176x3) -> (índices 0-3 por pixel, paleta de cada bloco 16x16, fundo, 4 paletas [NES])."""
    h, w, _ = img.shape
    L = S.lab(img).reshape(-1, 3)
    D = ((L[:, None, :] - S.LAB[None, :, :]) ** 2).sum(-1)
    blocos = []
    for by in range(0, h, 16):
        for bx in range(0, w, 16):
            ys, xs = np.mgrid[by:min(h, by + 16), bx:min(w, bx + 16)]
            blocos.append((ys * w + xs).ravel())
    fundos = [int(np.argmin(S.RGB.sum(1)))] if preto else None    # fundo preto: as bordas da tela ficam pretas
    _, bg, pals, esc = S.otimizar(D, blocos, fundos=fundos)
    idx = np.zeros(h * w, np.uint8)
    for b, q in zip(blocos, esc):
        cores = [bg] + pals[q]
        idx[b] = D[b][:, cores].argmin(1)
    return idx.reshape(h, w), np.array(esc).reshape((h + 15) // 16, (w + 15) // 16), bg, pals


def tiles_da_tela(idx):
    """Tela 240x256 de índices -> lista [linha][coluna] de padrões de 16 bytes."""
    out = []
    for ty in range(30):
        linha = []
        for tx in range(32):
            t = idx[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
            p0 = bytes(int(''.join(str(v & 1) for v in r), 2) for r in t)
            p1 = bytes(int(''.join(str(v >> 1) for v in r), 2) for r in t)
            linha.append(p0 + p1)
        out.append(linha)
    return out


def alocar(pad):
    """Números de tile por bloco (2, 3, 4), com as linhas 9 e 19 iguais nos dois blocos vizinhos."""
    grupos = {2: range(0, 10), 3: range(9, 20), 4: range(19, 30)}
    mapa = {b: {} for b in grupos}
    livre = {b: set(range(256)) - ({TILE_SYNC, TILE_SYNC + 1} if b == 3 else set()) for b in grupos}

    def fixar(p, blocos):
        if all(p in mapa[b] for b in blocos): return
        ja = [mapa[b][p] for b in blocos if p in mapa[b]]
        i = ja[0] if ja else min(set.intersection(*[livre[b] for b in blocos]))
        for b in blocos:
            assert mapa[b].get(p, i) == i, 'conflito de tile compartilhado'
            if p not in mapa[b]: mapa[b][p] = i; livre[b].discard(i)
    for p in pad[9]: fixar(p, (2, 3))
    for p in pad[19]: fixar(p, (3, 4))
    for b, linhas in grupos.items():
        for ty in linhas:
            for p in pad[ty]:
                if p not in mapa[b]:
                    assert livre[b], 'bloco %d sem espaço' % b
                    i = min(livre[b]); mapa[b][p] = i; livre[b].discard(i)
    nt = bytearray(960)
    for ty in range(30):
        b = 2 if ty < 10 else 3 if ty < 20 else 4
        for tx in range(32):
            nt[ty * 32 + tx] = mapa[b][pad[ty][tx]]
    chr_ = {}
    for b in grupos:
        c = bytearray(4096)
        for p, i in mapa[b].items(): c[i * 16:i * 16 + 16] = p
        chr_[b] = c
    chr_[3][TILE_SYNC * 16] = 0x80                                     # sprite de sincronia: só o pixel (0,0)
    return nt, chr_, {b: len(m) for b, m in mapa.items()}


def espera(ciclos):
    """(Y, A) com Y*(5A+6)+15 o mais perto possível de `ciclos`."""
    melhor = None
    for a in range(1, 256):
        y = max(1, min(255, round((ciclos - 15) / (5 * a + 6))))
        e = abs(y * (5 * a + 6) + 15 - ciclos)
        if melhor is None or e < melhor[0]: melhor = (e, y, a)
    return melhor[1], melhor[2]


def converter(path, forca=120, preto=True):
    """-> dict com os 27 setores (bytes) sem o CRC (posto depois), a imagem vista e informações."""
    img = S.carregar(path, W, H, forca)
    idx, esc, bg, pals = quantizar(img, preto)
    tela = np.zeros((240, 256), np.uint8); tela[:, X0:X0 + W] = idx
    attr_blocos = np.zeros((15, 16), np.uint8); attr_blocos[:, X0 // 16:X0 // 16 + W // 16] = esc
    attr = bytearray(64)
    for by in range(15):
        for bx in range(16):
            sh = (2 if bx & 1 else 0) + (4 if by & 1 else 0)
            attr[(by // 2) * 8 + bx // 2] |= int(attr_blocos[by, bx]) << sh
    nt, chr_, usados = alocar(tiles_da_tela(tela))
    pal16 = bytearray()
    for q in range(4): pal16 += bytes([S.CORES[bg][0]] + [S.CORES[c][0] for c in pals[q]])
    # sprite 0: primeiro pixel opaco do fundo (índice != 0) nas linhas 1-63, x 8-247
    ys, xs = np.nonzero(tela[1:64, 8:248])
    assert len(ys), 'sem pixel opaco no topo para o sprite 0'
    k = np.lexsort((xs, ys))[0]; hy, hx = int(ys[k]) + 1, int(xs[k]) + 8
    spr = bytes([hy - 1, TILE_SYNC | 1, 0x20, hx])                     # Y-1, tile $FF (8x16: $FE/$FF da tabela 1), atrás do fundo
    # esperas: do sprite 0 (linha hy, ponto ~hx) até o meio das janelas; cada escrita custa ~20 ciclos depois da espera
    c1 = ((LINHA_1 - hy) * 341 + (300 - hx)) / 3 - 30
    c2 = (LINHA_2 - LINHA_1) * 341 / 3 - 20
    y1, a1 = espera(c1); y2, a2 = espera(c2)
    meta = bytearray(512)
    meta[4:20] = pal16; meta[20:24] = spr; meta[24:28] = bytes([y1, a1, y2, a2])
    setores = bytes(meta) + bytes(nt) + bytes(attr) + bytes(chr_[2]) + bytes(chr_[3]) + bytes(chr_[4])
    assert len(setores) == SETORES * 512
    rgb = np.zeros((240, 256, 3), np.uint8)
    nes = {i: rgb_ for i, rgb_ in S.CORES}
    for y in range(240):
        for x in range(256):
            q = attr_blocos[y // 16, x // 16]
            rgb[y, x] = nes[pal16[q * 4 + tela[y, x]]]
    return dict(setores=setores, vista=rgb, sprite0=(hy, hx), esperas=(y1, a1, y2, a2), tiles=usados,
                pal16=bytes(pal16), tela=tela, attr_blocos=attr_blocos)
