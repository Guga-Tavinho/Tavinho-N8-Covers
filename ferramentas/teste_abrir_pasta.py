"""Abrir uma pasta no navegador, com o código do OS DE VERDADE + os ganchos das capas, em tempo real (ppu_tempo).

Roda a função do navegador do OS ($D953, browser_unk_d937) desde o começo: ela lê a pasta (fat_dir_scan, aqui
simulado com N itens), ordena (FUN_c822, real), desenha a lista (browser_draw_list, real; o nome de cada item vem
de dir_get_entry, simulado), manda a tela inteira (com o gancho do texto, w82fa) e entra na espera do botão (o
idle_hook das capas, que carrega a capa do item). Para depois de X quadros na espera. Se o OS ou um gancho travar
no caminho, o teste acusa (não chega na espera, ou passa do limite de instruções).
uso: python teste_abrir_pasta.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teste_capas_emu import setup
from ppu_tempo import Tempo, QUADRO
import build_poc_capa_grande as B


class Parou(Exception):
    pass


def abrir(modulo_poc, n_itens, nomes, quadros=60, max_passos=40_000_000, log=print):
    import importlib
    P = importlib.import_module(modulo_poc)
    buf, S, covers, fila = P.main(180, log=lambda *a: None, roms=None, escrever=False)
    cpu, mem, ppu = setup(buf, covers)
    v = ppu['vram']
    chr_os = bytes(buf[0:0x2000])
    pal_os = bytes(buf[0x6000 + 0x825F - 0x8000:][:16])
    est = dict(banco=0, idx=None, bancos=[], chr=bytearray(16 * 4096), initchr=[], fase='pasta', lbas=[])
    base_w = cpu.on_write

    def on_write(a, val):
        if a == 0x4400: est['idx'] = val; return True
        if a == 0x4401:
            if est['idx'] == 0x82: est['banco'] = val
            return True
        if a == 0x2007 and ppu['addr'] < 0x2000:
            est['chr'][est['banco'] * 4096 + ppu['addr']] = val; ppu['addr'] += 1; return True
        return base_w(a, val)
    cpu.on_write = on_write
    tempo = Tempo(cpu, mem, ppu, est)

    def initchr(c):
        b = est['banco']; est['chr'][b * 4096:b * 4096 + 0x2000] = chr_os
        v[0x3F00:0x3F10] = pal_os
        est['nmi_on'], est['mask'] = True, 0x0A
    cpu.stubs[0x826F] = initchr
    cpu.stubs[0x82FA] = lambda c: v.__setitem__(slice(0x2000, 0x2400), mem[0x6000:0x6400])
    cpu.stubs[0x8393] = lambda c: tempo.ate_vblank()
    rd0 = cpu.stubs[0xC53F]

    def rdsec(c):
        tempo.cartao(); rd0(c)
    cpu.stubs[0xC53F] = rdsec
    cpu.call(S['chr_all'])
    cpu.call(S['init_hook'])

    # a pasta: N itens; nomes (os primeiros são ROMs com capa), ordem i -> i, todos arquivos, sem ordenar
    ORD, ATR, NOME, ZERO = 0x7A00, 0x7B00, 0x7C00, 0x7D00
    mem[0x4F7], mem[0x4F8] = ORD & 255, ORD >> 8
    mem[0x4F5], mem[0x4F6] = ATR & 255, ATR >> 8
    mem[0x4F9], mem[0x4FA] = NOME & 255, NOME >> 8
    mem[0x49F], mem[0x4A0] = ZERO & 255, ZERO >> 8
    mem[ZERO] = 0

    def sp(): return mem[0x28] | mem[0x29] << 8

    def popa(k):
        s = sp() + k; mem[0x28], mem[0x29] = s & 255, s >> 8

    def dir_scan(c):
        popa(4); mem[0x549], mem[0x54A] = n_itens & 255, n_itens >> 8; c.a = c.x = 0
    cpu.stubs[0x8DC2] = dir_scan

    def dir_entry(c):                                    # dir_get_entry(item, nome*, ?, ?): o nome do item
        s = sp(); item = mem[s + 6] | mem[s + 7] << 8
        nome = nomes[item % len(nomes)].encode('ascii')
        dst = mem[s + 4] | mem[s + 5] << 8
        mem[dst:dst + len(nome) + 1] = nome + b'\0'
        popa(8); c.a = c.x = 0
    cpu.stubs[0x9254] = dir_entry
    esperas = []

    def espera(c):                                       # FUN_ab25 (lê o controle): um quadro; para depois de X
        esperas.append(est['t'])
        tempo.ate_vblank()
        mem[0x515] = 0
        if len(esperas) >= quadros: raise Parou()
    cpu.stubs[0xAB25] = espera
    mem[0x8259] = mem[0x825A] = 0
    mem[0x8258] = 0
    cpu.steps = 0
    try:
        cpu.call(0xD953, max_steps=max_passos)
        resultado = 'saiu da função (não devia)'
    except Parou:
        resultado = 'chegou na espera do botão'
    except Exception as ex:
        resultado = 'TRAVOU/ERRO: %s' % ex
    lista = [bytes(mem[0x6000 + r * 32:0x6000 + r * 32 + 16]).decode('latin1').rstrip('\0 ') for r in range(2, 24)]
    return resultado, len(esperas), mem[S['has']], lista


if __name__ == '__main__':
    nomes = B.roms_da_firmware()
    nomes = [n for n in nomes if n.startswith(('Super Mario Bros 3', 'Contra', 'Castlevania'))] + nomes
    ok = True
    for poc in ('build_poc_capa_grande_v11', 'build_poc_capa_grande_v12'):
        for n in (5, 20, 21, 40, 200):
            r, q, has, lista = abrir(poc, n, nomes)
            bom = r == 'chegou na espera do botão'
            ok &= bom
            itens = sum(1 for l in lista[:21] if l)
            print('  %s %s pasta com %3d itens: %s (%d quadros na espera, capa carregada: %s, %d linhas de lista)'
                  % ('OK   ' if bom else 'FALHA', poc[-3:], n, r, q, 'sim' if has else 'não', itens), flush=True)
    print('TUDO OK' if ok else 'HOUVE FALHAS')
