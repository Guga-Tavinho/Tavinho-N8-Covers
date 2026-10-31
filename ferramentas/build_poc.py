"""PoC: capa FIXA no navegador do EverDrive N8 clone (EDFC), usando sprites 8x16.

uso:  python build_poc.py [--perfil base|v126] [capa.png]
  perfil padrão: base  (firmware_base/EDFC/OS.BIN, o OS que roda no clone)
  sem PNG -> gera uma capa de teste.
saida: poc_capa_fixa/EDFC/OS.BIN (base) ou poc_capa_fixa_v126/EDFC/OS.BIN, + preview_capa.png

O que é alterado no OS.BIN (endereços do perfil "base"; ver NOTAS-TECNICAS-FIRMWARE.md):
  CHR tab.1 (arquivo 0x1000-0x15FF) : 96 tiles da capa (48 sprites 8x16)
  CHR banco (arquivo 0x1EF0-0x1EFF) : paleta dos sprites, lida em $7EF0 com reg $81=$09
  CHR banco (arquivo 0x1F00-0x1FFF) : tabela OAM pronta, lida em $7F00 com reg $81=$09
  $81C5  hook_cursor: JSR $83E6 / (cai em cover_show)   [sobre a rotina de checksum morta]
  $81C8  cover_show A: banco CHR, copia OAM p/ $0200, vblank, paleta $3F10, JMP parte B
  $FBD4  cover_show B: WRAM de volta, OAMDMA, PPUCTRL=$A0, scroll 0,0, PPUMASK=$1E
  $CB8B  LDA #$0A/STA $2001 -> JSR cover_show (redesenho completo da lista)
  $CB94  JSR $83E6 -> JSR hook_cursor          (cursor mudou)
  $82EB,$841A,$BB9B: PPUCTRL $80->$A0 ; $83FF: $84->$A4  (sprites 8x16)
  $CB29  tamanho do nome na lista 29 -> 21 (abre espaço para a capa)
  $833D  JMP $8343 -> JSR $81DE (esconde a capa quando um menu/popup redesenha a tela)
"""
import hashlib, os, struct, sys, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROFILES = {
    # OS que roda no cartucho clone (pasta EDFC-20261023T010636Z-1-001)
    'base': dict(src='firmware_base/EDFC/OS.BIN', sha1='dbea89d33eacd7ae72ee24d2652727b0cb5740ae',
                 out='poc_capa_fixa', part_b=0xFBD4,
                 mask_full=0xCB8B, cursor_call=0xCB94, name_len=0xCB29,
                 ppuctrl=(0x82EB, 0x841A, 0xBB9B), ppuctrl_inc=0x83FF),
    # nesos-v1.26 original do krikzz (primeira análise)
    'v126': dict(src='firmware_original/EDFC/OS.BIN', sha1='8a5cd5659b87202cdc7f037cba696f69e95defce',
                 out='poc_capa_fixa_v126', part_b=0xFBA2,
                 mask_full=0xCB6F, cursor_call=0xCB78, name_len=0xCB0D,
                 ppuctrl=(0x82EB, 0x841A, 0xBCB0), ppuctrl_inc=0x83FF),
}

COVER_W, COVER_H = 64, 96          # 8 x 6 sprites 8x16
COVER_X, COVER_Y = 184, 40         # colunas 23-30, abaixo do topo da lista
COLS, ROWS = COVER_W // 8, COVER_H // 16

ADDR_HOOK = 0x81C5                 # rotina de checksum sem chamadores ($81C5-$820F) nos dois builds
DEAD_END = 0x8210
PAL_FILE_OFS = 0x1EF0              # banco CHR mapeado em $6000 -> $7EF0
OAM_FILE_OFS = 0x1F00              # banco CHR mapeado em $6000 -> $7F00

# Paleta NES 2C02 (valores estilo FCEUX). Índices "pretos" duplicados ficam de fora.
NES_RGB = [
    0x7C7C7C, 0x0000FC, 0x0000BC, 0x4428BC, 0x940084, 0xA80020, 0xA81000, 0x881400,
    0x503000, 0x007800, 0x006800, 0x005800, 0x004058, 0x000000, 0x000000, 0x000000,
    0xBCBCBC, 0x0078F8, 0x0058F8, 0x6844FC, 0xD800CC, 0xE40058, 0xF83800, 0xE45C10,
    0xAC7C00, 0x00B800, 0x00A800, 0x00A844, 0x008888, 0x000000, 0x000000, 0x000000,
    0xF8F8F8, 0x3CBCFC, 0x6888FC, 0x9878F8, 0xF878F8, 0xF85898, 0xF87858, 0xFCA044,
    0xF8B800, 0xB8F818, 0x58D854, 0x58F898, 0x00E8D8, 0x787878, 0x000000, 0x000000,
    0xFCFCFC, 0xA4E4FC, 0xB8B8F8, 0xD8B8F8, 0xF8B8F8, 0xF8A4C0, 0xF0D0B0, 0xFCE0A8,
    0xF8D878, 0xD8F878, 0xB8F8B8, 0xB8F8D8, 0x00FCFC, 0xF8D8F8, 0x000000, 0x000000]
BLACK = 0x0F
USABLE = [i for i in range(64) if i not in (0x0D, 0x0E, 0x0F, 0x1D, 0x1E, 0x1F, 0x2E, 0x2F, 0x3E, 0x3F)]


def rgb(i):
    v = NES_RGB[i]
    return (v >> 16) & 255, (v >> 8) & 255, v & 255


_LAB = {}


def lab(c):
    """sRGB -> CIE Lab (D65), com cache."""
    v = _LAB.get(c)
    if v is None:
        def lin(u):
            u /= 255.0
            return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4
        r, g, b = lin(c[0]), lin(c[1]), lin(c[2])
        x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
        y = 0.2126 * r + 0.7152 * g + 0.0722 * b
        z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
        f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
        fx, fy, fz = f(x), f(y), f(z)
        v = _LAB[c] = (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))
    return v


def dist(a, b):
    """Distância perceptual em Lab, pesando mais o TOM do que a saturação: o NES não tem várias
    cores (ex.: amarelo-limão), e trocar amarelo por amarelo-claro incomoda menos que por verde."""
    la, lb = lab(a), lab(b)
    dl = la[0] - lb[0]
    ca, cb = (la[1] ** 2 + la[2] ** 2) ** 0.5, (lb[1] ** 2 + lb[2] ** 2) ** 0.5
    dc = ca - cb
    dh2 = max(0.0, (la[1] - lb[1]) ** 2 + (la[2] - lb[2]) ** 2 - dc * dc)
    return dl * dl + dc * dc + 3.0 * dh2


# ---------------------------------------------------------------- PNG (sem dependências)
def png_read(path):
    data = open(path, 'rb').read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'não é PNG'
    pos, idat, plte, trns = 8, b'', None, None
    while pos < len(data):
        n, typ = struct.unpack('>I4s', data[pos:pos + 8]); body = data[pos + 8:pos + 8 + n]; pos += 12 + n
        if typ == b'IHDR': w, h, depth, ctype, _, _, inter = struct.unpack('>IIBBBBB', body)
        elif typ == b'PLTE': plte = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif typ == b'tRNS': trns = body
        elif typ == b'IDAT': idat += body
    if depth != 8 or inter != 0:
        sys.exit('PNG precisa ser 8 bits por canal e sem entrelaçamento')
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat); stride = w * bpp; rows = []; prev = bytearray(stride); i = 0
    for _ in range(h):
        f = raw[i]; line = bytearray(raw[i + 1:i + 1 + stride]); i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0; b = prev[x]; c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line); prev = line
    px = []
    for line in rows:
        out = []
        for x in range(w):
            s = line[x * bpp:(x + 1) * bpp]
            if ctype == 0: out.append((s[0],) * 3)
            elif ctype == 2: out.append(tuple(s))
            elif ctype == 3: out.append(plte[s[0]] if not (trns and s[0] < len(trns) and trns[s[0]] == 0) else (0, 0, 0))
            elif ctype == 4: out.append(tuple(v * s[1] // 255 for v in (s[0],) * 3))
            else: out.append(tuple(v * s[3] // 255 for v in s[:3]))
        px.append(out)
    return w, h, px


def png_write(path, w, h, px, scale=1):
    raw = b''.join(b'\0' + bytes(v for x in range(w * scale) for v in px[y // scale][x // scale])
                   for y in range(h * scale))
    def chunk(t, b): return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b))
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w * scale, h * scale, 8, 2, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def resize(w, h, px, nw, nh):
    """Redimensiona por média de área (preenche a área, cortando o excesso no centro)."""
    s = max(nw / w, nh / h); cw, ch = nw / s, nh / s; ox, oy = (w - cw) / 2, (h - ch) / 2
    out = []
    for y in range(nh):
        y0, y1 = oy + y * ch / nh, oy + (y + 1) * ch / nh
        row = []
        for x in range(nw):
            x0, x1 = ox + x * cw / nw, ox + (x + 1) * cw / nw
            acc = [0, 0, 0]; n = 0
            for yy in range(int(y0), max(int(y0) + 1, int(y1 + 0.999))):
                for xx in range(int(x0), max(int(x0) + 1, int(x1 + 0.999))):
                    p = px[min(yy, h - 1)][min(xx, w - 1)]
                    acc[0] += p[0]; acc[1] += p[1]; acc[2] += p[2]; n += 1
            row.append(tuple(v // n for v in acc))
        out.append(row)
    return out


FORCA_NITIDEZ = 70                 # % da máscara de nitidez (padrão; a ferramenta deixa escolher 10-200 por capa)


def resize_nitido(path, nw, nh, forca=FORCA_NITIDEZ):
    """Redução com nitidez: o mesmo recorte central do resize(), mas com filtro Lanczos e uma máscara de
    nitidez (unsharp mask) suave depois. Preserva melhor contornos e letras grandes do que a média de área."""
    from PIL import Image, ImageFilter
    im = Image.open(path).convert('RGBA')
    preto = Image.new('RGBA', im.size, (0, 0, 0, 255))
    im = Image.alpha_composite(preto, im).convert('RGB')         # transparência sobre preto, como o png_read
    w, h = im.size
    s = max(nw / w, nh / h); cw, ch = nw / s, nh / s; ox, oy = (w - cw) / 2, (h - ch) / 2
    im = im.resize((nw, nh), Image.Resampling.LANCZOS, box=(ox, oy, ox + cw, oy + ch))
    im = im.filter(ImageFilter.UnsharpMask(radius=1.0, percent=int(forca), threshold=1))
    d = list(im.getdata())
    return [d[y * nw:(y + 1) * nw] for y in range(nh)]


def carregar_capa(path, nitidez=False):
    """Pixels 64x96 de uma capa em imagem (PNG; com nitidez, qualquer formato que o Pillow abra).
    nitidez: False/0 = sem; True = força padrão (70%); um número = a força em % (10-200)."""
    if nitidez: return resize_nitido(path, COVER_W, COVER_H, FORCA_NITIDEZ if nitidez is True else nitidez)
    w, h, px = png_read(path)
    return resize(w, h, px, COVER_W, COVER_H)


def test_cover(os_bin):
    """Capa de teste: degradê, moldura e o texto 'CAPA' / 'TESTE' com a fonte do próprio OS."""
    px = [[(0, 0, 0)] * COVER_W for _ in range(COVER_H)]
    for y in range(COVER_H):
        for x in range(COVER_W):
            if y < 48: px[y][x] = (0, 88, 248)                    # céu
            elif y < 72: px[y][x] = (228, 92, 16)                 # faixa laranja
            else: px[y][x] = (0, 168, 0)                          # chão verde
    for y in range(COVER_H):
        for x in range(COVER_W):
            if x < 2 or x >= COVER_W - 2 or y < 2 or y >= COVER_H - 2:
                px[y][x] = (248, 248, 248)
    def text(s, tx, ty, color, sc):
        for ci, ch in enumerate(s):
            t = ord(ch); base = t * 16
            for r in range(8):
                lo, hi = os_bin[base + r], os_bin[base + 8 + r]
                for c in range(8):
                    if ((lo >> (7 - c)) & 1) and not ((hi >> (7 - c)) & 1):   # cor 1 da fonte
                        for sy in range(sc):
                            for sx in range(sc):
                                X, Y = tx + (ci * 8 + c) * sc + sx, ty + r * sc + sy
                                if 0 <= X < COVER_W and 0 <= Y < COVER_H: px[Y][X] = color
    text('CAPA', 0, 10, (248, 184, 0), 2)
    text('TESTE', 12, 76, (252, 252, 252), 1)
    return px


# ---------------------------------------------------------------- quantização NES
def quantize(px):
    nearest = {}
    def near(c):
        if c not in nearest:
            best = min(USABLE + [BLACK], key=lambda i: dist(c, rgb(i)))
            nearest[c] = best
        return nearest[c]
    idx = [[near(px[y][x]) for x in range(COVER_W)] for y in range(COVER_H)]
    blocks = []
    for r in range(ROWS):
        for c in range(COLS):
            blocks.append([px[r * 16 + y][c * 8 + x] for y in range(16) for x in range(8)])
    # paletas iniciais: cores mais frequentes
    hist = {}
    for row in idx:
        for i in row:
            if i != BLACK: hist[i] = hist.get(i, 0) + 1
    common = sorted(hist, key=hist.get, reverse=True) or [0x30]
    pals = [[common[(p * 3 + k) % len(common)] for k in range(3)] for p in range(4)]

    # busca local: troca uma cor de uma paleta por outra candidata se o erro total cair
    cands = common[:24]
    ublocks = []                                     # pixels únicos por bloco (com peso)
    for b in blocks:
        h = {}
        for p in b: h[p] = h.get(p, 0) + 1
        ublocks.append(list(h.items()))

    # distância de cada cor da imagem para cada cor do NES, calculada uma vez só
    D = {}
    for ub in ublocks:
        for p, _ in ub:
            if p not in D: D[p] = [dist(p, rgb(i)) for i in range(64)]

    def berr(ub, pal):
        a, b, c = pal
        return sum(n * min(D[p][BLACK], D[p][a], D[p][b], D[p][c]) for p, n in ub)

    perr = [[berr(ub, pal) for ub in ublocks] for pal in pals]   # erro de cada bloco com cada paleta

    def total(pe):
        return sum(min(pe[0][k], pe[1][k], pe[2][k], pe[3][k]) for k in range(len(ublocks)))

    best = total(perr)
    for _ in range(3):
        improved = False
        for p in range(4):
            for s in range(3):
                for cnd in cands:
                    if cnd in pals[p]: continue
                    old = pals[p][s]; pals[p][s] = cnd
                    old_err = perr[p]; perr[p] = [berr(ub, pals[p]) for ub in ublocks]
                    e = total(perr)
                    if e < best: best, improved = e, True
                    else: pals[p][s] = old; perr[p] = old_err
        if not improved: break
    assign = [min(range(4), key=lambda p: perr[p][k]) for k in range(len(ublocks))]
    out_px = [[(0, 0, 0)] * COVER_W for _ in range(COVER_H)]
    pix_idx = [[0] * COVER_W for _ in range(COVER_H)]
    for k, (b, a) in enumerate(zip(blocks, assign)):
        cols = [BLACK] + pals[a]; r, c = divmod(k, COLS)
        for j, p in enumerate(b):
            v = min(range(4), key=lambda q: D[p][cols[q]])
            y, x = r * 16 + j // 8, c * 8 + j % 8
            pix_idx[y][x] = v; out_px[y][x] = rgb(cols[v])
    return pals, assign, pix_idx, out_px


def make_tiles(pix_idx):
    chr_ = bytearray()
    for r in range(ROWS):
        for c in range(COLS):
            for half in range(2):
                lo = bytearray(8); hi = bytearray(8)
                for y in range(8):
                    for x in range(8):
                        v = pix_idx[r * 16 + half * 8 + y][c * 8 + x]
                        lo[y] |= (v & 1) << (7 - x); hi[y] |= ((v >> 1) & 1) << (7 - x)
                chr_ += lo + hi
    return chr_


def make_oam(assign):
    oam = bytearray([0xFF] * 256)
    for k in range(ROWS * COLS):
        r, c = divmod(k, COLS)
        oam[k * 4:k * 4 + 4] = bytes([COVER_Y + r * 16 - 1, (k * 2) | 1, assign[k], COVER_X + c * 8])
    return oam


# ---------------------------------------------------------------- código 6502
def lo(a): return a & 255
def hi(a): return a >> 8


def code_hook():
    return bytes([0x20, 0xE6, 0x83])                 # JSR ppu_update_cursor_column, cai em cover_show


NAME_ROWS = 0x6320                 # buffer de tela, linhas 25-26: nome completo do item selecionado
EXT = b'.nes'                      # comparado com (caractere | $20): aceita .NES/.nes/.Nes


def code_show_a(addr, part_b):
    """Filtro de extensão + início do cover_show. O fim (len - 4) guarda a tabela EXT."""
    oam = 0x6000 + OAM_FILE_OFS
    ext = addr + 65                                 # logo depois do código da parte A
    c = bytes([
        # --- filtro: os 4 últimos caracteres não-nulos das linhas 25-26 precisam ser ".nes"
        0xA0, 0x03,                                 # LDY #3
        0xA2, 0x3F,                                 # LDX #$3F
        0xBD, lo(NAME_ROWS), hi(NAME_ROWS),         # loop: LDA $6320,X
        0xF0, 0x0A,                                 #     BEQ skip        (posição vazia)
        0x09, 0x20,                                 #     ORA #$20        (minúscula; pasta em destaque não casa)
        0xD9, lo(ext), hi(ext),                     #     CMP ext,Y
        0xD0, 0x06,                                 #     BNE no
        0x88,                                       #     DEY
        0x30, 0x09,                                 #     BMI yes
        0xCA,                                       # skip: DEX
        0x10, 0xEE,                                 #     BPL loop
        0xA9, 0x0A, 0x8D, 0x01, 0x20,               # no: LDA #$0A / STA PPUMASK (esconde sprites)
        0x60,                                       #     RTS
        # --- yes: mostra a capa (banco CHR mapeado em $6000: OAM em $7F00, paleta em $7EF0)
        0xA9, 0x81, 0x8D, 0x00, 0x44,               # LDA #$81 / STA $4400
        0xA9, 0x09, 0x8D, 0x01, 0x44,               # LDA #$09 / STA $4401   banco CHR em $6000
        0xA2, 0x00,                                 # LDX #0
        0xBD, lo(oam), hi(oam),                     # L1: LDA $7F00,X
        0x9D, 0x00, 0x02,                           #     STA $0200,X
        0xE8, 0xD0, 0xF7,                           #     INX / BNE L1     (sai com X=0)
        0x20, 0x93, 0x83,                           # JSR ppu_wait_vblank
        0xA9, 0x3F, 0x8D, 0x06, 0x20,               # LDA #$3F / STA $2006
        0xA9, 0x10, 0x8D, 0x06, 0x20,               # LDA #$10 / STA $2006
        0x4C, lo(part_b), hi(part_b)])              # JMP parte B
    assert len(c) == 65
    return c + EXT


def code_show_b():
    pal = 0x6000 + PAL_FILE_OFS
    return bytes([
        0xBD, lo(pal), hi(pal),                     # L2: LDA $7EF0,X   (X=0 vindo da parte A)
        0x8D, 0x07, 0x20,                           #     STA $2007
        0xE8, 0xE0, 0x10, 0xD0, 0xF5,               #     INX / CPX #$10 / BNE L2
        0xA9, 0x08, 0x8D, 0x01, 0x44,               # LDA #$08 / STA $4401   WRAM de volta (índice ainda $81)
        0xA9, 0x00, 0x8D, 0x03, 0x20,               # LDA #0 / STA OAMADDR
        0x8D, 0x05, 0x20, 0x8D, 0x05, 0x20,         # STA $2005 x2 (scroll 0,0)
        0xA9, 0x02, 0x8D, 0x14, 0x40,               # LDA #2 / STA OAMDMA  ($0200)
        0xA9, 0xA0, 0x8D, 0x00, 0x20,               # LDA #$A0 / STA PPUCTRL (NMI + 8x16)
        0xA9, 0x1E, 0x8D, 0x01, 0x20,               # LDA #$1E / STA PPUMASK (fundo+sprites)
        0x60])                                      # RTS


def cpu2file(a): return a - 0x8000 + 0x6000


def patch(buf, addr, old, new):
    o = cpu2file(addr)
    assert buf[o:o + len(old)] == bytes(old), 'bytes inesperados em $%04X: %s' % (addr, buf[o:o + len(old)].hex())
    buf[o:o + len(new)] = bytes(new)


def main():
    args = sys.argv[1:]
    perfil = 'base'
    if args and args[0] == '--perfil':
        perfil = args[1]; args = args[2:]
    orig, buf, info = build(perfil, args[0] if args else None)
    P = PROFILES[perfil]
    out_dir = os.path.join(ROOT, P['out'])
    os.makedirs(os.path.join(out_dir, 'EDFC'), exist_ok=True)
    out = os.path.join(out_dir, 'EDFC', 'OS.BIN')
    open(out, 'wb').write(buf)
    png_write(os.path.join(out_dir, 'preview_capa.png'), COVER_W, COVER_H, info['preview'], 4)
    diff = sum(1 for a, b in zip(orig, buf) if a != b)
    print('perfil:', perfil, '| origem:', P['src'])
    print('gerado:', out, 'tamanho', len(buf), 'bytes alterados', diff)
    print('SHA1:', hashlib.sha1(buf).hexdigest())
    pal16 = info['pal16']
    print('paletas:', ' | '.join(' '.join('%02X' % v for v in pal16[i:i + 4]) for i in range(0, 16, 4)))
    print(info['layout'])


def build(perfil='base', png=None):
    """Monta o OS.BIN com a capa fixa. Retorna (original, novo, info)."""
    P = PROFILES[perfil]
    orig = open(os.path.join(ROOT, P['src']), 'rb').read()
    assert hashlib.sha1(orig).hexdigest() == P['sha1'], 'OS.BIN de origem não confere com o perfil "%s"' % perfil
    buf = bytearray(orig)

    if png:
        w, h, px = png_read(png); px = resize(w, h, px, COVER_W, COVER_H)
    else:
        px = test_cover(orig)
    pals, assign, pix_idx, preview = quantize(px)

    tiles = make_tiles(pix_idx)
    assert len(tiles) == 96 * 16
    buf[0x1000:0x1000 + len(tiles)] = tiles
    pal16 = bytearray()
    for p in pals: pal16 += bytes([BLACK] + p)       # $3F10 espelha o fundo: mantém preto
    buf[PAL_FILE_OFS:PAL_FILE_OFS + 16] = pal16
    buf[OAM_FILE_OFS:OAM_FILE_OFS + 256] = make_oam(assign)

    show_a_addr = ADDR_HOOK + 3
    dead = code_hook() + code_show_a(show_a_addr, P['part_b'])
    show_b = code_show_b()
    assert ADDR_HOOK + len(dead) <= DEAD_END, 'parte A não cabe na rotina morta'
    assert P['part_b'] + len(show_b) <= 0xFC00, 'parte B invade a área da BIOS ($FC00)'
    patch(buf, ADDR_HOOK, orig[cpu2file(ADDR_HOOK):cpu2file(ADDR_HOOK) + len(dead)], dead)
    patch(buf, P['part_b'], [0] * len(show_b), show_b)
    patch(buf, P['mask_full'], [0xA9, 0x0A, 0x8D, 0x01, 0x20], [0x20, lo(show_a_addr), hi(show_a_addr), 0xEA, 0xEA])
    patch(buf, P['cursor_call'], [0x20, 0xE6, 0x83], [0x20, lo(ADDR_HOOK), hi(ADDR_HOOK)])
    for a in P['ppuctrl']:
        patch(buf, a, [0xA9, 0x80, 0x8D, 0x00, 0x20], [0xA9, 0xA0, 0x8D, 0x00, 0x20])
    patch(buf, P['ppuctrl_inc'], [0xA9, 0x84, 0x8D, 0x00, 0x20], [0xA9, 0xA4, 0x8D, 0x00, 0x20])
    patch(buf, P['name_len'], [0xA9, 0x1D], [0xA9, 0x15])
    # ppu_refresh_screen_vblank ($8326, usada por popups/menus, nunca pelo navegador): o JMP $8343
    # inútil em $833D vira JSR para o trecho "no" do filtro (PPUMASK=$0A) -> sprites somem no menu.
    hide_addr = show_a_addr + 22
    assert dead[3 + 22:3 + 28] == bytes([0xA9, 0x0A, 0x8D, 0x01, 0x20, 0x60])
    patch(buf, 0x833D, [0x4C, 0x43, 0x83], [0x20, lo(hide_addr), hi(hide_addr)])

    layout = 'hook+parte A: $%04X-$%04X (%d B) | parte B: $%04X-$%04X (%d B)' % (
        ADDR_HOOK, ADDR_HOOK + len(dead) - 1, len(dead), P['part_b'], P['part_b'] + len(show_b) - 1, len(show_b))
    return orig, buf, dict(preview=preview, pal16=pal16, layout=layout)

if __name__ == '__main__':
    main()
