"""Gera /EDFC/COVERS.BIN para a firmware de capas (build_capas.py).

uso:
  python gerar_covers.py <pasta_das_capas_png> [-o COVERS.BIN] [--roms <pasta_das_roms>] [--preview <pasta>]
  python gerar_covers.py --roms <pasta_das_roms> --sinteticas [-o COVERS.BIN]
      (capa de TESTE para cada ROM sem PNG: cor própria + início do nome; serve para validar no aparelho)

Cada capa é um PNG com o MESMO nome da ROM (ex.: "Contra (USA).png" para "Contra (USA).nes").
Também vale um PROJETO do Palette Lab (.json) com o mesmo nome: ele tem prioridade sobre o PNG.
No formato v1, um projeto no modo capa (64x96, bloco 8x16) é usado como está, sem reconverter.
Com --roms, o nome exato do arquivo .nes é tirado da pasta de ROMs (subpastas incluídas) pela associação
inteligente de associar_roms.py: "001 Contra (U).nes" recebe "Contra (USA).png". Várias ROMs podem usar a mesma
capa (convertida uma vez só). Sem --roms, usa-se o nome do PNG + ".nes".

Formato (setores de 512 bytes):
  0..255   índice: balde = CRC & $FF. Entradas de 5 bytes [crc>>8, crc>>16, crc>>24, idx_lo, idx_hi];
           fim do balde = entrada com idx_hi = $FF. Máx. 101 entradas por balde.
  256+4*i  capa i: setor 0 = OAM[256] + paleta[16] + verificação[3] (crc>>8, crc>>16, crc>>24)
                   setores 1-3 = 96 tiles (48 sprites 8x16, tabela de padrões 1)
CRC = CRC-32 padrão (zlib) sem o XOR final, sobre o nome exibido pelo OS (até 60 caracteres)
com cada byte OR $20 — exatamente o que o 6502 calcula a partir das linhas 25-26 da tela.
"""
import argparse, os, sys, zlib
sys.path.insert(0, os.path.dirname(__file__))
from build_poc import (png_read, png_write, resize, carregar_capa, quantize, make_tiles, make_oam, BLACK,
                       COVER_W, COVER_H, NES_RGB, ROOT)
import conv_v2
import conv_v3
import associar_roms
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'palette_lab'))
import capa_edfc

MAX_NAME = 60          # o OS mostra o nome em 2 linhas de 30 colunas
MAX_COVERS = 16320     # setor = 256 + 4*idx precisa caber em 16 bits (v2: 8*idx -> 8160)
PER_BUCKET = 101


def name_crc(name):
    data = bytes(c | 0x20 for c in name.encode('ascii'))
    return (~zlib.crc32(data)) & 0xFFFFFFFF


def synthetic(name, crc):
    """Capa de teste: fundo com cor derivada do CRC, moldura branca e o início do nome."""
    font = open(os.path.join(ROOT, 'firmware_base', 'EDFC', 'OS.BIN'), 'rb').read()[:0x800]
    cores = [0x01, 0x05, 0x06, 0x07, 0x09, 0x0A, 0x0B, 0x0C, 0x02, 0x03, 0x04, 0x08, 0x13, 0x16, 0x18, 0x19]
    v = NES_RGB[cores[crc % len(cores)]]
    bg = ((v >> 16) & 255, (v >> 8) & 255, v & 255)
    px = [[bg] * COVER_W for _ in range(COVER_H)]
    for y in range(COVER_H):
        for x in range(COVER_W):
            if x < 2 or x >= COVER_W - 2 or y < 2 or y >= COVER_H - 2: px[y][x] = (248, 248, 248)
    palavras = os.path.splitext(name)[0].replace('(', ' (').split()
    linhas, atual = [], ''
    for w in palavras:
        if len(atual) + len(w) + (1 if atual else 0) <= 7: atual = (atual + ' ' + w).strip()
        else:
            if atual: linhas.append(atual)
            atual = w[:7]
        if len(linhas) == 9: break
    if atual and len(linhas) < 9: linhas.append(atual)
    for li, txt in enumerate(linhas):
        for ci, ch in enumerate(txt):
            t = ord(ch) if 32 <= ord(ch) < 128 else ord('?')
            for r in range(8):
                lo, hi = font[t * 16 + r], font[t * 16 + 8 + r]
                for c in range(8):
                    if (lo >> (7 - c)) & 1 and not (hi >> (7 - c)) & 1:
                        X, Y = 4 + ci * 8 + c, 6 + li * 10 + r
                        if X < COVER_W - 2 and Y < COVER_H - 2: px[Y][X] = (252, 252, 252)
    return px


def cover_record(png_path, crc, name=None, v2=False, v3=False, lam=0.22, pal_dir=None, nitidez=False):
    stem = os.path.splitext(os.path.basename(png_path))[0] if png_path else None
    if png_path and nitidez and not png_path.lower().endswith('.json'):
        px_nitido = carregar_capa(png_path, nitidez)              # nitidez = força em % (ou True = 70)
    else:
        nitidez = False
    if v3:                                                   # POC: alternância só nas capas com imagem real
        chr0 = open(os.path.join(ROOT, 'firmware_base', 'EDFC', 'OS.BIN'), 'rb').read()[:0x1000]
        if png_path and png_path.lower().endswith('.json'):
            px = capa_edfc.project_pixels(capa_edfc.load_project(png_path))
        elif png_path:
            px = px_nitido if nitidez else carregar_capa(png_path)
        else:
            return conv_v3.record_v3(synthetic(name, crc), crc, chr0, flicker=False)
        return conv_v3.record_v3(px, crc, chr0, flicker=lam is not None, lam=lam,     # λ None: sem flicker
                                 pals=conv_v3.ler_paletas(pal_dir, stem, lam, px, nitidez))
    if png_path and png_path.lower().endswith('.json'):
        proj = capa_edfc.load_project(png_path)
        if not v2 and proj.is_capa():
            return capa_edfc.record_v1(proj, crc)            # ajustes feitos à mão preservados
        px = capa_edfc.project_pixels(proj)                  # outros casos: a imagem já convertida
        if v2:
            chr0 = open(os.path.join(ROOT, 'firmware_base', 'EDFC', 'OS.BIN'), 'rb').read()[:0x1000]
            return conv_v2.record_v2(px, crc, chr0, conv_v3.ler_paletas(pal_dir, stem, None, px))
        pals, assign, pix_idx, preview = quantize(px)
        meta = bytearray(512)
        meta[0:256] = make_oam(assign)
        pal16 = bytearray()
        for pl in pals: pal16 += bytes([BLACK] + pl)
        meta[256:272] = pal16
        meta[272:275] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
        return bytes(meta) + make_tiles(pix_idx), preview
    if png_path:
        px = px_nitido if nitidez else carregar_capa(png_path)
    else:
        px = synthetic(name, crc)
    if v2:
        chr0 = open(os.path.join(ROOT, 'firmware_base', 'EDFC', 'OS.BIN'), 'rb').read()[:0x1000]
        return conv_v2.record_v2(px, crc, chr0,
                                 conv_v3.ler_paletas(pal_dir, stem, None, px, nitidez) if png_path else None)
    pals, assign, pix_idx, preview = quantize(px)
    meta = bytearray(512)
    meta[0:256] = make_oam(assign)
    pal16 = bytearray()
    for p in pals: pal16 += bytes([BLACK] + p)
    meta[256:272] = pal16
    meta[272:275] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
    tiles = make_tiles(pix_idx)
    assert len(tiles) == 1536
    return bytes(meta) + tiles, preview


def com_crc(rec, v2, v3, crc_de, crc):
    """O mesmo registro de capa para outra ROM: só troca os 3 bytes de verificação do CRC no setor 0."""
    off = 312 if v3 else 284 if v2 else 272
    r = bytearray(rec)
    assert r[off:off + 3] == bytes([(crc_de >> 8) & 255, (crc_de >> 16) & 255, (crc_de >> 24) & 255])
    r[off:off + 3] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
    return bytes(r)


def _cover_record_safe(args):
    try:
        return cover_record(*args)
    except Exception as ex:
        return str(ex)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('capas', nargs='?')
    ap.add_argument('-o', '--saida', default='COVERS.BIN')
    ap.add_argument('--roms', action='append', help='pasta de ROMs (pode repetir)')
    ap.add_argument('--preview')
    ap.add_argument('--sinteticas', action='store_true', help='gera capa de teste para ROM sem PNG')
    ap.add_argument('--v2', action='store_true', help='formato EXPERIMENTAL v2 (sprites + fundo, 8 setores/capa)')
    ap.add_argument('--v3', action='store_true', help='POC v3: sprites + fundo + alternância (16 setores/capa)')
    ap.add_argument('--lambda', dest='lam', type=float, default=0.22,
                    help='v3: penalidade de tremido (0.05 fidelidade máxima, 0.15 intermediária, 0.20 suave, 0.22 = padrão)')
    ap.add_argument('--jobs', type=int, default=1, help='capas convertidas em paralelo (processos)')
    ap.add_argument('--flicker-por-capa', action='store_true',
                    help='v3: usa o nível de cada capa salvo em <capas>/capas_config.json ("flicker"); '
                         'capas sem escolha usam o padrão de lá ou --lambda')
    ap.add_argument('--paletas', help='pasta das paletas editadas à mão (padrão: <capas>/paletas_editadas)')
    ap.add_argument('--nitidez', choices=('sim', 'nao'), default='nao',
                    help='nitidez das capas sem escolha salva em <capas>/capas_config.json (a ferramenta usa "sim")')
    a = ap.parse_args()
    if not a.capas and not a.sinteticas:
        ap.error('informe a pasta das capas ou use --roms ... --sinteticas')
    if a.sinteticas and not a.roms:
        ap.error('--sinteticas precisa de --roms')

    roms = associar_roms.listar_roms(a.roms or [])

    entries, data, avisos = [], [], []
    seen = {}
    pngs = {}
    if a.capas:
        files = sorted(os.listdir(a.capas))
        for f in files:                                      # PNG primeiro; projeto .json do Palette Lab vence
            if f.lower().endswith('.png'): pngs[os.path.splitext(f)[0].lower()] = f
        for f in files:
            if f.lower().endswith('.json') and f != conv_v3.ARQ_CONFIG: pngs[os.path.splitext(f)[0].lower()] = f
    jobs = []                                        # (png ou None, nome da ROM)
    if a.roms:
        assoc = associar_roms.associar(roms, list(pngs.values()))
        usadas = set()
        for r in roms:
            f, n = assoc[r]
            if f is None:
                if a.sinteticas: jobs.append((None, r))
                continue
            usadas.add(f)
            if not associar_roms.exata(r, f, n):
                print('associada: %s  <-  %s  (%.0f%%)' % (r, f, n * 100), flush=True)
            jobs.append((os.path.join(a.capas, f), r))
        sobra = sorted(f for f in pngs.values() if f not in usadas)
        if len(sobra) <= 100:
            avisos += ['sem ROM correspondente: ' + f for f in sobra]
        else:
            avisos.append('%d imagens sem ROM associada (normal numa coleção grande de capas)' % len(sobra))
        sem_capa = [r for r in roms if assoc[r][0] is None]
        if sem_capa and not a.sinteticas:
            avisos.append('%d de %d ROMs sem capa: %s' % (len(sem_capa), len(roms), ', '.join(sem_capa[:30]) +
                                                          (', …' if len(sem_capa) > 30 else '')))
    else:
        jobs = [(os.path.join(a.capas, f), os.path.splitext(f)[0] + '.nes') for _, f in sorted(pngs.items())]
    fila = []                                        # (png, nome, crc) depois dos filtros
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
        if len(fila) >= (4080 if a.v3 else 8160 if a.v2 else MAX_COVERS):
            avisos.append('limite de %d capas atingido' % MAX_COVERS); break
        seen[crc] = name
        fila.append((png, name, crc))
    pal_dir = a.paletas or (os.path.join(a.capas, 'paletas_editadas') if a.capas else None)
    cfg = conv_v3.ler_config(a.capas) if a.capas else {}

    def lam_de(png):
        """Nível da capa: --v2 = sem flicker; --flicker-por-capa = o da capa (ou o padrão); senão --lambda."""
        if a.v2: return None
        if a.v3 and a.flicker_por_capa and png: return conv_v3.flicker_de(cfg, os.path.basename(png), a.lam)
        return a.lam
    nit = lambda png: bool(png) and not png.lower().endswith('.json') and \
        conv_v3.nitidez_efetiva(cfg, os.path.basename(png), a.nitidez == 'sim')
    for png in dict.fromkeys(png for png, _, _ in fila):          # cada capa uma vez (várias ROMs podem usá-la)
        if not png: continue
        if a.v3 and a.flicker_por_capa:
            lam = lam_de(png)
            print('flicker: %s · %s' % (os.path.basename(png), 'sem' if lam is None else 'λ %.3f' % lam), flush=True)
        if nit(png): print('nitidez: %s (%d%%)' % (os.path.basename(png), nit(png)), flush=True)
        if pal_dir and (a.v2 or a.v3) and os.path.exists(conv_v3.arquivo_paletas(
                pal_dir, os.path.splitext(os.path.basename(png))[0], lam_de(png), nit(png))):
            print('paletas editadas à mão: %s' % os.path.basename(png), flush=True)
    primeira = {}                                    # capa -> CRC da 1ª ROM que a usa (as outras reaproveitam)
    for png, name, crc in fila:
        if png: primeira.setdefault(png, crc)
    args = [(png, crc, name, a.v2, a.v3, lam_de(png), pal_dir, nit(png)) for png, name, crc in fila
            if not png or primeira[png] == crc]
    if a.jobs > 1 and len(args) > 1:
        from multiprocessing import Pool
        pool = Pool(a.jobs)
        resultados = pool.imap(_cover_record_safe, args)
    else:
        pool = None
        resultados = map(_cover_record_safe, args)
    feitos = {}                                      # capa -> (registro, preview, crc) já convertida
    res_it = iter(resultados)
    for png, name, crc in fila:
        stem = os.path.splitext(name)[0]
        if png and png in feitos:
            res = feitos[png]
            if isinstance(res, str): continue
            rec, preview = com_crc(res[0], a.v2, a.v3, res[2], crc), res[1]
        else:
            res = next(res_it)
            if isinstance(res, str):
                if png: feitos[png] = res
                avisos.append('não foi possível usar %s: %s' % (os.path.basename(png or name), res)); continue
            rec, preview = res
            if png: feitos[png] = (rec, preview, crc)
        if a.preview:
            os.makedirs(a.preview, exist_ok=True)
            png_write(os.path.join(a.preview, stem + '.png'), COVER_W, COVER_H, preview, 3)
        entries.append((crc, len(data), name))
        data.append(rec)
        print('%5d  %08X  %s' % (len(data) - 1, crc, name), flush=True)
    if pool:
        pool.close()

    buckets = [[] for _ in range(256)]
    for crc, idx, name in entries:
        buckets[crc & 0xFF].append((crc, idx))
    index = bytearray()
    for b in buckets:
        if len(b) > PER_BUCKET:
            sys.exit('balde com %d capas (máx. %d)' % (len(b), PER_BUCKET))
        sec = bytearray([0xFF] * 512)
        for k, (crc, idx) in enumerate(b):
            sec[k * 5:k * 5 + 5] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255, idx & 255, idx >> 8])
        index += sec
    with open(a.saida, 'wb') as out:
        out.write(index)
        for rec in data: out.write(rec)
    print('\n%d capas -> %s (%d KB)' % (len(entries), a.saida, os.path.getsize(a.saida) // 1024))
    for w in avisos: print('AVISO:', w)


if __name__ == '__main__':
    main()
