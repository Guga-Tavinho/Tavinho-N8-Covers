"""Gerador de firmware com capas (EDFC / EverDrive N8 clone): capa grande 112x160 ao lado da lista (firmware v15:
a v10 + "@tavinho.games" embaixo da capa + 20 jogos por página + ← → vão para o topo da página + correção do
travamento ao ligar; o COVERS.BIN é o da v10).

1. Escolha a pasta das capas (PNG), as pastas de ROMs e a pasta de saída.
2. Prévia de cada capa como fica no NES. Por capa: nitidez (+ força) e flicker nos sprites (alterna a 60 Hz,
   sincronizado com o monitor; cada TV reage de um jeito: se tremer demais, desligue o flicker dela).
   Para todas: a espera (s) com o cursor parado antes de carregar a capa (qualquer botão cancela a carga).
3. Clique em GERAR FIRMWARE: sai <saída>/EDFC/OS.BIN + COVERS.BIN, prontos para o SD (ou já copiados para ele).

uso: pythonw gerador_firmware_capas.py   (ou o atalho "Gerador de firmware (capas + flicker).bat")
"""
import ctypes, hashlib, json, os, queue, re, shutil, subprocess, sys, threading, time, traceback, webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageTk
import conv_v3
import copiar_sd
import associar_roms
from gerar_covers import name_crc
import gerar_covers_v10 as gcv
import capa_grande_cores as CC
import sim_tela_cheia as stc
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'palette_lab'))
from nes_core import NES_HEX, FORBIDDEN, hex2, lum

CONGELADO = getattr(sys, 'frozen', False)               # rodando como .exe (PyInstaller): não há python
AQUI = os.path.dirname(os.path.abspath(__file__))      # (no .exe: a pasta interna, com firmwares/)
ROOT = os.path.dirname(sys.executable) if CONGELADO else os.path.dirname(AQUI)
FIRMWARE = (os.path.join(AQUI, 'firmwares', 'OS_v15.BIN'), 'caa12ed797d374341a40a76a7d2124ee3ce51e8a')
# v15 = v10 + "@tavinho.games" embaixo da capa + 20 jogos por página + ← → para o topo da página + o lmod confere
# o módulo em $66FC (o OS estraga $6400-$66FF ao ligar); o módulo (MOD_v10) é o mesmo da v10
MODULO = (os.path.join(AQUI, 'firmwares', 'MOD_v10.BIN'), '6e5e9cbfe33f9ff11185bb6a5e818528b4595650')
ESPQ = 34566                                     # byte da espera no OS.BIN: quadros + 1 (símbolo espq, $A706)
ESPERA_PADRAO = 0.5                              # segundos com o cursor parado antes de carregar a capa grande
ESPERA_MAX = 4.0                                 # (quadros + 1) cabe num byte
ARQ_PREFS = (os.path.join(os.environ.get('APPDATA', ROOT), 'NES N8 Covers editor', 'gerador_config.json')
             if CONGELADO else os.path.join(AQUI, 'gerador_config.json'))   # pastas e opções da última vez
TITULO = 'NES N8 Everdrive Covers editor - TavinhoGames'
REDES = [('github', 'GitHub', 'https://github.com/Guga-Tavinho'),
         ('instagram', 'Instagram', 'https://www.instagram.com/tavinho.games'),
         ('youtube', 'YouTube', 'https://www.youtube.com/@tavinho-games')]
NITIDEZ_PADRAO = True                            # capas sem escolha salva: com nitidez (pedido do usuário)
MODOS = [('alt', 'alternando 60 Hz'), ('P', 'média (sem flicker)'), ('A', 'só quadro A'), ('B', 'só quadro B')]
FUNDO, PAINEL, OURO, TEXTO, APAGADO = '#14110f', '#1d1916', '#d9a441', '#ece3d3', '#8d8273'
BOTAO = '#54473b'                                # botões: um tom bem mais claro que o fundo (pedido do usuário)
VERMELHO = '#d63b31'


def cor_nes(i): return '#' + NES_HEX[i]


def texto_sobre(i): return '#000' if lum(i) > 140 else '#fff'


def icone(tipo, lado=16):
    """Ícone pequeno (desenhado com suavização): 'nitidez' = brilho branco num círculo dourado;
    'editada' = paleta de pintor com pontos coloridos."""
    from PIL import ImageDraw
    k = 4                                                      # desenha 4x maior e reduz (bordas suaves)
    L = lado * k
    im = Image.new('RGBA', (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if tipo == 'nitidez':
        import math
        d.ellipse((0, 0, L - 1, L - 1), fill=(217, 164, 65, 255))
        def brilho(cx, cy, r):                            # estrela de lados curvos (astroide), como um brilho
            d.polygon([(cx + r * math.cos(t) ** 3, cy + r * math.sin(t) ** 3)
                       for t in [i * 2 * math.pi / 64 for i in range(64)]], fill=(255, 255, 255, 255))
        brilho(L * 0.44, L * 0.52, L * 0.34)
        brilho(L * 0.74, L * 0.27, L * 0.15)
    else:
        d.ellipse((0, L * 0.08, L - 1, L * 0.92), fill=(236, 220, 190, 255))          # a paleta
        d.ellipse((L * 0.58, L * 0.52, L * 0.86, L * 0.80), fill=(0, 0, 0, 0))       # o furo do dedo
        for (x, y), cor in (((0.22, 0.30), (214, 52, 52)), ((0.48, 0.22), (60, 170, 70)),
                            ((0.26, 0.58), (52, 110, 220)), ((0.62, 0.36), (240, 190, 40))):
            d.ellipse((L * x, L * y, L * (x + 0.2), L * (y + 0.2)), fill=cor + (255,))
    return im.resize((lado, lado), Image.Resampling.LANCZOS)


def logo(rede, lado=26):
    """Logo simplificado de cada rede, desenhado com suavização (sem baixar nada)."""
    from PIL import ImageDraw
    k = 4
    L = lado * k
    im = Image.new('RGBA', (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if rede == 'youtube':
        d.rounded_rectangle((0, L * 0.16, L - 1, L * 0.84), radius=L * 0.2, fill=(255, 0, 0, 255))
        d.polygon([(L * 0.40, L * 0.33), (L * 0.40, L * 0.67), (L * 0.69, L * 0.50)], fill=(255, 255, 255, 255))
    elif rede == 'instagram':
        g = Image.new('RGBA', (L, L))                          # degradê amarelo -> rosa -> roxo (na diagonal)
        cores = [(254, 218, 117), (250, 126, 30), (214, 41, 118), (150, 47, 191), (79, 91, 213)]
        px = g.load()
        for y in range(L):
            for x in range(L):
                t = min(0.999, max(0.0, ((L - 1 - y) + x) / (2.0 * (L - 1))))
                t = 1 - t
                i = int(t * (len(cores) - 1)); f = t * (len(cores) - 1) - i
                a, b = cores[i], cores[min(i + 1, len(cores) - 1)]
                px[x, y] = tuple(int(a[c] + (b[c] - a[c]) * f) for c in range(3)) + (255,)
        m = Image.new('L', (L, L), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, L - 1, L - 1), radius=L * 0.28, fill=255)
        im.paste(g, (0, 0), m)
        w = L * 0.075
        d.rounded_rectangle((L * 0.2, L * 0.2, L * 0.8, L * 0.8), radius=L * 0.18, outline=(255, 255, 255, 255), width=int(w))
        d.ellipse((L * 0.36, L * 0.36, L * 0.64, L * 0.64), outline=(255, 255, 255, 255), width=int(w))
        d.ellipse((L * 0.655, L * 0.27, L * 0.725, L * 0.34), fill=(255, 255, 255, 255))
    else:                                                      # github: círculo escuro com o gato (simplificado)
        d.ellipse((0, 0, L - 1, L - 1), fill=(240, 240, 240, 255))
        d.ellipse((L * 0.05, L * 0.05, L * 0.95, L * 0.95), fill=(24, 23, 23, 255))
        bco = (240, 240, 240, 255)
        d.ellipse((L * 0.28, L * 0.30, L * 0.72, L * 0.66), fill=bco)                      # cabeça
        d.polygon([(L * 0.29, L * 0.42), (L * 0.31, L * 0.22), (L * 0.42, L * 0.33)], fill=bco)   # orelhas
        d.polygon([(L * 0.71, L * 0.42), (L * 0.69, L * 0.22), (L * 0.58, L * 0.33)], fill=bco)
        d.rectangle((L * 0.42, L * 0.62, L * 0.58, L * 0.86), fill=bco)                     # pescoço/corpo
        d.arc((L * 0.12, L * 0.56, L * 0.46, L * 0.84), 90, 200, fill=bco, width=int(L * 0.06))   # rabo
    return im.resize((lado, lado), Image.Resampling.LANCZOS)


class _Razao(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('num', ctypes.c_uint32), ('den', ctypes.c_uint32)]


class _DwmTiming(ctypes.Structure):
    """DWM_TIMING_INFO (dwmapi.h, empacotada em 1 byte): só usamos rateRefresh e cRefresh."""
    _pack_ = 1
    _fields_ = ([('cbSize', ctypes.c_uint32), ('rateRefresh', _Razao), ('qpcRefreshPeriod', ctypes.c_uint64),
                 ('rateCompose', _Razao), ('qpcVBlank', ctypes.c_uint64), ('cRefresh', ctypes.c_uint64),
                 ('cDXRefresh', ctypes.c_uint32), ('qpcCompose', ctypes.c_uint64), ('cFrame', ctypes.c_uint64),
                 ('cDXPresent', ctypes.c_uint32), ('cRefreshFrame', ctypes.c_uint64),
                 ('cFrameSubmitted', ctypes.c_uint64), ('cDXPresentSubmitted', ctypes.c_uint32),
                 ('cFrameConfirmed', ctypes.c_uint64), ('cDXPresentConfirmed', ctypes.c_uint32),
                 ('cRefreshConfirmed', ctypes.c_uint64), ('cDXRefreshConfirmed', ctypes.c_uint32),
                 ('cFramesLate', ctypes.c_uint64), ('cFramesOutstanding', ctypes.c_uint32),
                 ('cFrameDisplayed', ctypes.c_uint64), ('qpcFrameDisplayed', ctypes.c_uint64),
                 ('cRefreshFrameDisplayed', ctypes.c_uint64), ('cFrameComplete', ctypes.c_uint64),
                 ('qpcFrameComplete', ctypes.c_uint64), ('cFramePending', ctypes.c_uint64),
                 ('qpcFramePending', ctypes.c_uint64)]
                + [(n, ctypes.c_uint64) for n in ('cFramesDisplayed', 'cFramesComplete', 'cFramesPending',
                                                   'cFramesAvailable', 'cFramesDropped', 'cFramesMissed',
                                                   'cRefreshNextDisplayed', 'cRefreshNextPresented',
                                                   'cRefreshesDisplayed', 'cRefreshesPresented', 'cRefreshStarted',
                                                   'cPixelsReceived', 'cPixelsDrawn', 'cBuffersEmpty')])


def vsync_info(dwm):
    """(número da atualização da tela, Hz do monitor) segundo o compositor do Windows, ou None."""
    t = _DwmTiming(); t.cbSize = ctypes.sizeof(t)
    if dwm.DwmGetCompositionTimingInfo(None, ctypes.byref(t)) != 0 or not t.rateRefresh.den:
        return None
    return t.cRefresh, t.rateRefresh.num / t.rateRefresh.den


class App:
    def __init__(self, root):
        self.root = root
        root.title(TITULO)
        root.configure(bg=FUNDO)
        self.estilo()
        self.fila = queue.Queue()
        import multiprocessing
        self.fila_prog = multiprocessing.Queue()              # andamento das prévias, vindo dos processos
        self.prog_g = {}                                       # (png, nitidez, flicker, λ, pontilhado) -> 0..1
        self.pool = ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 2),   # níveis com flicker
                                        initializer=gcv.iniciar_worker, initargs=(self.fila_prog,))
        self.pool_rapido = ProcessPoolExecutor(max_workers=1)  # prévia sem flicker (~1 s): nunca fica na fila deles
        self.fotos = {}
        self.modo = tk.StringVar(value='alt')
        self.zoom = tk.IntVar(value=2)                         # visualização 2x ao abrir (pedido do usuário)
        self.capas = tk.StringVar(value=os.path.join(ROOT, 'imagens'))
        self.saida = tk.StringVar(value=os.path.join(ROOT, 'firmware_gerada'))
        self.unidade = tk.StringVar()                          # cartão SD (unidade com a pasta EDFC)
        self.capa_teste = tk.StringVar()
        self.busca = tk.StringVar()
        self.so_rom = False                                    # lista só com as capas associadas às ROMs
        self.assoc = None                                      # capa -> [(rom, nota)] (da última busca nas ROMs)
        self.roms_sem_capa = []
        self.busca_rom = 0                                     # muda a cada busca (resultado antigo é ignorado)
        self.nitidez = tk.BooleanVar(value=False)
        self.flicker = tk.BooleanVar(value=False)              # flicker nos sprites desta capa
        self.pontilhado = tk.BooleanVar(value=False)           # pontilhado (dithering) no fundo desta capa
        self.acrescentar = tk.BooleanVar(value=False)          # só acrescenta capas novas a um COVERS.BIN existente
        self.base = tk.StringVar()                             # esse COVERS.BIN
        self.espera = tk.StringVar(value='%.1f' % ESPERA_PADRAO)   # segundos com o cursor parado antes de carregar
        self.gerando = False
        self.miniaturas = {}                                   # nome do arquivo -> imagem 32x48
        self.adiado = None
        self.cache_g = {}                                      # (png, nitidez, flicker) -> prévia
        self.pedidos_g = {}                                    # (png, nitidez, flicker) -> cálculo em andamento
        self.g_src, self.g_nit, self.g_orig, self.g_pont = None, 0, None, False
        self.eds = {}                                          # (png, nitidez, flicker) -> paletas atuais (editadas)
        self.ver_ed = {}                                       # (png, nitidez, flicker) -> versão (muda a cada edição)
        self.imgs_ed = {}                                      # (png, nitidez, flicker) -> (versão, (A, B, P))
        self.desfazer = []                                     # [((png, nitidez, flicker), paletas antes)]
        self.picker = None
        self.i_lam = gcv.LAMBDAS.index(gcv.LAMBDA_PADRAO)       # nível do flicker desta capa (índice em LAMBDAS)

        self.lateral = ttk.Frame(root)
        self.lateral.pack(side='left', fill='y', padx=(10, 0), pady=10)
        # o corpo (seções 1-3) fica num Canvas com barra de rolagem à direita: em tela baixa nada fica tampado
        self.rolagem = ttk.Scrollbar(root, orient='vertical')
        self.rolagem.pack(side='right', fill='y')
        self.tela_corpo = tk.Canvas(root, bg=FUNDO, highlightthickness=0, borderwidth=0,
                                    yscrollcommand=self.rolagem.set)
        self.tela_corpo.pack(side='left', fill='both', expand=True)
        self.rolagem.configure(command=self.tela_corpo.yview)
        self.corpo = ttk.Frame(self.tela_corpo)
        self.janela_corpo = self.tela_corpo.create_window(0, 0, window=self.corpo, anchor='nw')
        self.tam_corpo = None
        root.bind_all('<MouseWheel>', self.roda_mouse)
        self.montar_lateral()
        self.montar_cabecalho()
        self.montar_config()
        self.montar_teste()
        self.montar_gerar()
        self.ler_prefs()
        self.mostrar_espera()
        self.mostrar_base()
        self.listar_capas()
        self.mostrar_so_rom(); self.procurar_roms()
        root.bind('<Left>', lambda e: self.passo_lam(-1))
        root.bind('<Right>', lambda e: self.passo_lam(1))
        root.protocol('WM_DELETE_WINDOW', self.fechar)
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)              # temporizador de 1 ms
            self.dwm = ctypes.windll.dwmapi                     # DwmFlush: espera o próximo vsync do monitor
        except Exception:
            self.dwm = None
        self.quadro = 0
        self.ult_vsync = None
        self.vsync_perdidos = 0                                # atualizações da tela sem troca (estatística)
        self.hz = 60.0
        self.corpo.update_idletasks()                          # janela inicial do tamanho do conteúdo
        self.tela_corpo.configure(width=self.corpo.winfo_reqwidth(), height=self.corpo.winfo_reqheight())
        self.ajustar_rolagem()
        self.animar()
        self.ler_fila()

    # ------------------------------------------------------------------ interface
    def estilo(self):
        st = ttk.Style()
        st.theme_use('clam')
        st.configure('.', background=FUNDO, foreground=TEXTO, fieldbackground='#26211d')
        st.configure('TLabelframe', background=FUNDO, bordercolor='#3a332c')
        st.configure('TLabelframe.Label', background=FUNDO, foreground=OURO, font=('Segoe UI', 10, 'bold'))
        st.configure('TButton', background=BOTAO, foreground='#f6eedf', borderwidth=1, bordercolor='#7a6a58',
                     lightcolor=BOTAO, darkcolor=BOTAO, padding=(8, 4))
        st.map('TButton', background=[('disabled', '#2a2420'), ('pressed', '#3e352c'), ('active', '#6b5c4c')],
               foreground=[('disabled', '#5a5249')])
        st.configure('Seta.TButton', font=('Segoe UI', 14, 'bold'), padding=(12, 0))
        st.configure('Gerar.TButton', background=OURO, foreground='#000', font=('Segoe UI', 11, 'bold'), padding=(16, 8))
        st.map('Gerar.TButton', background=[('disabled', '#5a5249'), ('active', '#e8b85a')])
        st.configure('Rom.TButton', background='#2f7d6d', foreground='#ffffff', bordercolor='#5fc4ad',
                     lightcolor='#2f7d6d', darkcolor='#2f7d6d')
        st.map('Rom.TButton', background=[('disabled', '#2a2420'), ('pressed', '#24604f'), ('active', '#3b9985')])
        st.configure('Creditos.TButton', background='#e0457b', foreground='#ffffff', bordercolor='#ff7aa5',
                     lightcolor='#e0457b', darkcolor='#e0457b', font=('Segoe UI', 10, 'bold'), padding=(14, 5))
        st.map('Creditos.TButton', background=[('pressed', '#b8325f'), ('active', '#ff6b9a')])
        st.configure('TCheckbutton', background=FUNDO, foreground=TEXTO)
        st.configure('TRadiobutton', background=FUNDO, foreground=TEXTO)
        st.configure('Painel.TRadiobutton', background=PAINEL, foreground=TEXTO)
        st.configure('Horizontal.TScale', background=FUNDO, troughcolor='#26211d')
        st.configure('Horizontal.TProgressbar', background=OURO, troughcolor='#26211d')
        st.configure('TCombobox', fieldbackground='#26211d', foreground=TEXTO, arrowcolor=TEXTO)
        st.configure('Capas.Treeview', background=PAINEL, fieldbackground=PAINEL, foreground=TEXTO, rowheight=54,
                     borderwidth=0, font=('Segoe UI', 9))
        st.map('Capas.Treeview', background=[('selected', OURO)], foreground=[('selected', '#000')])
        st.configure('Vertical.TScrollbar', background='#26211d', troughcolor=FUNDO, arrowcolor=TEXTO)

    def montar_lateral(self):
        f = ttk.LabelFrame(self.lateral, text=' Capas ', padding=6)
        f.pack(fill='y', expand=True)
        ttk.Label(f, text='Clique numa imagem para ver como ela fica no NES.', foreground=APAGADO,
                  wraplength=250).pack(anchor='w')
        e = ttk.Entry(f, textvariable=self.busca)
        e.pack(fill='x', pady=(4, 4))
        self.busca.trace_add('write', lambda *a: self.filtrar_lista())
        lb = ttk.Frame(f); lb.pack(fill='x')
        ttk.Label(lb, text='buscar ↑', foreground=APAGADO, font=('Segoe UI', 8)).pack(side='left')
        ttk.Button(lb, text='⟳ Atualizar', command=self.atualizar_capas).pack(side='right')
        self.b_so_rom = ttk.Button(f, text='🎮  Mostrar só capas das minhas ROMs', command=self.trocar_so_rom)
        self.b_so_rom.pack(fill='x', pady=(4, 0))
        self.lb_assoc = ttk.Label(f, text='', foreground=APAGADO, wraplength=280, font=('Segoe UI', 8))
        self.icones = {t: icone(t) for t in ('nitidez', 'editada')}
        self.icones_tk = {t: ImageTk.PhotoImage(i) for t, i in self.icones.items()}
        q = ttk.Frame(f); q.pack(fill='y', expand=True)
        self.lista = ttk.Treeview(q, style='Capas.Treeview', show='tree', selectmode='browse', height=10)
        self.lista.column('#0', width=290)
        sb_ = ttk.Scrollbar(q, orient='vertical', command=self.lista.yview)
        self.lista.configure(yscrollcommand=sb_.set)
        self.lista.pack(side='left', fill='y', expand=True)
        sb_.pack(side='left', fill='y')
        self.lista.bind('<<TreeviewSelect>>', lambda e: self.ao_escolher())
        self.lb_rom = ttk.Label(f, text='', foreground=APAGADO, wraplength=290, font=('Segoe UI', 8))
        self.b_sem_capa = ttk.Button(f, text='', command=self.mostrar_sem_capa)
        rodape = ttk.Frame(f); rodape.pack(fill='x', pady=(4, 0))       # total de capas + legenda dos ícones
        self.rodape = rodape
        self.n_capas = ttk.Label(rodape, text='', foreground=APAGADO)
        self.n_capas.pack(side='left')
        for t, txt in (('editada', 'cores editadas'), ('nitidez', 'nitidez')):
            ttk.Label(rodape, image=self.icones_tk[t], text=' ' + txt, compound='left', foreground=APAGADO
                      ).pack(side='right', padx=(10, 0))

    def abrir_creditos(self):
        """Janela de créditos: autor e redes sociais (links clicáveis com o logo de cada uma)."""
        if getattr(self, 'win_creditos', None) and self.win_creditos.winfo_exists():
            self.win_creditos.lift(); return
        win = tk.Toplevel(self.root); win.title('Créditos'); win.configure(bg=PAINEL)
        win.transient(self.root); win.resizable(False, False)
        self.win_creditos = win
        tk.Label(win, text='NES N8 Everdrive Covers editor', bg=PAINEL, fg=OURO,
                 font=('Segoe UI', 14, 'bold')).pack(padx=28, pady=(20, 2))
        tk.Label(win, text='por TavinhoGames', bg=PAINEL, fg=TEXTO, font=('Segoe UI', 11)).pack(pady=(0, 14))
        self.logos_tk = {}
        caixa = tk.Frame(win, bg=PAINEL); caixa.pack(padx=28, anchor='w')
        for rede, nome, url in REDES:
            self.logos_tk[rede] = ImageTk.PhotoImage(logo(rede))
            linha = tk.Frame(caixa, bg=PAINEL); linha.pack(anchor='w', pady=5)
            tk.Label(linha, image=self.logos_tk[rede], bg=PAINEL).pack(side='left')
            tk.Label(linha, text=nome, bg=PAINEL, fg=TEXTO, font=('Segoe UI', 10, 'bold'), width=9,
                     anchor='w').pack(side='left', padx=(10, 0))
            ln = tk.Label(linha, text=url, bg=PAINEL, fg='#6cb4ff', cursor='hand2',
                          font=('Segoe UI', 10, 'underline'))
            ln.pack(side='left')
            ln.bind('<Button-1>', lambda e, u=url: webbrowser.open(u))
            ln.bind('<Enter>', lambda e, w=ln: w.configure(fg='#a9d4ff'))
            ln.bind('<Leave>', lambda e, w=ln: w.configure(fg='#6cb4ff'))
        ttk.Button(win, text='Fechar', command=win.destroy).pack(pady=(16, 18))
        win.bind('<Escape>', lambda e: win.destroy())
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_reqwidth()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_reqheight()) // 3
        win.geometry('+%d+%d' % (max(0, x), max(0, y)))

    def atualizar_capas(self):
        """Procura de novo as imagens da pasta das capas (novas, apagadas, renomeadas)."""
        antes = set(getattr(self, 'nomes_capas', []))
        self.listar_capas()
        novas = len(set(self.nomes_capas) - antes)
        self.nota_novas = '  · %d nova(s)' % novas if novas else ''        # fica até a próxima leitura da pasta
        self.n_capas.configure(text=self.n_capas.cget('text') + self.nota_novas)
        self.procurar_roms()                                      # ROMs novas no cartão também

    # ------------------------------------------------------------------ só as capas das ROMs
    def trocar_so_rom(self):
        """Liga/desliga a lista só com as capas que têm ROM (associação inteligente, não só o nome exato)."""
        if self.so_rom:
            self.so_rom = False
            self.mostrar_so_rom(); self.filtrar_lista(); self.salvar_prefs(); return
        if not self.roms.get(0, 'end'):
            if not messagebox.askyesno('Capas das ROMs', 'Nenhuma pasta de ROMs configurada.\n\n'
                                       'Escolher a pasta das ROMs agora (pode ser a do cartão SD)?'):
                return
            self.adicionar_roms()
            if not self.roms.get(0, 'end'): return
        self.so_rom = True
        self.salvar_prefs()
        self.procurar_roms()

    def procurar_roms(self):
        """Lê as pastas de ROMs (em segundo plano: o cartão SD pode demorar) e associa cada ROM a uma capa.
        Com pastas de ROMs, só as capas associadas vão para a firmware (contagem do botão Gerar e flicker)."""
        self.busca_rom += 1
        g, pastas, capas = self.busca_rom, list(self.roms.get(0, 'end')), list(getattr(self, 'nomes_capas', []))
        if not pastas:
            self.assoc = None; self.so_rom = False
            self.mostrar_so_rom(); self.filtrar_lista(); self.atualizar_info(); return
        if self.so_rom: self.b_so_rom.configure(text='🎮  Procurando as ROMs…')
        self.b_so_rom.state(['disabled'])

        def rodar():
            try:
                roms = associar_roms.listar_roms(pastas)
                self.fila.put(('roms', g, roms, associar_roms.associar(roms, capas), pastas))
            except Exception as ex:
                self.fila.put(('roms', g, None, str(ex), pastas))
        threading.Thread(target=rodar, daemon=True).start()

    def fim_roms(self, g, roms, res, pastas):
        if g != self.busca_rom: return
        self.b_so_rom.state(['!disabled'])
        if roms is None:
            self.assoc = None
            if self.so_rom:
                self.so_rom = False; self.mostrar_so_rom()
                messagebox.showerror('Capas das ROMs', 'Erro ao ler as ROMs: %s' % res)
            self.atualizar_info(); return
        self.guardar_assoc(roms, res, pastas)
        self.mostrar_so_rom()
        self.filtrar_lista()
        self.atualizar_info()

    def guardar_assoc(self, roms, res, pastas):
        self.assoc = {}
        for r in roms:
            c, n = res[r]
            if c: self.assoc.setdefault(c, []).append((r, n))
        self.roms_sem_capa = [(r, res[r][1]) for r in roms if res[r][0] is None]
        self.total_roms = len(roms)
        faltando = [p for p in pastas if not os.path.isdir(p)]
        self.aviso_pastas = ('  ·  pasta não encontrada: ' + ', '.join(faltando)) if faltando else ''

    def mostrar_so_rom(self):
        """Botão, resumo e "ROMs sem capa" conforme o modo (lista completa ou só as capas das ROMs)."""
        if not self.so_rom:
            self.b_so_rom.configure(text='🎮  Mostrar só capas das minhas ROMs', style='TButton')
            for w in (self.lb_assoc, self.lb_rom, self.b_sem_capa): w.pack_forget()
            return
        self.b_so_rom.configure(text='✓  Só capas das minhas ROMs (clique para ver todas)', style='Rom.TButton')
        if self.assoc is None: return
        aprox = sum(1 for v in self.assoc.values() for r, n in v if not associar_roms.exata(r, '', n))
        self.lb_assoc.configure(text='%d de %d ROMs com capa (%d por nome parecido)%s' % (
            self.total_roms - len(self.roms_sem_capa), self.total_roms, aprox, self.aviso_pastas))
        self.lb_assoc.pack(anchor='w', after=self.b_so_rom, pady=(2, 0))
        self.lb_rom.pack(anchor='w', fill='x', before=self.rodape, pady=(4, 0))
        if self.roms_sem_capa:
            self.b_sem_capa.configure(text='Ver %d ROM(s) sem capa…' % len(self.roms_sem_capa))
            self.b_sem_capa.pack(fill='x', before=self.rodape, pady=(4, 0))
        else:
            self.b_sem_capa.pack_forget()
        self.mostrar_rom_da_capa()

    def mostrar_rom_da_capa(self):
        """Embaixo da lista: a(s) ROM(s) que vão usar a capa escolhida."""
        if not self.so_rom or self.assoc is None: return
        v = self.assoc.get(self.capa_teste.get(), [])
        if not v:
            self.lb_rom.configure(text='Esta capa não tem ROM (fica fora da firmware).'); return
        txt = '; '.join('%s%s' % (r, '' if associar_roms.exata(r, '', n) else ' (≈ %d%%)' % round(n * 100))
                        for r, n in v[:3])
        self.lb_rom.configure(text='ROM: ' + txt + (' … (+%d)' % (len(v) - 3) if len(v) > 3 else ''))

    def mostrar_sem_capa(self):
        """Janela com as ROMs que não ganharam capa (para procurar/renomear a imagem)."""
        win = tk.Toplevel(self.root); win.title('ROMs sem capa'); win.configure(bg=PAINEL)
        win.transient(self.root)
        tk.Label(win, text='%d ROM(s) sem capa' % len(self.roms_sem_capa), bg=PAINEL, fg=OURO,
                 font=('Segoe UI', 11, 'bold')).pack(anchor='w', padx=12, pady=(10, 0))
        tk.Label(win, text='Nenhuma imagem da pasta das capas parece com estes nomes. Para incluir, coloque uma '
                           'imagem com o nome do jogo (ou da ROM) na pasta das capas e clique em ⟳ Atualizar.',
                 bg=PAINEL, fg=APAGADO, wraplength=520, justify='left').pack(anchor='w', padx=12, pady=(2, 6))
        q = tk.Frame(win, bg=PAINEL); q.pack(fill='both', expand=True, padx=12)
        lb = tk.Listbox(q, width=80, height=18, bg='#26211d', fg=TEXTO, borderwidth=0, highlightthickness=0)
        sb_ = ttk.Scrollbar(q, orient='vertical', command=lb.yview); lb.configure(yscrollcommand=sb_.set)
        lb.pack(side='left', fill='both', expand=True); sb_.pack(side='left', fill='y')
        for r, _ in self.roms_sem_capa: lb.insert('end', r)
        ttk.Button(win, text='Fechar', command=win.destroy).pack(pady=10)
        win.bind('<Escape>', lambda e: win.destroy())
        self.posicionar(win)

    def filtrar_lista(self):
        termo = self.busca.get().strip().lower()
        self.lista.delete(*self.lista.get_children())
        vis = [n for n in self.nomes_capas if termo in n.lower()]
        if self.so_rom and self.assoc is not None:
            vis = [n for n in vis if n in self.assoc]
        nitidas = self.capas_nitidas()
        editadas = CC.editadas(self.capas.get())
        cfg_l = conv_v3.ler_config(self.capas.get())
        self.marcas_capa = {}
        for n in vis:
            st = os.path.splitext(n)[0]
            marca = '  · flicker λ %.2f' % gcv.lambda_grande(cfg_l, n) if gcv.flicker_grande(cfg_l, n) else ''
            if gcv.pontilhado_de(cfg_l, n): marca += '  · pontilhado'
            self.marcas_capa[n] = (n in nitidas, st in editadas)
            if self.so_rom and self.assoc is not None and len(self.assoc[n]) > 1:
                marca += '  · %d ROMs' % len(self.assoc[n])
            self.lista.insert('', 'end', iid=n, text=' ' + st + marca, image=self.imagem_item(n))
        if self.capa_teste.get() in vis:
            self.lista.selection_set(self.capa_teste.get()); self.lista.see(self.capa_teste.get())
        elif vis and self.so_rom:
            self.lista.selection_set(vis[0]); self.lista.see(vis[0])
        self.n_capas.configure(text='%d de %d imagens' % (len(vis), len(self.nomes_capas)) + getattr(self, 'nota_novas', ''))
        self.mostrar_rom_da_capa()

    def gerar_miniaturas(self, nomes, g):
        """Miniaturas aos poucos (algumas por vez), para a janela não travar com muitas capas."""
        if g != self.geracao_lista: return
        for n in nomes[:6]:
            try:
                im = Image.open(os.path.join(self.capas.get(), n)).convert('RGB')
                im.thumbnail((32, 48), Image.Resampling.LANCZOS)
                fundo = Image.new('RGB', (32, 48), PAINEL); fundo.paste(im, ((32 - im.width) // 2, (48 - im.height) // 2))
                self.miniaturas[n] = fundo
                if self.lista.exists(n): self.lista.item(n, image=self.imagem_item(n))
            except Exception:
                pass
        if nomes[6:]: self.root.after(1, self.gerar_miniaturas, nomes[6:], g)

    def imagem_item(self, n):
        """Miniatura da capa + coluna de ícones (nitidez em cima, cores editadas embaixo)."""
        nit, ed = getattr(self, 'marcas_capa', {}).get(n, (False, False))
        mini = self.miniaturas.get(n)
        chave = (n if mini is not None else None, nit, ed)
        cache = self.__dict__.setdefault('imgs_item', {})
        if chave not in cache:
            im = Image.new('RGB', (32 + 22, 48), PAINEL)
            if mini is not None: im.paste(mini, (0, 0))
            for ok, tipo, y in ((nit, 'nitidez', 7), (ed, 'editada', 27)):
                if ok:
                    ic = self.icones[tipo]
                    im.paste(ic, (36, y), ic)
            cache[chave] = ImageTk.PhotoImage(im)
        return cache[chave]

    def capas_nitidas(self):
        cfg = conv_v3.ler_config(self.capas.get())
        return {n for n in self.nomes_capas if conv_v3.nitidez_de(cfg, n, NITIDEZ_PADRAO)}

    def mostrar_forca(self, forca, ligada):
        self.barra_forca.set(forca)
        self.lbl_forca.configure(text='%d%%' % forca)
        for w in (self.barra_forca, self.b_forca_menos, self.b_forca_mais):
            w.state(['!disabled'] if ligada else ['disabled'])

    def passo_forca(self, d):
        """< e > da nitidez: 5% por clique; aplica quando os cliques param (meio segundo)."""
        if not self.nitidez.get(): return
        v = max(10, min(200, int(round(float(self.barra_forca.get()) / 5.0) * 5) + d))
        self.barra_forca.set(v)
        self.lbl_forca.configure(text='%d%%' % v)
        if getattr(self, 'adiado_forca', None): self.root.after_cancel(self.adiado_forca)
        self.adiado_forca = self.root.after(500, self.aplicar_forca)

    def aplicar_forca(self):
        self.adiado_forca = None
        self.trocar_forca()

    def trocar_forca(self):
        """Barra da nitidez solta: salva a força desta capa e recalcula (com a nitidez ligada)."""
        if not self.nitidez.get(): return
        forca = int(round(float(self.barra_forca.get()) / 5.0) * 5)       # de 5 em 5%
        cfg = conv_v3.ler_config(self.capas.get())
        if forca == conv_v3.forca_de(cfg, self.capa_teste.get()): self.mostrar_forca(forca, True); return
        conv_v3.definir_forca(cfg, self.capa_teste.get(), forca)
        try:
            conv_v3.salvar_config(self.capas.get(), cfg)
        except OSError as ex:
            messagebox.showerror('Nitidez', 'Não consegui salvar a configuração:\n%s' % ex)
        self.mostrar_nitidez_padrao()
        self.calcular_niveis()

    def trocar_pontilhado(self):
        """Liga/desliga o pontilhado da capa atual (salvo em capas_config.json, "pontilhado"); reconverte."""
        cfg = conv_v3.ler_config(self.capas.get())
        gcv.definir_pontilhado(cfg, self.capa_teste.get(), self.pontilhado.get())
        try:
            conv_v3.salvar_config(self.capas.get(), cfg)
        except OSError as ex:
            messagebox.showerror('Pontilhado', 'Não consegui salvar a configuração:\n%s' % ex)
        self.filtrar_lista()
        self.calcular_niveis()

    def trocar_nitidez(self):
        """Liga/desliga a nitidez da capa atual (fica salvo em <capas>/capas_config.json e vale na geração)."""
        nome = self.capa_teste.get()
        cfg = conv_v3.ler_config(self.capas.get())
        conv_v3.definir_nitidez(cfg, nome, self.nitidez.get())
        try:
            conv_v3.salvar_config(self.capas.get(), cfg)
        except OSError as ex:
            messagebox.showerror('Nitidez', 'Não consegui salvar a configuração:\n%s' % ex)
        self.filtrar_lista()
        self.calcular_niveis()

    def definir_padrao_nitidez(self):
        """A nitidez desta capa (ligada/desligada + força) vira o padrão das capas sem escolha própria."""
        nome = self.capa_teste.get()
        ligada = self.nitidez.get()
        forca = int(round(float(self.barra_forca.get()) / 5.0) * 5)
        cfg = conv_v3.ler_config(self.capas.get())
        conv_v3.definir_nitidez_padrao(cfg, ligada, forca, self.nomes_capas, NITIDEZ_PADRAO)
        conv_v3.definir_nitidez(cfg, nome, None)                # esta capa passa a seguir o padrão
        conv_v3.definir_forca(cfg, nome, None)
        try:
            conv_v3.salvar_config(self.capas.get(), cfg)
        except OSError as ex:
            messagebox.showerror('Nitidez', 'Não consegui salvar a configuração:\n%s' % ex); return
        self.filtrar_lista()
        self.mostrar_nitidez_padrao()

    def mostrar_nitidez_padrao(self):
        cfg = conv_v3.ler_config(self.capas.get())
        lig, f = conv_v3.nitidez_padrao(cfg, NITIDEZ_PADRAO), conv_v3.forca_padrao(cfg)
        nome = self.capa_teste.get()
        segue = nome not in cfg.get('nitidez', {}) and nome not in cfg.get('nitidez_forca', {})
        self.lbl_nit_padrao.configure(text='padrão: %s%s' % ('%d%%' % f if lig else 'desligada',
                                                            ' (esta capa segue)' if segue else ''))

    def ao_escolher(self):
        sel = self.lista.selection()
        if not sel or sel[0] == self.capa_teste.get(): return
        self.capa_teste.set(sel[0])
        self.mostrar_rom_da_capa()
        if self.adiado: self.root.after_cancel(self.adiado)
        self.adiado = self.root.after(250, self.calcular_niveis)     # ↑/↓ rápido na lista: só a última conta

    def ajustar_rolagem(self):
        """O corpo ocupa a largura do Canvas e pelo menos a altura dele; a rolagem cobre o que passar
        (conferido a cada 200 ms: o conteúdo muda de altura com o zoom, o formato, as prévias…)."""
        c = self.tela_corpo
        w, h = c.winfo_width(), c.winfo_height()
        alt = max(h, self.corpo.winfo_reqheight())
        if (w, alt) != self.tam_corpo and w > 1:
            self.tam_corpo = (w, alt)
            c.itemconfigure(self.janela_corpo, width=w, height=alt)
            c.configure(scrollregion=(0, 0, w, alt))
        self.root.after(200, self.ajustar_rolagem)

    def roda_mouse(self, e):
        """Roda do mouse rola a ferramenta, menos sobre o que já rola sozinho (lista das capas, log, listas)."""
        w = e.widget
        if not isinstance(w, tk.Misc) or isinstance(w, (tk.Text, tk.Listbox, ttk.Treeview, ttk.Spinbox)): return
        if not (str(w) + '.').startswith(str(self.tela_corpo) + '.'): return       # fora do corpo (lateral, outras janelas)
        if self.tela_corpo.yview() != (0.0, 1.0):
            self.tela_corpo.yview_scroll(-1 if e.delta > 0 else 1, 'units')

    def montar_cabecalho(self):
        """Faixa no topo: nome da ferramenta e o botão de créditos em destaque."""
        h = ttk.Frame(self.corpo); h.pack(fill='x', padx=10, pady=(6, 0))
        ttk.Label(h, text='NES N8 Everdrive Covers editor', foreground=OURO,
                  font=('Segoe UI', 13, 'bold')).pack(side='left')
        ttk.Label(h, text='  ·  TavinhoGames', foreground=APAGADO, font=('Segoe UI', 10)).pack(side='left')
        ttk.Button(h, text='★  Créditos', style='Creditos.TButton', command=self.abrir_creditos).pack(side='right')

    def montar_config(self):
        f = ttk.LabelFrame(self.corpo, text=' 1. Capas, ROMs e saída ', padding=(8, 5))
        f.pack(fill='x', padx=10, pady=(4, 4))
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text='Pasta das capas (PNG):').grid(row=0, column=0, sticky='w')
        e = ttk.Entry(f, textvariable=self.capas)
        e.grid(row=0, column=1, sticky='ew', padx=4)
        e.bind('<Return>', lambda ev: self.listar_capas())
        ttk.Button(f, text='Procurar…', command=self.escolher_capas).grid(row=0, column=2)
        ttk.Label(f, text='Pastas de ROMs (.nes):').grid(row=1, column=0, sticky='nw', pady=(4, 0))
        self.roms = tk.Listbox(f, height=2, bg='#26211d', fg=TEXTO, selectbackground=OURO, borderwidth=0,
                               highlightthickness=0)
        self.roms.grid(row=1, column=1, sticky='ew', padx=4, pady=(4, 0))
        b = ttk.Frame(f); b.grid(row=1, column=2, sticky='n', pady=(4, 0))
        ttk.Button(b, text='Adicionar…', command=self.adicionar_roms).pack(fill='x')
        ttk.Button(b, text='Remover', command=self.remover_roms).pack(fill='x', pady=(2, 0))
        ttk.Label(f, text='Pasta de saída:').grid(row=3, column=0, sticky='w', pady=(4, 0))
        ttk.Entry(f, textvariable=self.saida).grid(row=3, column=1, sticky='ew', padx=4, pady=(4, 0))
        ttk.Button(f, text='Procurar…', command=self.escolher_saida).grid(row=3, column=2, pady=(4, 0))
        ttk.Checkbutton(f, text='Só acrescentar capas novas ao COVERS.BIN:', variable=self.acrescentar,
                        command=self.trocar_acrescentar).grid(row=4, column=0, sticky='w', pady=(4, 0))
        ttk.Entry(f, textvariable=self.base, state='readonly').grid(row=4, column=1, sticky='ew', padx=4, pady=(4, 0))
        ttk.Button(f, text='Escolher…', command=self.escolher_base).grid(row=4, column=2, pady=(4, 0))
        self.lbl_base = ttk.Label(f, text='', foreground=APAGADO)
        self.lbl_base.grid(row=5, column=1, sticky='w', padx=4)

    def montar_teste(self):
        f = ttk.LabelFrame(self.corpo, text=' 2. Prévia da capa — nitidez e flicker por capa ', padding=(8, 5))
        f.pack(fill='both', expand=True, padx=10, pady=4)
        self.f_teste = f
        fm = ttk.Frame(f); fm.pack(fill='x', pady=(0, 6))
        ttk.Label(fm, text='Espera antes de carregar a capa:').pack(side='left')
        sp = ttk.Spinbox(fm, from_=0, to=ESPERA_MAX, increment=0.1, format='%.1f', width=5,
                         textvariable=self.espera, command=self.trocar_espera)
        sp.pack(side='left', padx=4)
        sp.bind('<FocusOut>', lambda e: self.trocar_espera())
        sp.bind('<Return>', lambda e: self.trocar_espera())
        self.lbl_espera = ttk.Label(fm, text='', foreground=APAGADO, font=('Segoe UI', 8))
        self.lbl_espera.pack(side='left')
        topo = ttk.Frame(f); topo.pack(fill='x')
        ttk.Label(topo, text='Capa:').pack(side='left')
        ttk.Label(topo, textvariable=self.capa_teste, foreground=OURO).pack(side='left', padx=4)
        self.chk_nitidez = ttk.Checkbutton(topo, text='Nitidez (nesta capa)', variable=self.nitidez,
                                           command=self.trocar_nitidez)
        self.chk_nitidez.pack(side='left', padx=(16, 0))
        self.chk_pont = ttk.Checkbutton(topo, text='Pontilhado (nesta capa)', variable=self.pontilhado,
                                        command=self.trocar_pontilhado)
        self.b_forca_menos = ttk.Button(topo, text='<', width=2, command=lambda: self.passo_forca(-5))
        self.b_forca_menos.pack(side='left', padx=(6, 0))
        self.barra_forca = ttk.Scale(topo, from_=10, to=200, orient='horizontal', length=140,
                                     command=lambda v: self.lbl_forca.configure(text='%d%%' % round(float(v))))
        self.barra_forca.pack(side='left', padx=(2, 0))
        self.b_forca_mais = ttk.Button(topo, text='>', width=2, command=lambda: self.passo_forca(5))
        self.b_forca_mais.pack(side='left', padx=(2, 0))
        self.barra_forca.bind('<ButtonRelease-1>', lambda e: self.trocar_forca())
        self.lbl_forca = ttk.Label(topo, text='70%', width=5)
        self.lbl_forca.pack(side='left', padx=(4, 0))
        self.b_nit_padrao = ttk.Button(topo, text='Definir padrão', command=self.definir_padrao_nitidez)
        self.b_nit_padrao.pack(side='left', padx=(4, 0))
        self.lbl_nit_padrao = ttk.Label(topo, text='', foreground=APAGADO, font=('Segoe UI', 8))
        self.lbl_nit_padrao.pack(side='left', padx=(6, 0))
        self.chk_pont.pack(side='left', padx=(16, 0))
        self.status = ttk.Label(topo, text='', foreground=APAGADO)
        self.status.pack(side='right', padx=10)

        ctl = ttk.Frame(f); ctl.pack(fill='x', pady=(8, 0))
        ttk.Checkbutton(ctl, text='Flicker nos sprites (nesta capa)', variable=self.flicker,
                        command=self.trocar_flicker).pack(side='left', padx=(0, 10))
        ttk.Label(ctl, text='nível:', foreground=APAGADO).pack(side='left')
        self.b_lam_menos = ttk.Button(ctl, text='<', width=2, command=lambda: self.passo_lam(-1))
        self.b_lam_menos.pack(side='left', padx=(4, 0))
        self.barra_lam = ttk.Scale(ctl, from_=0, to=len(gcv.LAMBDAS) - 1, orient='horizontal', length=360,
                                   command=lambda v: self.mostrar_lam(int(round(float(v)))))
        self.barra_lam.pack(side='left', padx=6)
        self.barra_lam.bind('<ButtonRelease-1>', lambda e: self.escolher_lam(int(round(float(self.barra_lam.get())))))
        self.b_lam_mais = ttk.Button(ctl, text='>', width=2, command=lambda: self.passo_lam(1))
        self.b_lam_mais.pack(side='left')
        self.lbl_lam = ttk.Label(ctl, text='', foreground=APAGADO, font=('Consolas', 9))
        self.lbl_lam.pack(side='left', padx=(8, 0))
        pc = ttk.Frame(f); pc.pack(fill='x', pady=(6, 0))
        self.lbl_capa_flk = ttk.Label(pc, text='', foreground=OURO)
        self.lbl_capa_flk.pack(side='left')
        self.b_usar_padrao = ttk.Button(pc, text='Usar o padrão nesta capa', command=self.usar_padrao)
        self.b_usar_padrao.pack(side='right')
        self.b_def_padrao = ttk.Button(pc, text='Definir como padrão', command=self.definir_padrao)
        self.b_def_padrao.pack(side='right', padx=(0, 4))
        self.info = tk.Label(f, text='', bg=FUNDO, fg=TEXTO, font=('Consolas', 12), anchor='w')
        self.info.pack(fill='x', pady=(3, 3))

        op = ttk.Frame(f); op.pack(fill='x')
        ttk.Label(op, text='mostrar:', foreground=APAGADO).pack(side='left')
        for v, t in MODOS:
            ttk.Radiobutton(op, text=t, value=v, variable=self.modo).pack(side='left', padx=4)
        ttk.Label(op, text='   zoom:', foreground=APAGADO).pack(side='left')
        for z in (1, 2, 3):
            ttk.Radiobutton(op, text='%d×' % z, value=z, variable=self.zoom, command=self.redesenhar).pack(side='left')
        telas = ttk.Frame(f); telas.pack(pady=(4, 0))
        self.telas = {}
        for k, t in (('orig', 'Original'), ('nes', 'Capa no NES (escolha desta capa)'),
                     ('v2', 'Capa sem flicker nos sprites')):
            q = tk.Frame(telas, bg=PAINEL, padx=8, pady=6); q.pack(side='left', padx=8, anchor='n')
            tk.Label(q, text=t, bg=PAINEL, fg=OURO, font=('Segoe UI', 9)).pack(anchor='w')
            c = tk.Label(q, bg='#000', fg=APAGADO, text='calculando…', font=('Segoe UI', 9), compound='center',
                         image=self.vazio(), borderwidth=0)
            c.pack(pady=(4, 0))
            self.telas[k] = c
        self.barra_nes = ttk.Progressbar(self.telas['nes'].master, mode='determinate', maximum=100)
        self.telas['nes'].configure(cursor='tcross')                 # conta-gotas
        self.telas['nes'].bind('<Button-1>', self.conta_gotas)
        self.telas['nes'].bind('<Motion>', self.sobre_capa)
        self.telas['nes'].bind('<Leave>', lambda e: self.dica.configure(text=self.dica_padrao))
        q = tk.Frame(telas, bg=PAINEL, padx=8, pady=6); q.pack(side='left', padx=8, anchor='n')
        tk.Label(q, text='Paletas desta capa', bg=PAINEL, fg=OURO, font=('Segoe UI', 9)).pack(anchor='w')
        self.pal_frame = tk.Frame(q, bg=PAINEL); self.pal_frame.pack(anchor='w', pady=(4, 0))
        bb = tk.Frame(q, bg=PAINEL); bb.pack(anchor='w', pady=(6, 0))
        self.b_desfazer = ttk.Button(bb, text='Desfazer', command=self.desfazer_cor)
        self.b_desfazer.pack(side='left')
        self.b_restaurar = ttk.Button(bb, text='Restaurar originais', command=self.restaurar_cores)
        self.b_restaurar.pack(side='left', padx=(4, 0))
        self.dica_padrao = ('Clique numa cor da capa no NES (conta-gotas) ou num espaço das paletas para trocar a cor. '
                            'Texto, barra e preto são cores fixas da firmware.')
        self.dica = tk.Label(f, text=self.dica_padrao, bg=FUNDO, fg=APAGADO, font=('Consolas', 9), anchor='w')
        self.dica.pack(fill='x', pady=(2, 0))

    def montar_gerar(self):
        f = ttk.LabelFrame(self.corpo, text=' 3. Gerar ', padding=(8, 5))
        f.pack(fill='x', padx=10, pady=(4, 6))
        top = ttk.Frame(f); top.pack(fill='x')
        self.b_gerar = ttk.Button(top, text='GERAR FIRMWARE', style='Gerar.TButton', command=self.gerar)
        self.b_gerar.pack(side='left')
        self.prog = ttk.Progressbar(top, mode='determinate')
        self.prog.pack(side='left', fill='x', expand=True, padx=10)
        self.b_pasta = ttk.Button(top, text='Abrir pasta de saída', command=self.abrir_saida)
        self.b_pasta.pack(side='left')
        sd = ttk.Frame(f); sd.pack(fill='x', pady=(6, 0))
        ttk.Label(sd, text='Cartão SD:').pack(side='left')
        ttk.Entry(sd, textvariable=self.unidade, width=28, state='readonly').pack(side='left', padx=4)
        ttk.Button(sd, text='Adicionar caminho…', command=self.escolher_sd).pack(side='left')
        ttk.Button(sd, text='Remover', command=lambda: (self.unidade.set(''), self.salvar_prefs())).pack(side='left', padx=2)
        self.b_copiar = ttk.Button(sd, text='Copiar agora', command=self.copiar_para_sd)
        self.b_copiar.pack(side='left', padx=(8, 0))
        ttk.Label(sd, text='(com o caminho, ao gerar a firmware ela já vai para o cartão: o COVERS.BIN antigo é '
                           'apagado e o novo gravado sem fragmentar)', foreground=APAGADO).pack(side='left', padx=8)
        self.log = tk.Text(f, height=4, bg='#0d0b0a', fg=TEXTO, font=('Consolas', 9), borderwidth=0, wrap='none')
        self.log.pack(fill='x', pady=(6, 0))

    # ------------------------------------------------------------------ acrescentar a um COVERS.BIN existente
    def trocar_acrescentar(self):
        """Ligado sem arquivo escolhido: sugere o do cartão SD (ou o da pasta de saída)."""
        if self.acrescentar.get() and not self.base.get():
            for c in ([os.path.join(copiar_sd.pasta_edfc(self.unidade.get()), 'COVERS.BIN')] if self.unidade.get() else []) \
                    + [os.path.join(self.saida.get(), 'EDFC', 'COVERS.BIN')]:
                if os.path.isfile(c): self.base.set(os.path.normpath(c)); break
        self.mostrar_base()

    def escolher_base(self):
        a = filedialog.askopenfilename(title='COVERS.BIN existente (as capas dele ficam como estão)',
                                       filetypes=[('COVERS.BIN', '*.BIN'), ('Todos', '*.*')],
                                       initialdir=os.path.dirname(self.base.get()) or self.saida.get())
        if a:
            self.base.set(os.path.normpath(a)); self.acrescentar.set(True)
        self.mostrar_base()

    def mostrar_base(self):
        if not self.acrescentar.get():
            self.lbl_base.configure(text='(desligado: gera o COVERS.BIN completo)'); return
        if not self.base.get():
            self.lbl_base.configure(text='escolha o COVERS.BIN'); return
        b = gcv.ler_base(self.base.get(), open(MODULO[0], 'rb').read() if os.path.exists(MODULO[0]) else None)
        self.lbl_base.configure(text=('não serve: ' + b) if isinstance(b, str) else
                                '%d capa(s) nele: ficam como estão; só as ROMs novas são convertidas' % b['n'])

    def ler_espera(self):
        """Segundos de espera (0 a ESPERA_MAX) ou None se o campo não for um número."""
        try:
            v = float(self.espera.get().replace(',', '.'))
        except ValueError:
            return None
        return v if 0 <= v <= ESPERA_MAX else None

    def trocar_espera(self):
        v = self.ler_espera()
        if v is None: v = ESPERA_PADRAO
        self.espera.set('%.1f' % v)
        self.mostrar_espera()
        self.salvar_prefs()

    def mostrar_espera(self):
        v = self.ler_espera()
        self.lbl_espera.configure(text='Segundos com o cursor parado em cima do nome do jogo' if v is not None
                                  else 'Segundos (de 0 a %.0f)' % ESPERA_MAX)

    def pedir_grande(self, flk, lam=None):
        chave = (self.g_src, self.g_nit, flk, lam if flk else None, self.g_pont)
        if chave in self.cache_g or chave in self.pedidos_g: return
        fut = (self.pool if flk else self.pool_rapido).submit(gcv.previa, *chave)
        self.pedidos_g[chave] = fut
        self.g_t0 = time.time()
        fut.add_done_callback(lambda fu: self.fila.put(('grande', chave, fu)))

    def fim_grande(self, chave, fu):
        if self.pedidos_g.get(chave) is fu: del self.pedidos_g[chave]
        if fu.cancelled(): return
        if fu.exception() is not None:
            self.log.insert('end', 'capa %s: erro no cálculo: %s\n' % (os.path.basename(chave[0]), fu.exception()))
            return
        self.cache_g[chave] = fu.result()
        if chave[:2] == (self.g_src, self.g_nit): self.redesenhar()

    def prev_grande(self, flk=None):
        if flk is None: flk = self.flicker.get()
        return self.cache_g.get((self.g_src, self.g_nit, flk, gcv.LAMBDAS[self.i_lam] if flk else None, self.g_pont))

    def pedir_niveis(self):
        """Com flicker: o nível escolhido primeiro, depois os outros (para a barra responder na hora)."""
        if not self.flicker.get(): return
        for k in sorted(range(len(gcv.LAMBDAS)), key=lambda k: abs(k - self.i_lam)):
            self.pedir_grande(True, gcv.LAMBDAS[k])

    # ------------------------------------------------------------------ nível do flicker (λ)
    def mostrar_lam(self, i=None):
        """Texto e estado da barra (i: posição enquanto arrasta)."""
        if i is None: i = self.i_lam
        flk = self.flicker.get()
        for w in (self.barra_lam,):
            w.state(['!disabled'] if flk else ['disabled'])
        self.b_lam_menos.state(['!disabled'] if flk and i > 0 else ['disabled'])
        self.b_lam_mais.state(['!disabled'] if flk and i < len(gcv.LAMBDAS) - 1 else ['disabled'])
        if not flk:
            self.lbl_lam.configure(text='(ligue o flicker para escolher o nível)'); return
        r = self.cache_g.get((self.g_src, self.g_nit, True, gcv.LAMBDAS[i], self.g_pont))
        prontos = sum(1 for l in gcv.LAMBDAS if (self.g_src, self.g_nit, True, l, self.g_pont) in self.cache_g)
        self.lbl_lam.configure(text='%d/%d · λ %.2f%s · ← mais fiel, treme mais · treme menos →%s' % (
            i + 1, len(gcv.LAMBDAS), gcv.LAMBDAS[i], ' · tremido %.1f' % r['tremido'] if r else ' · calculando… %d%%'
            % (100 * self.prog_g.get((self.g_src, self.g_nit, True, gcv.LAMBDAS[i], self.g_pont), 0.0)),
            '' if prontos == len(gcv.LAMBDAS) else ' (%d/%d níveis prontos)' % (prontos, len(gcv.LAMBDAS))))

    def passo_lam(self, d):
        if isinstance(self.root.focus_get(), (tk.Entry, ttk.Entry, tk.Text, ttk.Spinbox)): return
        self.escolher_lam(max(0, min(len(gcv.LAMBDAS) - 1, self.i_lam + d)))

    def escolher_lam(self, i):
        """Nível escolhido pelo usuário: vale para esta capa e fica salvo (capas_config.json)."""
        if not self.flicker.get(): return
        self.fechar_picker()
        self.i_lam = i
        self.barra_lam.set(i)
        cfg = conv_v3.ler_config(self.capas.get())
        gcv.definir_lambda_grande(cfg, self.capa_teste.get(), gcv.LAMBDAS[i])
        self.salvar_cfg(cfg)
        self.pedir_niveis()
        self.redesenhar()

    def foto_g(self, chave, px):
        z = self.zoom.get()
        k = ('g', chave, z)
        if k not in self.fotos:
            self.fotos[k] = ImageTk.PhotoImage(Image.fromarray(px).resize((gcv.CW * z, gcv.CH * z),
                                                                          Image.Resampling.NEAREST))
        return self.fotos[k]

    def resumo_grande(self):
        """(com flicker, sem) entre as capas que vão para a firmware: com pastas de ROMs, só as associadas a
        alguma ROM; sem, todas as da pasta."""
        cfg = conv_v3.ler_config(self.capas.get())
        nomes = getattr(self, 'nomes_capas', [])
        if self.roms.get(0, 'end') and self.assoc is not None: nomes = [n for n in nomes if n in self.assoc]
        com = sum(1 for n in nomes if gcv.flicker_grande(cfg, n))
        return com, len(nomes) - com

    # ------------------------------------------------------------------ pastas
    def escolher_capas(self):
        d = filedialog.askdirectory(initialdir=self.capas.get() or ROOT, title='Pasta das capas')
        if d:
            self.capas.set(os.path.normpath(d)); self.listar_capas()
            self.procurar_roms()

    def adicionar_roms(self):
        d = filedialog.askdirectory(initialdir=ROOT, title='Pasta de ROMs')
        if d and os.path.normpath(d) not in self.roms.get(0, 'end'):
            self.roms.insert('end', os.path.normpath(d)); self.salvar_prefs()
            self.procurar_roms()

    def remover_roms(self):
        for i in self.roms.curselection()[::-1]: self.roms.delete(i)
        self.salvar_prefs()
        self.procurar_roms()

    def escolher_saida(self):
        d = filedialog.askdirectory(initialdir=ROOT, title='Pasta de saída')
        if d: self.saida.set(os.path.normpath(d))

    def abrir_saida(self):
        d = self.saida.get()
        if os.path.isdir(d): os.startfile(d)

    def listar_capas(self):
        d = self.capas.get()
        nomes = sorted((f for f in os.listdir(d) if f.lower().endswith('.png')), key=str.lower) \
            if os.path.isdir(d) else []
        self.nomes_capas = nomes
        self.nota_novas = ''
        self.miniaturas = {}
        self.imgs_item = {}
        if not hasattr(self, 'mini_vazia'): self.mini_vazia = ImageTk.PhotoImage(Image.new('RGB', (32, 48), PAINEL))
        self.geracao_lista = getattr(self, 'geracao_lista', 0) + 1
        if nomes and self.capa_teste.get() not in nomes:
            pref = [n for n in nomes if n.lower().startswith('super mario bros. 3')]
            self.capa_teste.set(pref[0] if pref else nomes[0])
        self.filtrar_lista()
        self.gerar_miniaturas(nomes, self.geracao_lista)
        if nomes: self.calcular_niveis()

    # ------------------------------------------------------------------ níveis (em segundo plano)
    def calcular_niveis(self):
        """Prévia da capa escolhida (num processo do pool): sem flicker (~1 s) e, se a capa usa, com flicker
        (~1,5 min). Os cálculos de outra capa que nem começaram são cancelados."""
        self.adiado = None
        nome = self.capa_teste.get()
        src = os.path.join(self.capas.get(), nome)
        cfg = conv_v3.ler_config(self.capas.get())
        ligada = conv_v3.nitidez_de(cfg, nome, NITIDEZ_PADRAO)
        nit = conv_v3.forca_de(cfg, nome) if ligada else 0                  # 0 ou a força em %
        self.nitidez.set(ligada)
        self.mostrar_forca(conv_v3.forca_de(cfg, nome), ligada)
        self.mostrar_nitidez_padrao()
        for c, fu in list(self.pedidos_g.items()):
            if c[0] != src: fu.cancel()
        self.flicker.set(gcv.flicker_grande(cfg, nome))
        self.pontilhado.set(gcv.pontilhado_de(cfg, nome))
        self.i_lam = min(range(len(gcv.LAMBDAS)), key=lambda k: abs(gcv.LAMBDAS[k] - gcv.lambda_grande(cfg, nome)))
        self.barra_lam.set(self.i_lam)
        self.fechar_picker()
        self.g_src, self.g_nit, self.g_orig, self.g_pont = src, nit, None, self.pontilhado.get()
        try:
            self.g_orig = stc.carregar(src, gcv.CW, gcv.CH, nit).clip(0, 255).astype('uint8')
        except Exception as ex:
            messagebox.showerror('Capa', 'Não consegui abrir %s:\n%s' % (src, ex)); return
        self.pedir_grande(False)
        self.pedir_niveis()
        self.redesenhar()

    def atualizar_status(self):
        n = sum(1 for c in self.pedidos_g if c[2])
        self.status.configure(text='' if not self.pedidos_g else 'calculando a prévia%s… %d s' % (
            ' (%d nível(is) de flicker)' % n if n else '', time.time() - getattr(self, 'g_t0', time.time())))
        if hasattr(self, 'lbl_lam'): self.mostrar_lam()

    def mostrar_prog_nes(self):
        """Barra de carregamento embaixo da "Capa no NES" enquanto a capa com flicker é calculada."""
        k = self.chave_atual()
        if self.cache_g.get(k) or not self.flicker.get():
            self.barra_nes.pack_forget(); return
        f = self.prog_g.get(k, 0.0)
        self.barra_nes.configure(value=f * 100, length=gcv.CW * self.zoom.get())
        if not self.barra_nes.winfo_ismapped(): self.barra_nes.pack(pady=(6, 0))
        self.telas['nes'].configure(text='calculando a capa com flicker…\n%d%%' % (f * 100))

    def ler_fila(self):
        mudou = False
        try:
            while True:                                        # andamento das prévias (dos processos)
                chave, f = self.fila_prog.get_nowait()
                self.prog_g[chave] = max(f, self.prog_g.get(chave, 0.0))
                mudou = True
        except (queue.Empty, OSError, ValueError, EOFError):
            pass
        if mudou and not self.cache_g.get(self.chave_atual()): self.mostrar_prog_nes()
        try:
            while True:
                msg = self.fila.get_nowait()
                if msg[0] == 'grande':
                    self.fim_grande(*msg[1:])
                elif msg[0] == 'log':
                    self.log.insert('end', msg[1] + '\n'); self.log.see('end')
                elif msg[0] == 'prog':
                    self.prog.configure(maximum=msg[2], value=msg[1])
                elif msg[0] == 'fim':
                    self.fim_geracao(*msg[1:])
                elif msg[0] == 'roms':
                    self.fim_roms(*msg[1:])
                elif msg[0] == 'copia':
                    self.b_copiar.state(['!disabled'])
                    self.log.insert('end', '\n' + msg[2] + '\n'); self.log.see('end')
                    (messagebox.showinfo if msg[1] else messagebox.showerror)('Cartão SD', msg[2])
        except queue.Empty:
            pass
        self.root.after(50, self.ler_fila)

    def trocar_flicker(self):
        """Flicker nos sprites desta capa (salvo em capas_config.json, "flicker_grande")."""
        cfg = conv_v3.ler_config(self.capas.get())
        gcv.definir_flicker_grande(cfg, self.capa_teste.get(), self.flicker.get())
        self.salvar_cfg(cfg)
        self.pedir_niveis()
        self.redesenhar()

    def salvar_cfg(self, cfg):
        try:
            conv_v3.salvar_config(self.capas.get(), cfg)
        except OSError as ex:
            messagebox.showerror('Configuração', 'Não consegui salvar a configuração:\n%s' % ex)
        self.filtrar_lista()
        self.atualizar_info()

    def definir_padrao(self):
        """Com ou sem flicker (e o nível), como nesta capa, vira o padrão das capas sem ajuste próprio."""
        cfg = conv_v3.ler_config(self.capas.get())
        cfg['flicker_grande_padrao'] = bool(self.flicker.get())
        if self.flicker.get(): cfg['flicker_grande_lambda_padrao'] = gcv.LAMBDAS[self.i_lam]
        gcv.definir_flicker_grande(cfg, self.capa_teste.get(), None)
        gcv.definir_lambda_grande(cfg, self.capa_teste.get(), None)
        self.salvar_cfg(cfg)

    def usar_padrao(self):
        """Tira o ajuste desta capa: ela volta a usar o padrão."""
        cfg = conv_v3.ler_config(self.capas.get())
        gcv.definir_flicker_grande(cfg, self.capa_teste.get(), None)
        gcv.definir_lambda_grande(cfg, self.capa_teste.get(), None)
        self.salvar_cfg(cfg)
        self.flicker.set(gcv.flicker_grande(cfg, self.capa_teste.get()))
        self.i_lam = min(range(len(gcv.LAMBDAS)),
                         key=lambda k: abs(gcv.LAMBDAS[k] - gcv.lambda_grande(cfg, self.capa_teste.get())))
        self.barra_lam.set(self.i_lam)
        self.pedir_niveis()
        self.redesenhar()

    def atualizar_info(self):
        self.atualizar_status()
        flk = self.flicker.get()
        r = self.prev_grande()
        s = 'Capa 112×160 · %s' % ('com flicker nos sprites' if flk else 'sem flicker')
        if flk: s += ' (λ %.2f)' % gcv.LAMBDAS[self.i_lam]
        if self.g_pont: s += ' · pontilhado'
        if r:
            s += ' · ΔE %.1f · %d sprites' % (r['erro'], r['sprites'])
            if flk: s += ' · tremido %.1f' % r['tremido']
            orig, atual = self.pals_de(self.chave_atual())
            if atual['c3'] != 0x28: s += ' · usa a cor livre da paleta 3 (%s)' % hex2(atual['c3'])
            if atual != orig: s += ' · cores editadas'
        else: s += ' · calculando…'
        self.info.configure(text=s)
        cfg = conv_v3.ler_config(self.capas.get())
        nome = self.capa_teste.get()
        texto = lambda f, l: 'com flicker (λ %.2f)' % l if f else 'sem flicker'
        padrao = texto(cfg.get('flicker_grande_padrao', False),
                       float(cfg.get('flicker_grande_lambda_padrao', gcv.LAMBDA_PADRAO)))
        proprio = nome in cfg.get('flicker_grande', {}) or nome in cfg.get('flicker_grande_lambda', {})
        if proprio:
            self.lbl_capa_flk.configure(text='Esta capa: %s (ajuste próprio) · padrão das outras: %s'
                                        % (texto(flk, gcv.LAMBDAS[self.i_lam]), padrao))
        else:
            self.lbl_capa_flk.configure(text='Esta capa usa o padrão: %s' % padrao)
        self.b_usar_padrao.state(['!disabled'] if proprio else ['disabled'])
        self.mostrar_lam()
        com, sem = self.resumo_grande()
        txt = '%d com flicker · %d sem' % (com, sem) if com else 'nenhuma com flicker'
        if self.roms.get(0, 'end') and self.assoc is not None:
            txt = '%d capas p/ %d ROMs · %s' % (com + sem, sum(len(v) for v in self.assoc.values()), txt)
        self.b_gerar.configure(text='GERAR FIRMWARE (%s)' % txt)
        self.b_gerar.state(['disabled'] if self.gerando else ['!disabled'])

    def vazio(self):
        """Quadro preto do tamanho da capa (a área não muda de tamanho enquanto calcula)."""
        z = self.zoom.get()
        k = ('vazio', z)
        if k not in self.fotos:
            self.fotos[k] = ImageTk.PhotoImage(Image.new('RGB', (gcv.CW * z, gcv.CH * z)))
        return self.fotos[k]

    def redesenhar(self):
        self.atualizar_info()
        if self.g_orig is not None:
            self.telas['orig'].configure(image=self.foto_g(('orig', self.g_src, self.g_nit), self.g_orig), text='')
        cs = (self.g_src, self.g_nit, False, None, self.g_pont)
        if self.cache_g.get(cs):
            self.telas['v2'].configure(image=self.foto_g(cs + ('P', self.ver_ed.get(cs, 0)), self.imagens(cs)[2]),
                                       text='')
        else: self.telas['v2'].configure(image=self.vazio(), text='calculando…')
        self.desenhar_paletas()
        k = self.chave_atual()
        r = self.cache_g.get(k)
        if not r:
            self.atual = None
            self.telas['nes'].configure(image=self.vazio(), text='calculando…')
            self.mostrar_prog_nes()
            return
        self.barra_nes.pack_forget()
        A, B, P = self.imagens(k)
        v = self.ver_ed.get(k, 0)
        P = self.foto_g(k + ('P', v), P)
        self.atual = dict(A=self.foto_g(k + ('A', v), A), B=self.foto_g(k + ('B', v), B), P=P) \
            if r['flicker'] else dict(A=P, B=P, P=P)

    # ------------------------------------------------------------------ cores (conta-gotas, como no Palette Lab)
    def chave_atual(self):
        flk = self.flicker.get()
        return (self.g_src, self.g_nit, flk, gcv.LAMBDAS[self.i_lam] if flk else None, self.g_pont)

    def pals_de(self, chave):
        """(originais, atuais) das paletas da capa nessa configuração, ou (None, None) enquanto calcula."""
        r = self.cache_g.get(chave)
        if not r: return None, None
        if chave not in self.eds:
            self.eds[chave] = CC.ler(self.arq_ed(chave), r['orig']) or CC.copia(r['orig'])
        return r['orig'], self.eds[chave]

    def arq_ed(self, chave):
        return CC.arquivo(self.capas.get(), chave[0], chave[1], chave[2], chave[3] or gcv.LAMBDA_PADRAO, chave[4])

    def imagens(self, chave):
        """(A, B, P) RGB da capa com as cores editadas (as da conversão, se não há edição)."""
        r = self.cache_g[chave]
        orig, atual = self.pals_de(chave)
        if atual == orig: return r['A'], r['B'], r['P']
        v = self.ver_ed.get(chave, 0)
        if self.imgs_ed.get(chave, (None,))[0] != v: self.imgs_ed[chave] = (v, CC.renderizar(r['est'], atual))
        return self.imgs_ed[chave][1]

    def desenhar_paletas(self):
        for w in self.pal_frame.winfo_children(): w.destroy()
        orig, atual = self.pals_de(self.chave_atual())
        if not atual:
            tk.Label(self.pal_frame, text='calculando…', bg=PAINEL, fg=APAGADO, font=('Segoe UI', 9)).pack(anchor='w')
            self.b_desfazer.state(['disabled']); self.b_restaurar.state(['disabled'])
            return

        def linha(titulo, espacos):
            row = tk.Frame(self.pal_frame, bg=PAINEL); row.pack(anchor='w')
            tk.Label(row, text=titulo, bg=PAINEL, fg=TEXTO, font=('Consolas', 8), width=9, anchor='w').pack(side='left')
            for e in espacos:
                if isinstance(e, int):                                   # cor fixa da firmware
                    tk.Label(row, text=hex2(e)[1:], width=3, bg=cor_nes(e), fg='#5a5249', font=('Consolas', 7),
                             highlightthickness=1, highlightbackground=PAINEL).pack(side='left', padx=1)
                elif e is None:                                          # sprite: transparente
                    tk.Label(row, text='··', width=3, bg=PAINEL, fg=APAGADO, font=('Consolas', 7),
                             highlightthickness=1, highlightbackground=PAINEL).pack(side='left', padx=1)
                else:
                    i = CC.cor(atual, e)
                    sw = tk.Label(row, text=hex2(i)[1:], width=3, bg=cor_nes(i), fg=texto_sobre(i),
                                  font=('Consolas', 7, 'bold'), cursor='hand2', highlightthickness=2,
                                  highlightbackground=OURO if i != CC.cor(orig, e) else PAINEL)
                    sw.pack(side='left', padx=1)
                    sw.slot = e
                    sw.bind('<Button-1>', lambda ev, a=e: self.abrir_picker([a]))
        tk.Label(self.pal_frame, text='Fundo', bg=PAINEL, fg=APAGADO, font=('Segoe UI', 8, 'bold')).pack(anchor='w')
        for p in range(2): linha('Fundo %d' % (p + 1), [0x0F] + [('bg', p, s) for s in range(3)])
        linha('Barra', [0x0F, 0x30, 0x00, ('c3',)])
        flk = self.flicker.get()
        for q in ('A', 'B') if flk else ('A',):
            tk.Label(self.pal_frame, text='Sprites · quadro %s' % q if flk else 'Sprites', bg=PAINEL, fg=APAGADO,
                     font=('Segoe UI', 8, 'bold')).pack(anchor='w', pady=(6, 0))
            for k in range(4): linha('Sprite %d' % k, [None] + [('sp', q, k, s) for s in range(3)])
        chave = self.chave_atual()
        self.b_restaurar.state(['!disabled'] if atual != orig else ['disabled'])
        self.b_desfazer.state(['!disabled'] if any(c == chave for c, _ in self.desfazer) else ['disabled'])

    def pixel(self, e):
        z = self.zoom.get()
        w = self.telas['nes']
        x0 = (w.winfo_width() - gcv.CW * z) // 2; y0 = (w.winfo_height() - gcv.CH * z) // 2
        x, y = (e.x - x0) // z, (e.y - y0) // z
        return (x, y) if 0 <= x < gcv.CW and 0 <= y < gcv.CH else None

    def espacos_pixel(self, e):
        """((x, y), [(quadro, espaço ou texto da cor fixa)]) do ponto sob o mouse, ou None."""
        k = self.chave_atual()
        r = self.cache_g.get(k)
        if not r or not self.atual: return None
        _, atual = self.pals_de(k)
        xy = self.pixel(e)
        if not xy: return None
        return xy, [(q, CC.espaco(r['est'], atual, q, *xy)) for q in (('A', 'B') if r['flicker'] else ('A',))]

    def sobre_capa(self, e):
        rr = self.espacos_pixel(e)
        if not rr: self.dica.configure(text=self.dica_padrao); return
        (x, y), sps = rr
        _, atual = self.pals_de(self.chave_atual())
        partes = [('quadro %s: ' % q if len(sps) > 1 else '') +
                  ('cor fixa ' + sp if isinstance(sp, str) else '%s = %s' % (CC.nome(sp), hex2(CC.cor(atual, sp))))
                  for q, sp in sps]
        livre = any(not isinstance(sp, str) for _, sp in sps)
        self.dica.configure(text='(%d,%d) · %s — %s' % (x, y, ' · '.join(partes), 'clique para trocar' if livre
                                                          else 'cor da firmware: não dá para trocar'))

    def conta_gotas(self, e):
        rr = self.espacos_pixel(e)
        if not rr: return
        alvos = []
        for _, sp in rr[1]:
            if not isinstance(sp, str) and sp not in alvos: alvos.append(sp)
        if not alvos: return
        for sp in alvos: self.piscar(sp)
        self.abrir_picker(alvos)

    def piscar(self, sp, n=6):
        sw = next((w for row in self.pal_frame.winfo_children() for w in row.winfo_children()
                   if getattr(w, 'slot', None) == sp), None)
        if sw is None: return
        normal = sw.cget('highlightbackground')

        def blink(k):
            if not sw.winfo_exists(): return
            sw.configure(highlightbackground=(VERMELHO if k % 2 == 0 else normal) if k < n else normal)
            if k < n: self.root.after(160, blink, k + 1)
        blink(0)

    def nome_alvo(self, sp):
        return ('quadro %s · ' % sp[1] if sp[0] == 'sp' and self.flicker.get() else '') + CC.nome(sp)

    def abrir_picker(self, alvos):
        """Seletor das 64 cores do NES. alvos = espaços a trocar (2 quando o ponto muda entre os quadros A e B)."""
        orig, atual = self.pals_de(self.chave_atual())
        if not atual: return
        self.fechar_picker()
        win = tk.Toplevel(self.root); win.configure(bg=PAINEL); win.transient(self.root); win.resizable(False, False)
        win.title('Trocar cor')
        self.picker = win
        win.bind('<Escape>', lambda e: self.fechar_picker())
        escolha = tk.IntVar(value=3)                                  # 1 = só o 1º, 2 = só o 2º, 3 = os dois
        if len(alvos) == 2:
            tk.Label(win, text='Trocar em:', bg=PAINEL, fg=OURO, font=('Segoe UI', 9, 'bold')).pack(pady=(10, 2))
            for v, t in ((3, 'os dois (a cor que a TV mostra)'), (1, 'só ' + self.nome_alvo(alvos[0])),
                         (2, 'só ' + self.nome_alvo(alvos[1]))):
                ttk.Radiobutton(win, text=t, value=v, variable=escolha, style='Painel.TRadiobutton').pack(anchor='w', padx=14)
        else:
            tk.Label(win, text=self.nome_alvo(alvos[0]), bg=PAINEL, fg=OURO,
                     font=('Segoe UI', 9, 'bold')).pack(pady=(10, 2))

        def selecionados():
            return alvos if len(alvos) == 1 else {1: alvos[:1], 2: alvos[1:], 3: alvos}[escolha.get()]
        atuais = {CC.cor(atual, a) for a in alvos}
        hexl = tk.Label(win, text='', bg=PAINEL, fg=TEXTO, font=('Consolas', 9)); hexl.pack()
        grade = tk.Frame(win, bg=PAINEL, padx=10, pady=8); grade.pack()
        for i in range(64):
            proibida = i in FORBIDDEN
            c = tk.Label(grade, width=3, height=1, bg=cor_nes(i), fg=texto_sobre(i), font=('Consolas', 8),
                         text='·' if proibida else '', highlightthickness=2,
                         highlightbackground=OURO if i in atuais else PAINEL, cursor='arrow' if proibida else 'hand2')
            c.grid(row=i // 16, column=i % 16, padx=1, pady=1)
            if proibida:
                c.bind('<Enter>', lambda e, i=i: hexl.configure(text=hex2(i) + ' — não usável'))
            else:
                c.bind('<Enter>', lambda e, i=i: hexl.configure(text=hex2(i)))
                c.bind('<Button-1>', lambda e, i=i: self.trocar_cor(selecionados(), i))
        bb = tk.Frame(win, bg=PAINEL); bb.pack(pady=(0, 10))
        ttk.Button(bb, text='Original', command=lambda: self.trocar_cor(selecionados(), None)).pack(side='left', padx=4)
        ttk.Button(bb, text='Cancelar', command=self.fechar_picker).pack(side='left', padx=4)
        self.posicionar(win)

    def fechar_picker(self):
        if self.picker:
            self.picker.destroy(); self.picker = None

    def trocar_cor(self, alvos, i):
        """Troca a cor dos espaços (i = None: volta à original) e salva a edição."""
        self.fechar_picker()
        chave = self.chave_atual()
        orig, atual = self.pals_de(chave)
        self.desfazer.append((chave, CC.copia(atual)))
        for a in alvos: CC.definir(atual, a, CC.cor(orig, a) if i is None else i, chave[2])
        self.salvar_ed(chave)

    def salvar_ed(self, chave):
        orig, atual = self.pals_de(chave)
        try:
            CC.salvar(self.arq_ed(chave), orig, atual)
        except OSError as ex:
            messagebox.showerror('Cores', 'Não consegui salvar as cores editadas:\n%s' % ex)
        self.ver_ed[chave] = self.ver_ed.get(chave, 0) + 1
        self.filtrar_lista()
        self.redesenhar()

    def desfazer_cor(self):
        chave = self.chave_atual()
        for k in range(len(self.desfazer) - 1, -1, -1):
            if self.desfazer[k][0] == chave:
                self.eds[chave] = self.desfazer.pop(k)[1]
                self.salvar_ed(chave); return

    def restaurar_cores(self):
        chave = self.chave_atual()
        orig, atual = self.pals_de(chave)
        if not atual or atual == orig: return
        self.desfazer.append((chave, CC.copia(atual)))
        self.eds[chave] = CC.copia(orig)
        self.salvar_ed(chave)

    def posicionar(self, win):
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x = min(self.root.winfo_pointerx() + 16, win.winfo_screenwidth() - w - 8)
        y = min(self.root.winfo_pointery() + 16, win.winfo_screenheight() - h - 48)
        win.geometry('+%d+%d' % (max(0, x), max(0, y)))

    def animar(self):
        """Alternância A/B sincronizada com o monitor (vsync do Windows, DwmFlush), como no NES:
        num monitor de 60 Hz troca a cada atualização da tela; em 120/144 Hz troca a cada 1/60 s."""
        info = None
        if self.dwm:
            try:
                self.dwm.DwmFlush()
                info = vsync_info(self.dwm)
            except Exception:
                self.dwm = None
        agora = time.perf_counter()
        if info:
            n, self.hz = info
            if self.ult_vsync is not None and n - self.ult_vsync > 1: self.vsync_perdidos += n - self.ult_vsync - 1
            self.ult_vsync = n
        if info and 55 <= self.hz <= 65:
            self.quadro = n & 1                                      # 60 Hz: quadro do NES = paridade do vsync
        else:
            self.quadro = int(agora * 60) & 1
        f = getattr(self, 'atual', None)
        if f:
            m = self.modo.get()
            self.telas['nes'].configure(image=(f['B'] if self.quadro else f['A']) if m == 'alt' else f[m], text='')
            self.root.update_idletasks()                             # desenha já, antes do próximo vsync
        self.root.after(1, self.animar)

    # ------------------------------------------------------------------ gerar
    def gerar(self):
        """Firmware v10: OS.BIN de referência com a espera escolhida + COVERS.BIN do gerar_covers_v10."""
        pastas = list(self.roms.get(0, 'end'))
        if pastas:                                      # associação de agora (ROMs podem ter mudado no cartão)
            roms_ = associar_roms.listar_roms(pastas)
            self.guardar_assoc(roms_, associar_roms.associar(roms_, list(self.nomes_capas)), pastas)
            self.mostrar_so_rom(); self.filtrar_lista()
            if not self.assoc:
                messagebox.showerror('Gerar', 'Nenhuma ROM das pastas de ROMs ganhou capa%s.\n\n%s' % (
                    self.aviso_pastas, 'O cartão SD está conectado?' if self.aviso_pastas else
                    'Confira a pasta das capas e as pastas de ROMs.'))
                self.atualizar_info(); return
        capas = self.capas.get().strip()
        roms = list(self.roms.get(0, 'end'))
        saida = self.saida.get().strip()
        if not os.path.isdir(capas):
            messagebox.showerror('Gerar', 'Escolha a pasta das capas.'); return
        if not saida:
            messagebox.showerror('Gerar', 'Escolha a pasta de saída.'); return
        espera = self.ler_espera()
        if espera is None:
            messagebox.showerror('Gerar', 'A espera antes de carregar tem que ser um número de 0 a %.0f segundos.'
                                 % ESPERA_MAX); return
        quadros = int(round(espera * 60))
        edfc = os.path.join(saida, 'EDFC')
        self.salvar_prefs()
        if any(os.path.exists(os.path.join(edfc, f)) for f in ('OS.BIN', 'COVERS.BIN')):
            if not messagebox.askyesno('Gerar', 'Já existe firmware em\n%s\n\nSubstituir OS.BIN e COVERS.BIN?' % edfc):
                return
        refs = []
        for arq, sha in (FIRMWARE, MODULO):
            b = open(arq, 'rb').read() if os.path.exists(arq) else b''
            if hashlib.sha1(b).hexdigest() != sha:
                messagebox.showerror('Gerar', 'A firmware de referência não confere:\n%s\n(esperado SHA-1 %s…)'
                                     % (arq, sha[:8])); return
            refs.append(b)
        buf = bytearray(refs[0])
        assert buf[ESPQ] == 31, 'byte da espera fora do lugar'
        buf[ESPQ] = quadros + 1
        base, mantidas, total = None, None, self.contar(capas, roms)
        if self.acrescentar.get():
            if not self.base.get():
                messagebox.showerror('Gerar', 'Escolha o COVERS.BIN existente (ou desligue "Só acrescentar").'); return
            b = gcv.ler_base(self.base.get(), refs[1])
            if isinstance(b, str):
                messagebox.showerror('Gerar', 'Esse COVERS.BIN não serve para acrescentar:\n%s' % b); return
            if roms and self.assoc is not None:
                todas = [r for v in self.assoc.values() for r, _ in v]
                total = sum(1 for r in todas if name_crc(r) not in b['crcs'])
                if not total:
                    messagebox.showinfo('Gerar', 'Todas as %d ROMs com capa já estão nesse COVERS.BIN: não há nada '
                                        'novo para acrescentar.' % len(todas)); return
            if not messagebox.askyesno('Acrescentar capas', 'O COVERS.BIN escolhido tem %d capa(s): elas ficam '
                                       'exatamente como estão.\n\nSerão convertidas e acrescentadas só as ROMs '
                                       'novas%s.\n\nUma cópia do COVERS.BIN de antes fica em\n%s\n\nContinuar?'
                                       % (b['n'], ' (%d)' % total if roms and self.assoc is not None else '',
                                          os.path.join(saida, 'COVERS_anterior.BIN'))):
                return
            base, mantidas = os.path.join(saida, 'COVERS_anterior.BIN'), b['n']
            os.makedirs(saida, exist_ok=True)
            if os.path.normcase(os.path.abspath(self.base.get())) != os.path.normcase(os.path.abspath(base)):
                shutil.copyfile(self.base.get(), base)              # cópia (e o gerador lê dela: a saída é refeita)
        cmd = [capas]                                           # argumentos do gerar_covers_v10
        if base: cmd += ['--base', base]
        for r in roms: cmd += ['--roms', r]
        cmd += ['--nitidez', 'sim' if NITIDEZ_PADRAO else 'nao', '--modulo', MODULO[0],
                '--jobs', str(max(1, (os.cpu_count() or 2) - 1)),
                '-o', os.path.join(edfc, 'COVERS.BIN'), '--preview', os.path.join(saida, 'previews')]
        com, sem = self.resumo_grande()
        self.gerando = True
        self.atualizar_info()
        self.log.delete('1.0', 'end')
        self.prog.configure(value=0, maximum=max(1, total))
        desc = ('Capa grande (v15): %d capa(s) com flicker nos sprites, %d sem · espera de %.1f s (%d quadros) '
                'com o cursor parado antes de carregar' % (com, sem, espera, quadros))
        if mantidas is not None:
            desc = ('Só acrescentando: %d capa(s) do COVERS.BIN anterior mantidas como estão · espera de %.1f s'
                    % (mantidas, espera))
        fmt = ('v15 — capa grande 112x160 ao lado da lista (20 jogos por página, "@tavinho.games" embaixo da capa); '
               'espera de %.1f s com o cursor parado antes de carregar; qualquer botão cancela a carga' % espera)
        dica = ('Se uma capa com flicker tremer demais na sua TV, desligue o flicker dela e gere de novo. '
                'A espera muda no campo "Espera antes de carregar a capa".')
        conv = ('Convertendo as capas (sem flicker ~1 s cada; com flicker ~1,5 min cada, essas primeiro, '
                'em paralelo)…')
        sd = self.unidade.get().strip()                         # lido aqui: a thread não pode tocar na janela
        threading.Thread(target=self.rodar, args=(cmd, bytes(buf), edfc, saida, desc, fmt, dica, conv, total, sd,
                                                  mantidas), daemon=True).start()

    def contar(self, capas, roms):
        if roms and self.assoc is not None:                 # gerar() acabou de refazer a associação
            return sum(len(v) for v in self.assoc.values())
        return len([f for f in os.listdir(capas) if f.lower().endswith('.png')]) if os.path.isdir(capas) else 0

    def rodar(self, cmd, buf, edfc, saida, desc, fmt, dica, conv, total, sd='', mantidas=None):
        put = self.fila.put
        try:
            os.makedirs(edfc, exist_ok=True)
            if os.path.exists(os.path.join(edfc, 'COVERS.BIN')): os.remove(os.path.join(edfc, 'COVERS.BIN'))
            prev = os.path.join(saida, 'previews')                 # prévias da geração anterior saem
            if os.path.isdir(prev) and mantidas is None:           # (acrescentando: as anteriores ficam)
                for f in os.listdir(prev):
                    if f.lower().endswith('.png'): os.remove(os.path.join(prev, f))
            put(('log', desc))
            put(('log', conv))
            codigo = []
            feitas = 0
            sem_rom, incluidas, sem_capa = [], [], ''
            for linha in linhas_gerador(cmd, codigo):
                linha = linha.rstrip()
                if linha[:5].strip().isdigit():
                    feitas += 1; put(('prog', feitas, max(total, feitas)))
                    incluidas.append(linha[17:])
                if linha.startswith('AVISO: sem ROM correspondente: '): sem_rom.append(linha[31:])
                if re.match(r'AVISO: \d+ de \d+ ROMs sem capa', linha): sem_capa = linha[7:].split(':')[0]
                put(('log', linha))
            if codigo[0] != 0:
                put(('fim', False, 'O gerador de capas falhou (código %s). Veja o log.' % codigo[0])); return
            os_bin = os.path.join(edfc, 'OS.BIN')
            open(os_bin, 'wb').write(buf)
            cov = os.path.join(edfc, 'COVERS.BIN')
            h_os = hashlib.sha1(buf).hexdigest()
            h_cov = hashlib.sha1(open(cov, 'rb').read()).hexdigest()
            open(os.path.join(saida, 'LEIA-ME.txt'), 'w', encoding='utf-8').write(
                'Firmware EDFC com capas — gerada pelo gerador_firmware_capas.py em %s\n\n'
                '%s\nFormato: %s\n\n'
                'Instalar: copie EDFC\\OS.BIN e EDFC\\COVERS.BIN para /EDFC/ no cartão SD\n'
                '(apague o COVERS.BIN antigo antes). O COVERS.BIN só funciona com este OS.BIN.\n\n'
                '%s\n\n'
                'SHA-1\n  OS.BIN      %s\n  COVERS.BIN  %s\n'
                % (time.strftime('%d/%m/%Y %H:%M'), desc, fmt, dica, h_os, h_cov))
            pronto = ('%d capas no COVERS.BIN' % len(incluidas) if mantidas is None else
                      '%d capa(s) nova(s) acrescentada(s); %d mantidas como estavam' % (len(incluidas), mantidas))
            msg = 'Pronto! %s.\n\n%s\n\nArquivos gerados:\n  %s\n  %s' % (pronto, desc, os_bin, cov)
            if sem_rom:
                msg += ('\n\nATENÇÃO: %d imagem(ns) ficaram de fora porque nenhuma ROM das pastas de ROMs parece '
                        'com elas:\n  %s\n\nAdicione a pasta onde estão essas ROMs (pode ser a do cartão SD) em '
                        '"Pastas de ROMs" e gere de novo.' % (len(sem_rom), '\n  '.join(sem_rom[:15]) +
                                                              ('\n  …' if len(sem_rom) > 15 else '')))
            if sem_capa:
                msg += '\n\n%s (veja no botão "Mostrar só capas das minhas ROMs").' % sem_capa
            if sd:
                put(('log', 'Copiando para o cartão SD (%s)…' % copiar_sd.pasta_edfc(sd)))
                try:
                    ok_sd, msg_sd = copiar_sd.copiar(saida, sd)
                except Exception as ex:
                    ok_sd, msg_sd = False, 'Erro ao copiar para o cartão: %s' % ex
                msg += '\n\nCARTÃO SD: ' + msg_sd
                if not ok_sd:
                    put(('fim', 'aviso', msg)); return
            put(('fim', True, msg))
        except Exception as ex:
            put(('fim', False, 'Erro: %s' % ex))

    def fim_geracao(self, ok, msg):
        self.gerando = False
        self.atualizar_info()
        self.log.insert('end', '\n' + msg + '\n'); self.log.see('end')
        mostrar = {True: messagebox.showinfo, 'aviso': messagebox.showwarning}.get(ok, messagebox.showerror)
        mostrar('Gerar firmware', msg)

    # ------------------------------------------------------------------ cartão SD
    def escolher_sd(self):
        """O caminho do cartão: a raiz (F:\\) ou a pasta EDFC dele."""
        d = filedialog.askdirectory(title='Cartão SD do EverDrive (a raiz do cartão ou a pasta EDFC)')
        if not d: return
        if not os.path.isdir(copiar_sd.pasta_edfc(d)):
            messagebox.showerror('Cartão SD', 'Não achei a pasta EDFC em %s.\nEscolha a raiz do cartão do EverDrive '
                                 '(ou a pasta EDFC dele).' % os.path.normpath(d))
            return
        self.unidade.set(os.path.normpath(d))
        self.salvar_prefs()

    def copiar_para_sd(self):
        un = self.unidade.get().strip()
        if not un:
            messagebox.showerror('Cartão SD', 'Adicione o caminho do cartão SD primeiro ("Adicionar caminho…").')
            return
        saida = self.saida.get().strip()
        if not os.path.exists(os.path.join(saida, 'EDFC', 'COVERS.BIN')):
            messagebox.showerror('Cartão SD', 'Gere a firmware primeiro (não achei %s).' % os.path.join(saida, 'EDFC'))
            return
        if not messagebox.askyesno('Cartão SD', 'Copiar OS.BIN e COVERS.BIN de\n%s\npara %s (substituindo os de lá)?'
                                   % (os.path.join(saida, 'EDFC'), copiar_sd.pasta_edfc(un))):
            return
        self.salvar_prefs()
        self.b_copiar.state(['disabled'])

        def rodar():
            try:
                ok, msg = copiar_sd.copiar(saida, un)
            except Exception as ex:
                ok, msg = False, 'Erro ao copiar: %s' % ex
            self.fila.put(('copia', ok, msg))
        threading.Thread(target=rodar, daemon=True).start()

    # ------------------------------------------------------------------ configurações lembradas
    def ler_prefs(self):
        """Pastas e opções da última vez (na primeira vez: as pastas de exemplo do projeto)."""
        try:
            d = json.load(open(ARQ_PREFS, encoding='utf-8'))
        except (OSError, ValueError):
            d = None
        if d is None:
            for p in ('super mario', '001-200'):
                if os.path.isdir(os.path.join(ROOT, p)): self.roms.insert('end', os.path.join(ROOT, p))
            return
        if d.get('capas'): self.capas.set(d['capas'])
        if d.get('saida'): self.saida.set(d['saida'])
        for r in d.get('roms', []): self.roms.insert('end', r)
        if d.get('unidade'): self.unidade.set(d['unidade'])
        self.so_rom = bool(d.get('so_rom')) and bool(d.get('roms'))
        if isinstance(d.get('espera'), (int, float)) and 0 <= d['espera'] <= ESPERA_MAX:
            self.espera.set('%.1f' % d['espera'])

    def salvar_prefs(self):
        d = dict(capas=self.capas.get(), saida=self.saida.get(), roms=list(self.roms.get(0, 'end')),
                 unidade=self.unidade.get(), so_rom=self.so_rom,
                 espera=self.ler_espera() if self.ler_espera() is not None else ESPERA_PADRAO)
        try:
            os.makedirs(os.path.dirname(ARQ_PREFS), exist_ok=True)
            with open(ARQ_PREFS, 'w', encoding='utf-8') as f: json.dump(d, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def fechar(self):
        self.salvar_prefs()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.pool_rapido.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def area_util():
    """(x, y, largura, altura) da área da tela sem a barra de tarefas (Windows); senão, a tela toda."""
    try:
        from ctypes import wintypes
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):     # SPI_GETWORKAREA
            return r.left, r.top, r.right - r.left, r.bottom - r.top
    except Exception:
        pass
    return None


def posicionar_janela(root):
    """Abre a janela no topo da área útil, sem passar da barra de tarefas (o rodapé da lista fica visível)."""
    root.update_idletasks()
    a = area_util()
    if not a: return
    x0, y0, aw, ah = a
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    borda = 40                                          # barra de título e moldura da janela
    h = min(h, ah - borda)
    x = x0 + max(0, (aw - w) // 2)
    root.geometry('%dx%d+%d+%d' % (w, h, x, y0))


def _gerador_processo(args, fila):
    """Roda o gerar_covers_v10 neste processo e manda cada linha da saída pela fila (no .exe não há python para
    chamá-lo como programa separado)."""
    import io

    class Linhas(io.TextIOBase):
        def __init__(self): self.resto = ''
        def writable(self): return True

        def write(self, t):
            self.resto += t
            while '\n' in self.resto:
                linha, self.resto = self.resto.split('\n', 1)
                fila.put(('linha', linha))
            return len(t)
    sys.stdout = sys.stderr = Linhas()
    sys.argv = ['gerar_covers_v10.py'] + list(args)
    codigo = 0
    try:
        gcv.main()
    except SystemExit as ex:
        if isinstance(ex.code, int): codigo = ex.code
        elif ex.code: print(ex.code); codigo = 1
    except Exception:
        traceback.print_exc(); codigo = 1
    if sys.stdout.resto: fila.put(('linha', sys.stdout.resto))
    fila.put(('fim', codigo))


def linhas_gerador(args, codigo):
    """As linhas da saída do gerador de capas, enquanto ele roda; no fim põe o código de saída em codigo[0].
    Em desenvolvimento: `python gerar_covers_v10.py` (como sempre); no .exe (ou com GERADOR_EM_PROCESSO=1): um
    processo do multiprocessing com o próprio programa."""
    if not CONGELADO and not os.environ.get('GERADOR_EM_PROCESSO'):
        p = subprocess.Popen([sys.executable, '-u', os.path.join(AQUI, 'gerar_covers_v10.py')] + list(args),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                             errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for linha in p.stdout: yield linha
        codigo.append(p.wait()); return
    import multiprocessing
    fila = multiprocessing.Queue()
    pr = multiprocessing.Process(target=_gerador_processo, args=(list(args), fila))
    pr.start()
    while True:
        try:
            tipo, v = fila.get(timeout=1)
        except queue.Empty:
            if not pr.is_alive():
                codigo.append(pr.exitcode or 1); return
            continue
        if tipo == 'linha':
            yield v
        else:
            pr.join(); codigo.append(v); return


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(os.path.join(AQUI, 'icone.ico'))   # o console NES: na barra de título e na de tarefas
    except tk.TclError:
        pass
    root.minsize(1160, 760)
    try:
        app = App(root)
    except Exception:
        messagebox.showerror(TITULO, traceback.format_exc())
        raise
    posicionar_janela(root)
    def hz():
        app.atualizar_status()                              # segundos da prévia em cálculo
        root.after(1000, hz)
    hz()
    root.mainloop()


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()                       # .exe: os processos filhos rodam o próprio programa
    if len(sys.argv) > 1 and sys.argv[1] == '--gerar-covers':  # (o gerador sem janela: para testar o .exe)
        if sys.stdout is None: sys.stdout = sys.stderr = open(os.devnull, 'w')
        sys.argv = ['gerar_covers_v10.py'] + sys.argv[2:]
        gcv.main()
        sys.exit(0)
    if len(sys.argv) > 2 and sys.argv[1] == '--testar-geracao':  # (teste do .exe: o caminho que a janela usa)
        log, codigo = open(sys.argv[2], 'w', encoding='utf-8'), []
        for linha in linhas_gerador(sys.argv[3:], codigo): log.write(linha.rstrip('\n') + '\n'); log.flush()
        log.write('CODIGO %s\n' % codigo[0]); log.close()
        sys.exit(0)
    main()
