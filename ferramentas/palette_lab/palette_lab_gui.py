"""Palette Lab — conversor de imagem para NES com interface gráfica (tkinter).

Reproduz as funções do nesdevtools.com/palette-lab (ver palette_lab_analise/FUNCIONALIDADES.md):
entrada (PNG/JPG/GIF/WebP/projeto .json ou tela em branco), conversão (ajuste, tamanho, bloco
16×16/8×8, color match, suavização de emendas, pontilhado, grade), paletas (ligar/desligar, fixar,
seletor de cor, banir cores da paleta mestre), refazer/travar/desfazer, editor de pixels e
exportação (PNG, BMP com espaços codificados, .byte, projeto .json).

uso:  python palette_lab_gui.py [imagem_ou_projeto]
"""
import os, sys, subprocess, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageTk
from nes_core import (Projeto, NES_HEX, NES_RGB, FORBIDDEN, BLACK, USABLE, OUT_SIZES, CAPA, CAPA_BLOCK, hex2, lum)

GERAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gerar_covers.py')

# ---------------------------------------------------------------- aparência
BG, PANEL, PANEL2, FG, DIM, GOLD, RED, ACC = ('#14110f', '#1d1916', '#26211d', '#ece3d3', '#8d8273',
                                               '#d9a441', '#d63b31', '#3a322b')
MONO = ('Consolas', 9)
UI = ('Segoe UI', 9)
UIB = ('Segoe UI', 9, 'bold')
VIEW = 384                                                           # lado das prévias, em pixels de tela

FIT_OPTS = [('Recortar no centro', 'crop'), ('Esticar', 'stretch')]
SIZE_OPTS = [('Auto', 'auto')] + [('%d×%d' % (s, s), s) for s in OUT_SIZES[1:]] + [('Capa EDFC 64×96', CAPA)]
BLOCK_OPTS = [('16×16 fundo (BG)', 16), ('8×8 sprite (SPR)', 8), ('8×16 capa (SPR)', CAPA_BLOCK)]
GRID_OPTS = [('Desligada', 'off'), ('8×8', '8'), ('16×16', '16')]
EDGRID_OPTS = [('Desligada', 'off'), ('1×1', '1'), ('4×4', '4'), ('8×8', '8'), ('16×16', '16')]


def nes_color(i): return '#' + NES_HEX[i]


def text_on(i): return '#000' if lum(i) > 140 else '#fff'


class Combo(ttk.Combobox):
    """Combobox com pares (rótulo, valor)."""

    def __init__(self, master, opts, cb, width=16):
        super().__init__(master, values=[o[0] for o in opts], state='readonly', width=width, font=UI)
        self.opts = opts
        self.bind('<<ComboboxSelected>>', lambda e: cb(self.get_value()))

    def get_value(self): return self.opts[self.current()][1]

    def set_value(self, v):
        for k, (_, val) in enumerate(self.opts):
            if str(val) == str(v): self.current(k); return


class App:
    def __init__(self, root, path=None):
        self.root = root
        self.p = Projeto()
        self.editor = None
        self.picker = None
        self.confirm = None
        self.drag = None
        self._img_refs = {}
        root.title('Palette Lab — conversor de imagem para NES')
        root.configure(bg=BG)
        root.minsize(1100, 720)
        self._style()
        self._header()
        self.landing = tk.Frame(root, bg=BG)
        self.work = tk.Frame(root, bg=BG)
        self._build_landing()
        self._build_work()
        self.status = tk.Label(root, text='', bg=PANEL, fg=GOLD, anchor='w', font=MONO, padx=10)
        self.status.pack(side='bottom', fill='x')
        self.landing.pack(fill='both', expand=True)
        root.bind('<Escape>', self._escape)
        root.bind('<Control-z>', lambda e: self.undo())
        if path: root.after(50, lambda: self.open_path(path))

    # ============================================================ estrutura
    def _style(self):
        st = ttk.Style()
        try: st.theme_use('clam')
        except tk.TclError: pass
        st.configure('TCombobox', fieldbackground=PANEL2, background=PANEL2, foreground=FG, arrowcolor=GOLD)
        st.map('TCombobox', fieldbackground=[('readonly', PANEL2)], foreground=[('readonly', FG)])
        st.configure('Horizontal.TScale', background=PANEL, troughcolor=ACC)

    def _header(self):
        h = tk.Frame(self.root, bg=BG)
        h.pack(fill='x', padx=14, pady=(10, 4))
        tk.Label(h, text='PALETTE LAB', bg=BG, fg=GOLD, font=('Segoe UI', 18, 'bold')).pack(side='left')
        tk.Label(h, text='  PPU $3F00 · conversor de imagem para NES', bg=BG, fg=DIM, font=MONO).pack(side='left')
        self.steps = []
        sf = tk.Frame(h, bg=BG); sf.pack(side='right')
        for n, t in ((1, 'ENTRADA'), (2, 'CONVERTER'), (3, 'EXPORTAR')):
            l = tk.Label(sf, text=' %d %s ' % (n, t), bg=PANEL, fg=DIM, font=UIB, padx=8, pady=3)
            l.pack(side='left', padx=3)
            self.steps.append(l)
        self._set_step(1)

    def _set_step(self, n, done_below=True):
        for k, l in enumerate(self.steps, 1):
            if k == n: l.configure(bg=GOLD, fg='#000')
            elif k < n and done_below: l.configure(bg=ACC, fg=FG)
            else: l.configure(bg=PANEL, fg=DIM)

    def _btn(self, master, text, cmd, **kw):
        b = tk.Button(master, text=text, command=cmd, bg=kw.pop('bg', PANEL2), fg=kw.pop('fg', FG),
                      activebackground=ACC, activeforeground=FG, relief='flat', font=kw.pop('font', UI),
                      padx=kw.pop('padx', 10), pady=kw.pop('pady', 4), cursor='hand2', **kw)
        return b

    # ------------------------------------------------------------ tela inicial
    def _build_landing(self):
        f = tk.Frame(self.landing, bg=PANEL, padx=40, pady=40)
        f.place(relx=0.5, rely=0.45, anchor='center')
        tk.Label(f, text='1 · ENTRADA', bg=PANEL, fg=GOLD, font=UIB).pack(anchor='w')
        self._btn(f, '📂  Abrir imagem ou projeto…', self.open_dialog, font=('Segoe UI', 12, 'bold'),
                  bg=GOLD, fg='#000', padx=24, pady=12).pack(pady=(14, 8), fill='x')
        tk.Label(f, text='PNG, JPG, GIF, WebP ou projeto .json salvo.\n'
                         'Imagens de até 128 px ficam no tamanho original; maiores viram 128×128.\n'
                         'Tudo roda neste computador: nada é enviado para a internet.',
                 bg=PANEL, fg=DIM, font=UI, justify='left').pack(anchor='w')
        tk.Label(f, text='Ou comece com uma tela em branco no editor de pixels:', bg=PANEL, fg=FG,
                 font=UI).pack(anchor='w', pady=(18, 6))
        row = tk.Frame(f, bg=PANEL); row.pack(anchor='w')
        for s in (16, 32, 64, 128):
            self._btn(row, '%d×%d' % (s, s), lambda s=s: self.start_blank(s)).pack(side='left', padx=(0, 6))

    # ------------------------------------------------------------ área de trabalho
    def _build_work(self):
        w = self.work
        # barra de ferramentas
        tb = tk.Frame(w, bg=PANEL, padx=10, pady=8); tb.pack(fill='x', padx=14, pady=(4, 6))
        self.lockable = []

        def lab(t): tk.Label(tb, text=t, bg=PANEL, fg=DIM, font=UI).pack(side='left', padx=(8, 3))
        lab('Ajuste')
        self.fit_cb = Combo(tb, FIT_OPTS, self.on_fit, 17); self.fit_cb.pack(side='left'); self.lockable.append(self.fit_cb)
        lab('Tamanho de saída')
        self.size_cb = Combo(tb, SIZE_OPTS, self.on_size, 15); self.size_cb.pack(side='left'); self.lockable.append(self.size_cb)
        lab('Bloco do solver')
        self.block_cb = Combo(tb, BLOCK_OPTS, self.on_block, 16); self.block_cb.pack(side='left'); self.lockable.append(self.block_cb)
        lab('Fidelidade de cor')
        self.mix_var = tk.IntVar(value=50)
        self.mix_sc = tk.Scale(tb, from_=0, to=100, orient='horizontal', variable=self.mix_var, showvalue=True,
                               length=110, bg=PANEL, fg=FG, troughcolor=ACC, highlightthickness=0, font=MONO,
                               sliderrelief='flat', activebackground=GOLD)
        self.mix_sc.pack(side='left'); self.mix_sc.bind('<ButtonRelease-1>', lambda e: self.on_mix())
        self.lockable.append(self.mix_sc)
        lab('Suavizar emendas')
        self.seam_var = tk.IntVar(value=35)
        self.seam_sc = tk.Scale(tb, from_=0, to=100, orient='horizontal', variable=self.seam_var, showvalue=True,
                                length=110, bg=PANEL, fg=FG, troughcolor=ACC, highlightthickness=0, font=MONO,
                                sliderrelief='flat', activebackground=GOLD)
        self.seam_sc.pack(side='left'); self.seam_sc.bind('<ButtonRelease-1>', lambda e: self.on_seam())
        self.lockable.append(self.seam_sc)
        self.dither_btn = self._btn(tb, 'Pontilhado: desligado', self.on_dither); self.dither_btn.pack(side='left', padx=8)
        self.lockable.append(self.dither_btn)
        lab('Grade')
        self.grid_cb = Combo(tb, GRID_OPTS, self.on_grid, 9); self.grid_cb.pack(side='left')

        tb2 = tk.Frame(w, bg=BG); tb2.pack(fill='x', padx=14)
        self._btn(tb2, '✎  Editor de pixels', self.open_editor).pack(side='left')
        self._btn(tb2, '＋  Novo projeto', self.new_project).pack(side='left', padx=6)
        self._btn(tb2, '⇩  Salvar projeto', self.save_project).pack(side='left')
        self._btn(tb2, '🎮  Salvar capa para o COVERS…', self.save_capa, bg=ACC).pack(side='left', padx=(12, 0))
        self._btn(tb2, '📦  Gerar COVERS.BIN…', self.open_gerar, bg=ACC).pack(side='left', padx=6)
        self.info = {}
        for key, t in (('orig', 'Original'), ('work', 'Trabalho'), ('fmt', 'Formato'), ('size', 'Arquivo')):
            tk.Label(tb2, text=t, bg=BG, fg=DIM, font=UI).pack(side='left', padx=(16, 4))
            self.info[key] = tk.Label(tb2, text='—', bg=BG, fg=FG, font=MONO); self.info[key].pack(side='left')

        body = tk.Frame(w, bg=BG); body.pack(fill='both', expand=True, padx=14, pady=8)
        left = tk.Frame(body, bg=BG); left.pack(side='left', fill='both', expand=True)
        right = tk.Frame(body, bg=PANEL, padx=10, pady=8); right.pack(side='right', fill='y')

        views = tk.Frame(left, bg=BG); views.pack(anchor='w')
        self.src_title, self.src_cv = self._view(views, 'Imagem de origem')
        self.out_title, self.out_cv = self._view(views, 'Saída NES')
        # conta-gotas: clicar numa cor da saída leva ao espaço da paleta (e abre o seletor)
        self.out_cv.configure(cursor='tcross')
        self.out_cv.bind('<Button-1>', self.on_out_click)
        self.out_cv.bind('<Motion>', self.on_out_hover)
        self.out_cv.bind('<Leave>', lambda e: self.status.configure(text=self.p.status))
        tk.Label(left, text='🎯 clique numa cor da Saída NES para ir até ela na paleta e trocá-la',
                 bg=BG, fg=DIM, font=('Segoe UI', 8)).pack(anchor='w', pady=(4, 0))

        ctl = tk.Frame(left, bg=BG); ctl.pack(anchor='w', pady=8)
        self.resolve_btn = self._btn(ctl, '↻  Refazer', self.resolve); self.resolve_btn.pack(side='left')
        self.lockable.append(self.resolve_btn)
        self.lock_btn = self._btn(ctl, '🔒  Travar', self.toggle_lock); self.lock_btn.pack(side='left', padx=6)
        self.undo_btn = self._btn(ctl, '↶  Desfazer', self.undo); self.undo_btn.pack(side='left')
        st = tk.Frame(left, bg=PANEL, padx=10, pady=6); st.pack(anchor='w', fill='x')
        self.stat = {}
        for key, t in (('mode', 'Modo NES'), ('tiles', 'Tiles'), ('attrs', 'Atributos'), ('colors', 'Cores usadas')):
            box = tk.Frame(st, bg=PANEL); box.pack(side='left', padx=(0, 26))
            tk.Label(box, text=t, bg=PANEL, fg=DIM, font=UI).pack(anchor='w')
            self.stat[key] = tk.Label(box, text='—', bg=PANEL, fg=GOLD, font=('Consolas', 12, 'bold'))
            self.stat[key].pack(anchor='w')

        exp = tk.Frame(left, bg=BG); exp.pack(anchor='w', pady=8)
        tk.Label(exp, text='3 · EXPORTAR', bg=BG, fg=GOLD, font=UIB).pack(side='left', padx=(0, 10))
        self._btn(exp, '⇩  Salvar PNG', self.export_png).pack(side='left')
        self._btn(exp, 'Exportar BMP (RGB)', self.export_bmp).pack(side='left', padx=6)
        self.copy_btn = self._btn(exp, 'Copiar paletas (.byte)', self.copy_asm); self.copy_btn.pack(side='left')

        # paletas
        tk.Label(right, text='PALETAS', bg=PANEL, fg=GOLD, font=UIB).pack(anchor='w')
        tk.Label(right, text='Clique num espaço para escolher a cor · arraste uma cor da paleta mestre\n'
                             'para um espaço para fixá-la · ON/OFF liga e desliga a paleta',
                 bg=PANEL, fg=DIM, font=('Segoe UI', 8), justify='left').pack(anchor='w')
        self.pal_frame = tk.Frame(right, bg=PANEL); self.pal_frame.pack(anchor='w', pady=6)
        self.asm_var = tk.StringVar()
        e = tk.Entry(right, textvariable=self.asm_var, font=('Consolas', 8), bg=PANEL2, fg=FG, relief='flat',
                     readonlybackground=PANEL2, state='readonly', width=62)
        e.pack(anchor='w', fill='x')
        self.unpin_btn = self._btn(right, 'Soltar todas', self.unpin_all); self.unpin_btn.pack(anchor='w', pady=6)
        self.lockable.append(self.unpin_btn)

        tk.Label(right, text='PALETA MESTRE DO NES', bg=PANEL, fg=GOLD, font=UIB).pack(anchor='w', pady=(8, 0))
        tk.Label(right, text='clique = banir/permitir · arraste para um espaço = fixar',
                 bg=PANEL, fg=DIM, font=('Segoe UI', 8)).pack(anchor='w')
        self.master_frame = tk.Frame(right, bg=PANEL); self.master_frame.pack(anchor='w', pady=4)
        self.master_cells = []
        for i in range(64):
            c = tk.Label(self.master_frame, width=3, height=1, bg=nes_color(i), font=('Consolas', 7),
                         relief='flat', bd=0, highlightthickness=2, highlightbackground=PANEL)
            c.grid(row=i // 16, column=i % 16, padx=1, pady=1)
            c.nes = i
            c.bind('<ButtonPress-1>', self._drag_start)
            c.bind('<B1-Motion>', self._drag_move)
            c.bind('<ButtonRelease-1>', self._drag_end)
            self.master_cells.append(c)
        mb = tk.Frame(right, bg=PANEL); mb.pack(anchor='w', fill='x')
        self.ban_lbl = tk.Label(mb, text='', bg=PANEL, fg=DIM, font=MONO); self.ban_lbl.pack(side='left')
        self.enable_btn = self._btn(mb, 'Permitir todas', self.enable_all); self.enable_btn.pack(side='right')
        self.lockable.append(self.enable_btn)

    def _view(self, master, title):
        f = tk.Frame(master, bg=BG); f.pack(side='left', padx=(0, 12))
        t = tk.Label(f, text=title, bg=BG, fg=DIM, font=UI, anchor='w'); t.pack(anchor='w')
        cv = tk.Canvas(f, width=VIEW, height=VIEW, bg='#000', highlightthickness=1, highlightbackground=ACC)
        cv.pack()
        return t, cv

    # ============================================================ entrada
    def open_dialog(self):
        path = filedialog.askopenfilename(title='Abrir imagem ou projeto', filetypes=[
            ('Imagens e projetos', '*.png *.jpg *.jpeg *.gif *.webp *.bmp *.json'), ('Todos', '*.*')])
        if path: self.open_path(path)

    def open_path(self, path):
        try:
            if path.lower().endswith('.json'):
                self.p = Projeto()
                self.p.from_json(open(path, encoding='utf-8').read())
                self.enter_work()
                self.sync_controls()
                self.refresh()
                return
            self.p.load_image(path)
        except Exception as ex:
            messagebox.showerror('Palette Lab', 'Não foi possível abrir:\n%s' % ex)
            return
        self.p.locked = False
        self.enter_work()
        self.run(self.p.process)

    def start_blank(self, size):
        self.p.start_blank(size)
        self.enter_work()
        self.sync_controls()
        self.run(self.p.process)
        self.p.status = 'Tela em branco — fixe cores e pinte'
        self.open_editor()
        self.refresh()

    def enter_work(self):
        self.landing.pack_forget()
        self.work.pack(fill='both', expand=True)
        self._set_step(2)
        self.sync_controls()

    def run(self, fn, *a):
        """Executa uma operação pesada mostrando 'processando…'."""
        self.status.configure(text='processando…'); self.root.update_idletasks()
        fn(*a)
        self.refresh()

    # ============================================================ controles da barra
    def sync_controls(self):
        p = self.p
        self.fit_cb.set_value(p.fit); self.size_cb.set_value(p.out_size); self.block_cb.set_value(p.block)
        self.grid_cb.set_value(p.main_grid)
        self.mix_var.set(round(p.mix * 100)); self.seam_var.set(round(p.seam * 100))
        self.dither_btn.configure(text='Pontilhado: %s' % ('ligado' if p.dither else 'desligado'),
                                  bg=GOLD if p.dither else PANEL2, fg='#000' if p.dither else FG)
        self.apply_lock_state()

    def _locked_guard(self):
        if self.p.check_locked():
            self.sync_controls(); self.refresh(); return True
        return False

    def on_fit(self, v):
        if self._locked_guard(): return
        self.p.fit = v; self.run(self.p.process)

    def on_size(self, v):
        if self._locked_guard(): return
        self.p.out_size = v
        nota = ''
        if v == CAPA:
            nota = self._modo_capa()
        self.run(self.p.process)
        if v == CAPA: self.status.configure(text=self.p.status + ' — modo capa EDFC (64×96, blocos 8×16)' + nota)

    def _modo_capa(self):
        """Ajustes do modo capa: bloco 8x16 e, se a fidelidade ainda estiver no padrão do site (50%),
        75% (testado com capas de caixa: cores mais fiéis sem perder tons de pele)."""
        p, nota = self.p, ''
        p.out_size = CAPA
        if p.block != CAPA_BLOCK:
            p.block = CAPA_BLOCK
        if abs(p.mix - 0.5) < 1e-9:
            p.mix = 0.75; nota = ' · fidelidade de cor ajustada para 75%'
        self.sync_controls()
        return nota

    def on_block(self, v):
        if self._locked_guard(): return
        self.p.block = v; self.run(self.p.process)

    def on_mix(self):
        if self._locked_guard(): return
        self.p.mix = self.mix_var.get() / 100; self.run(self.p.process)

    def on_seam(self):
        if self._locked_guard(): return
        self.p.seam = self.seam_var.get() / 100; self.run(self.p.process)

    def on_dither(self):
        if self._locked_guard(): return
        self.p.dither = not self.p.dither
        self.sync_controls()
        self.run(self.p.render, 'Pontilhado %s' % ('ligado' if self.p.dither else 'desligado'))

    def on_grid(self, v):
        self.p.main_grid = v; self.draw_views()

    def resolve(self):
        if not self.p.img: return
        self.run(self.p.resolve)

    def undo(self):
        if not self.p.img: return
        self.p.do_undo(); self.refresh()

    def toggle_lock(self):
        if not self.p.img: return
        self.p.locked = not self.p.locked
        self.p.status = '🔒 Travado — visual congelado' if self.p.locked else 'Destravado'
        self.apply_lock_state(); self.refresh()

    def apply_lock_state(self):
        st = 'disabled' if self.p.locked else 'normal'
        for wdg in self.lockable:
            try: wdg.configure(state=st if not isinstance(wdg, ttk.Combobox) else ('disabled' if self.p.locked else 'readonly'))
            except tk.TclError: pass
        self.lock_btn.configure(text='🔓  Destravar' if self.p.locked else '🔒  Travar',
                                bg=GOLD if self.p.locked else PANEL2, fg='#000' if self.p.locked else FG)
        self.undo_btn.configure(state='disabled' if (self.p.locked or not self.p.undo) else 'normal')

    # ============================================================ desenho
    def refresh(self):
        p = self.p
        if not p.img or not p.C: return
        self.draw_views()
        self.draw_palettes()
        self.draw_master()
        s = p.stats()
        for k in ('mode', 'tiles', 'attrs', 'colors'): self.stat[k].configure(text=str(s[k]))
        self.out_title.configure(text='Saída NES — ' + s['meta'])
        self.src_title.configure(text='Imagem de origem — ' + p.src_meta)
        self.info['orig'].configure(text=p.src_info.get('orig', '—'))
        self.info['work'].configure(text='%d × %d' % (p.W, p.H))
        self.info['fmt'].configure(text=p.src_info.get('fmt', '—'))
        self.info['size'].configure(text=p.src_info.get('size', '—'))
        self.asm_var.set(p.asm_text())
        self.apply_lock_state()
        self.status.configure(text=p.status)
        if self.editor: self.editor.sync()

    def _scale(self):
        return max(1, VIEW // max(self.p.W, self.p.H))

    def draw_views(self):
        p, sc = self.p, self._scale()
        for cv, im, key in ((self.src_cv, p.src_canvas, 'src'), (self.out_cv, p.output_image(), 'out')):
            big = im.resize((p.W * sc, p.H * sc), Image.Resampling.NEAREST)
            ph = ImageTk.PhotoImage(big)
            self._img_refs[key] = ph
            cv.delete('all')
            cv.configure(width=p.W * sc, height=p.H * sc)
            cv.create_image(0, 0, image=ph, anchor='nw')
        if p.main_grid != 'off':
            g = int(p.main_grid) * sc
            for x in range(g, p.W * sc, g): self.out_cv.create_line(x, 0, x, p.H * sc, fill=GOLD)
            for y in range(g, p.H * sc, g): self.out_cv.create_line(0, y, p.W * sc, y, fill=GOLD)

    def draw_palettes(self):
        p = self.p
        for wdg in self.pal_frame.winfo_children(): wdg.destroy()
        for g in range(4):
            off = g in p.pal_off
            row = tk.Frame(self.pal_frame, bg=PANEL); row.pack(anchor='w', pady=2)
            pw = tk.Button(row, text='OFF' if off else 'ON', width=4, relief='flat', font=('Consolas', 8, 'bold'),
                           bg=ACC if off else GOLD, fg=FG if off else '#000', cursor='hand2',
                           command=lambda g=g: self.toggle_pal(g),
                           state='disabled' if p.locked else 'normal')
            pw.pack(side='left', padx=(0, 6))
            tk.Label(row, text=('PAL %d · desligada' % g) if off else ('PAL %d · %d blocos' % (g, p.block_count(g))),
                     bg=PANEL, fg=DIM if off else FG, font=MONO, width=17, anchor='w').pack(side='left')
            pal = p.palettes[g] if g < len(p.palettes) else []
            full = [BLACK] * 4 if off else [BLACK] + list(pal)
            for pos, i in enumerate(full):
                s = pos - 1
                pinned = (not off) and pos > 0 and (g, s) in p.pins
                sw = tk.Label(row, text=hex2(i), width=5, bg=nes_color(i), fg=text_on(i), font=('Consolas', 8, 'bold'),
                              relief='flat', highlightthickness=2,
                              highlightbackground=GOLD if pinned else (ACC if pos == 0 else PANEL))
                sw.pack(side='left', padx=1)
                if not off and pos > 0:
                    sw.slot = (g, s)
                    sw.configure(cursor='hand2')
                    sw.bind('<Button-1>', lambda e, g=g, s=s: self.open_picker(g, s))
                    if pinned: tk.Label(row, text='📌', bg=PANEL, fg=GOLD, font=('Segoe UI', 7)).pack(side='left')

    def draw_master(self):
        p = self.p
        used = p.used_colors()
        for i, c in enumerate(self.master_cells):
            txt, hl = '', PANEL
            if i in FORBIDDEN and i != BLACK: txt = '·'
            if i == BLACK: txt, hl = 'BK', ACC
            if i in used: hl = GOLD
            if i in p.disabled: txt = '✕'
            c.configure(text=txt, fg=text_on(i), highlightbackground=hl,
                        cursor='arrow' if i in FORBIDDEN else 'hand2')
        n = len(p.disabled)
        self.ban_lbl.configure(text=('%d banidas · %d disponíveis' % (n, p.enabled_count())) if n
                               else '%d disponíveis · $0F = fundo' % p.enabled_count())

    # ============================================================ paletas
    def toggle_pal(self, g):
        self.run(self.p.toggle_pal, g)

    def unpin_all(self):
        self.p.unpin_all(); self.refresh()

    def enable_all(self):
        self.p.enable_all(); self.refresh()

    # arrastar da paleta mestre para um espaço (fixar) ou clicar (banir)
    def _drag_start(self, e):
        i = e.widget.nes
        if i in FORBIDDEN: self.drag = None; return
        self.drag = dict(i=i, x=e.x_root, y=e.y_root, moved=False, ghost=None)

    def _drag_move(self, e):
        d = self.drag
        if not d or d['i'] == BLACK: return
        if abs(e.x_root - d['x']) + abs(e.y_root - d['y']) > 4: d['moved'] = True
        if d['moved']:
            if not d['ghost']:
                gh = tk.Toplevel(self.root); gh.overrideredirect(True); gh.attributes('-topmost', True)
                tk.Label(gh, text=hex2(d['i']), bg=nes_color(d['i']), fg=text_on(d['i']), font=('Consolas', 9, 'bold'),
                         width=5, height=2).pack()
                d['ghost'] = gh
            d['ghost'].geometry('+%d+%d' % (e.x_root + 10, e.y_root + 10))

    def _drag_end(self, e):
        d, self.drag = self.drag, None
        if not d: return
        if d['ghost']: d['ghost'].destroy()
        if not d['moved']:
            if self.p.toggle_color(d['i']): self.refresh()
            else: self.status.configure(text=self.p.status)
            return
        target = self.root.winfo_containing(e.x_root, e.y_root)
        if target is not None and getattr(target, 'slot', None):
            g, s = target.slot
            self.p.pin_color(g, s, d['i']); self.refresh()

    # seletor de cor
    # conta-gotas na saída
    def _out_info(self, e):
        p = self.p
        if not p.img or not p.slot_map: return None
        sc = self._scale()
        return p.pixel_info(e.x // sc, e.y // sc)

    @staticmethod
    def _describe(i):
        base = '(%d,%d) · bloco %d · ' % (i['x'], i['y'], i['block'])
        if i['slot'] == 0: return base + 'fundo %s (fixo)' % hex2(BLACK)
        return base + 'PAL %d · espaço %d · %s' % (i['g'], i['slot'], hex2(i['idx']))

    def on_out_hover(self, e):
        i = self._out_info(e)
        if i: self.status.configure(text=self._describe(i) + ('' if i['slot'] == 0 else ' — clique para trocar'))

    def on_out_click(self, e):
        i = self._out_info(e)
        if not i: return
        if i['slot'] == 0:
            self.status.configure(text=self._describe(i) + ' — o fundo é sempre $0F e não pode ser trocado')
            return
        self.goto_slot(i['g'], i['slot'] - 1)

    def goto_slot(self, g, s):
        """Destaca o espaço (g, s) no painel de paletas e abre o seletor de cor dele."""
        self.flash_slot(g, s)
        self.open_picker(g, s)

    def flash_slot(self, g, s, n=6):
        sw = next((w for row in self.pal_frame.winfo_children() for w in row.winfo_children()
                   if getattr(w, 'slot', None) == (g, s)), None)
        if sw is None: return
        normal = sw.cget('highlightbackground')

        def blink(k):
            if not sw.winfo_exists(): return
            sw.configure(highlightbackground=(RED if k % 2 == 0 else normal) if k < n else normal,
                         highlightthickness=3 if k < n else 2)
            if k < n: self.root.after(160, blink, k + 1)
        blink(0)

    def open_picker(self, g, s):
        p = self.p
        if p.check_locked() or g in p.pal_off: self.status.configure(text=p.status); return
        self.close_picker()
        cur = p.palettes[g][s] if g < len(p.palettes) and s < len(p.palettes[g]) else None
        win = tk.Toplevel(self.root); win.title('PAL %d · ESPAÇO %d' % (g, s + 1)); win.configure(bg=PANEL)
        win.transient(self.root); win.resizable(False, False)
        self.picker = win
        win.bind('<Escape>', lambda e: self.close_picker())
        tk.Label(win, text='PAL %d · ESPAÇO %d' % (g, s + 1), bg=PANEL, fg=GOLD, font=UIB).pack(pady=(10, 4))
        hexl = tk.Label(win, text='', bg=PANEL, fg=FG, font=MONO); hexl.pack()
        grid = tk.Frame(win, bg=PANEL, padx=10, pady=8); grid.pack()
        for i in range(64):
            forb = i in FORBIDDEN
            c = tk.Label(grid, width=3, height=1, bg=nes_color(i), fg=text_on(i), font=('Consolas', 8),
                         text='·' if forb else ('✕' if i in p.disabled else ''), relief='flat',
                         highlightthickness=2, highlightbackground=GOLD if i == cur else PANEL,
                         cursor='arrow' if forb else 'hand2')
            c.grid(row=i // 16, column=i % 16, padx=1, pady=1)
            if not forb:
                info = hex2(i) + (' — banida; escolher desbane' if i in p.disabled else '')
                c.bind('<Enter>', lambda e, t=info: hexl.configure(text=t))
                c.bind('<Button-1>', lambda e, i=i: self._pick(g, s, i))
            else:
                c.bind('<Enter>', lambda e, i=i: hexl.configure(text=hex2(i) + ' — não usável'))
        bb = tk.Frame(win, bg=PANEL); bb.pack(pady=(0, 10))
        self._btn(bb, 'Auto (soltar)', lambda: self._pick_auto(g, s)).pack(side='left', padx=4)
        self._btn(bb, 'Cancelar', self.close_picker).pack(side='left', padx=4)
        # abre ao lado do ponteiro, sem sair da tela
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x = min(self.root.winfo_pointerx() + 16, win.winfo_screenwidth() - w - 8)
        y = min(self.root.winfo_pointery() + 16, win.winfo_screenheight() - h - 48)
        win.geometry('+%d+%d' % (max(0, x), max(0, y)))

    def _pick(self, g, s, i):
        self.close_picker()
        self.p.pin_color(g, s, i); self.refresh()
        if self.editor: self.editor.build_brushes()

    def _pick_auto(self, g, s):
        self.close_picker()
        self.run(self.p.release_slot, g, s)
        if self.editor: self.editor.build_brushes()

    def close_picker(self):
        if self.picker:
            self.picker.destroy(); self.picker = None

    # ============================================================ exportação / projeto
    def export_png(self):
        if not self.p.img: return
        path = filedialog.asksaveasfilename(defaultextension='.png', initialfile='nes-%dx%d.png' % (self.p.W, self.p.H),
                                            filetypes=[('PNG', '*.png')])
        if path:
            self.p.save_png(path); self._set_step(3)
            self.status.configure(text='PNG salvo: %s' % os.path.basename(path))

    def export_bmp(self):
        if not self.p.slot_map: return
        path = filedialog.asksaveasfilename(defaultextension='.bmp', initialfile='nes-rgb-%dx%d.bmp' % (self.p.W, self.p.H),
                                            filetypes=[('BMP', '*.bmp')])
        if path:
            self.p.save_bmp(path); self._set_step(3)
            self.status.configure(text='BMP exportado — espaços codificados em RGB (fundo preto, 1 R, 2 G, 3 B)')

    def copy_asm(self):
        if not self.p.img: return
        self.root.clipboard_clear(); self.root.clipboard_append(self.p.asm_text())
        self.copy_btn.configure(text='Copiado!')
        self.root.after(1200, lambda: self.copy_btn.configure(text='Copiar paletas (.byte)'))

    # ============================================================ capa EDFC
    def save_capa(self):
        p = self.p
        if not p.img: return
        if not p.is_capa():
            if not messagebox.askyesno('Capa EDFC', 'A capa da firmware é 64×96 com blocos 8×16.\n'
                                       'Mudar para o modo capa agora? (a conversão será refeita)'):
                return
            nota = self._modo_capa(); self.run(p.process)
            self.status.configure(text=p.status + ' — modo capa EDFC' + nota + '. Confira e clique de novo para salvar.')
            return
        stem = os.path.splitext(os.path.basename(p.src_path))[0] if p.src_path else 'capa'
        path = filedialog.asksaveasfilename(
            title='Salvar capa — use o MESMO nome da ROM (ex.: Contra (USA).json)',
            initialdir=os.path.dirname(p.src_path) if p.src_path else None,
            initialfile=stem + '.json', defaultextension='.json', filetypes=[('Capa (projeto Palette Lab)', '*.json')])
        if not path: return
        open(path, 'w', encoding='utf-8').write(p.to_json())
        self._set_step(3)
        self.status.configure(text='Capa salva: %s — ela entra no COVERS.BIN com estas cores e pixels exatos'
                                   % os.path.basename(path))

    def open_gerar(self):
        GerarDialog(self)

    def save_project(self):
        if not self.p.img: return False
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='palette-lab-project.json',
                                            filetypes=[('Projeto Palette Lab', '*.json')])
        if not path: return False
        open(path, 'w', encoding='utf-8').write(self.p.to_json())
        self.status.configure(text='Projeto salvo: %s' % os.path.basename(path))
        return True

    def new_project(self):
        if not self.p.img: self.reset(); return
        if self.confirm: return
        win = tk.Toplevel(self.root); win.title('Novo projeto'); win.configure(bg=PANEL); win.transient(self.root)
        win.resizable(False, False)
        self.confirm = win
        win.bind('<Escape>', lambda e: self._close_confirm())
        win.protocol('WM_DELETE_WINDOW', self._close_confirm)
        tk.Label(win, text='Começar um novo projeto?', bg=PANEL, fg=FG, font=UIB).pack(padx=20, pady=(16, 4))
        tk.Label(win, text='O trabalho atual será fechado.', bg=PANEL, fg=DIM, font=UI).pack(padx=20)
        bb = tk.Frame(win, bg=PANEL); bb.pack(pady=14, padx=14)

        def save_new():
            if self.save_project():
                self._close_confirm(); self.reset()
        self._btn(bb, 'Salvar e novo', save_new, bg=GOLD, fg='#000').pack(side='left', padx=4)
        self._btn(bb, 'Descartar e novo', lambda: (self._close_confirm(), self.reset())).pack(side='left', padx=4)
        self._btn(bb, 'Cancelar', self._close_confirm).pack(side='left', padx=4)

    def _close_confirm(self):
        if self.confirm: self.confirm.destroy(); self.confirm = None

    def reset(self):
        if self.editor: self.editor.close()
        self.p = Projeto()
        self.work.pack_forget()
        self.landing.pack(fill='both', expand=True)
        self._set_step(1)
        self.status.configure(text='')

    def _escape(self, e=None):
        if self.confirm: self._close_confirm()
        elif self.picker: self.close_picker()
        elif self.editor: self.editor.close()

    # ============================================================ editor
    def open_editor(self):
        if not self.p.img or not self.p.C: return
        if self.editor: self.editor.win.lift(); return
        self.editor = Editor(self)


class Editor:
    """Editor de pixels: Pintar / Borracha automática / Definir paleta do bloco."""

    def __init__(self, app):
        self.app, p = app, app.p
        self.tool = 'paint'
        self.sel = ('bk',)
        for g in range(4):
            if g not in p.pal_off and g < len(p.palettes) and p.palettes[g]:
                self.sel = (g, 0); break
        self.painting = False
        self.dirty = False
        win = self.win = tk.Toplevel(app.root)
        win.title('Editor de pixels'); win.configure(bg=BG)
        win.protocol('WM_DELETE_WINDOW', self.close)
        win.bind('<Escape>', lambda e: self.close())
        win.bind('<Control-z>', lambda e: self.undo())
        top = tk.Frame(win, bg=PANEL, padx=8, pady=6); top.pack(fill='x')
        self.tool_btns = {}
        for key, t in (('paint', 'Pintar'), ('erase', 'Borracha automática'), ('attr', 'Definir paleta')):
            b = app._btn(top, t, lambda k=key: self.set_tool(k)); b.pack(side='left', padx=(0, 4))
            self.tool_btns[key] = b
        app._btn(top, '↶ Desfazer', self.undo).pack(side='left', padx=8)
        tk.Label(top, text='GRADE', bg=PANEL, fg=DIM, font=UI).pack(side='left', padx=(8, 3))
        self.grid_cb = Combo(top, EDGRID_OPTS, self.on_grid, 9); self.grid_cb.pack(side='left')
        self.grid_cb.set_value(p.ed_grid)
        app._btn(top, 'Limpar pintura', self.clear).pack(side='left', padx=8)
        app._btn(top, 'Concluir', self.close, bg=GOLD, fg='#000').pack(side='right')
        mid = tk.Frame(win, bg=BG); mid.pack(fill='both', expand=True, padx=8, pady=8)
        self.sc = max(1, min(640 // max(p.W, p.H), 12))
        self.cv = tk.Canvas(mid, width=p.W * self.sc, height=p.H * self.sc, bg='#000', highlightthickness=0,
                            cursor='crosshair')
        self.cv.pack(side='left')
        side = tk.Frame(mid, bg=PANEL, padx=8, pady=8); side.pack(side='left', fill='y', padx=(8, 0))
        tk.Label(side, text='PINCEL', bg=PANEL, fg=GOLD, font=UIB).pack(anchor='w')
        self.brush_frame = tk.Frame(side, bg=PANEL); self.brush_frame.pack(anchor='w', pady=4)
        tk.Label(side, text='clique = escolher pincel\nclique no pincel ativo = trocar a cor\n'
                            'botão direito na imagem = pegar a cor (conta-gotas)\n'
                            'direito de novo na mesma cor = trocá-la',
                 bg=PANEL, fg=DIM, font=('Segoe UI', 8), justify='left').pack(anchor='w', pady=(6, 0))
        self.coords = tk.Label(side, text='', bg=PANEL, fg=FG, font=MONO); self.coords.pack(anchor='w', pady=10)
        self.cv.bind('<Button-3>', self.eyedropper)
        self.cv.bind('<ButtonPress-1>', self.down)
        self.cv.bind('<B1-Motion>', self.move)
        self.cv.bind('<Motion>', self.hover)
        self.cv.bind('<ButtonRelease-1>', self.up)
        self.cv.bind('<Leave>', lambda e: self.coords.configure(text=''))
        self.set_tool('paint')
        self.build_brushes()
        self.sync()

    # ------------------------------------------------------------
    def set_tool(self, k):
        self.tool = k
        for key, b in self.tool_btns.items():
            b.configure(bg=GOLD if key == k else PANEL2, fg='#000' if key == k else FG)

    def on_grid(self, v):
        self.app.p.ed_grid = v; self.sync()

    def build_brushes(self):
        p = self.app.p
        for wdg in self.brush_frame.winfo_children(): wdg.destroy()
        row = tk.Frame(self.brush_frame, bg=PANEL); row.pack(anchor='w', pady=2)
        tk.Label(row, text='FUNDO', bg=PANEL, fg=DIM, font=MONO, width=6, anchor='w').pack(side='left')
        sel = self.sel == ('bk',)
        b = tk.Label(row, text=hex2(BLACK), width=5, bg=nes_color(BLACK), fg='#fff', font=('Consolas', 8, 'bold'),
                     highlightthickness=3, highlightbackground=GOLD if sel else PANEL, cursor='hand2')
        b.pack(side='left'); b.bind('<Button-1>', lambda e: self.choose(('bk',)))
        for g in range(4):
            if g in p.pal_off or g >= len(p.palettes) or not p.palettes[g]: continue
            row = tk.Frame(self.brush_frame, bg=PANEL); row.pack(anchor='w', pady=2)
            tk.Label(row, text='PAL %d' % g, bg=PANEL, fg=DIM, font=MONO, width=6, anchor='w').pack(side='left')
            for s, ci in enumerate(p.palettes[g]):
                sel = self.sel == (g, s)
                b = tk.Label(row, text=hex2(ci), width=5, bg=nes_color(ci), fg=text_on(ci), font=('Consolas', 8, 'bold'),
                             highlightthickness=3, highlightbackground=GOLD if sel else PANEL, cursor='hand2')
                b.pack(side='left', padx=1)
                b.bind('<Button-1>', lambda e, g=g, s=s: self.choose((g, s)))

    def choose(self, sel):
        if sel != ('bk',) and sel == self.sel:
            self.app.open_picker(*sel)                     # 2º clique no pincel ativo = trocar a cor
            return
        self.sel = sel
        self.build_brushes()

    def eyedropper(self, e):
        """Botão direito: o pincel vira a cor clicada; de novo na mesma cor abre o seletor dela."""
        p = self.app.p
        pi = self._pix(e)
        if pi < 0: return
        i = p.pixel_info(pi % p.W, pi // p.W)
        sel = ('bk',) if i['slot'] == 0 else (i['g'], i['slot'] - 1)
        if sel == self.sel and sel != ('bk',):
            self.app.goto_slot(*sel)
            return
        self.sel = sel
        self.set_tool('paint')
        self.build_brushes()
        if sel != ('bk',): self.app.flash_slot(*sel)
        self.app.status.configure(text='Conta-gotas: ' + self.app._describe(i) +
                                       ('' if sel == ('bk',) else ' — botão direito de novo para trocar a cor'))

    # ------------------------------------------------------------ desenho
    def sync(self):
        p, sc = self.app.p, self.sc
        big = p.output_image().resize((p.W * sc, p.H * sc), Image.Resampling.NEAREST)
        self.ph = ImageTk.PhotoImage(big)
        self.cv.delete('all')
        self.cv.create_image(0, 0, image=self.ph, anchor='nw')
        if p.ed_grid != 'off':
            g = int(p.ed_grid) * sc
            if g >= 3:
                for x in range(g, p.W * sc, g): self.cv.create_line(x, 0, x, p.H * sc, fill='#7a5f2a')
                for y in range(g, p.H * sc, g): self.cv.create_line(0, y, p.W * sc, y, fill='#7a5f2a')
            if int(p.ed_grid) < max(p.bw, p.bh):            # bordas dos blocos de paleta em vermelho
                for x in range(p.bw * sc, p.W * sc, p.bw * sc): self.cv.create_line(x, 0, x, p.H * sc, fill=RED, width=2)
                for y in range(p.bh * sc, p.H * sc, p.bh * sc): self.cv.create_line(0, y, p.W * sc, y, fill=RED, width=2)

    def _pix(self, e):
        p = self.app.p
        x, y = e.x // self.sc, e.y // self.sc
        if x < 0 or y < 0 or x >= p.W or y >= p.H: return -1
        return y * p.W + x

    def hover(self, e):
        p = self.app.p
        pi = self._pix(e)
        if pi < 0: self.coords.configure(text=''); return
        b = p.block_of(pi)
        self.coords.configure(text='(%d,%d) · bloco %d · PAL %d' % (pi % p.W, pi // p.W, b, p.block_pal[b]))

    def down(self, e):
        p = self.app.p
        if p.locked:
            self.app.status.configure(text='🔒 Travado — destrave para editar'); return
        p.push_undo()
        self.painting, self.dirty = True, False
        self.apply(e)

    def move(self, e):
        self.hover(e)
        if self.painting: self.apply(e)

    def apply(self, e):
        pi = self._pix(e)
        if pi < 0: return
        p = self.app.p
        if p.ed_apply(pi, self.tool, self.sel):
            self.dirty = True
            if self.tool == 'paint' or self.tool == 'erase':
                x, y = pi % p.W, pi // p.W
                c = nes_color(p.idx_map[pi])
                self.cv.create_rectangle(x * self.sc, y * self.sc, (x + 1) * self.sc, (y + 1) * self.sc,
                                         fill=c, outline='')
            if self.tool == 'attr' or p.status.startswith('Bloco'):
                self.app.refresh()
        self.app.status.configure(text=p.status)

    def up(self, e):
        p = self.app.p
        if not self.painting: return
        self.painting = False
        if not self.dirty:
            if p.undo: p.undo.pop()
        else:
            p.render('Pintado — pixels salvos')
        self.app.refresh()

    def undo(self):
        self.app.undo(); self.build_brushes()

    def clear(self):
        if self.app.p.clear_paint(): self.app.refresh()
        else: self.app.status.configure(text=self.app.p.status)

    def close(self):
        self.win.destroy()
        self.app.editor = None


class GerarDialog:
    """Monta o /EDFC/COVERS.BIN a partir de uma pasta de capas (PNG e/ou projetos .json)."""

    def __init__(self, app):
        self.app = app
        win = self.win = tk.Toplevel(app.root)
        win.title('Gerar COVERS.BIN'); win.configure(bg=PANEL); win.transient(app.root)
        win.bind('<Escape>', lambda e: win.destroy())
        f = tk.Frame(win, bg=PANEL, padx=14, pady=12); f.pack(fill='both', expand=True)
        src = app.p.src_path
        self.capas = tk.StringVar(value=os.path.dirname(src) if src else '')
        self.saida = tk.StringVar(value='')
        self.prev = tk.StringVar(value='')
        self.v2 = tk.BooleanVar(value=False)
        self.sint = tk.BooleanVar(value=False)
        self.roms = []

        def row(lbl, var, pick):
            r = tk.Frame(f, bg=PANEL); r.pack(fill='x', pady=3)
            tk.Label(r, text=lbl, bg=PANEL, fg=FG, font=UI, width=24, anchor='w').pack(side='left')
            tk.Entry(r, textvariable=var, width=58, bg=PANEL2, fg=FG, insertbackground=FG, relief='flat',
                     font=MONO).pack(side='left', padx=4)
            app._btn(r, '…', pick, padx=6).pack(side='left')
        row('Pasta das capas (PNG/.json)', self.capas, lambda: self._dir(self.capas))
        r = tk.Frame(f, bg=PANEL); r.pack(fill='x', pady=3)
        tk.Label(r, text='Pastas das ROMs (opcional)', bg=PANEL, fg=FG, font=UI, width=24, anchor='w').pack(side='left')
        self.roms_lbl = tk.Label(r, text='(nenhuma: nome da capa + .nes)', bg=PANEL, fg=DIM, font=MONO, anchor='w',
                                 width=58, justify='left', wraplength=440)
        self.roms_lbl.pack(side='left', padx=4)
        app._btn(r, '+', self._add_rom, padx=6).pack(side='left')
        app._btn(r, 'limpar', self._clear_roms, padx=6).pack(side='left', padx=2)
        row('Salvar COVERS.BIN em', self.saida, self._out)
        row('Pasta de prévias (opcional)', self.prev, lambda: self._dir(self.prev))
        o = tk.Frame(f, bg=PANEL); o.pack(fill='x', pady=6)
        for txt, var in (('Formato v2 (experimental: sprites + fundo)', self.v2),
                         ('Capas de teste para ROMs sem capa (precisa das pastas das ROMs)', self.sint)):
            tk.Checkbutton(o, text=txt, variable=var, bg=PANEL, fg=FG, selectcolor=PANEL2, activebackground=PANEL,
                           activeforeground=FG, font=UI).pack(anchor='w')
        tk.Label(f, text='Copie o COVERS.BIN gerado para /EDFC/ no cartão '
                         '(v1 com o OS.BIN da favorita; v2 com o OS.BIN do experimento).',
                 bg=PANEL, fg=DIM, font=('Segoe UI', 8)).pack(anchor='w')
        b = tk.Frame(f, bg=PANEL); b.pack(fill='x', pady=8)
        self.go = app._btn(b, 'Gerar', self.run, bg=GOLD, fg='#000'); self.go.pack(side='left')
        app._btn(b, 'Fechar', win.destroy).pack(side='left', padx=6)
        self.log = tk.Text(f, height=16, width=100, bg='#0c0a09', fg=FG, font=('Consolas', 8), relief='flat')
        self.log.pack(fill='both', expand=True)

    def _dir(self, var):
        d = filedialog.askdirectory(parent=self.win, initialdir=var.get() or None)
        if d: var.set(d)

    def _add_rom(self):
        d = filedialog.askdirectory(parent=self.win, title='Pasta com ROMs .nes')
        if d and d not in self.roms:
            self.roms.append(d); self.roms_lbl.configure(text='\n'.join(self.roms), fg=FG)

    def _clear_roms(self):
        self.roms = []; self.roms_lbl.configure(text='(nenhuma: nome da capa + .nes)', fg=DIM)

    def _out(self):
        p = filedialog.asksaveasfilename(parent=self.win, initialfile='COVERS.BIN', defaultextension='.BIN',
                                         filetypes=[('COVERS.BIN', '*.BIN')])
        if p: self.saida.set(p)

    def command(self):
        capas, saida = self.capas.get().strip(), self.saida.get().strip()
        cmd = [sys.executable, GERAR] + ([capas] if capas else []) + ['-o', saida]
        for r in self.roms: cmd += ['--roms', r]
        if self.v2.get(): cmd.append('--v2')
        if self.sint.get(): cmd.append('--sinteticas')
        if self.prev.get().strip(): cmd += ['--preview', self.prev.get().strip()]
        return cmd

    def run(self):
        capas, saida = self.capas.get().strip(), self.saida.get().strip()
        if not saida or (not capas and not self.sint.get()):
            messagebox.showwarning('Gerar COVERS.BIN', 'Escolha a pasta das capas e onde salvar.', parent=self.win)
            return
        if self.sint.get() and not self.roms:
            messagebox.showwarning('Gerar COVERS.BIN', 'Capas de teste precisam das pastas das ROMs.', parent=self.win)
            return
        cmd = self.command()
        self.log.delete('1.0', 'end'); self.log.insert('end', 'processando…\n')
        self.go.configure(state='disabled')

        def work():
            r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            out = (r.stdout or '') + (r.stderr or '')
            self.win.after(0, lambda: self._done(out, r.returncode))
        threading.Thread(target=work, daemon=True).start()

    def _done(self, out, rc):
        self.log.delete('1.0', 'end'); self.log.insert('end', out or '(sem saída)')
        self.log.see('end')
        self.go.configure(state='normal')
        self.app.status.configure(text='COVERS.BIN gerado' if rc == 0 else 'Erro ao gerar o COVERS.BIN (veja o log)')


def main():
    root = tk.Tk()
    App(root, sys.argv[1] if len(sys.argv) > 1 else None)
    root.mainloop()


if __name__ == '__main__':
    main()
