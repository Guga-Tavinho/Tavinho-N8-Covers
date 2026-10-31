"""SIMULAÇÃO (só no PC): capa com sprites + fundo + alternância de quadros (flicker), para avaliar o ganho.

Modelo (o que a firmware conseguiria fazer):
  - quadro A e quadro B: tiles de sprite próprios (96 + 96 de 256), 4 paletas de sprite próprias e paleta por
    bloco 8x16 própria;
  - camada de fundo: os MESMOS tiles/nametable/atributos nos dois quadros (só há 63 tiles livres); só as
    2 paletas de fundo livres trocam a cada quadro; a paleta do texto (0) fica fixa;
  - percebido = média dos dois quadros em luz linear (60 Hz -> o olho mistura).
Otimização: quadro A = conversor v2; depois B é otimizado contra A, e A de novo contra B (busca local nas
paletas + escolha por pixel), com penalidade de tremido lam * ΔE²(A, B).

uso: python sim_flicker.py capa.png pasta_saida
"""
import base64, io, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
from build_poc import png_read, resize, quantize, rgb, lab, USABLE, BLACK, COVER_W, COVER_H


def d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
import conv_v2
import progresso
import rapido

W, H = COVER_W, COVER_H
NBX, NBY = W // 8, H // 16                       # blocos de sprite 8x16


def lin(c): return [((v / 255 + 0.055) / 1.055) ** 2.4 if v / 255 > 0.04045 else v / 255 / 12.92 for v in c]


def unlin(l):
    out = []
    for v in l:
        v = max(0.0, min(1.0, v))
        v = 1.055 * v ** (1 / 2.4) - 0.055 if v > 0.0031308 else 12.92 * v
        out.append(int(round(v * 255)))
    return tuple(out)


_AVG = {}


def avg_color(i, j):
    """Cor percebida da alternância entre os índices NES i e j."""
    k = (i, j) if i <= j else (j, i)
    if k not in _AVG:
        a, b = lin(rgb(i)), lin(rgb(j))
        _AVG[k] = unlin([(a[n] + b[n]) / 2 for n in range(3)])
    return _AVG[k]


def frame_colors(sp_pals, sp_assign, spr, bg_pals_frame, bg_assign, bg):
    """Índice NES de cada pixel num quadro."""
    out = [[BLACK] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            v = spr[y][x]
            if v:
                out[y][x] = sp_pals[sp_assign[(y // 16) * NBX + x // 8]][v - 1]
            else:
                b = bg[y][x]
                out[y][x] = BLACK if b == 0 else bg_pals_frame[bg_assign[(y // 16) * 4 + x // 16]][b - 1]
    return out


def optimize_frame(T, other, bg, bg_assign, bg_pals_init, sp_pals_init, sp_assign_init, lam, fixed_bg=(0,),
                   fixed_assign=None):
    """Otimiza UM quadro sabendo o outro. bg/bg_assign fixos; paletas de fundo em fixed_bg não mudam.
    (NumPy: o mesmo algoritmo e o mesmo resultado do laço em Python, só que o erro de cada bloco é somado
    de uma vez — ver rapido.py.)"""
    np = rapido.np
    cand = [BLACK] + USABLE
    P = W * H
    # E[p][c]: erro percebido se este quadro mostrar c no pixel p + penalidade de tremido
    Tl = [lab(T[y][x]) for y in range(H) for x in range(W)]
    O = [other[y][x] for y in range(H) for x in range(W)]
    pares = {}                                          # (outra cor, alvo) -> índice
    for o, t in zip(O, Tl):
        pares.setdefault((o, t), len(pares))
    chaves = list(pares)
    LAV = np.array([[lab(avg_color(o, c)) for c in cand] for o, _ in chaves])      # (k, 55, 3)
    TT = np.array([t for _, t in chaves])                                          # (k, 3)
    LO = {o: lab(rgb(o)) for o in set(O)}
    LC = np.array([lab(rgb(c)) for c in cand])
    lo = np.array([LO[o] for o, _ in chaves])
    t1 = (rapido.quad(LAV[:, :, 0] - TT[:, None, 0]) + rapido.quad(LAV[:, :, 1] - TT[:, None, 1])) + \
        rapido.quad(LAV[:, :, 2] - TT[:, None, 2])
    t2 = (rapido.quad(lo[:, None, 0] - LC[None, :, 0]) + rapido.quad(lo[:, None, 1] - LC[None, :, 1])) + \
        rapido.quad(lo[:, None, 2] - LC[None, :, 2])
    Ek = t1 + lam * t2                                                             # (k, 55)
    E = np.full((P, 64), np.inf)
    E[:, cand] = Ek[[pares[(o, t)] for o, t in zip(O, Tl)]]
    sp_pals = [list(p) for p in sp_pals_init]
    bgp = [list(p) for p in bg_pals_init]
    blocks = [[(by * 16 + y, bx * 8 + x) for y in range(16) for x in range(8)] for by in range(NBY) for bx in range(NBX)]
    BLK = np.array([[y * W + x for (y, x) in blk] for blk in blocks])              # (48, 128), na ordem do laço
    BGV = np.array([[bg[y][x] for x in range(W)] for y in range(H)]).ravel()
    BGA = np.array([bg_assign[(p // W // 16) * 4 + (p % W) // 16] for p in range(P)])
    PIX = np.arange(P)

    def bgcol_arr():
        tab = np.array([[BLACK] + list(q) for q in bgp])                          # bgp[a][b-1] = tab[a][b]
        return np.where(BGV == 0, BLACK, tab[BGA, np.maximum(BGV, 0)])

    BGC = bgcol_arr()
    EBG = E[PIX, BGC]

    def perr_g(g):
        pal = sp_pals[g]
        m = np.minimum(np.minimum(np.minimum(E[:, pal[0]], E[:, pal[1]]), E[:, pal[2]]), EBG)
        return rapido.soma_seq(m[BLK], 1)                                          # s = 0.0; s += ... por bloco

    perr = [perr_g(g) for g in range(4)]
    if fixed_assign is None:
        total = lambda: rapido.total_min(perr)
    else:                                        # paleta por bloco fixa (a mesma nos dois quadros)
        total = lambda: rapido.total_fixo(perr, fixed_assign)
    # candidatos: as cores que mais aparecem como melhor escolha isolada
    melhor = [cand[i] for i in E[:, cand].argmin(axis=1).tolist()]
    hist = {}
    for c in melhor:
        hist[c] = hist.get(c, 0) + 1
    cands = [c for c in sorted(hist, key=hist.get, reverse=True) if c != BLACK][:28]
    best = total()
    nq = len([q for q in range(len(bgp)) if q not in fixed_bg])
    passos = 12 + nq * 3
    for it in range(3):
        imp = False; passo = 0
        r0, r1 = PESO_RODADA[it]
        for g in range(4):
            for s in range(3):
                passo += 1; progresso.avancar(r0 + (r1 - r0) * passo / passos)
                for c in cands:
                    if c in sp_pals[g]: continue
                    old, olde = sp_pals[g][s], perr[g]
                    sp_pals[g][s] = c; perr[g] = perr_g(g)
                    e = total()
                    if e < best: best, imp = e, True
                    else: sp_pals[g][s], perr[g] = old, olde
        for q in range(len(bgp)):
            if q in fixed_bg: continue
            for s in range(3):
                passo += 1; progresso.avancar(r0 + (r1 - r0) * passo / passos)
                for c in cands:
                    if c in bgp[q]: continue
                    old, oldp, oldc, olde = bgp[q][s], perr, BGC, EBG
                    bgp[q][s] = c
                    BGC = bgcol_arr(); EBG = E[PIX, BGC]
                    perr = [perr_g(g) for g in range(4)]
                    e = total()
                    if e < best: best, imp = e, True
                    else: bgp[q][s], perr, BGC, EBG = old, oldp, oldc, olde
        if not imp: break
    if fixed_assign is not None:
        sp_assign = list(fixed_assign)
    else:
        sp_assign = [int(g) for g in np.asarray(perr).argmin(axis=0)]
    # cada pixel: fundo (0) ou um dos 3 espaços do sprite do bloco; empate -> o menor (como o min de tuplas)
    PALB = np.array([sp_pals[g] for g in sp_assign])                               # (48, 3)
    opts = np.stack([EBG[BLK]] + [E[BLK, PALB[:, s][:, None]] for s in range(3)], axis=2)   # (48, 128, 4)
    esc = opts.argmin(axis=2)
    spr = [[0] * W for _ in range(H)]
    for k, blk in enumerate(blocks):
        ek = esc[k].tolist()
        for j, (y, x) in enumerate(blk):
            spr[y][x] = ek[j]
    frame = frame_colors(sp_pals, sp_assign, spr, bgp, bg_assign, bg)
    return dict(sp_pals=sp_pals, sp_assign=sp_assign, spr=spr, bg_pals=bgp, frame=frame, err=best)


PESOS_FLK = [(0.0, 0.25), (0.25, 0.55), (0.55, 0.80), (0.80, 1.0)]  # conversão base, B, A, B (fração do tempo, NumPy)
PESO_RODADA = [(0.15, 0.75), (0.75, 0.95), (0.95, 1.0)]   # optimize_frame: a 1ª rodada é a mais longa


def flicker_sim(T, lam, same_assign=False):
    with progresso.etapa(*PESOS_FLK[0]):
        r = conv_v2.convert(T)                                   # quadro A inicial = conversor v2
    bg, bg_assign = r['bg'], r['bg_assign']
    A = dict(sp_pals=r['sp_pals'], sp_assign=r['sp_assign'], spr=r['spr'], bg_pals=r['bg_pals'])
    A['frame'] = frame_colors(A['sp_pals'], A['sp_assign'], A['spr'], A['bg_pals'], bg_assign, bg)
    fa = list(A['sp_assign']) if same_assign else None
    with progresso.etapa(*PESOS_FLK[1]):
        B = optimize_frame(T, A['frame'], bg, bg_assign, A['bg_pals'], A['sp_pals'], A['sp_assign'], lam, fixed_assign=fa)
    with progresso.etapa(*PESOS_FLK[2]):
        A = optimize_frame(T, B['frame'], bg, bg_assign, A['bg_pals'], A['sp_pals'], A['sp_assign'], lam, fixed_assign=fa)
    with progresso.etapa(*PESOS_FLK[3]):
        B = optimize_frame(T, A['frame'], bg, bg_assign, B['bg_pals'], B['sp_pals'], B['sp_assign'], lam, fixed_assign=fa)
    perc = [[avg_color(A['frame'][y][x], B['frame'][y][x]) for x in range(W)] for y in range(H)]
    tremor = sum(d2(lab(rgb(A['frame'][y][x])), lab(rgb(B['frame'][y][x]))) ** 0.5
                 for y in range(H) for x in range(W)) / (W * H)
    return dict(A=A, B=B, perc=perc, v2=r['preview'], tremor=tremor, n_bg=r['n_bg_tiles'], conv=r)


def to_img(px, scale=1):
    im = Image.new('RGB', (W, H)); im.putdata([c for row in px for c in row])
    return im.resize((W * scale, H * scale), Image.Resampling.NEAREST) if scale > 1 else im


def idx_img(fr, scale=1): return to_img([[rgb(i) for i in row] for row in fr], scale)


def erro_medio(px, T):
    return sum(d2(lab(px[y][x]), lab(T[y][x])) ** 0.5 for y in range(H) for x in range(W)) / (W * H)


def b64(im):
    buf = io.BytesIO(); im.save(buf, 'PNG'); return base64.b64encode(buf.getvalue()).decode()


VARIANTES = [(0.05, 'fidelidade máxima'), (0.15, 'equilibrada'), (0.20, 'suave')]


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    w, h, big = png_read(src)
    T = resize(w, h, big, W, H)
    v1 = quantize(T)[3]
    sims = [(lam, nome, flicker_sim(T, lam)) for lam, nome in VARIANTES]
    v2 = sims[0][2]['v2']
    paineis = [('Original', T), ('v1 sprites', v1), ('v2 spr+fundo', v2)]
    paineis += [('alternância %s' % nome, sim['perc']) for lam, nome, sim in sims]
    S = 4; gap = 8
    comp = Image.new('RGB', (len(paineis) * (W * S + gap) - gap, H * S), (32, 32, 32))
    for k, (nome, px) in enumerate(paineis):
        comp.paste(to_img(px, S), (k * (W * S + gap), 0))
    comp.save(os.path.join(out, 'comparacao.png'))
    linhas = []
    print('erro médio ΔE (menor = mais fiel):')
    for nome, px in paineis[1:]:
        print('  %-34s %5.2f   cores na tela: %d' % (nome, erro_medio(px, T), len({c for r in px for c in r})))
    for lam, nome, sim in sims:
        print('  tremido médio ΔE entre quadros (%s, λ=%.2f): %.1f' % (nome, lam, sim['tremor']))
        linhas.append(dict(nome=nome, lam=lam, erro=round(erro_medio(sim['perc'], T), 1), tremor=round(sim['tremor'], 1),
                           A=b64(idx_img(sim['A']['frame'], S)), B=b64(idx_img(sim['B']['frame'], S)),
                           P=b64(to_img(sim['perc'], S))))
        for k in ('A', 'B'):
            idx_img(sim[k]['frame'], S).save(os.path.join(out, 'quadro_%s_%s.png' % (k, nome.split()[0])))
    data = dict(orig=b64(to_img(T, S)), v1=b64(to_img(v1, S)), v2=b64(to_img(v2, S)),
                e1=round(erro_medio(v1, T), 1), e2=round(erro_medio(v2, T), 1), vars=linhas)
    import json
    open(os.path.join(out, 'simulacao_60hz.html'), 'w', encoding='utf-8').write(PAGE.replace('__DATA__', json.dumps(data)))
    print('salvo em', out)


PAGE = r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Simulação: alternância de quadros</title>
<style>
body{background:#14110f;color:#ece3d3;font:14px Segoe UI,sans-serif;margin:24px}
h1{color:#d9a441;font-size:20px;margin:0 0 6px} p{color:#8d8273;max-width:980px;line-height:1.45}
.row{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start;margin-top:14px}
figure{margin:0;background:#1d1916;padding:10px;border-radius:6px}
figcaption{font-size:12px;color:#d9a441;margin-bottom:6px;min-height:32px}
figcaption small{color:#8d8273}
img,canvas{image-rendering:pixelated;display:block;width:192px;height:288px;background:#000}
button{background:#26211d;color:#ece3d3;border:0;padding:5px 8px;margin:2px 1px;border-radius:4px;cursor:pointer;font-size:12px}
button.on{background:#d9a441;color:#000}
</style></head><body>
<h1>Capa do Mario 3 — sprites + fundo + alternância de quadros (simulação)</h1>
<p>As três telas da direita mostram os quadros A e B se alternando a ~60 Hz, como seria no NES. É nelas que dá para
avaliar o tremido. "ΔE" é a distância de cor até a original (menor = mais fiel). Num monitor de 120/144 Hz a alternância
fica diferente da de uma TV; numa TV de tubo o tremido costuma incomodar <b>menos</b> do que num LCD.</p>
<div class="row" id="row"></div>
<script>
const D=__DATA__;
const row=document.getElementById('row');
function fig(t,sub,src){const f=document.createElement('figure');f.innerHTML='<figcaption>'+t+'<br><small>'+sub+'</small></figcaption>';
  const i=document.createElement('img');i.src='data:image/png;base64,'+src;f.appendChild(i);row.appendChild(f);}
fig('Original 64×96','',D.orig); fig('v1 — só sprites','ΔE '+D.e1,D.v1); fig('v2 — sprites + fundo (estável)','ΔE '+D.e2,D.v2);
const V=[];
D.vars.forEach((v,n)=>{const f=document.createElement('figure');
  f.innerHTML='<figcaption>Alternância — '+v.nome+'<br><small>ΔE '+v.erro+' · tremido '+v.tremor+'</small></figcaption>';
  const c=document.createElement('canvas');c.width=192;c.height=288;f.appendChild(c);
  const bar=document.createElement('div');
  [['alt','alternando 60 Hz'],['P','média'],['A','quadro A'],['B','quadro B']].forEach(([m,t])=>{
    const b=document.createElement('button');b.textContent=t;if(m==='alt')b.className='on';
    b.onclick=()=>{V[n].m=m;bar.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));};bar.appendChild(b);});
  f.appendChild(bar);row.appendChild(f);
  const im=k=>{const i=new Image();i.src='data:image/png;base64,'+v[k];return i};
  const ctx=c.getContext('2d');ctx.imageSmoothingEnabled=false;
  V.push({ctx,A:im('A'),B:im('B'),P:im('P'),m:'alt'});});
const t0=performance.now();
function tick(t){const f=Math.floor((t-t0)/(1000/60))%2;
  for(const s of V){const im=s.m==='alt'?(f?s.B:s.A):s[s.m]; if(im.complete) s.ctx.drawImage(im,0,0,192,288);}
  requestAnimationFrame(tick);}
requestAnimationFrame(tick);
</script></body></html>'''

if __name__ == '__main__':
    main()
