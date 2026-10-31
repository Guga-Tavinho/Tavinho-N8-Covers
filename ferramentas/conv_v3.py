"""Conversor v3 (POC): sprites + fundo + ALTERNÂNCIA de quadros (λ padrão 0,22).

Registro de 16 setores (8 KB) por capa no COVERS.BIN v3:
  setor 0  OAM do quadro A[256] (o B é o mesmo com tiles +96) | paletas $3F04-$3F1F do quadro A[28] em 256 |
           do quadro B[28] em 284 | verificação[3] em 312 | nametable[96] em 320 | atributos[19] em 416
  1-3      tiles de sprite do quadro A  -> PPU $1000 (tiles 0-95)
  4-6      tiles de sprite do quadro B  -> PPU $1600 (tiles 96-191)
  7        tiles de fundo $00-$1F       -> PPU $0000
  8        tiles de fundo $80-$9F       -> PPU $0800
  9-15     livres
A camada de fundo (tiles/nametable/atributos) é a mesma nos dois quadros; só as paletas alternam.
"""
import hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import BLACK, COVER_W, COVER_H
import conv_v2
from conv_v2 import X0, Y0, OS_PAL3

SECTORS = 16
LAMBDA = 0.22                      # escolhido pelo usuário (0,15 flicou muito no console; 0,05 = fidelidade máxima)


def chave_paletas(px):
    """Identifica a imagem (pixels 64x96) das paletas editadas: se a imagem mudar, a edição não vale mais."""
    return hashlib.sha1(json.dumps(px).encode()).hexdigest()


def sufixo_nitidez(nitidez):
    """'' (sem), '.nitido' (força padrão 70%) ou '.nitidoNN' (outra força)."""
    if not nitidez: return ''
    f = 70 if nitidez is True else int(nitidez)
    return '.nitido' if f == 70 else '.nitido%d' % f


def arquivo_paletas(pasta, stem, lam, nitidez=False):
    """<pasta>/<nome>.L0.220.json (nível com alternância) ou <nome>.v2.json (v2, sem alternância);
    com nitidez, <nome>.L0.220.nitido.json ou .nitido120.json (a imagem reduzida é outra, as paletas também)."""
    return os.path.join(pasta, '%s.%s%s.json' % (stem, 'v2' if lam is None else 'L%.3f' % lam,
                                                 sufixo_nitidez(nitidez)))


ARQ_CONFIG = 'capas_config.json'                 # na pasta das capas: {"nitidez": {"Contra (USA).png": true, ...}}


def nitidez_padrao(cfg, padrao):
    """Nitidez das capas sem escolha própria: a definida na ferramenta ("Definir padrão"), ou a do programa."""
    return bool(cfg.get('nitidez_padrao', padrao))


def nitidez_de(cfg, nome, padrao):
    """Nitidez da capa: a escolha salva para ela, ou o padrão. (Formato antigo: lista das capas com nitidez.)"""
    padrao = nitidez_padrao(cfg, padrao)
    v = cfg.get('nitidez', {})
    if isinstance(v, list): return nome in v or padrao
    return bool(v.get(nome, padrao))


SEM_FLICKER = 'sem'                              # no capas_config.json: capa sem alternância


def flicker_de(cfg, nome, padrao):
    """Nível de flicker da capa: λ (float) ou None (sem flicker); sem escolha salva, o padrão."""
    v = cfg.get('flicker', {}).get(nome, flicker_padrao(cfg, padrao))
    return None if v in (None, SEM_FLICKER) else float(v)


def flicker_padrao(cfg, padrao):
    v = cfg.get('flicker_padrao', padrao)
    return None if v in (None, SEM_FLICKER) else float(v)


def definir_flicker(cfg, nome, lam):
    """lam = λ, None (sem flicker) ou 'padrao' (tira a escolha da capa)."""
    v = dict(cfg.get('flicker', {}))
    if lam == 'padrao': v.pop(nome, None)
    else: v[nome] = SEM_FLICKER if lam is None else lam
    cfg['flicker'] = dict(sorted(v.items()))


FORCA_PADRAO = 70


def forca_padrao(cfg):
    return int(cfg.get('nitidez_forca_padrao', FORCA_PADRAO))


def forca_de(cfg, nome):
    """Força da nitidez da capa (%); sem escolha salva, a padrão (70 se não foi definida outra)."""
    return int(cfg.get('nitidez_forca', {}).get(nome, forca_padrao(cfg)))


def nitidez_efetiva(cfg, nome, padrao):
    """0 (sem nitidez) ou a força em % (10-200)."""
    return forca_de(cfg, nome) if nitidez_de(cfg, nome, padrao) else 0


def definir_forca(cfg, nome, forca):
    v = dict(cfg.get('nitidez_forca', {}))
    if forca is None or int(forca) == forca_padrao(cfg): v.pop(nome, None)      # igual ao padrão: segue o padrão
    else: v[nome] = int(forca)
    cfg['nitidez_forca'] = dict(sorted(v.items()))


def definir_nitidez(cfg, nome, valor):
    """valor = True/False, ou None (tira a escolha da capa: ela segue o padrão)."""
    v = cfg.get('nitidez', {})
    if isinstance(v, list): v = {n: True for n in v}
    if valor is None: v.pop(nome, None)
    else: v[nome] = bool(valor)
    cfg['nitidez'] = dict(sorted(v.items()))


def definir_nitidez_padrao(cfg, ligada, forca, nomes, padrao, congelar=()):
    """Novo padrão da nitidez (ligada + força). As capas em `congelar` (as que têm cores editadas e seguiam o
    padrão) ficam com o que tinham, para a edição continuar valendo; `nomes` = todas as capas da pasta."""
    antes = {n: (nitidez_de(cfg, n, padrao), forca_de(cfg, n)) for n in congelar}
    cfg['nitidez_padrao'] = bool(ligada)
    cfg['nitidez_forca_padrao'] = int(forca)
    for n, (lig, f) in antes.items():
        if nitidez_de(cfg, n, padrao) != lig: definir_nitidez(cfg, n, lig)
        if lig and forca_de(cfg, n) != f:
            v = dict(cfg.get('nitidez_forca', {})); v[n] = int(f); cfg['nitidez_forca'] = dict(sorted(v.items()))
    for n in nomes:                                              # força igual à nova padrão: passa a seguir o padrão
        if n not in antes and cfg.get('nitidez_forca', {}).get(n) == int(forca): definir_forca(cfg, n, None)


def ler_config(capas):
    try:
        return json.load(open(os.path.join(capas, ARQ_CONFIG), encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {}


def salvar_config(capas, cfg):
    with open(os.path.join(capas, ARQ_CONFIG), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def ler_paletas(pasta, stem, lam, px, nitidez=False):
    """Paletas editadas à mão ({'A': {'bg': [2 x 3], 'sp': [4 x 3]}, 'B': ...}) ou None."""
    if not pasta: return None
    arq = arquivo_paletas(pasta, stem, lam, nitidez)
    if not os.path.exists(arq): return None
    d = json.load(open(arq, encoding='utf-8'))
    if d.get('chave') != chave_paletas(px):
        print('AVISO: paletas editadas de "%s" ignoradas (a imagem mudou depois da edição)' % stem, flush=True)
        return None
    return d


def com_pontos(spr, pontos):
    """Camada de sprite com pontos pintados à mão ([[x, y, v], ...], v = 0..3; 0 = transparente)."""
    if not pontos: return spr
    spr = [list(row) for row in spr]
    for x, y, v in pontos: spr[y][x] = v
    return spr


def _sprite_chr(spr):
    out = bytearray()
    for row in range(COVER_H // 16):
        for col in range(COVER_W // 8):
            for half in range(2):
                lo = bytearray(8); hi = bytearray(8)
                for y in range(8):
                    for x in range(8):
                        v = spr[row * 16 + half * 8 + y][col * 8 + x]
                        lo[y] |= (v & 1) << (7 - x); hi[y] |= (v >> 1) << (7 - x)
                out += lo + hi
    return bytes(out)


def _pals(bg_pals, sp_pals):
    """28 bytes para $3F04-$3F1F: fundo 1-2, paleta 3 do OS intacta, sprites 0-3."""
    out = bytearray()
    for p in bg_pals[1:3]: out += bytes([BLACK] + list(p))
    out += OS_PAL3
    for p in sp_pals: out += bytes([BLACK] + list(p))
    assert len(out) == 28
    return bytes(out)


def record_v3(px, crc, chr0, flicker=True, lam=LAMBDA, pals=None):
    """pals: paletas editadas à mão (ler_paletas): cores e, em 'pix', pontos pintados na camada de sprite
    (cada bloco 8x16 tem o seu tile em cada quadro, então pintar um ponto não mexe nos outros blocos)."""
    if flicker:
        from sim_flicker import flicker_sim, frame_colors, avg_color
        sim = flicker_sim(px, lam, same_assign=True)
        r = sim['conv']; A, B = sim['A'], sim['B']
        preview = sim['perc']
        if pals:
            pix = pals.get('pix') or {}
            A = dict(A, bg_pals=[A['bg_pals'][0]] + pals['A']['bg'], sp_pals=pals['A']['sp'],
                     spr=com_pontos(A['spr'], pix.get('A')))
            B = dict(B, bg_pals=[B['bg_pals'][0]] + pals['B']['bg'], sp_pals=pals['B']['sp'],
                     spr=com_pontos(B['spr'], pix.get('B')))
            fa, fb = [frame_colors(q['sp_pals'], q['sp_assign'], q['spr'], q['bg_pals'], r['bg_assign'], r['bg'])
                      for q in (A, B)]
            preview = [[avg_color(fa[y][x], fb[y][x]) for x in range(COVER_W)] for y in range(COVER_H)]
    else:                                                        # capa sem alternância (A = B): igual à v2
        r = conv_v2.convert(px)
        if pals: r = conv_v2.com_paletas(r, pals)                # cores editadas no modo "sem flicker"
        A = B = dict(sp_pals=r['sp_pals'], sp_assign=r['sp_assign'], spr=r['spr'], bg_pals=r['bg_pals'])
        preview = r['preview']
    assert A['sp_assign'] == B['sp_assign']
    meta = bytearray(512)
    oam = bytearray([0xFF] * 256)
    for k in range(48):
        row, col = divmod(k, 8)
        oam[k * 4:k * 4 + 4] = bytes([Y0 + row * 16 - 1, (k * 2) | 1, A['sp_assign'][k], X0 + col * 8])
    meta[0:256] = oam
    meta[256:284] = _pals(A['bg_pals'], A['sp_pals'])
    meta[284:312] = _pals(B['bg_pals'], B['sp_pals'])
    meta[312:315] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
    meta[320:416] = bytes(r['tile_slot'])
    attr = bytearray(24)
    for by in range(COVER_H // 16):
        for bx in range(COVER_W // 16):
            tc, tr = 22 + bx * 2, 4 + by * 2
            shift = (2 if tc % 4 >= 2 else 0) + (4 if tr % 4 >= 2 else 0)
            attr[(tr // 4 - 1) * 8 + tc // 4] |= r['bg_assign'][by * 4 + bx] << shift
    meta[416:435] = attr[5:24]
    bga = bytearray(chr0[0x000:0x200]); bgb = bytearray(chr0[0x800:0xA00])
    for slot, data in r['bg_chr'].items():
        if slot < 0x20: bga[slot * 16:slot * 16 + 16] = data
        else: bgb[(slot - 0x80) * 16:(slot - 0x80) * 16 + 16] = data
    rec = bytes(meta) + _sprite_chr(A['spr']) + _sprite_chr(B['spr']) + bytes(bga) + bytes(bgb)
    rec += bytes(SECTORS * 512 - len(rec))
    return rec, preview
