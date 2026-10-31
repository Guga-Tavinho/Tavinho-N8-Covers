"""Teste do início (chr_all) no emulador: a tela nunca fica ligada mostrando um banco de CHR ainda não preparado.

Roda o chr_all da firmware com o $826F REAL do OS (espera do vblank simulada). Acompanha: o banco na tela ($82),
a tela ligada/desligada ($2001) e quais bancos já foram preparados pelo $826F. Falha se, com a tela ligada, o
banco ativo ainda não foi preparado (= lixo da memória ao ligar na tela). Confere também que no fim os 8 bancos
estão prontos, o banco 0 está ativo e a tela está ligada.
uso: python teste_ligar_v12b.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu6502 import CPU
from build_poc import cpu2file


def ligar(buf, S):
    mem = bytearray(65536)
    mem[0x8000:0x10000] = buf[cpu2file(0x8000):cpu2file(0x8000) + 0x8000]
    est = dict(idx=None, banco=0, tela=True, prontos=set(), lixo=[], em_826f=False)
    cpu = CPU(mem)

    def wr(a, v):
        if a == 0x4400: est['idx'] = v; return True
        if a == 0x4401:
            if est['idx'] == 0x82:
                est['banco'] = v
                if est['tela'] and v not in est['prontos']: est['lixo'].append(('troca', v))
            return True
        if a == 0x2001:
            est['tela'] = bool(v & 0x18)
            if est['tela'] and est['banco'] not in est['prontos']: est['lixo'].append(('liga', est['banco']))
            return True
        if 0x2000 <= a < 0x2008: return True
        return False
    cpu.on_write = wr
    orig = 0x826F

    def initchr_marca(c):
        est['prontos'].add(est['banco'])
    # o $826F de verdade: marca o banco como pronto quando ele religa a tela ($82F0: LDA #$0A / STA $2001)
    cpu.stubs[0x8393] = lambda c: None                     # espera do vblank
    cpu.stubs[0x82F0] = lambda c: (est['prontos'].add(est['banco']), setattr(c, 'pc', 0x82F0 + 0)) and None
    del cpu.stubs[0x82F0]
    ant = cpu.step

    def passo():
        if cpu.pc == 0x82F0: est['prontos'].add(est['banco'])        # o banco ficou pronto (vai religar a tela)
        ant()
    cpu.step = passo
    est['tela'] = True                                     # ao ligar, a BIOS deixa a tela ligada
    cpu.call(S['chr_all'])
    return est


if __name__ == '__main__':
    import build_capas_v12 as V12
    import build_capas_v11 as V11
    ok = True
    buf, S, _ = V12.main(log=print)
    e = ligar(buf, S)
    bom = not e['lixo'] and e['prontos'] == {0, 1, 3, 5, 7, 9, 11, 13} and e['banco'] == 0 and e['tela']
    print('  %s v12b: lixo na tela: %s; bancos prontos %s; no fim banco %d, tela %s'
          % ('OK   ' if bom else 'FALHA', e['lixo'] or 'nenhum', sorted(e['prontos']), e['banco'],
             'ligada' if e['tela'] else 'desligada'))
    ok &= bom
    print('TUDO OK' if ok else 'HOUVE FALHAS')
