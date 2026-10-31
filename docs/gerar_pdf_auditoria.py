"""Gera docs/AUDITORIA-DESENVOLVEDOR.pdf a partir de docs/AUDITORIA-DESENVOLVEDOR.md (+ apêndices).

Apêndice A: tabela de símbolos da firmware v15 (montada na hora pelo build_capas_v15, se o OS original estiver em
firmware_base/EDFC/OS.BIN; senão usa docs/simbolos_v15.json). Apêndice B: NOTAS-TECNICAS-FIRMWARE.md inteiro.

uso: python docs/gerar_pdf_auditoria.py        requer: pip install reportlab
"""
import json, os, re, sys
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, Preformatted, KeepTogether)
from reportlab.platypus.tableofcontents import TableOfContents

DOCS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DOCS)
FONTES = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
pdfmetrics.registerFont(TTFont('Corpo', os.path.join(FONTES, 'arial.ttf')))
pdfmetrics.registerFont(TTFont('Corpo-B', os.path.join(FONTES, 'arialbd.ttf')))
pdfmetrics.registerFont(TTFont('Corpo-I', os.path.join(FONTES, 'ariali.ttf')))
pdfmetrics.registerFont(TTFont('Corpo-BI', os.path.join(FONTES, 'arialbi.ttf')))
pdfmetrics.registerFont(TTFont('Mono', os.path.join(FONTES, 'consola.ttf')))
pdfmetrics.registerFont(TTFont('Mono-B', os.path.join(FONTES, 'consolab.ttf')))
pdfmetrics.registerFontFamily('Corpo', normal='Corpo', bold='Corpo-B', italic='Corpo-I', boldItalic='Corpo-BI')
pdfmetrics.registerFontFamily('Mono', normal='Mono', bold='Mono-B', italic='Mono', boldItalic='Mono-B')
GLIFOS = {f: set(pdfmetrics.getFont(f).face.charToGlyph) for f in ('Corpo', 'Mono')}

AZUL = colors.HexColor('#1F3A5F')
CINZA = colors.HexColor('#F2F4F7')
BORDA = colors.HexColor('#C8CED8')
CODIGO = colors.HexColor('#8A1F11')

ST = dict(
    titulo=ParagraphStyle('titulo', fontName='Corpo-B', fontSize=24, leading=30, textColor=AZUL, alignment=TA_CENTER),
    sub=ParagraphStyle('sub', fontName='Corpo', fontSize=12, leading=16, alignment=TA_CENTER, textColor=colors.grey),
    h1=ParagraphStyle('h1', fontName='Corpo-B', fontSize=16, leading=20, textColor=AZUL, spaceBefore=10, spaceAfter=6),
    h2=ParagraphStyle('h2', fontName='Corpo-B', fontSize=13, leading=16, textColor=AZUL, spaceBefore=8, spaceAfter=4),
    h3=ParagraphStyle('h3', fontName='Corpo-B', fontSize=11, leading=14, spaceBefore=6, spaceAfter=3),
    p=ParagraphStyle('p', fontName='Corpo', fontSize=9.2, leading=12.4, spaceAfter=4),
    li=ParagraphStyle('li', fontName='Corpo', fontSize=9.2, leading=12.4, spaceAfter=1.5),
    q=ParagraphStyle('q', fontName='Corpo', fontSize=9, leading=12, leftIndent=10, borderPadding=(4, 6, 4, 6),
                     backColor=colors.HexColor('#FFF6E0'), borderColor=colors.HexColor('#E8C36A'), borderWidth=0.6,
                     spaceBefore=4, spaceAfter=7),
    td=ParagraphStyle('td', fontName='Corpo', fontSize=7.8, leading=9.6),
    th=ParagraphStyle('th', fontName='Corpo-B', fontSize=7.8, leading=9.6, textColor=colors.white),
    pre=ParagraphStyle('pre', fontName='Mono', fontSize=7.6, leading=9.4, backColor=CINZA, borderPadding=4,
                       spaceBefore=3, spaceAfter=6),
)


def limpa(s, fonte='Corpo'):
    """Troca caracteres sem glifo na fonte (emojis etc.)."""
    g = GLIFOS[fonte]
    s = s.replace('\ufe0f', '')
    return ''.join(c if (ord(c) in g or c in '\n\t \x01') else {'✅': '[OK]', '⭐': '*', '⚠': '(!)', '⇒': '=>', '◆': '*', '★': '*', '✎': '(editar)', '✨': '*', '⟳': '(atualizar)', '🎨': '(cores)'}.get(c, '?') for c in s)


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def inline(s):
    """Markdown inline -> marcação do reportlab."""
    partes = re.split(r'(`[^`]+`)', s)            # negrito pode envolver `código`: \x01 abre/fecha no fim
    out = []
    for t in partes:
        if t.startswith('`') and t.endswith('`') and len(t) > 1:
            out.append('<font face="Mono" color="#8A1F11">%s</font>' % esc(limpa(t[1:-1], 'Mono')))
            continue
        t = esc(limpa(t.replace('**', '\x01')))
        t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<link href="\2" color="#1F5FAF">\1</link>', t)
        t = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<i>\1</i>', t)
        out.append(t)
    s = ''.join(out)
    n = s.count('\x01')
    if n % 2: s = s.replace('\x01', '**')        # desbalanceado: deixa literal
    else:
        k = [0]
        def tag(m):
            k[0] += 1
            return '<b>' if k[0] % 2 else '</b>'
        s = re.sub('\x01', tag, s)
    return s


class Doc(BaseDocTemplate):
    def __init__(self, arq, **kw):
        super().__init__(arq, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                         bottomMargin=16 * mm, **kw)
        f = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='f')
        self.addPageTemplates([PageTemplate('p', [f], onPage=self.rodape)])

    def rodape(self, c, doc):
        c.saveState()
        c.setFont('Corpo', 7.5)
        c.setFillColor(colors.grey)
        c.drawString(16 * mm, 9 * mm, 'NES N8 Everdrive Covers editor — auditoria técnica (firmware v15)')
        c.drawRightString(A4[0] - 16 * mm, 9 * mm, 'página %d' % doc.page)
        c.restoreState()

    def beforeDocument(self):
        self._ntit = 0                            # (as chaves têm que repetir a cada passada do multiBuild)

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and getattr(f, '_nivel', None) is not None:
            n = f._nivel
            self._ntit += 1
            chave = 'h%d' % self._ntit
            self.canv.bookmarkPage(chave)
            self.canv.addOutlineEntry(f.getPlainText(), chave, level=n, closed=n > 0)
            if n <= 1:
                self.notify('TOCEntry', (n, f.getPlainText(), self.page, chave))


def titulo(texto, nivel):
    p = Paragraph(inline(texto), ST['h%d' % (nivel + 1)])
    p._nivel = nivel
    return p


def tabela(linhas, larg):
    cab = [c.strip() for c in linhas[0].strip().strip('|').split('|')]
    corpo = []
    for l in linhas[2:]:
        l = l.strip()
        if l.startswith('|'): l = l[1:]
        if l.endswith('|'): l = l[:-1]
        cel = [c.strip() for c in re.split(r'(?<!\\)\|', l)]
        cel += [''] * (len(cab) - len(cel))
        corpo.append(cel[:len(cab)])
    n = len(cab)
    # largura proporcional ao texto (com mínimo)
    tam = [max([len(cab[i])] + [len(r[i]) for r in corpo]) for i in range(n)]
    tam = [min(max(t, 6), 70) for t in tam]
    tot = sum(tam)
    ws = [larg * t / tot for t in tam]
    dados = [[Paragraph(inline(c), ST['th']) for c in cab]]
    dados += [[Paragraph(inline(c.replace('\\|', '|')), ST['td']) for c in r] for r in corpo]
    t = Table(dados, colWidths=ws, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CINZA]),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDA),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return [t, Spacer(1, 6)]


def markdown(texto, larg, nivel_base=0, pular_h1=False):
    """Markdown simples (o usado nos .md do projeto) -> flowables."""
    fl = []
    linhas = texto.replace('\r', '').split('\n')
    i = 0
    par = []

    def fecha_par():
        if par:
            fl.append(Paragraph(inline(' '.join(x.strip() for x in par)), ST['p']))
            par.clear()
    while i < len(linhas):
        l = linhas[i]
        s = l.strip()
        if s.startswith('```'):
            fecha_par()
            j = i + 1
            bloco = []
            while j < len(linhas) and not linhas[j].strip().startswith('```'):
                bloco.append(linhas[j]); j += 1
            fl.append(Preformatted(limpa('\n'.join(bloco), 'Mono'), ST['pre'], maxLineLength=118))
            i = j + 1; continue
        m = re.match(r'^(#{1,4})\s+(.*)$', s)
        if m and not l.startswith(' '):
            fecha_par()
            n = len(m.group(1)) - 1
            if n == 0 and pular_h1:
                i += 1; continue
            fl.append(titulo(m.group(2), max(0, min(nivel_base + n, 2))))
            i += 1; continue
        if s.startswith('|') and i + 1 < len(linhas) and re.match(r'^\s*\|?\s*:?-{2,}', linhas[i + 1]):
            fecha_par()
            j = i
            bloco = []
            while j < len(linhas) and linhas[j].strip().startswith('|'):
                bloco.append(linhas[j]); j += 1
            fl += tabela(bloco, larg)
            i = j; continue
        if s.startswith('>'):
            fecha_par()
            bloco = []
            while i < len(linhas) and linhas[i].strip().startswith('>'):
                bloco.append(linhas[i].strip()[1:].strip()); i += 1
            txt = ' '.join(b.lstrip('#').strip() for b in bloco if b)
            fl.append(Paragraph(inline(txt), ST['q']))
            continue
        m = re.match(r'^(\s*)([-*]|\d+\.)\s+(.*)$', l)
        if m:
            fecha_par()
            ind = len(m.group(1))
            item = [m.group(3)]
            i += 1
            while i < len(linhas) and linhas[i].strip() and not re.match(r'^\s*([-*]|\d+\.)\s+', linhas[i]) \
                    and not linhas[i].strip().startswith(('|', '#', '>', '```')):
                item.append(linhas[i].strip()); i += 1
            marca = m.group(2) if m.group(2)[0].isdigit() else '•'
            st = ParagraphStyle('li%d' % ind, parent=ST['li'], leftIndent=12 + ind * 4, bulletIndent=2 + ind * 4)
            fl.append(Paragraph(inline(' '.join(item)), st, bulletText=marca))
            continue
        if s == '---':
            fecha_par(); fl.append(Spacer(1, 4)); i += 1; continue
        if not s:
            fecha_par(); i += 1; continue
        par.append(l)
        i += 1
    fecha_par()
    return fl


def simbolos():
    arq = os.path.join(DOCS, 'simbolos_v15.json')
    try:
        sys.path.insert(0, os.path.join(ROOT, 'ferramentas'))
        import build_capas_v15 as V
        _, S, _ = V.main(log=lambda *a: None)
        tab = {k: v for k, v in S.items() if isinstance(v, int)}
        json.dump(tab, open(arq, 'w'), indent=0, sort_keys=True)
    except Exception as e:                       # sem o OS original: usa a tabela salva
        print('(símbolos do arquivo salvo: %s)' % e)
        tab = json.load(open(arq))
    return tab


def zona(v):
    for a, b, n in [(0x6400, 0x67FF, 'módulo (WRAM)'), (0x7F00, 0x7FFF, 'variáveis WRAM'), (0x81C5, 0x820F, 'SEG_A'),
                    (0xA680, 0xA706, 'SEG_E'), (0xD0C6, 0xD329, 'SEG_MAIN'), (0xF753, 0xF895, 'SEG_C'),
                    (0xFBD4, 0xFBFF, 'SEG_D')]:
        if a <= v <= b: return n
    return 'OS / constante'


def apendice_a(larg):
    tab = simbolos()
    cod = sorted((v, k) for k, v in tab.items() if 0x6000 <= v <= 0xFFFF and not k.isupper())
    const = sorted((k, v) for k, v in tab.items() if (k, v) not in [(c[1], c[0]) for c in cod])
    fl = [titulo('Apêndice A — Tabela de símbolos da firmware v15', 0),
          Paragraph(inline('Gerada pelo montador (`asm6502`) ao construir a v15 (`build_capas_v15.main()`): %d símbolos. '
                           'Rótulos de código/variáveis por endereço e, depois, as constantes/equates (rotinas do OS, '
                           'registradores, endereços fixos).' % len(tab)), ST['p'])]
    linhas = ['| Endereço | Símbolo | Região |', '|---|---|---|'] + \
             ['| `$%04X` | `%s` | %s |' % (v, k, zona(v)) for v, k in cod]
    # 2 colunas lado a lado para economizar páginas
    def mini(sub):
        d = [[Paragraph('<b>End.</b>', ST['th']), Paragraph('<b>Símbolo</b>', ST['th']), Paragraph('<b>Região</b>', ST['th'])]]
        d += [[Paragraph('<font face="Mono">$%04X</font>' % v, ST['td']), Paragraph('<font face="Mono">%s</font>' % esc(k), ST['td']),
               Paragraph(zona(v), ST['td'])] for v, k in sub]
        t = Table(d, colWidths=[larg * .09, larg * .22, larg * .17], repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), AZUL), ('GRID', (0, 0), (-1, -1), 0.3, BORDA),
                               ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CINZA]),
                               ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
        return t
    POR = 56                                      # linhas por coluna em cada bloco (cabe numa página)
    for j in range(0, len(cod), 2 * POR):
        a, b = cod[j:j + POR], cod[j + POR:j + 2 * POR]
        duo = Table([[mini(a), mini(b) if b else '']], colWidths=[larg / 2, larg / 2])
        duo.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        fl += [duo, Spacer(1, 4)]
    fl.append(Spacer(1, 8))
    fl.append(titulo('Constantes e equates', 1))
    linhas = ['| Nome | Valor | Nome | Valor | Nome | Valor |', '|---|---|---|---|---|---|']
    for j in range(0, len(const), 3):
        g = const[j:j + 3] + [('', None)] * (3 - len(const[j:j + 3]))
        linhas.append('| ' + ' | '.join(('`%s` | `$%X`' % (k, v)) if v is not None else ' | ' for k, v in g) + ' |')
    fl += tabela(linhas, larg)
    return fl


def main():
    saida = os.path.join(DOCS, 'AUDITORIA-DESENVOLVEDOR.pdf')
    doc = Doc(saida, title='Auditoria técnica — NES N8 Everdrive Covers editor (v15)', author='TavinhoGames',
              subject='Firmware com capas para o EverDrive N8 clone (EDFC)')
    larg = doc.width
    md = open(os.path.join(DOCS, 'AUDITORIA-DESENVOLVEDOR.md'), encoding='utf-8').read()
    notas = open(os.path.join(ROOT, 'NOTAS-TECNICAS-FIRMWARE.md'), encoding='utf-8').read()
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle('t0', fontName='Corpo-B', fontSize=9.5, leading=13, leftIndent=0),
                       ParagraphStyle('t1', fontName='Corpo', fontSize=8.5, leading=11, leftIndent=12)]
    st = [Spacer(1, 60 * mm),
          Paragraph('Auditoria técnica', ST['titulo']), Spacer(1, 4 * mm),
          Paragraph('NES N8 Everdrive Covers editor', ST['titulo']), Spacer(1, 8 * mm),
          Paragraph('Firmware v15 com capas de jogos para o EverDrive N8 clone (EDFC) — documento para desenvolvedores',
                    ST['sub']), Spacer(1, 4 * mm),
          Paragraph('TavinhoGames · 30/10/2026', ST['sub']), Spacer(1, 30 * mm),
          Paragraph(inline('`OS.BIN` v15 SHA-1 `caa12ed797d374341a40a76a7d2124ee3ce51e8a` · módulo `MOD_v10.BIN` '
                           'SHA-1 `6e5e9cbfe33f9ff11185bb6a5e818528b4595650`'), ST['sub']),
          PageBreak(),
          Paragraph('Sumário', ST['h1']), toc, PageBreak()]
    st += markdown(md, larg, nivel_base=-1, pular_h1=True)
    st += [PageBreak()] + apendice_a(larg)
    st += [PageBreak(), titulo('Apêndice B — Notas técnicas completas (NOTAS-TECNICAS-FIRMWARE.md)', 0),
           Paragraph(inline('O diário técnico do projeto, na ordem em que as coisas foram descobertas (seções 0–39). '
                            'Endereços das seções 1–9 são do OS v1.26 do krikzz; a partir da seção 10 valem os do build '
                            'do clone (base).'), ST['p'])]
    st += markdown(notas, larg, nivel_base=0, pular_h1=True)
    doc.multiBuild(st)
    print('pronto:', saida)


if __name__ == '__main__':
    main()
