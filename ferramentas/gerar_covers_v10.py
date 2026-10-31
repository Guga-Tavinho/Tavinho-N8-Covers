"""Gera /EDFC/COVERS.BIN da CAPA GRANDE (firmware v10: capa 112x160 no navegador, espera + cancelamento).

uso:
  python gerar_covers_v10.py <pasta_das_capas_png> [--roms <pasta>]... [-o COVERS.BIN] [--preview <pasta>]
                             [--nitidez sim|nao] [--jobs N] [--modulo firmwares/MOD_v10.BIN]

Mesma associação ROM <-> capa do gerar_covers.py (associar_roms). Por capa, em <capas>/capas_config.json:
  nitidez / nitidez_forca (as mesmas da ferramenta; desligada = sem máscara de nitidez)
  flicker_grande: {"Contra (USA).png": true, ...}  (flicker nos sprites da capa grande; padrão
                  "flicker_grande_padrao", ou desligado)
  flicker_grande_lambda: {"Contra (USA).png": 0.1, ...}  (nível do flicker: λ, penalidade do tremido; padrão
                  "flicker_grande_lambda_padrao", ou 0.05)
  pontilhado: {"Zelda.png": true, ...}  (pontilhado/dithering no fundo; padrão "pontilhado_padrao", ou desligado)
  cores editadas na ferramenta: <capas>/paletas_editadas_grande (capa_grande_cores)
Projetos .json do Palette Lab não servem para a capa grande (são da capa pequena 64x96): usa-se o PNG de mesmo
nome, se houver.

Formato (setores de 512 bytes): 0-255 índice (balde = CRC & $FF, entradas [crc>>8, crc>>16, crc>>24, idx_lo,
idx_hi]); 256 zerado; 257-258 o módulo de 1 KB da firmware (carregado na WRAM, com a impressão digital no fim);
capa i em 512 + 64*i (conv_capa_grande.converter_v9). O setor é de 16 bits no 6502: no máximo 1015 capas.

--base COVERS.BIN: só ACRESCENTA. As capas que já estão no COVERS.BIN anterior (pelo CRC do nome da ROM no índice)
ficam exatamente como estão (os registros são copiados byte a byte); só as ROMs que ainda não estão nele são
convertidas e entram no fim. O índice é refeito com todas. O módulo do anterior tem que ser o desta firmware.
"""
import argparse, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gerar_covers import name_crc, MAX_NAME, PER_BUCKET
import associar_roms
import conv_v3
import capa_grande_cores as CC

AQUI = os.path.dirname(os.path.abspath(__file__))
MODULO = os.path.join(AQUI, 'firmwares', 'MOD_v10.BIN')
MAX_CAPAS = 1015                                  # 512 + 64*1014 + 63 < 65536
SETORES = 64
CW, CH = 112, 160
X0 = 8                                            # a capa começa 8 pixels depois da coluna 16 da tela


LAMBDAS = [0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25]   # níveis do flicker (0 = mais fiel e mais tremido)
LAMBDA_PADRAO = 0.05                                 # o da POC v8-v10 (aprovado no aparelho)


def lambda_grande(cfg, nome):
    """Nível do flicker da capa: o escolhido para ela, ou o padrão."""
    return float(cfg.get('flicker_grande_lambda', {}).get(nome, cfg.get('flicker_grande_lambda_padrao', LAMBDA_PADRAO)))


def definir_lambda_grande(cfg, nome, lam):
    """lam = λ, ou None (tira a escolha: a capa segue o padrão)."""
    v = dict(cfg.get('flicker_grande_lambda', {}))
    if lam is None or abs(lam - float(cfg.get('flicker_grande_lambda_padrao', LAMBDA_PADRAO))) < 1e-9: v.pop(nome, None)
    else: v[nome] = lam
    cfg['flicker_grande_lambda'] = dict(sorted(v.items()))


def pontilhado_de(cfg, nome):
    """Pontilhado (dithering) no fundo da capa: a escolha dela, ou o padrão (desligado)."""
    return bool(cfg.get('pontilhado', {}).get(nome, cfg.get('pontilhado_padrao', False)))


def definir_pontilhado(cfg, nome, valor):
    v = dict(cfg.get('pontilhado', {}))
    if valor is None or bool(valor) == bool(cfg.get('pontilhado_padrao', False)): v.pop(nome, None)
    else: v[nome] = bool(valor)
    cfg['pontilhado'] = dict(sorted(v.items()))


def flicker_grande(cfg, nome):
    """Flicker nos sprites da capa grande: a escolha da capa, ou o padrão (desligado)."""
    return bool(cfg.get('flicker_grande', {}).get(nome, cfg.get('flicker_grande_padrao', False)))


def definir_flicker_grande(cfg, nome, valor):
    """valor = True/False, ou None (tira a escolha: a capa segue o padrão)."""
    v = dict(cfg.get('flicker_grande', {}))
    if valor is None or bool(valor) == bool(cfg.get('flicker_grande_padrao', False)): v.pop(nome, None)
    else: v[nome] = bool(valor)
    cfg['flicker_grande'] = dict(sorted(v.items()))


def ler_base(caminho, modulo=None):
    """COVERS.BIN anterior -> dict(crcs={crc: idx}, n=registros, registros=bytes) ou str (por que não serve)."""
    try:
        d = open(caminho, 'rb').read()
    except OSError as ex:
        return 'não consegui ler %s: %s' % (caminho, ex)
    if len(d) < 512 * 512 or len(d) % 512 or (len(d) // 512 - 512) % SETORES:
        return 'não é um COVERS.BIN da capa grande (tamanho %d bytes)' % len(d)
    if modulo is not None and d[257 * 512:259 * 512] != modulo:
        return 'o COVERS.BIN é de outra versão da firmware (o módulo não confere): gere a firmware completa'
    n = (len(d) // 512 - 512) // SETORES
    crcs = {}
    for b in range(256):
        sec = d[b * 512:b * 512 + 512]
        for k in range(0, 510, 5):
            if sec[k + 4] == 0xFF: break
            crc = b | sec[k] << 8 | sec[k + 1] << 16 | sec[k + 2] << 24
            idx = sec[k + 3] | sec[k + 4] << 8
            if idx >= n: return 'o índice aponta para a capa %d, mas o arquivo só tem %d' % (idx, n)
            crcs[crc] = idx
    return dict(crcs=crcs, n=n, registros=d[512 * 512:])


def converter(args):
    """(png, forca, flicker[, pasta das capas[, λ]]) -> (registro, prévia percebida 112x160, quadro A, quadro B,
    info) ou str (erro). Com a pasta das capas, aplica as cores editadas na ferramenta (capa_grande_cores)."""
    import conv_capa_grande as G
    import capa_grande_cores as CC
    import sim_tela_cheia as S
    png, forca, flicker = args[:3]
    capas = args[3] if len(args) > 3 else None
    lam = args[4] if len(args) > 4 and args[4] is not None else LAMBDA_PADRAO
    pont = bool(args[5]) if len(args) > 5 else False
    progresso = args[6] if len(args) > 6 else None
    try:
        reg, vista, info = G.converter_v9(png, 0, forca, flicker=flicker, lam=lam, pontilhado=pont,
                                          progresso=progresso)
    except Exception as ex:
        return '%s: %s' % (type(ex).__name__, ex)
    corta = lambda a: np.asarray(a)[:, X0:X0 + CW].astype(np.uint8)
    est = info['est']
    orig = CC.paletas(est)
    P, A, B = corta(vista), corta(info['quadro_a']), corta(info['quadro_b'])
    if pont: A, B, P = CC.renderizar(est, orig)                         # os pontos de verdade (a vista é a mistura)
    novo = CC.ler(CC.arquivo(capas, png, forca, flicker, lam, pont), orig) if capas else None
    if novo:
        reg = CC.aplicar_reg(reg, novo)
        A, B, P = CC.renderizar(est, novo)
    tremido = float(np.sqrt(((S.lab(A.astype(float)) - S.lab(B.astype(float))) ** 2).sum(-1)).mean())
    return reg, P, A, B, dict(erro=info['erro'], cor3=info['cor3'], sprites=info['sprites'], flicker=flicker,
                              est=est, orig=orig, editada=bool(novo), lam=lam if flicker else None, tremido=tremido,
                              pontilhado=pont)


_FILA = None                                      # nos processos da ferramenta: fila do andamento das prévias


def iniciar_worker(fila):
    """Initializer do pool da ferramenta: guarda a fila por onde o andamento de cada prévia volta para a janela."""
    global _FILA
    _FILA = fila


def previa(png, forca, flicker, lam=None, pont=False):
    """Para a ferramenta (num processo do pool): imagens + estrutura (para o editor de cores), sem edições.
    O andamento vai para a fila do iniciar_worker como ((png, forca, flicker, lam, pont), fração)."""
    chave, ultimo = (png, forca, flicker, lam if flicker else None, pont), [0.0]

    def avisa(f):
        if _FILA is not None and (f - ultimo[0] >= 0.02 or f >= 1):
            ultimo[0] = f
            try:
                _FILA.put((chave, f))
            except Exception:
                pass
    r = converter((png, forca, flicker, None, lam, pont, avisa))
    if isinstance(r, str): raise RuntimeError(r)
    _, P, A, B, info = r
    return dict(info, P=P, A=A, B=B)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('capas')
    ap.add_argument('-o', '--saida', default='COVERS.BIN')
    ap.add_argument('--roms', action='append', help='pasta de ROMs (pode repetir)')
    ap.add_argument('--preview')
    ap.add_argument('--jobs', type=int, default=1)
    ap.add_argument('--nitidez', choices=('sim', 'nao'), default='sim',
                    help='nitidez das capas sem escolha salva em capas_config.json')
    ap.add_argument('--modulo', default=MODULO, help='módulo de 1 KB da firmware v10 (MOD_v10.BIN)')
    ap.add_argument('--base', help='COVERS.BIN anterior: mantém as capas dele e só acrescenta as ROMs novas')
    a = ap.parse_args()
    modulo = open(a.modulo, 'rb').read()
    assert len(modulo) == 1024, 'módulo com %d bytes (esperado 1024)' % len(modulo)
    base = dict(crcs={}, n=0, registros=b'')
    if a.base:
        base = ler_base(a.base, modulo)
        if isinstance(base, str): sys.exit('ERRO: ' + base)

    avisos, pngs = [], {}
    for f in sorted(os.listdir(a.capas)):
        if f.lower().endswith('.png'): pngs[os.path.splitext(f)[0].lower()] = f
    so_json = sorted(f for f in os.listdir(a.capas) if f.lower().endswith('.json') and f != conv_v3.ARQ_CONFIG
                     and os.path.splitext(f)[0].lower() not in pngs)
    if so_json:
        avisos.append('%d projeto(s) .json sem PNG de mesmo nome (a capa grande usa o PNG): %s'
                      % (len(so_json), ', '.join(so_json[:10]) + (', …' if len(so_json) > 10 else '')))
    jobs = []
    if a.roms:
        roms = associar_roms.listar_roms(a.roms)
        assoc = associar_roms.associar(roms, list(pngs.values()))
        usadas = set()
        for r in roms:
            f, n = assoc[r]
            if f is None: continue
            usadas.add(f)
            if not associar_roms.exata(r, f, n):
                print('associada: %s  <-  %s  (%.0f%%)' % (r, f, n * 100), flush=True)
            jobs.append((os.path.join(a.capas, f), r))
        sobra = sorted(f for f in pngs.values() if f not in usadas)
        if len(sobra) <= 100: avisos += ['sem ROM correspondente: ' + f for f in sobra]
        else: avisos.append('%d imagens sem ROM associada (normal numa coleção grande de capas)' % len(sobra))
        sem_capa = [r for r in roms if assoc[r][0] is None]
        if sem_capa:
            avisos.append('%d de %d ROMs sem capa: %s' % (len(sem_capa), len(roms), ', '.join(sem_capa[:30]) +
                                                          (', …' if len(sem_capa) > 30 else '')))
    else:
        jobs = [(os.path.join(a.capas, f), os.path.splitext(f)[0] + '.nes') for _, f in sorted(pngs.items())]

    fila, seen = [], {}
    for png, name in jobs:
        try:
            name.encode('ascii')
        except UnicodeEncodeError:
            avisos.append('nome com acento/caractere especial (o OS pode mostrar diferente), pulado: ' + name); continue
        if len(name) > MAX_NAME:
            avisos.append('nome com mais de %d caracteres (o OS corta), pulado: %s' % (MAX_NAME, name)); continue
        crc = name_crc(name)
        if crc in seen:
            avisos.append('CRC repetido entre "%s" e "%s"; mantido o primeiro' % (seen[crc], name)); continue
        seen[crc] = name
        if crc in base['crcs']: continue                              # já está no COVERS.BIN anterior: fica como está
        if base['n'] + len(fila) >= MAX_CAPAS:
            avisos.append('limite de %d capas da capa grande atingido' % MAX_CAPAS); break
        fila.append((png, name, crc))
    if a.base:
        print('COVERS.BIN anterior: %d capa(s) mantida(s) como estão; %d ROM(s) nova(s) para acrescentar'
              % (base['n'], len(fila)), flush=True)

    cfg = conv_v3.ler_config(a.capas)
    opcoes = {}
    for png in dict.fromkeys(p for p, _, _ in fila):             # cada capa uma vez (várias ROMs podem usá-la)
        nome = os.path.basename(png)
        forca = conv_v3.nitidez_efetiva(cfg, nome, a.nitidez == 'sim')
        flk = flicker_grande(cfg, nome)
        lam = lambda_grande(cfg, nome) if flk else None
        pont = pontilhado_de(cfg, nome)
        opcoes[png] = (png, forca, flk, a.capas, lam, pont)
        if flk: print('flicker: %s (λ %.2f)' % (nome, lam), flush=True)
        if forca: print('nitidez: %s (%d%%)' % (nome, forca), flush=True)
        if pont: print('pontilhado: %s' % nome, flush=True)
        if os.path.exists(CC.arquivo(a.capas, png, forca, flk, lam or LAMBDA_PADRAO, pont)):
            print('cores editadas: %s' % nome, flush=True)
    # as com flicker (~1,5 min cada) primeiro, para o paralelismo render mais
    ordem = sorted(opcoes, key=lambda p: not opcoes[p][2])
    if a.jobs > 1 and len(ordem) > 1:
        from multiprocessing import Pool
        pool = Pool(a.jobs)
        it = pool.imap(converter, [opcoes[p] for p in ordem])
    else:
        pool, it = None, map(converter, [opcoes[p] for p in ordem])
    feitos = {}
    pendentes = list(ordem)

    def resultado(png):
        while png not in feitos:
            feitos[pendentes.pop(0)] = next(it)
        return feitos[png]

    registros, entradas = [], []
    if a.preview: os.makedirs(a.preview, exist_ok=True)
    from PIL import Image
    previas_feitas = set()
    for png, name, crc in fila:
        res = resultado(png)
        if isinstance(res, str):
            if png not in previas_feitas: avisos.append('não foi possível usar %s: %s' % (os.path.basename(png), res))
            previas_feitas.add(png)
            continue
        reg = bytearray(res[0])
        reg[0:3] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
        if a.preview:
            Image.fromarray(res[1]).resize((CW * 2, CH * 2), Image.Resampling.NEAREST).save(
                os.path.join(a.preview, os.path.splitext(name)[0] + '.png'))
        entradas.append((crc, base['n'] + len(registros), name))
        registros.append(bytes(reg))
        print('%5d  %08X  %s' % (base['n'] + len(registros) - 1, crc, name), flush=True)
    if pool: pool.close()

    baldes = [[] for _ in range(256)]
    for crc, idx in sorted(base['crcs'].items(), key=lambda t: t[1]): baldes[crc & 0xFF].append((crc, idx))
    for crc, idx, _ in entradas: baldes[crc & 0xFF].append((crc, idx))
    indice = bytearray()
    for b in baldes:
        if len(b) > PER_BUCKET: sys.exit('balde com %d capas (máx. %d)' % (len(b), PER_BUCKET))
        sec = bytearray([0xFF] * 512)
        for k, (crc, idx) in enumerate(b):
            sec[k * 5:k * 5 + 5] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255, idx & 255, idx >> 8])
        indice += sec
    with open(a.saida, 'wb') as out:
        out.write(bytes(indice) + bytes(512) + modulo + bytes(253 * 512))
        out.write(base['registros'])                                    # as anteriores, byte a byte
        for r in registros: out.write(r)
    assert os.path.getsize(a.saida) == (512 + SETORES * (base['n'] + len(registros))) * 512
    print('\n%d capas -> %s (%d KB)%s' % (base['n'] + len(entradas), a.saida, os.path.getsize(a.saida) // 1024,
                                         ' (%d mantidas + %d novas)' % (base['n'], len(entradas)) if a.base else ''))
    for w in avisos: print('AVISO:', w)


if __name__ == '__main__':
    main()
