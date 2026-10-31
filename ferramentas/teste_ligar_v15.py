"""O travamento ao ligar: a WRAM com BATERIA guarda o módulo da sessão anterior e o OS, ao iniciar, estraga
$6400-$66FF (flash_cmd_stub_save_ram) sem tocar na marca do fim. Simula isso no emulador de tempo real e carrega
capas: a v14 (confere a marca do fim) deve rodar o módulo estragado; a v15 (confere $66FC) deve reler e carregar.
uso: python teste_ligar_v15.py
"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teste_capas_emu import setup, show_name
from ppu_tempo import Tempo

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COVERS = os.path.join(R, 'firmware_gerada', 'EDFC', 'COVERS.BIN')
ROMS = ['Contra (U).nes', 'Mega Man 2 (U).nes', 'Super Mario Bros 3 (U) (PRG 0).nes']


def ligar(buf, S, modulo, semente):
    covers = open(COVERS, 'rb').read()
    cpu, mem, ppu = setup(buf, covers)
    r = random.Random(semente)
    mem[0x6400:0x6800] = modulo                       # o módulo da sessão anterior (bateria), com a marca
    for a in range(0x6400, 0x6700): mem[a] = r.randrange(256)   # o OS ao iniciar estraga $6400-$66FF
    v = ppu['vram']
    est = dict(banco=0, idx=None, bancos=[], chr=bytearray(16 * 4096), initchr=[], fase='ligar', lbas=[])
    base_w = cpu.on_write

    def on_write(a, val):
        if a == 0x4400: est['idx'] = val; return True
        if a == 0x4401: return True
        if a == 0x2007 and ppu['addr'] < 0x2000: ppu['addr'] += 1; return True
        return base_w(a, val)
    cpu.on_write = on_write
    tempo = Tempo(cpu, mem, ppu, est)
    cpu.stubs[0x826F] = lambda c: est.update(nmi_on=True, mask=0x0A)
    cpu.stubs[0x82FA] = lambda c: v.__setitem__(slice(0x2000, 0x2400), mem[0x6000:0x6400])
    cpu.stubs[0xAB25] = lambda c: None
    cpu.stubs[0x8393] = lambda c: tempo.ate_vblank()
    rd0 = cpu.stubs[0xC53F]
    lidos = []

    def rd(c):
        s = mem[0x28] | mem[0x29] << 8
        lidos.append(int.from_bytes(mem[s:s + 4], 'little')); tempo.cartao(); rd0(c)
    cpu.stubs[0xC53F] = rd
    cpu.call(S['chr_all']); cpu.call(S['init_hook'])
    res = []
    for rom in ROMS:
        show_name(mem, rom); cpu.call(S['draw_hook'])
        cpu.stubs[S['split']] = lambda c: None
        n, erro = 0, None
        try:
            while not mem[S['has']] and n < 400000:
                cpu.call(S['idle_hook'], max_steps=2_000_000); cpu.steps = 0; n += 1
        except Exception as ex:
            erro = type(ex).__name__
        del cpu.stubs[S['split']]
        res.append('ok' if mem[S['has']] and not erro else ('TRAVOU/' + (erro or 'sem carga')))
        mem[S['has']] = 0; mem[S['pending']] = 0
    releu = any(l - 0x12340 in (257, 258) for l in lidos)   # (BASE_LBA do teste_capas_emu)
    return res, releu


if __name__ == '__main__':
    import importlib
    ok = True
    for nome, esperado in (('build_capas_v14', False), ('build_capas_v15', True)):
        V = importlib.import_module(nome)
        buf, S, modulo = V.main(log=lambda *a: None)
        for s in (1, 2, 3):
            res, modulo_ok = ligar(bytearray(buf), S, bytes(modulo), s)
            bom = all(x == 'ok' for x in res)
            print('  %s ligada %d: %s (módulo relido do cartão: %s)' % (nome[-3:], s, res, modulo_ok), flush=True)
            if esperado: ok &= bom
    print('TUDO OK (a v15 recupera o módulo estragado)' if ok else 'HOUVE FALHAS')

