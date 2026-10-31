"""Referência para conferir otimizações: resume (SHA-1) tudo o que a conversão produz para várias capas e níveis.

uso: python referencia_conversao.py <pasta_do_codigo> <saida.json>
     (rodar uma vez com o código antigo e outra com o novo; os dois JSON têm que ser iguais)
"""
import hashlib, json, os, sys, time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPAS = [('Super Mario Bros. 3 (USA).png', False), ('contra.png', True), ('zelda.png', True),
         ('metroid.png', False), ('kirby.png', True)]
LAMS = [None, 0.05, 0.15, 0.22]


def h(x):
    return hashlib.sha1(json.dumps(x, sort_keys=True, default=lambda o: o.hex() if isinstance(o, bytes) else str(o))
                        .encode()).hexdigest()[:16]


def caso(args):
    pasta, nome, nit, lam = args
    sys.path.insert(0, pasta)
    import build_poc, conv_v2, conv_v3, sim_flicker
    T = build_poc.carregar_capa(os.path.join(ROOT, 'imagens', nome), nit)
    chr0 = open(os.path.join(ROOT, 'firmware_base', 'EDFC', 'OS.BIN'), 'rb').read()[:0x1000]
    t = time.time()
    if lam is None:
        r = conv_v2.convert(T)
        res = dict(sp_pals=r['sp_pals'], sp_assign=r['sp_assign'], spr=r['spr'], bg_pals=r['bg_pals'],
                   bg_assign=r['bg_assign'], tile_slot=r['tile_slot'], bg_chr=sorted(r['bg_chr'].items()),
                   bg=r['bg'], preview=r['preview'])
        rec = conv_v3.record_v3(T, 0x12345678, chr0, flicker=False)[0]
    else:
        s = sim_flicker.flicker_sim(T, lam, same_assign=True)
        res = dict(A={k: s['A'][k] for k in ('sp_pals', 'sp_assign', 'spr', 'bg_pals', 'frame')},
                   B={k: s['B'][k] for k in ('sp_pals', 'sp_assign', 'spr', 'bg_pals', 'frame')},
                   perc=s['perc'], tremor=repr(s['tremor']), conv_tiles=s['conv']['tile_slot'])
        rec = conv_v3.record_v3(T, 0x12345678, chr0, flicker=True, lam=lam)[0]
    dt = time.time() - t
    return '%s|%s|%s' % (nome, nit, lam), dict(partes={k: h(v) for k, v in res.items()}, registro=h(rec)), dt


if __name__ == '__main__':
    pasta, saida = sys.argv[1], sys.argv[2]
    casos = [(pasta, n, nit, lam) for n, nit in CAPAS for lam in LAMS]
    t0 = time.time()
    with Pool(min(len(casos), max(1, (os.cpu_count() or 2) - 1))) as p:
        out = p.map(caso, casos)
    ref = {k: v for k, v, _ in out}
    json.dump(ref, open(saida, 'w'), indent=1, sort_keys=True)
    for k, _, dt in out: print('%-45s %6.1f s' % (k, dt))
    print('total %.0f s -> %s' % (time.time() - t0, saida))
