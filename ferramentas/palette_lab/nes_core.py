"""Núcleo do Palette Lab (conversor de imagem para NES): algoritmos e estado do projeto.

Implementação própria, em Python, do mesmo pipeline do nesdevtools.com/palette-lab
(levantamento em palette_lab_analise/FUNCIONALIDADES.md). Sem interface gráfica aqui.
Requer Pillow (leitura de PNG/JPG/GIF/WebP e redimensionamento).
"""
import base64, io, json, random

from PIL import Image

# ---------------------------------------------------------------- paleta NES (Nestopia / NesDev NTSC)
NES_HEX = [
    "666666", "002A88", "1412A7", "3B00A4", "5C007E", "6E0040", "6C0600", "561D00",
    "333500", "0B4800", "005200", "004F08", "00404D", "000000", "000000", "000000",
    "ADADAD", "155FD9", "4240FF", "7527FE", "A01ACC", "B71E7B", "B53120", "994E00",
    "6B6D00", "388700", "0C9300", "008F32", "007C8D", "000000", "000000", "000000",
    "FFFEFF", "64B0FF", "9290FF", "C676FF", "F36AFF", "FE6ECC", "FE8170", "EA9E22",
    "BCBE00", "88D800", "5CE430", "45E082", "48CDDE", "4F4F4F", "000000", "000000",
    "FFFEFF", "C0DFFF", "D3D2FF", "E8C8FF", "FBC2FF", "FEC4EA", "FECCC5", "F7D8A5",
    "E4E594", "CFEF96", "BDF4AB", "B3F3CC", "B5EBF2", "B8B8B8", "000000", "000000"]
FORBIDDEN = {0x0D, 0x0E, 0x0F, 0x1D, 0x1E, 0x1F, 0x2E, 0x2F, 0x3E, 0x3F}
BLACK = 0x0F                                   # fundo (backdrop): sempre disponível
NES_RGB = [tuple(int(h[k:k + 2], 16) for k in (0, 2, 4)) for h in NES_HEX]
USABLE = [i for i in range(64) if i not in FORBIDDEN]
OUT_SIZES = ['auto', 128, 96, 64, 48, 32, 16]
CAPA = '64x96'                                 # capa da firmware EDFC (8 x 6 sprites 8x16)
CAPA_BLOCK = '8x16'


def parse_block(block):
    """16 / 8 (quadrado, como no site) ou '8x16' (sprite 8x16 da capa) -> (largura, altura)."""
    if isinstance(block, str) and 'x' in block:
        w, h = block.split('x'); return int(w), int(h)
    return int(block), int(block)


def parse_size(size):
    """'auto', N (quadrado) ou 'LxA' -> None ou (L, A)."""
    if size in (None, 'auto'): return None
    if isinstance(size, str) and 'x' in size:
        w, h = size.split('x'); return int(w), int(h)
    return int(size), int(size)
UNDO_MAX = 5
BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def hex2(i): return '$%02X' % i


def lum(i):
    r, g, b = NES_RGB[i]
    return .299 * r + .587 * g + .114 * b


def _lin(u):
    u /= 255.0
    return ((u + 0.055) / 1.055) ** 2.4 if u > 0.04045 else u / 12.92


def _f(t): return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116


def rgb2lab(r, g, b):
    r, g, b = _lin(r), _lin(g), _lin(b)
    x = _f((r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047)
    y = _f(r * 0.2126 + g * 0.7152 + b * 0.0722)
    z = _f((r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883)
    return (116 * y - 16, 500 * (x - y), 200 * (y - z))


def d2(a, b):
    x, y, z = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return x * x + y * y + z * z


NES_LAB = [rgb2lab(*c) for c in NES_RGB]
BLACK_LAB = rgb2lab(0, 0, 0)


def kmeans(points, k, rng, iters=12):
    """k-means ponderado em Lab. points = [(lab, peso)]. 1º centróide aleatório, demais pelo
    ponto mais distante (ponderado)."""
    if not points: return []
    cents = [list(points[rng.randrange(len(points))][0])]
    while len(cents) < k:
        best, bd = None, -1
        for lab, w in points:
            dm = min(d2(lab, c) for c in cents) * w
            if dm > bd: bd, best = dm, lab
        cents.append(list(best))
    for _ in range(iters):
        sums = [[0.0, 0.0, 0.0, 0.0] for _ in cents]
        for lab, w in points:
            bi, bdist = 0, float('inf')
            for ci, c in enumerate(cents):
                dd = d2(lab, c)
                if dd < bdist: bdist, bi = dd, ci
            s = sums[bi]
            s[0] += lab[0] * w; s[1] += lab[1] * w; s[2] += lab[2] * w; s[3] += w
        for ci, s in enumerate(sums):
            if s[3] > 0: cents[ci] = [s[0] / s[3], s[1] / s[3], s[2] / s[3]]
    return cents


class Projeto:
    """Estado completo de uma conversão (equivale ao objeto S do site)."""

    def __init__(self):
        self.img = None                 # PIL.Image RGB (fonte)
        self.fit = 'crop'               # 'crop' | 'stretch'
        self.out_size = 'auto'          # 'auto' ou int
        self.block = 16                 # 16 (BG), 8 (SPR) ou '8x16' (capa EDFC)
        self.src_path = None
        self.mix = 0.5                  # Color match
        self.seam = 0.35                # Seam smooth
        self.dither = False
        self.main_grid = 'off'
        self.ed_grid = 'off'
        self.locked = False
        self.disabled = set()           # cores banidas
        self.pal_off = set()            # paletas desligadas
        self.pins = {}                  # (g, s) -> índice NES
        self.palettes = []              # 4 listas de 3 índices
        self.block_pal = []             # paleta de cada bloco
        self.paint = None               # por pixel: -1 automático, 0-3 espaço pintado
        self.slot_map = None            # espaço final de cada pixel
        self.idx_map = None             # índice NES final de cada pixel
        self.src_info = {'orig': '—', 'fmt': '—', 'size': '—'}
        self.W = self.H = 128
        self.native = False
        self.undo = []
        self.seed = 1
        self.C = None                   # análise da fonte (prepare)
        self.status = ''

    # ------------------------------------------------------------ utilidades
    def enabled_count(self):
        return sum(1 for i in USABLE if i not in self.disabled)

    def nearest_usable(self, lab, exclude=None):
        best, bd = -1, float('inf')
        for i in USABLE:
            if i in self.disabled or (exclude and i in exclude): continue
            dd = d2(lab, NES_LAB[i])
            if dd < bd: bd, best = dd, i
        return best

    def snap_palette(self, cents, count, exclude):
        used = set(exclude or ())
        out = []
        for c in cents:
            if len(out) >= count: break
            idx = self.nearest_usable(c, used)
            if idx >= 0: used.add(idx); out.append(idx)
        while len(out) < count:
            idx = self.nearest_usable((50, 0, 0), used)
            if idx < 0: break
            used.add(idx); out.append(idx)
        return out

    @property
    def bw(self): return parse_block(self.block)[0]

    @property
    def bh(self): return parse_block(self.block)[1]

    def is_capa(self):
        return (self.W, self.H) == (64, 96) and (self.bw, self.bh) == (8, 16)

    def active(self):
        return [g for g in range(4) if g not in self.pal_off]

    # ------------------------------------------------------------ entrada
    def load_image(self, path):
        im = Image.open(path)
        fmt = (im.format or '?').upper()
        size = __import__('os').path.getsize(path)
        im = self._flatten(im)
        self.img = im
        self.src_path = path
        self.paint = self.slot_map = self.idx_map = None
        self.src_info = {'orig': '%d × %d' % im.size, 'fmt': fmt,
                         'size': ('%.1f MB' % (size / 1048576)) if size >= 1048576 else '%d KB' % round(size / 1024)}

    @staticmethod
    def _flatten(im):
        """Converte para RGB; transparência vira preto (como o canvas do site)."""
        im = im.convert('RGBA')
        bg = Image.new('RGBA', im.size, (0, 0, 0, 255))
        bg.alpha_composite(im)
        return bg.convert('RGB')

    def start_blank(self, size):
        self.img = Image.new('RGB', (size, size), (0, 0, 0))
        self.out_size = size
        self.paint = self.slot_map = self.idx_map = None
        self.src_info = {'orig': '%d × %d em branco' % (size, size), 'fmt': 'CANVAS', 'size': '—'}

    # ------------------------------------------------------------ 1) fonte
    def draw_source(self):
        img, bw, bh = self.img, self.bw, self.bh
        explicit = parse_size(self.out_size)
        auto_native = not explicit and img.width <= 128 and img.height <= 128
        if explicit:
            W, H = explicit
        elif auto_native:
            W = max(bw, -(-img.width // bw) * bw)
            H = max(bh, -(-img.height // bh) * bh)
        else:
            W = H = 128
        self.W, self.H, self.native = W, H, auto_native
        canvas = Image.new('RGB', (W, H), (0, 0, 0))
        exact = img.size == (W, H)
        if auto_native or exact:
            canvas.paste(img, (0, 0))
        else:
            shrinking = min(img.width, img.height) > W
            res = Image.Resampling.LANCZOS if shrinking else Image.Resampling.NEAREST
            if self.fit == 'stretch':
                canvas = img.resize((W, H), res)
            else:                                    # maior retângulo central com a proporção de saída
                cw = min(img.width, img.height * W / H)
                ch = cw * H / W
                sx, sy = (img.width - cw) / 2, (img.height - ch) / 2
                x0, y0 = int(sx), int(sy)
                canvas = img.crop((x0, y0, x0 + round(cw), y0 + round(ch))).resize((W, H), res)
        if exact:
            meta = 'nativa %d×%d' % (W, H)
        elif auto_native:
            meta = 'nativa %d×%d' % img.size + ((' (completada %d×%d)' % (W, H)) if (W, H) != img.size else '')
        else:
            meta = 'redimensionada %d×%d' % (W, H)
        return canvas, meta

    # ------------------------------------------------------------ 2) análise
    def prepare(self):
        canvas, meta = self.draw_source()
        self.src_canvas, self.src_meta = canvas, meta
        W, H, bw, bh = self.W, self.H, self.bw, self.bh
        NBX, NBY = W // bw, H // bh
        raw = list(canvas.getdata())
        mix = self.mix
        px, labs = [], []
        cache = {}
        for r, g, b in raw:
            gray = .299 * r + .587 * g + .114 * b
            c = (max(0, min(255, round(gray + (r - gray) * mix))),
                 max(0, min(255, round(gray + (g - gray) * mix))),
                 max(0, min(255, round(gray + (b - gray) * mix))))
            px.append(c)
            lab = cache.get(c)
            if lab is None: lab = cache[c] = rgb2lab(*c)
            labs.append(lab)
        blocks, means = [], []
        for by in range(NBY):
            for bx in range(NBX):
                idxs = [(by * bh + y) * W + bx * bw + x for y in range(bh) for x in range(bw)]
                blocks.append(idxs)
                n = len(idxs)
                means.append(tuple(sum(labs[i][k] for i in idxs) / n for k in range(3)))
        contR = [0.0] * (NBX * NBY); contD = [0.0] * (NBX * NBY)
        for by in range(NBY):
            for bx in range(NBX):
                b = by * NBX + bx
                if bx < NBX - 1:                     # borda direita: bh pixels
                    s = sum(d2(labs[(by * bh + y) * W + bx * bw + bw - 1], labs[(by * bh + y) * W + bx * bw + bw])
                            for y in range(bh))
                    contR[b] = max(0.0, 1 - (s / bh) ** 0.5 / 18)
                if by < NBY - 1:                     # borda de baixo: bw pixels
                    s = sum(d2(labs[(by * bh + bh - 1) * W + bx * bw + x], labs[(by * bh + bh) * W + bx * bw + x])
                            for x in range(bw))
                    contD[b] = max(0.0, 1 - (s / bw) ** 0.5 / 18)
        self.C = dict(px=px, labs=labs, blocks=blocks, means=means, contR=contR, contD=contD,
                      NBX=NBX, NBY=NBY, NBLOCKS=NBX * NBY)

    # ------------------------------------------------------------ 3) resolver
    def solve(self):
        C = self.C
        labs, blocks, means = C['labs'], C['blocks'], C['means']
        NBX, NBY, NB = C['NBX'], C['NBY'], C['NBLOCKS']
        rng = random.Random(self.seed)
        seamW = self.seam * 2200 * (self.bw * self.bh) / 256     # proporcional aos pixels do bloco
        active = self.active()
        K = min(len(active), NB)
        used_active = active[:K]
        cents = kmeans([(m, 1) for m in means], K, rng, 10)
        assign = []
        for m in means:
            bi = min(range(K), key=lambda g: d2(m, cents[g]))
            assign.append(used_active[bi])
        palettes = [[] for _ in range(4)]
        for _ in range(4):
            for g in active:
                pinned = [self.pins[(g, s)] for s in range(3) if (g, s) in self.pins]
                free = 3 - len(pinned)
                fitted = []
                if free > 0:
                    pts = [(labs[pi], 1) for b in range(NB) if assign[b] == g for pi in blocks[b]
                           if d2(labs[pi], BLACK_LAB) > 90]
                    if not pts:
                        fitted = self.snap_palette([(50, 0, 0), (70, 0, 0), (30, 0, 0)], free, pinned)
                    else:
                        fitted = self.snap_palette(kmeans(pts, free, rng, 10), free, pinned)
                comp, fi = [], 0
                for s in range(3):
                    if (g, s) in self.pins: comp.append(self.pins[(g, s)])
                    elif fi < len(fitted): comp.append(fitted[fi]); fi += 1
                palettes[g] = comp
            for b in range(NB):
                bx, by = b % NBX, b // NBX
                bg, berr = active[0], float('inf')
                for g in active:
                    err = 0.0
                    if seamW > 0:
                        if bx < NBX - 1 and assign[b + 1] != g: err += seamW * C['contR'][b]
                        if bx > 0 and assign[b - 1] != g: err += seamW * C['contR'][b - 1]
                        if by < NBY - 1 and assign[b + NBX] != g: err += seamW * C['contD'][b]
                        if by > 0 and assign[b - NBX] != g: err += seamW * C['contD'][b - NBX]
                    if err >= berr: continue
                    cand = [NES_LAB[i] for i in palettes[g]] + [BLACK_LAB]
                    for pi in blocks[b]:
                        L = labs[pi]
                        err += min(d2(L, c) for c in cand)
                        if err >= berr: break
                    if err < berr: berr, bg = err, g
                assign[b] = bg
        self.palettes, self.block_pal = palettes, assign

    # ------------------------------------------------------------ 4) render
    def quant_pixel(self, pi, cand):
        C = self.C
        lab = C['labs'][pi]
        if self.dither:
            W = self.W
            t = (BAYER4[(pi // W) % 4][(pi % W) % 4] / 16 - 0.5) * 14
            r, g, b = C['px'][pi]
            lab = rgb2lab(max(0, min(255, r + t)), max(0, min(255, g + t)), max(0, min(255, b + t)))
        return min(cand, key=lambda ci: d2(lab, NES_LAB[ci]))

    def render(self, msg=None):
        C, N = self.C, self.W * self.H
        if not self.paint or len(self.paint) != N: self.paint = [-1] * N
        if not self.slot_map or len(self.slot_map) != N: self.slot_map = [0] * N
        if not self.idx_map or len(self.idx_map) != N: self.idx_map = [BLACK] * N
        for b, pis in enumerate(C['blocks']):
            pal = self.palettes[self.block_pal[b]]
            cand = pal + [BLACK]
            for pi in pis:
                pv = self.paint[pi]
                if pv >= 0:
                    slot = pv if (pv == 0 or pv - 1 < len(pal)) else 0
                    self.paint[pi] = slot
                else:
                    idx = self.quant_pixel(pi, cand)
                    pos = cand.index(idx)
                    slot = 0 if pos == len(pal) else pos + 1
                self.slot_map[pi] = slot
                self.idx_map[pi] = pal[slot - 1] if slot else BLACK
        self.status = msg or 'OK — %d bloco%s atribuído%s' % (C['NBLOCKS'], 's' if C['NBLOCKS'] > 1 else '',
                                                             's' if C['NBLOCKS'] > 1 else '')

    def repaint(self, msg=None):
        """Recolore a partir do mapa de espaços (sem requantizar)."""
        if not self.slot_map: return self.process()
        for b, pis in enumerate(self.C['blocks']):
            pal = self.palettes[self.block_pal[b]]
            for pi in pis:
                slot = self.slot_map[pi]
                if slot and slot - 1 >= len(pal): slot = 0
                self.idx_map[pi] = pal[slot - 1] if slot else BLACK
        self.status = msg or 'Recolorido'

    def process(self):
        self.undo.clear()
        self.prepare()
        self.solve()
        self.render()

    def output_image(self, scale=1):
        im = Image.new('RGB', (self.W, self.H))
        im.putdata([NES_RGB[i] for i in self.idx_map])
        if scale > 1: im = im.resize((self.W * scale, self.H * scale), Image.Resampling.NEAREST)
        return im

    # ------------------------------------------------------------ estatísticas
    def stats(self):
        live = self.active()
        used = {BLACK}
        for g in live:
            used.update(self.palettes[g] if g < len(self.palettes) else [])
        blk = '%d×%d' % (self.bw, self.bh)
        return dict(mode='%d PAL · %s' % (len(live), blk),
                    tiles=(self.W // 8) * (self.H // 8),
                    attrs=self.C['NBLOCKS'] if self.C else '—',
                    colors='%d / 13' % len(used),
                    meta='%d pal × 3 cores + fundo · %s' % (len(live), blk))

    def used_colors(self):
        used = {BLACK}
        for g in self.active():
            used.update(self.palettes[g] if g < len(self.palettes) else [])
        return used

    def block_count(self, g):
        return 0 if g in self.pal_off else self.block_pal.count(g)

    def asm_text(self):
        parts = []
        for g, pal in enumerate(self.palettes):
            full = [BLACK] * 4 if g in self.pal_off else [BLACK] + list(pal)
            parts.append('.byte ' + ', '.join(hex2(i) for i in full))
        return '   '.join(parts)

    # ------------------------------------------------------------ edição de paletas
    def check_locked(self):
        if self.locked:
            self.status = '🔒 Travado — destrave para alterar'
            return True
        return False

    def toggle_pal(self, g):
        if self.check_locked(): return False
        if g in self.pal_off:
            self.pal_off.discard(g)
        else:
            if 4 - len(self.pal_off) <= 1:
                self.status = 'É preciso pelo menos 1 paleta ligada'
                return False
            self.pal_off.add(g)
        self.solve()
        self.render('PAL %d %s — resolvido de novo' % (g, 'desligada' if g in self.pal_off else 'ligada'))
        return True

    def toggle_color(self, i):
        """Banir/permitir uma cor da paleta mestre."""
        if self.check_locked() or i in FORBIDDEN: return False
        if i in self.disabled:
            self.disabled.discard(i)
            self.status = '%s permitida — use Refazer para aproveitá-la' % hex2(i)
            return True
        if self.enabled_count() <= 3:
            self.status = 'É preciso pelo menos 3 cores usáveis'
            return False
        self.disabled.add(i)
        for k in [k for k, v in self.pins.items() if v == i]: del self.pins[k]
        for g in range(4):
            if g in self.pal_off or g >= len(self.palettes): continue
            for s, v in enumerate(self.palettes[g]):
                if v == i:
                    others = {x for j, x in enumerate(self.palettes[g]) if j != s}
                    sub = self.nearest_usable(NES_LAB[i], others)
                    if sub >= 0: self.palettes[g][s] = sub
        self.repaint('%s banida — trocada pela cor permitida mais próxima' % hex2(i))
        return True

    def pin_color(self, g, s, i):
        if self.check_locked() or i in FORBIDDEN or g in self.pal_off: return False
        self.disabled.discard(i)                       # fixar sempre vence o banimento
        self.pins[(g, s)] = i
        if g < len(self.palettes) and len(self.palettes[g]) == 3 and self.slot_map:
            self.palettes[g][s] = i
            self.repaint('PAL %d espaço %d → %s (fixada)' % (g, s + 1, hex2(i)))
        else:
            self.process()
        return True

    def release_slot(self, g, s):
        """'Auto (soltar)' do seletor: solta e resolve de novo."""
        if self.check_locked(): return False
        self.pins.pop((g, s), None)
        self.solve()
        self.render('PAL %d espaço %d solto — resolvido de novo' % (g, s + 1))
        return True

    def unpin_all(self):
        if self.check_locked() or not self.pins: return False
        self.pins = {}
        self.status = 'Todas as cores soltas — valem no próximo Refazer'
        return True

    def enable_all(self):
        if self.check_locked() or not self.disabled: return False
        self.disabled.clear()
        self.status = 'Todas as cores permitidas — use Refazer para aproveitá-las'
        return True

    def resolve(self):
        if self.check_locked(): return False
        self.push_undo()
        self.seed += 1
        self.solve()
        self.render('Resolvido de novo — fixações mantidas')
        return True

    # ------------------------------------------------------------ desfazer
    def push_undo(self):
        if not self.slot_map or not self.block_pal: return
        self.undo.append(dict(palettes=[list(p) for p in self.palettes], block_pal=list(self.block_pal),
                              paint=list(self.paint) if self.paint else None,
                              slot_map=list(self.slot_map), pins=dict(self.pins)))
        if len(self.undo) > UNDO_MAX: self.undo.pop(0)

    def do_undo(self):
        if self.check_locked() or not self.undo: return False
        u = self.undo.pop()
        self.palettes, self.block_pal = u['palettes'], u['block_pal']
        if u['paint']: self.paint = u['paint']
        self.slot_map, self.pins = u['slot_map'], u['pins']
        n = len(self.undo)
        self.repaint('Desfeito — %d desfazer%s restante%s' % (n, '' if n == 1 else 'es', '' if n == 1 else 's'))
        return True

    # ------------------------------------------------------------ editor de pixels
    def pixel_info(self, x, y):
        """Conta-gotas: de onde vem a cor do pixel (x, y). slot 0 = fundo $0F (fixo)."""
        if not self.slot_map or not (0 <= x < self.W and 0 <= y < self.H): return None
        pi = y * self.W + x
        b = self.block_of(pi)
        return dict(x=x, y=y, pi=pi, block=b, g=self.block_pal[b], slot=self.slot_map[pi], idx=self.idx_map[pi])

    def block_of(self, pi):
        return ((pi // self.W) // self.bh) * self.C['NBX'] + (pi % self.W) // self.bw

    def ed_apply(self, pi, tool, sel):
        """tool: 'paint' | 'erase' | 'attr'; sel: ('bk',) ou (g, s). Retorna True se mudou algo."""
        if self.locked:
            self.status = '🔒 Travado — destrave para pintar'
            return False
        b = self.block_of(pi)
        if tool == 'attr':
            if sel[0] == 'bk':
                self.status = 'Escolha antes uma cor de paleta — o fundo não tem paleta'
                return False
            g = sel[0]
            if g in self.pal_off or self.block_pal[b] == g: return False
            self.block_pal[b] = g
            self.repaint('Bloco %d → PAL %d' % (b, g))
            return True
        if tool == 'erase':
            self.paint[pi] = -1
            pal = self.palettes[self.block_pal[b]]
            cand = pal + [BLACK]
            idx = self.quant_pixel(pi, cand)
            pos = cand.index(idx)
            self.slot_map[pi] = 0 if pos == len(pal) else pos + 1
            self.idx_map[pi] = idx
            return True
        if sel[0] != 'bk' and self.block_pal[b] != sel[0]:
            self.block_pal[b] = sel[0]                  # regra do hardware: o bloco adota a paleta do pincel
            self.render('Bloco → PAL %d (troca de atributo)' % sel[0])
        slot = 0 if sel[0] == 'bk' else sel[1] + 1
        self.paint[pi] = slot
        self.slot_map[pi] = slot
        self.idx_map[pi] = BLACK if sel[0] == 'bk' else self.palettes[sel[0]][sel[1]]
        return True

    def clear_paint(self):
        if self.check_locked() or not self.paint: return False
        self.push_undo()
        self.paint = [-1] * (self.W * self.H)
        self.render('Pintura apagada')
        return True

    # ------------------------------------------------------------ exportação
    def save_png(self, path):
        self.output_image().save(path, 'PNG')

    def save_bmp(self, path):
        """BMP 24 bits com o espaço codificado: fundo preto, 1 vermelho, 2 verde, 3 azul (NESmaker)."""
        import struct
        W, H = self.W, self.H
        row = (W * 3 + 3) & ~3
        data = bytearray()
        for y in range(H - 1, -1, -1):
            line = bytearray()
            for x in range(W):
                s = self.slot_map[y * W + x]
                r, g, b = (255 if s == 1 else 0), (255 if s == 2 else 0), (255 if s == 3 else 0)
                line += bytes((b, g, r))
            data += line + bytes(row - len(line))
        hdr = b'BM' + struct.pack('<IHHI', 54 + len(data), 0, 0, 54)
        hdr += struct.pack('<IiiHHIIiiII', 40, W, H, 1, 24, 0, len(data), 2835, 2835, 0, 0)
        open(path, 'wb').write(hdr + data)

    # ------------------------------------------------------------ projeto (.json compatível com o site)
    def to_json(self):
        buf = io.BytesIO()
        self.img.save(buf, 'PNG')
        proj = dict(app='palette-lab', v=2, fit=self.fit, outSize=str(self.out_size), block=self.block,
                    mix=self.mix, seam=self.seam, dither=self.dither, mainGrid=self.main_grid,
                    edGrid=self.ed_grid, locked=self.locked, srcInfo=self.src_info, W=self.W, H=self.H,
                    img='data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode(),
                    disabled=sorted(self.disabled), palOff=sorted(self.pal_off),
                    pins={'%d-%d' % k: v for k, v in self.pins.items()},
                    palettes=self.palettes, blockPal=list(self.block_pal), paint=list(self.paint or []),
                    srcPath=self.src_path)
        return json.dumps(proj)

    def from_json(self, text):
        p = json.loads(text)
        if not isinstance(p, dict) or p.get('app') != 'palette-lab' or not p.get('img'):
            raise ValueError('Não é um projeto do Palette Lab')
        data = p['img'].split(',', 1)[1]
        self.img = self._flatten(Image.open(io.BytesIO(base64.b64decode(data))))
        self.fit = p.get('fit', 'crop')
        os_ = p.get('outSize', 'auto')
        self.out_size = 'auto' if os_ in (None, 'auto') else (os_ if 'x' in str(os_) else int(os_))
        bl = p.get('block', 16)
        self.block = bl if 'x' in str(bl) else int(bl)
        self.src_path = p.get('srcPath')
        self.mix = float(p.get('mix', 0.5)); self.seam = float(p.get('seam', 0.35))
        self.dither = bool(p.get('dither'))
        self.main_grid = p.get('mainGrid') or 'off'; self.ed_grid = p.get('edGrid') or 'off'
        self.locked = False
        self.disabled = set(p.get('disabled') or []); self.pal_off = set(p.get('palOff') or [])
        self.pins = {tuple(int(x) for x in k.split('-')): v for k, v in (p.get('pins') or {}).items()}
        self.src_info = p.get('srcInfo') or {'orig': '—', 'fmt': '—', 'size': '—'}
        self.paint = self.idx_map = self.slot_map = None
        self.undo.clear()
        self.prepare()
        bp = p.get('blockPal')
        if p.get('W') == self.W and p.get('H') == self.H and isinstance(bp, list) and len(bp) == self.C['NBLOCKS']:
            self.palettes = [list(x) for x in p['palettes']]
            self.block_pal = list(bp)
            pt = p.get('paint')
            self.paint = list(pt) if pt and len(pt) == self.W * self.H else [-1] * (self.W * self.H)
            self.render('Projeto restaurado')
        else:
            self.solve(); self.render('Projeto restaurado (resolvido de novo)')
        if p.get('locked'): self.locked = True
