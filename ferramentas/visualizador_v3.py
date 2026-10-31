"""Visualizador da POC v3 no PC (janela).

A área da capa é desenhada a partir do estado REAL da PPU produzido pelo código da firmware v3 rodando no
emulador 6502 (carga do COVERS.BIN, envio para a PPU e alternância pelo NMI a cada quadro).
A lista de jogos ao redor é uma IMITAÇÃO do navegador do OS (o OS inteiro não roda no emulador).

uso:  python visualizador_v3.py        (↑/↓ troca de jogo · Espaço: modo de exibição · +/-: zoom)
"""
import os, sys, tkinter as tk
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageTk
from build_poc import rgb
from teste_capas_emu import setup, show_name, ROOT
from teste_capas_v3_emu import nmi
from build_capas_v3 import assemble_all
from sim_flicker import avg_color

PASTA = sys.argv[1] if len(sys.argv) > 1 else 'experimento_v3'
OS_BIN = os.path.join(ROOT, PASTA, 'EDFC', 'OS.BIN')
COVERS = os.path.join(ROOT, PASTA, 'EDFC', 'COVERS.BIN')
PASTAS = [os.path.join(ROOT, 'super mario'), os.path.join(ROOT, '001-200')]
MODOS = ['alternando (60 Hz)', 'média percebida', 'só quadro A', 'só quadro B']


class Visualizador:
    def __init__(self, root):
        self.root = root
        root.title('Visualizador %s — capa emulada (código real da firmware) · lista imitada' % PASTA)
        root.configure(bg='#14110f')
        segs, self.S = assemble_all()
        self.buf = open(OS_BIN, 'rb').read()
        self.cov = open(COVERS, 'rb').read()
        self.cpu, self.mem, self.ppu = setup(self.buf, self.cov)
        v = self.ppu['vram']
        v[0x0000:0x2000] = self.buf[0x0000:0x2000]                  # CHR do OS (fonte), como no $826F
        v[0x3F00:0x3F10] = self.buf[0x6000 + 0x825F - 0x8000:0x6000 + 0x826F - 0x8000]   # paletas do OS
        self.cpu.call(self.S['init_hook'])
        self.nomes = []
        for p in PASTAS:
            if os.path.isdir(p):
                self.nomes += sorted(f for f in os.listdir(p) if f.lower().endswith('.nes'))
        self.sel = 0
        self.modo = 0
        self.zoom = 3
        self.frames = None
        self.tick = 0
        self.lbl = tk.Label(root, bg='#000'); self.lbl.pack(padx=10, pady=(10, 4))
        self.info = tk.Label(root, text='', bg='#14110f', fg='#d9a441', font=('Consolas', 10), justify='left')
        self.info.pack(anchor='w', padx=10, pady=(0, 10))
        root.bind('<Up>', lambda e: self.mover(-1))
        root.bind('<Down>', lambda e: self.mover(1))
        root.bind('<Prior>', lambda e: self.mover(-21))
        root.bind('<Next>', lambda e: self.mover(21))
        root.bind('<space>', lambda e: self.trocar_modo())
        root.bind('<plus>', lambda e: self.set_zoom(1)); root.bind('<equal>', lambda e: self.set_zoom(1))
        root.bind('<minus>', lambda e: self.set_zoom(-1))
        root.bind('<Escape>', lambda e: root.destroy())
        self.selecionar()
        self.animar()

    # ------------------------------------------------------------ firmware emulada
    def selecionar(self):
        nome = self.nomes[self.sel]
        show_name(self.mem, nome)
        self.ppu['reads'] = 0
        self.cpu.call(self.S['draw_hook'])                          # como no aparelho: desenho da lista...
        self.cpu.call(self.S['idle_hook'])                          # ...e carga quando o cursor para
        self.mem[0xA2] = 0
        visivel = (self.ppu['mask'] or [0x0A])[-1] == 0x1E
        flk = self.mem[self.S['flk']]
        quadros = []
        if visivel and flk:
            for _ in range(2):                                      # dois NMIs = quadro A e quadro B
                nmi(self.cpu)
                quadros.append(self.render(self.ppu['oam'], True))
        else:
            quadros = [self.render(None, False)] * 2
        self.frames = quadros
        self.media = self.media_linear(quadros[0], quadros[1]) if quadros[0] is not quadros[1] else quadros[0]
        self.preparar()
        tem = 'capa com alternância' if (visivel and flk and self.frames[0].tobytes() != self.frames[1].tobytes()) \
            else ('capa sem alternância' if visivel else 'sem capa')
        self.info.configure(text='%s\n%s · setores lidos do COVERS.BIN: %d · modo: %s\n'
                                 '↑/↓ (PgUp/PgDn) troca de jogo · Espaço muda o modo · +/- zoom · Esc fecha'
                            % (nome, tem, self.ppu['reads'], MODOS[self.modo]))

    def media_linear(self, a, b):
        pa, pb = a.load(), b.load()
        out = Image.new('RGB', a.size); po = out.load()
        cache = {}
        for y in range(a.height):
            for x in range(a.width):
                k = (pa[x, y], pb[x, y])
                if k not in cache:
                    ia, ib = self.rev.get(k[0]), self.rev.get(k[1])
                    cache[k] = avg_color(ia, ib) if ia is not None and ib is not None else k[0]
                po[x, y] = cache[k]
        return out

    # ------------------------------------------------------------ PPU -> imagem 256x240
    def render(self, oam, sprites):
        v = self.ppu['vram']
        for m in (0x3F10, 0x3F14, 0x3F18, 0x3F1C): v[m - 0x10] = v[m]   # espelhos do hardware
        nt = bytearray(v[0x2000:0x2400])
        self.texto_lista(nt)                                         # imitação da lista do OS
        im = Image.new('RGB', (256, 240))
        px = im.load()
        cores = [rgb(v[0x3F00 + i]) for i in range(32)]
        self.rev = {rgb(i): i for i in range(64)}
        for ty in range(30):
            for tx in range(32):
                t = nt[ty * 32 + tx]
                a = nt[0x3C0 + (ty // 4) * 8 + tx // 4]
                p = (a >> (((tx // 2) & 1) * 2 + ((ty // 2) & 1) * 4)) & 3
                for r in range(8):
                    lo, hi = v[t * 16 + r], v[t * 16 + 8 + r]
                    for c in range(8):
                        k = ((lo >> (7 - c)) & 1) | (((hi >> (7 - c)) & 1) << 1)
                        px[tx * 8 + c, ty * 8 + r] = cores[0] if k == 0 else cores[p * 4 + k]
        if sprites and oam:
            for k in range(63, -1, -1):
                sy, t, at, sx = oam[k * 4:k * 4 + 4]
                if sy >= 0xEF: continue
                base = (0x1000 if t & 1 else 0) + (t & 0xFE) * 16
                for r in range(16):
                    tb = base + (16 if r >= 8 else 0)
                    lo, hi = v[tb + r % 8], v[tb + 8 + r % 8]
                    for c in range(8):
                        kk = ((lo >> (7 - c)) & 1) | (((hi >> (7 - c)) & 1) << 1)
                        x, y = sx + c, sy + 1 + r
                        if kk and x < 256 and y < 240: px[x, y] = cores[16 + (at & 3) * 4 + kk]
        return im

    def texto_lista(self, nt):
        """Imita o navegador: 21 linhas (linha 2 em diante), '>' no item, nome com 20 colunas e o nome
        completo na barra cinza de baixo (paleta 3). A área da capa (linhas 4-15, colunas 22-29) é da PPU."""
        pag = self.sel // 21 * 21
        for i in range(21):
            row = 2 + i
            for col in range(0, 22): nt[row * 32 + col] = 0
            if pag + i < len(self.nomes):
                s = self.nomes[pag + i][:20]
                if pag + i == self.sel: nt[row * 32 + 1] = ord('>')
                for k, ch in enumerate(s): nt[row * 32 + 2 + k] = ord(ch) if 32 <= ord(ch) < 128 else ord('?')
        nome = self.nomes[self.sel]
        for row in (25, 26):
            for col in range(32): nt[row * 32 + col] = 0
        for k, ch in enumerate(nome[:60]):
            nt[(25 + k // 30) * 32 + 1 + k % 30] = ord(ch) if 32 <= ord(ch) < 128 else ord('?')
        for k in range(8): nt[0x3C0 + 6 * 8 + k] = 0xFF            # barra de baixo na paleta 3 (como no OS)

    # ------------------------------------------------------------ janela
    def mover(self, d):
        self.sel = max(0, min(len(self.nomes) - 1, self.sel + d))
        self.selecionar()

    def trocar_modo(self):
        self.modo = (self.modo + 1) % len(MODOS)
        self.selecionar()

    def set_zoom(self, d):
        self.zoom = max(1, min(5, self.zoom + d))
        self.preparar()

    def preparar(self):
        """Imagens ampliadas prontas (A, B, média): a animação só troca entre elas."""
        z = (256 * self.zoom, 240 * self.zoom)
        self.ph = [ImageTk.PhotoImage(im.resize(z, Image.Resampling.NEAREST))
                   for im in (self.frames[0], self.frames[1], self.media)]

    def animar(self):
        self.tick ^= 1
        k = self.tick if self.modo == 0 else (2 if self.modo == 1 else self.modo - 2)
        self.lbl.configure(image=self.ph[k])
        self.root.after(16, self.animar)                            # ~60 Hz (o Windows arredonda)


def main():
    root = tk.Tk()
    Visualizador(root)
    root.mainloop()


if __name__ == '__main__':
    main()
