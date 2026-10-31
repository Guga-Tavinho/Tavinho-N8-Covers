"""Página de teste (só no PC): barra com < e > para ajustar a força da alternância (λ) da capa e ver o resultado.

Calcula a simulação da firmware v3 (mesma paleta por bloco nos dois quadros, como no aparelho) para vários λ
e grava tudo numa página HTML só, sem arquivos externos.

uso: python sim_flicker_barra.py [capa.png] [saida.html]
"""
import hashlib, json, os, sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_flicker as sf
import conv_v3
import progresso
from build_poc import png_read, resize, rgb, carregar_capa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache_flicker')
LAMBDAS = [0.02, 0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.19, 0.20, 0.21, 0.22, 0.23, 0.24, 0.25]
POCS = {0.05: 'POC máxima', 0.15: 'POC intermediária (flicou muito no console)', 0.20: 'POC suave',
        0.22: 'POC λ=0,22'}
S = 4
VERSAO = 2                                       # 2: o cache guarda a estrutura (paletas/tiles) para editar as cores


def capa(src, nitidez=False):
    """Pixels 64x96 da capa: PNG (com ou sem nitidez) ou projeto do Palette Lab (.json)."""
    if src.lower().endswith('.json'):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'palette_lab'))
        import capa_edfc
        return capa_edfc.project_pixels(capa_edfc.load_project(src))
    return carregar_capa(src, nitidez)


_FILA = None                                     # fila de progresso (só nos processos da ferramenta)


def iniciar_worker(fila):
    global _FILA
    _FILA = fila


def nivel(T, lam, tarefa=None):
    """Um nível da barra: quadros A e B (índices NES), média percebida (RGB), ΔE e tremido.
    Fica em cache no disco (cache_flicker/), pela imagem e pelo λ. λ=None = v2 estável (sem alternância)."""
    chave = hashlib.sha1(json.dumps([T, lam, VERSAO]).encode()).hexdigest()
    arq = os.path.join(CACHE, chave + '.json')
    if os.path.exists(arq):
        try:
            return json.load(open(arq, encoding='utf-8'))
        except (OSError, ValueError):
            pass
    if _FILA is not None and tarefa is not None:
        progresso.definir(lambda v: _FILA.put((tarefa, v)))
    try:
        n = _calcular(T, lam)
    finally:
        progresso.definir(None)
    os.makedirs(CACHE, exist_ok=True)
    json.dump(n, open(arq, 'w', encoding='utf-8'))
    return n


def _calcular(T, lam):
    if lam is None:
        n = nivel_v2(T)
    else:
        sim = sf.flicker_sim(T, lam, same_assign=True)
        r = sim['conv']
        n = dict(lam=lam, poc=POCS.get(lam, ''), erro=round(sf.erro_medio(sim['perc'], T), 1),
                 tremor=round(sim['tremor'], 1), A=sim['A']['frame'], B=sim['B']['frame'],
                 P=[[list(c) for c in row] for row in sim['perc']],
                 est=dict(bg=r['bg'], bg_assign=r['bg_assign'], sp_assign=sim['A']['sp_assign'],
                          **{q: dict(bg_pals=sim[q]['bg_pals'], sp_pals=sim[q]['sp_pals'], spr=sim[q]['spr'])
                             for q in ('A', 'B')}))
    return n


def nivel_v2(T):
    """Último nível: a v2 estável (sem alternância)."""
    r = sf.conv_v2.convert(T)
    v2 = r['preview']
    P = [[list(c) for c in row] for row in v2]
    return dict(lam=None, poc='Capa sem Flicker', erro=round(sf.erro_medio(v2, T), 1), tremor=0,
                A=None, B=None, P=P,
                est=dict(bg=r['bg'], bg_assign=r['bg_assign'], sp_assign=r['sp_assign'], B=None,
                         A=dict(bg_pals=r['bg_pals'], sp_pals=r['sp_pals'], spr=r['spr'])))


def paletas(n):
    """Paletas editáveis do nível: {'A': {'bg': [fundo 1, fundo 2], 'sp': [sprite 0..3]}, 'B': ... ou None}.
    O fundo 0 (texto do OS) e o 3 (barra do OS) não entram: são do OS."""
    e = n['est']
    d = {q: (dict(bg=[list(p) for p in e[q]['bg_pals'][1:3]], sp=[list(p) for p in e[q]['sp_pals']])
             if e[q] else None) for q in ('A', 'B')}
    d['pix'] = {'A': [], 'B': []}                 # pontos pintados à mão na camada de sprite: [[x, y, v], ...]
    return d


def aplicar(n, T, pals):
    """O nível com outras paletas (pals = paletas(n) editado): quadros, média, ΔE e tremido refeitos."""
    e = n['est']
    fr = {}
    for q in ('A', 'B'):
        if not e[q]: continue
        bgp = [e[q]['bg_pals'][0]] + pals[q]['bg']
        spr = conv_v3.com_pontos(e[q]['spr'], (pals.get('pix') or {}).get(q))
        fr[q] = sf.frame_colors(pals[q]['sp'], e['sp_assign'], spr, bgp, e['bg_assign'], e['bg'])
    if 'B' in fr:
        A, B = fr['A'], fr['B']
        P = [[sf.avg_color(A[y][x], B[y][x]) for x in range(sf.W)] for y in range(sf.H)]
        tremor = sum(sf.d2(sf.lab(rgb(A[y][x])), sf.lab(rgb(B[y][x]))) ** 0.5
                     for y in range(sf.H) for x in range(sf.W)) / (sf.W * sf.H)
    else:
        A = B = None
        P = [[rgb(i) for i in row] for row in fr['A']]
        tremor = 0
    return dict(n, A=A, B=B, P=[[list(c) for c in row] for row in P], tremor=round(tremor, 1),
                erro=round(sf.erro_medio([[tuple(c) for c in row] for row in P], T), 1))


def _nivel(args):
    return nivel(*args)


def pagina(nome, T, niveis):
    """HTML autocontido com a barra < >, a partir dos níveis calculados."""
    def png(px): return sf.b64(sf.to_img([[tuple(c) for c in row] for row in px], S))
    def idx(fr): return sf.b64(sf.idx_img(fr, S))
    out = []
    for n in niveis:
        P = png(n['P'])
        out.append(dict(lam=n['lam'], poc=n['poc'], erro=n['erro'], tremor=n['tremor'],
                        A=idx(n['A']) if n['A'] else P, B=idx(n['B']) if n['B'] else P, P=P))
    data = dict(nome=nome, orig=sf.b64(sf.to_img(T, S)), niveis=out)
    return PAGE.replace('__DATA__', json.dumps(data))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'imagens', 'Super Mario Bros. 3 (USA).png')
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'experimento_flicker', 'ajuste_flicker.html')
    T = capa(src)
    with Pool(min(len(LAMBDAS), os.cpu_count() or 1)) as p:
        niveis = p.map(_nivel, [(T, lam) for lam in LAMBDAS])
    niveis.append(nivel_v2(T))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'w', encoding='utf-8').write(pagina(os.path.splitext(os.path.basename(src))[0], T, niveis))
    for n in niveis:
        print('  λ=%-6s ΔE %5.1f  tremido %5.1f  %s' % (n['lam'], n['erro'], n['tremor'], n['poc']))
    print('salvo em', out)


PAGE = r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Ajuste do flicker</title>
<style>
body{background:#14110f;color:#ece3d3;font:14px Segoe UI,sans-serif;margin:24px}
h1{color:#d9a441;font-size:20px;margin:0 0 6px} p{color:#8d8273;max-width:900px;line-height:1.45;margin:4px 0}
.row{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start;margin-top:16px}
figure{margin:0;background:#1d1916;padding:10px;border-radius:6px}
figcaption{font-size:12px;color:#d9a441;margin-bottom:6px}
img,canvas{image-rendering:pixelated;display:block;background:#000}
button{background:#26211d;color:#ece3d3;border:0;padding:6px 10px;margin:2px 1px;border-radius:4px;cursor:pointer;font-size:13px}
button.on{background:#d9a441;color:#000}
button:disabled{opacity:.35;cursor:default}
.ctl{display:flex;align-items:center;gap:10px;margin-top:16px;max-width:900px}
.ctl button.seta{font-size:22px;padding:4px 16px;font-weight:bold}
input[type=range]{flex:1;accent-color:#d9a441}
#info{font:15px Consolas,monospace;color:#ece3d3;margin:10px 0}
#info b{color:#d9a441}
.marcas{display:flex;justify-content:space-between;max-width:900px;padding:0 62px;box-sizing:border-box;font:11px Consolas,monospace;color:#8d8273}
</style></head><body>
<h1>Ajuste do flicker — <span id="nome"></span></h1>
<p>Use <b>&lt;</b> e <b>&gt;</b> (ou as setas ← → do teclado) para aumentar e diminuir a alternância.
Para a esquerda: mais flicker e cores mais fiéis (ΔE menor). Para a direita: menos flicker e cores menos fiéis, até a Capa sem Flicker.
ΔE é a distância de cor até a original (menor = mais fiel). "Tremido" é quanto os quadros A e B diferem (0 = parado).</p>
<p>A alternância é a 60 Hz, como no NES. Num monitor de 120/144 Hz ou num LCD ela fica diferente da TV; numa TV de tubo costuma incomodar menos.
Para julgar o tremido, olhe a capa no tamanho que ela teria na TV (use o zoom).</p>
<div class="ctl">
  <button class="seta" id="menos" title="mais flicker (←)">&lt;</button>
  <input type="range" id="barra" min="0" step="1">
  <button class="seta" id="mais" title="menos flicker (→)">&gt;</button>
</div>
<div class="marcas"><span>← mais flicker · mais fiel</span><span>menos flicker · menos fiel →</span></div>
<div id="info"></div>
<div>
  <span style="color:#8d8273;font-size:12px">mostrar:</span> <span id="modos"></span>
  <span style="color:#8d8273;font-size:12px;margin-left:14px">zoom:</span> <span id="zooms"></span>
</div>
<div class="row">
  <figure><figcaption>Original</figcaption><img id="orig"></figure>
  <figure><figcaption id="cap">Capa no NES</figcaption><canvas id="tela"></canvas></figure>
  <figure><figcaption>Capa sem Flicker — referência</figcaption><img id="ref"></figure>
</div>
<script>
const D=__DATA__, N=D.niveis;
const $=id=>document.getElementById(id);
$('nome').textContent=D.nome;
const barra=$('barra'); barra.max=N.length-1;
let i=N.findIndex(n=>n.lam===0.15); if(i<0)i=0;
let modo='alt', zoom=3;
const img=s=>{const im=new Image();im.src='data:image/png;base64,'+s;return im};
const IM=N.map(n=>({A:img(n.A),B:img(n.B),P:img(n.P)}));
$('orig').src='data:image/png;base64,'+D.orig;
$('ref').src='data:image/png;base64,'+N[N.length-1].P;
const tela=$('tela'), ctx=tela.getContext('2d');
function tamanho(){const w=64*zoom,h=96*zoom;tela.width=w;tela.height=h;ctx.imageSmoothingEnabled=false;
  for(const id of ['orig','ref']){$(id).style.width=w+'px';$(id).style.height=h+'px';}}
function grupo(el,itens,atual,f){el.innerHTML='';itens.forEach(([v,t])=>{const b=document.createElement('button');b.textContent=t;
  if(v===atual)b.className='on';b.onclick=()=>{f(v);el.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));};el.appendChild(b);});}
grupo($('modos'),[['alt','alternando 60 Hz'],['P','média (sem flicker)'],['A','só quadro A'],['B','só quadro B']],modo,v=>modo=v);
grupo($('zooms'),[[1,'1×'],[2,'2×'],[3,'3×'],[4,'4×']],zoom,v=>{zoom=v;tamanho();});
function mostra(){const n=N[i];barra.value=i;
  const lam=n.lam===null?'∞ (sem alternância)':n.lam.toFixed(3);
  $('info').innerHTML='Nível <b>'+(i+1)+'/'+N.length+'</b> · λ = <b>'+lam+'</b> · ΔE <b>'+n.erro+'</b> · tremido <b>'+n.tremor+'</b>'
    +(n.poc?' · <b>'+n.poc+'</b>':'');
  $('cap').textContent='Capa no NES — λ '+lam;
  $('menos').disabled=i===0;$('mais').disabled=i===N.length-1;}
const passo=d=>{i=Math.max(0,Math.min(N.length-1,i+d));mostra();};
$('menos').onclick=()=>passo(-1); $('mais').onclick=()=>passo(1);
barra.oninput=()=>{i=+barra.value;mostra();};
document.addEventListener('keydown',e=>{if(e.target===barra)return;
  if(e.key==='ArrowLeft'){passo(-1);e.preventDefault();} if(e.key==='ArrowRight'){passo(1);e.preventDefault();}});
tamanho();mostra();
const t0=performance.now();
function tick(t){const f=Math.floor((t-t0)/(1000/60))%2, s=IM[i];
  const im=modo==='alt'?(f?s.B:s.A):s[modo]; if(im.complete)ctx.drawImage(im,0,0,tela.width,tela.height);
  requestAnimationFrame(tick);}
requestAnimationFrame(tick);
</script></body></html>'''

if __name__ == '__main__':
    main()
