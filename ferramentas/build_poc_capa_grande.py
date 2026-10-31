"""POC v4 no console: capa GRANDE no navegador + tela cheia parando o cursor 3 s (nitidez 180%).

Gera poc_capa_grande/EDFC/OS.BIN (build_capas_v4.py) e o COVERS.BIN v4 para as ROMs da firmware_gerada (os nomes
das prévias = os nomes das ROMs do cartão), com as capas de imagens/Named_Boxarts escolhidas pela associação
inteligente. Cada capa é convertida uma vez (em paralelo); ROMs com a mesma capa só trocam o CRC no setor 0.

COVERS.BIN v4: setores 0-255 índice (baldes por CRC & $FF, entradas [crc>>8, crc>>16, crc>>24, idx_lo, idx_hi]),
256 = visualizador de tela cheia, 257 = módulo ($7F00), capa i em 512 + 64*i (conv_capa_grande.py).

uso:  python build_poc_capa_grande.py [força da nitidez, padrão 180]
"""
import hashlib, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import ROOT
from asm6502 import assemble
from gerar_covers import name_crc, PER_BUCKET
import associar_roms
import build_capas_v4 as V4
import build_poc_tela_cheia as TC
import conv_capa_grande as G

CAPAS = os.path.join(ROOT, 'imagens', 'Named_Boxarts')
SAIDA = os.path.join(ROOT, 'poc_capa_grande', 'EDFC')
MAX_CAPAS = 1015

# visualizador da POC de tela cheia, sem índice: os dados ficam no registro da capa (csec + 15)
VIEWER = TC.VIEWER_SRC
i, j = VIEWER.index('v_main: LDA #<IDXSEC'), VIEWER.index('v_load: LDA vsec')
VIEWER = VIEWER[:i] + '''v_main: LDA csec                ; dados da tela cheia: registro da capa + 15
        CLC
        ADC #15
        STA vsec
        LDA csec+1
        ADC #0
        STA vsec+1
        JMP v_load
v_no:   CLC                     ; sem tela cheia: volta sem mexer
        RTS
''' + VIEWER[j:]
VIEWER = VIEWER.replace('''        BNE v_ret
        JSR setP
        LDY #3''', '''        BNE v_no
        JSR setP
        LDY #3''')
VIEWER = VIEWER.replace('''        CMP v_mag,Y
        BNE v_ret''', '''        CMP v_mag,Y
        BNE v_no''')
VIEWER = VIEWER.replace('''        LDA #0
        STA flk                 ; alternância da capa pequena parada
''', '')
i, j = VIEWER.index('        LDA #$20\n        STA $2000               ; NMI desligado durante o envio'), VIEWER.index('v_bank: LDX #$82')
VIEWER = VIEWER[:i] + '''        LDA #$20
        STA $2000               ; NMI desligado durante o envio
        JSR bg_clear            ; a capa grande sai do buffer (ela recarrega depois)
        JSR GFX_FULL            ; a tela do navegador de volta (buffer $6000)
        SEC                     ; mostrou: quem chamou refaz a fonte e a capa
        RTS
''' + VIEWER[j:]
HEAD_V = V4.HEAD + '''
vn       = $67E0
vtmp     = $67E1
vcnt     = $67E2
vsec     = $67E3
vmeta    = $67E5
'''


def montar_viewer(S):
    """Monta em $6400; NOPs (rodam uma vez, antes do laço) até os laços temporizados não cruzarem página."""
    syms = dict(S)
    for nops in range(0, 32):
        src = VIEWER.replace('v_loop: LDA #0', '        NOP\n' * nops + 'v_loop: LDA #0')
        code, vs = assemble(HEAD_V + src, 0x6400, syms, strict=False)
        code, vs = assemble(HEAD_V + src, 0x6400, {**syms, **vs})
        if all(vs[r] >> 8 == (vs[r] + 8) >> 8 for r in ('v_dly', 'v_dl', 'v_w3', 'v_hit', 'v_w1')): break
    else:
        raise AssertionError('laços temporizados cruzando página')
    assert len(code) <= 512, 'visualizador com %d bytes' % len(code)
    return code, vs


def _conv(args):
    path, forca = args
    try:
        reg, vista, info = G.converter(path, 0, forca)
        return reg, info['tiles']
    except Exception as ex:
        return str(ex), None


def roms_da_firmware():
    prev = os.path.join(ROOT, 'firmware_gerada', 'previews')
    return sorted(os.path.splitext(f)[0] + '.nes' for f in os.listdir(prev) if f.lower().endswith('.png'))


def main(forca=180, log=print, roms=None, jobs=None, escrever=True):
    t0 = time.time()
    buf, S, modulo = V4.main(log=log)
    viewer, VS = montar_viewer(S)
    roms = roms if roms is not None else roms_da_firmware()
    capas = associar_roms.listar_capas(CAPAS, ('capas_config.json',))
    assoc = associar_roms.associar(roms, capas)
    fila, seen = [], {}
    for r in roms:
        c, n = assoc[r]
        if not c: continue
        try: r.encode('ascii')
        except UnicodeEncodeError: continue
        crc = name_crc(r)
        if crc in seen or len(r) > 60: continue
        seen[crc] = r
        fila.append((r, c, crc))
    fila = fila[:MAX_CAPAS]
    unicas = sorted({c for _, c, _ in fila})
    log('%d ROMs com capa, %d capas diferentes para converter (nitidez %d%%)...' % (len(fila), len(unicas), forca))
    from multiprocessing import Pool
    with Pool(jobs or max(1, (os.cpu_count() or 2) - 1)) as pool:
        res = dict(zip(unicas, pool.map(_conv, [(os.path.join(CAPAS, c), forca) for c in unicas], chunksize=4)))
    erros = {c: r for c, (r, t) in res.items() if t is None}
    for c, e in erros.items(): log('  ERRO em %s: %s' % (c, e))
    fila = [f for f in fila if f[1] not in erros]
    entradas, registros = [], []
    for idx, (r, c, crc) in enumerate(fila):
        reg = bytearray(res[c][0])
        reg[0:3] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
        registros.append(bytes(reg)); entradas.append((crc, idx))
    baldes = [[] for _ in range(256)]
    for crc, idx in entradas: baldes[crc & 0xFF].append((crc, idx))
    indice = bytearray()
    for b in baldes:
        assert len(b) <= PER_BUCKET
        sec = bytearray([0xFF] * 512)
        for k, (crc, idx) in enumerate(b):
            sec[k * 5:k * 5 + 5] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255, idx & 255, idx >> 8])
        indice += sec
    covers = bytes(indice) + viewer.ljust(512, b'\0') + modulo.ljust(512, b'\0') + bytes(254 * 512) + b''.join(registros)
    assert len(indice) == 256 * 512 and covers[512 * 512:512 * 512 + 3] == (registros[0][:3] if registros else b'')
    if escrever:
        os.makedirs(SAIDA, exist_ok=True)
        open(os.path.join(SAIDA, 'OS.BIN'), 'wb').write(buf)
        open(os.path.join(SAIDA, 'COVERS.BIN'), 'wb').write(covers)
    log('gerado: %s (%d capas, COVERS.BIN %.1f MB, visualizador %d bytes) em %.0f s'
        % (SAIDA, len(registros), len(covers) / 2 ** 20, len(viewer), time.time() - t0))
    log('  OS.BIN SHA1 %s  COVERS.BIN SHA1 %s' % (hashlib.sha1(buf).hexdigest(), hashlib.sha1(covers).hexdigest()))
    return buf, S, covers, VS, fila


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 180)
