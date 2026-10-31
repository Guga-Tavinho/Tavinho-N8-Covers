"""POC v12 no console: a v11 (texto embaixo da capa) + 20 jogos por página no navegador.

Só 5 capas (teste): Super Mario Bros 3, Mega Man 2, Castlevania, Contra e Zelda — com todas as versões dessas ROMs
que estão no cartão (nomes das prévias da firmware_gerada). As outras ROMs ficam sem capa.
COVERS.BIN v8: índice (0-255), módulo de 1 KB (257-258), capa i em 512 + 64*i.

uso:  python build_poc_capa_grande_v12.py [força da nitidez, padrão 180]
saída: poc_capa_grande_v12/EDFC/OS.BIN + COVERS.BIN
"""
import hashlib, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import ROOT
from gerar_covers import name_crc, PER_BUCKET
import associar_roms
import build_capas_v12 as V5
import build_poc_capa_grande as B
import conv_capa_grande as G

CAPAS = os.path.join(ROOT, 'imagens', 'Named_Boxarts')
SAIDA = os.path.join(ROOT, 'poc_capa_grande_v12', 'EDFC')
JOGOS = ('Super Mario Bros 3 ', 'Mega Man 2 ', 'Castlevania (', 'Contra (', 'Legend of Zelda, The (')


def roms_teste():
    return [r for r in B.roms_da_firmware() if r.startswith(JOGOS)]


# capas com flicker nos sprites (as outras sem); na ferramenta isso vira uma opção por capa
FLICKER = {'Super Mario Bros. 3 (USA).png', 'Mega Man 2 (USA).png', 'Castlevania (USA).png'}


def _conv(args):
    path, forca = args
    return G.converter_v9(path, 0, forca, flicker=os.path.basename(path) in FLICKER)[0]


def main(forca=180, log=print, roms=None, escrever=True):
    t0 = time.time()
    buf, S, modulo = V5.main(log=log)
    roms = roms if roms is not None else roms_teste()
    capas = associar_roms.listar_capas(CAPAS, ('capas_config.json',))
    assoc = associar_roms.associar(roms, capas)
    fila = []
    for r in roms:
        c, n = assoc[r]
        if c: fila.append((r, c, name_crc(r)))
    unicas = sorted({c for _, c, _ in fila})
    log('%d ROMs, %d capas: %s' % (len(fila), len(unicas), ', '.join(unicas)))
    from multiprocessing import Pool
    with Pool(min(len(unicas), max(1, (os.cpu_count() or 2) - 1))) as pool:
        res = dict(zip(unicas, pool.map(_conv, [(os.path.join(CAPAS, c), forca) for c in unicas])))
    registros, baldes = [], [[] for _ in range(256)]
    for idx, (r, c, crc) in enumerate(fila):
        reg = bytearray(res[c])
        reg[0:3] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255])
        registros.append(bytes(reg)); baldes[crc & 0xFF].append((crc, idx))
    indice = bytearray()
    for b in baldes:
        assert len(b) <= PER_BUCKET
        sec = bytearray([0xFF] * 512)
        for k, (crc, idx) in enumerate(b):
            sec[k * 5:k * 5 + 5] = bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255, idx & 255, idx >> 8])
        indice += sec
    assert len(modulo) <= 1024
    covers = bytes(indice) + bytes(512) + modulo.ljust(1024, b'\0') + bytes(253 * 512) + b''.join(registros)
    assert len(covers) == (512 + G.SETORES_V8 * len(registros)) * 512
    if escrever:
        os.makedirs(SAIDA, exist_ok=True)
        open(os.path.join(SAIDA, 'OS.BIN'), 'wb').write(buf)
        open(os.path.join(SAIDA, 'COVERS.BIN'), 'wb').write(covers)
        log('gerado: %s (%d ROMs, COVERS.BIN %.1f MB, módulo %d bytes) em %.0f s'
            % (SAIDA, len(registros), len(covers) / 2 ** 20, len(modulo), time.time() - t0))
        log('  OS.BIN SHA1 %s  COVERS.BIN SHA1 %s' % (hashlib.sha1(buf).hexdigest(), hashlib.sha1(covers).hexdigest()))
    return buf, S, covers, fila


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 180)
