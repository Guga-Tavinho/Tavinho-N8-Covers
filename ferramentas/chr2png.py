"""Renderiza CHR (2bpp NES) em PNG sem dependências. uso: python chr2png.py OS.BIN saida.png [offset_hex] [tamanho_hex]"""
import sys, zlib, struct
d = open(sys.argv[1], 'rb').read()
off = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0
size = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x2000
chr_ = d[off:off + size]
ntiles = len(chr_) // 16
cols = 16; rows = (ntiles + cols - 1) // cols
S = 3; G = 1   # escala e grade
pal = [(0, 0, 64), (255, 255, 255), (255, 160, 0), (0, 200, 255)]
W = cols * (8 * S + G) + G; H = rows * (8 * S + G) + G
img = [[(90, 90, 90)] * W for _ in range(H)]
for t in range(ntiles):
    tx, ty = t % cols, t // cols
    for y in range(8):
        lo, hi = chr_[t * 16 + y], chr_[t * 16 + 8 + y]
        for x in range(8):
            c = ((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1)
            for sy in range(S):
                for sx in range(S):
                    img[G + ty * (8 * S + G) + y * S + sy][G + tx * (8 * S + G) + x * S + sx] = pal[c]
raw = b''.join(b'\0' + bytes(v for p in row for v in p) for row in img)
def chunk(t, b): return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b))
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
open(sys.argv[2], 'wb').write(png)
print(sys.argv[2], W, H)
