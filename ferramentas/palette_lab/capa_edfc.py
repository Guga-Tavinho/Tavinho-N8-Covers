"""Ponte Palette Lab -> COVERS.BIN da firmware EDFC.

Um projeto no modo capa (64x96, blocos 8x16) é exatamente o modelo da firmware v1: 48 sprites
8x16, cada um com 1 de 4 paletas (3 cores + preto). O registro é gerado a partir do mapa de
espaços (slot_map) do projeto, sem reconverter a imagem.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nes_core import Projeto, BLACK, NES_RGB


def load_project(path):
    p = Projeto()
    p.from_json(open(path, encoding='utf-8').read())
    return p


def record_v1(p, crc):
    """Registro v1 (4 setores): OAM[256] + paleta[16] + verificação[3] / 1536 bytes de tiles."""
    from build_poc import make_tiles, make_oam, COVER_W, COVER_H
    if not p.is_capa():
        raise ValueError('o projeto não está no modo capa (64×96, bloco 8×16)')
    meta = bytearray(512)
    meta[0:256] = make_oam(list(p.block_pal))
    pal16 = bytearray()
    for g in range(4):
        pal = p.palettes[g] if g < len(p.palettes) and g not in p.pal_off else []
        pal = list(pal) + [BLACK] * (3 - len(pal))
        pal16 += bytes([BLACK] + pal)
    meta[256:272] = pal16
    meta[272:275] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
    pix = [[p.slot_map[y * 64 + x] for x in range(COVER_W)] for y in range(COVER_H)]
    tiles = make_tiles(pix)
    assert len(tiles) == 1536
    preview = [[NES_RGB[p.idx_map[y * 64 + x]] for x in range(64)] for y in range(96)]
    return bytes(meta) + bytes(tiles), preview


def project_pixels(p, w=64, h=96):
    """Imagem já convertida do projeto (cores NES), como entrada para outros formatos."""
    from PIL import Image
    im = p.output_image()
    if im.size != (w, h):
        cw = min(im.width, im.height * w / h); ch = cw * h / w
        x0, y0 = int((im.width - cw) / 2), int((im.height - ch) / 2)
        im = im.crop((x0, y0, x0 + round(cw), y0 + round(ch))).resize((w, h), Image.Resampling.LANCZOS)
    data = list(im.getdata())
    return [data[y * w:(y + 1) * w] for y in range(h)]
