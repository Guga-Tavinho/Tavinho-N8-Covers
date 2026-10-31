"""Teste de ponta a ponta (no PC) da firmware de capas, com o emulador 6502.

Roda o código real de capas_sd/EDFC/OS.BIN. São simulados: busca de arquivo do OS, cluster->LBA,
leitura de setor (servida de testes/COVERS.BIN), espera de vblank e a PPU (gravações registradas).
uso: python teste_capas_emu.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from emu6502 import CPU
from build_capas import main as build_main
from gerar_covers import name_crc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_LBA = 0x00012340
CLUSTER = 0x1234
FATBUF = 0x7400


def setup(buf, covers):
    mem = bytearray(0x10000)
    mem[0x8000:] = buf[0x6000:0xE000]
    mem[0x28], mem[0x29] = 0x00, 0x07           # c_sp
    mem[0x9F] = 0xFF
    mem[0x04E9], mem[0x04EA] = FATBUF & 255, FATBUF >> 8
    mem[0x04FF:0x0503] = bytes([0x22, 0, 0, 0])   # cluster da pasta edfc
    cpu = CPU(mem)
    ppu = dict(addr=0, latch=0, vram=bytearray(0x4000), mask=[], reads=0)

    def on_write(a, v):
        if a == 0x2006:
            if ppu['latch'] == 0: ppu['hi'] = v
            else: ppu['addr'] = ((ppu['hi'] << 8) | v) & 0x3FFF
            ppu['latch'] ^= 1; return True
        if a == 0x2007:
            ppu['vram'][ppu['addr']] = v; ppu['addr'] = (ppu['addr'] + 1) & 0x3FFF; return True
        if a == 0x2001: ppu['mask'].append(v); return True
        if a == 0x4014: ppu['oam'] = bytes(mem[v << 8:(v << 8) + 256]); return True
        if a in (0x2000, 0x2003, 0x2005): return True
        return False
    cpu.on_write = on_write

    def sp(): return mem[0x28] | mem[0x29] << 8
    def pop(n): s = sp() + n; mem[0x28], mem[0x29] = s & 255, s >> 8

    def findname(c):                     # file_find_by_name(dir32, nome, tam*, out*)
        s = sp()
        out = mem[s] | mem[s + 1] << 8
        name_p = mem[s + 4] | mem[s + 5] << 8
        name = bytes(mem[name_p:name_p + 11])
        if name == b'COVERS  BIN' and covers is not None:
            mem[out:out + 4] = CLUSTER.to_bytes(4, 'little')
        pop(10); c.a = 0
    def cl2lba(c):
        s = sp(); cl = int.from_bytes(mem[s:s + 4], 'little'); assert cl == CLUSTER, hex(cl)
        pop(4); v = BASE_LBA
        c.a, c.x, mem[0x2A], mem[0x2B] = v & 255, (v >> 8) & 255, (v >> 16) & 255, v >> 24
    def rdsec(c):
        s = sp(); lba = int.from_bytes(mem[s:s + 4], 'little'); pop(4)
        off = (lba - BASE_LBA) * 512
        ppu['reads'] += 1
        if covers is None or not 0 <= off < len(covers): c.a = 0x62; return
        mem[FATBUF:FATBUF + 512] = covers[off:off + 512].ljust(512, b'\0'); c.a = 0
    cpu.stubs[0x9DE0] = findname
    cpu.stubs[0x96B3] = cl2lba
    cpu.stubs[0xC53F] = rdsec
    for a in (0x8393, 0x83E6, 0xAB25): cpu.stubs[a] = lambda c: None
    return cpu, mem, ppu


def show_name(mem, name):
    mem[0x6320:0x6360] = bytes(64)
    b = name.encode()
    mem[0x6321:0x6321 + min(30, len(b))] = b[:30]
    if len(b) > 30: mem[0x6341:0x6341 + len(b) - 30] = b[30:60]


def main():
    buf, S = build_main()
    covers = open(os.path.join(ROOT, 'testes', 'COVERS.BIN'), 'rb').read()
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(('  OK   ' if cond else '  FALHA') + ' ' + msg); ok &= bool(cond)

    print('\n== init com COVERS.BIN')
    cpu, mem, ppu = setup(buf, covers)
    cpu.call(S['init_hook'])
    check(mem[S['enabled']] == 1, 'enabled = 1')
    check(int.from_bytes(mem[S['base']:S['base'] + 4], 'little') == BASE_LBA, 'base LBA = %08X' % BASE_LBA)

    def select(name):
        show_name(mem, name); ppu['mask'].clear(); ppu.pop('oam', None); ppu['reads'] = 0
        cpu.call(S['draw_hook'])
        r = dict(after_draw=list(ppu['mask']), pending=mem[S['pending']])
        cpu.call(S['idle_hook'])
        r.update(after_idle=list(ppu['mask']), reads=ppu['reads'], oam=ppu.get('oam'))
        return r

    for idx, name in enumerate(['Contra (USA).nes', 'Super Mario Bros. (World).nes',
                                'THE LEGEND OF ZELDA (USA) (REV 1).NES']):
        print('\n== selecionar', name)
        crc = name_crc(name)
        want = int.from_bytes(mem[S['want']:S['want'] + 4], 'little')
        r = select(name)
        check(int.from_bytes(mem[S['want']:S['want'] + 4], 'little') == crc, 'CRC no 6502 = %08X (Python)' % crc)
        check(r['after_draw'] == [0x0A] and r['pending'] == 1, 'desenho: sprites escondidos e capa pendente')
        rec = covers[(256 + 4 * idx) * 512:(256 + 4 * idx + 4) * 512]
        check(bytes(ppu['vram'][0x1000:0x1600]) == rec[512:2048], 'tiles na PPU $1000-$15FF = arquivo')
        check(bytes(ppu['vram'][0x3F10:0x3F20]) == rec[256:272], 'paleta em $3F10 = arquivo')
        check(r['oam'] == rec[0:256], 'OAM (DMA de $0200) = arquivo')
        check(r['after_idle'][-1:] == [0x1E], 'capa ligada (PPUMASK=$1E)')
        check(r['reads'] == 5, 'leituras de setor: %d (índice + meta + 3 tiles)' % r['reads'])

    print('\n== mesma ROM de novo (após fechar um menu): sem leitura')
    r = select('THE LEGEND OF ZELDA (USA) (REV 1).NES')
    check(r['pending'] == 0 and r['reads'] == 0 and r['after_draw'] == [0x1E], 'mostra direto, sem ler o SD')

    print('\n== ROM sem capa')
    r = select('Jogo Sem Capa.nes')
    check(r['reads'] == 1 and r['after_idle'] == [0x0A], 'lê só o índice e mantém escondido')
    r = select('Jogo Sem Capa.nes')
    check(r['reads'] == 0 and r['pending'] == 0, 'não tenta de novo')

    print('\n== pasta / .fds')
    for n in ('Jogos', 'Zelda.fds'):
        r = select(n)
        check(r['reads'] == 0 and r['pending'] == 0 and r['after_draw'] == [0x0A], n + ': sem capa, sem leitura')

    print('\n== rolando a lista (vários desenhos sem ociosidade) carrega só a última')
    for n in ('Contra (USA).nes', 'Jogos', 'Super Mario Bros. (World).nes'):
        show_name(mem, n); cpu.call(S['draw_hook'])
    ppu['reads'] = 0; cpu.call(S['idle_hook'])
    check(ppu['reads'] == 5 and bytes(ppu['vram'][0x1000:0x1600]) == covers[(256 + 4) * 512 + 512:(256 + 8) * 512],
          'carregou só Super Mario')

    print('\n== arquivo fragmentado (verificação errada no setor de metadados)')
    bad = bytearray(covers); bad[(256 + 0) * 512 + 272] ^= 0xFF
    cpu, mem, ppu = setup(buf, bytes(bad)); cpu.call(S['init_hook'])
    r = select('Contra (USA).nes')
    check(r['reads'] == 2 and r['after_idle'] == [0x0A], 'recusa a capa e não envia lixo para a PPU')

    print('\n== sem COVERS.BIN no cartão')
    cpu, mem, ppu = setup(buf, None); cpu.call(S['init_hook'])
    check(mem[S['enabled']] == 0, 'enabled = 0')
    r = select('Contra (USA).nes')
    check(r['reads'] == 0 and r['after_draw'] == [0x0A], 'nada é lido, sprites escondidos')

    print('\nRESULTADO:', 'TUDO OK' if ok else 'HÁ FALHAS')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
