"""Teste no PC da firmware v2 (sprites + fundo) com o emulador 6502.
uso: python teste_capas_v2_emu.py   (usa experimento_v2/EDFC/COVERS.BIN)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from teste_capas_emu import setup, show_name, ROOT
from build_capas_v2 import main as build_main
from gerar_covers import name_crc

NT_BUF, ATTR_BUF = 0x6096, 0x63CD


def nt_rows(mem_or_vram, base):
    return b''.join(bytes(mem_or_vram[base + r * 32:base + r * 32 + 8]) for r in range(12))


def main():
    buf, S = build_main()
    covers = open(os.path.join(ROOT, 'experimento_v2', 'EDFC', 'COVERS.BIN'), 'rb').read()
    names = [l.rstrip('\n')[17:] for l in open(os.path.join(ROOT, 'experimento_v2', 'gerar.txt'))
             if l[:5].strip().isdigit()]
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(('  OK   ' if cond else '  FALHA') + ' ' + msg); ok &= bool(cond)

    cpu, mem, ppu = setup(buf, covers)
    # o setup do v1 calcula setores com 4 por capa; aqui o leitor só serve setores por LBA: ok
    cpu.call(S['init_hook'])
    check(mem[S['enabled']] == 1, 'COVERS.BIN encontrado')

    def select(name):
        show_name(mem, name); ppu['mask'].clear(); ppu.pop('oam', None); ppu['reads'] = 0
        cpu.call(S['draw_hook'])
        r = dict(after_draw=list(ppu['mask']), pending=mem[S['pending']])
        cpu.call(S['idle_hook'])
        r.update(after_idle=list(ppu['mask']), reads=ppu['reads'], oam=ppu.get('oam'))
        return r

    def verify(i, name):
        rec = covers[(256 + 8 * i) * 512:(256 + 8 * i + 8) * 512]
        meta = rec[:512]
        v = ppu['vram']
        check(r['oam'] == meta[0:256], 'OAM')
        check(bytes(v[0x3F04:0x3F20]) == meta[256:284], 'paletas $3F04-$3F1F (fundo + sprites)')
        check(bytes(v[0x3F0C:0x3F10]) == bytes([0x0F, 0x30, 0x00, 0x28]), 'paleta 3 (barra de baixo do OS) intacta')
        check(all(((b >> s) & 3) <= 2 for b in meta[384:403] for s in (0, 2, 4, 6)), 'atributos só usam paletas 0-2')
        check(bytes(v[0x1000:0x1600]) == rec[512:2048], 'tiles dos sprites ($1000)')
        check(bytes(v[0x0000:0x0200]) == rec[2048:2560], 'tiles do fundo $00-$1F ($0000)')
        check(bytes(v[0x0800:0x0A00]) == rec[2560:3072], 'tiles do fundo $80-$9F ($0800)')
        check(nt_rows(mem, NT_BUF) == meta[288:384], 'nametable no buffer de tela')
        check(nt_rows(v, NT_BUF - 0x4000) == meta[288:384], 'nametable na PPU ($2096..)')
        check(bytes(mem[ATTR_BUF:ATTR_BUF + 19]) == meta[384:403], 'atributos no buffer')
        check(bytes(v[0x23CD:0x23E0]) == meta[384:403], 'atributos na PPU ($23CD-$23DF)')
        check(r['after_idle'][-1:] == [0x1E] and mem[S['bgshown']] == 1, 'capa ligada')
        check(r['reads'] == 7, 'leituras: %d (índice + meta + 5)' % r['reads'])

    for name in ('Super Mario Bros. 3 (USA).nes', names[3], names[100]):
        i = names.index(name)
        print('\n== selecionar', name)
        r = select(name)
        check(r['after_draw'] == [0x0A] and r['pending'] == 1, 'desenho: escondida e pendente')
        verify(i, name)
        meta = covers[(256 + 8 * i) * 512:(256 + 8 * i) * 512 + 512]
        check(all(0 < t < 0x20 or 0x80 <= t < 0xA0 for t in meta[288:384]), 'nametable só usa slots livres')

    print('\n== popup (menu) por cima: hide só limpa o fundo no buffer e preserva o texto')
    mem[NT_BUF + 2 * 32 + 3] = 0x41               # 'A' de um popup dentro da área da capa
    vram_before = bytes(ppu['vram'][0x2000:0x2400])
    # caixa cinza do File Menu: o OS põe paleta 3 nos atributos (aqui: linha 2 inteira e o canto
    # esquerdo-superior do byte $63CD), por cima dos atributos da capa (paletas 1-2)
    attrs_capa = bytes(mem[ATTR_BUF:ATTR_BUF + 19])
    mem[ATTR_BUF + 3] = 0xFF
    mem[ATTR_BUF] = (mem[ATTR_BUF] & 0xFC) | 0x03
    esperado = bytearray(19); esperado[3] = 0xFF; esperado[0] = 0x03
    cpu.call(S['hide'])
    reg = nt_rows(mem, NT_BUF)
    check(reg[2 * 8 + 3] == 0x41 and sum(1 for t in reg if t not in (0, 0x41)) == 0, 'texto do popup fica, capa sai')
    check(any(b for b in attrs_capa), 'havia atributos da capa (paletas 1-2) antes')
    check(bytes(mem[ATTR_BUF:ATTR_BUF + 19]) == bytes(esperado), 'atributos: paleta 3 do menu fica, paletas da capa saem')
    check(bytes(ppu['vram'][0x2000:0x2400]) == vram_before, 'nametable da PPU não é tocada (o OS envia o buffer)')
    check(bytes(ppu['vram'][0x3F04:0x3F0C]) == bytes([0x0F] * 8), 'paletas 1-2 pretas na hora: o fundo da capa some junto')
    check(bytes(ppu['vram'][0x3F0C:0x3F10]) == bytes([0x0F, 0x30, 0x00, 0x28]), 'paleta 3 (menu/barra) intacta')
    check(mem[S['has']] == 0 and mem[S['bgshown']] == 0, 'capa marcada como não carregada')

    print('\n== menu fecha: o OS restaura a tela, o refresh chama hide de novo, a lista é redesenhada')
    i = 100
    meta = covers[(256 + 8 * i) * 512:(256 + 8 * i) * 512 + 512]
    mem[NT_BUF + 2 * 32 + 3] = 0
    for rr in range(12): mem[NT_BUF + rr * 32:NT_BUF + rr * 32 + 8] = meta[288 + rr * 8:296 + rr * 8]
    mem[ATTR_BUF:ATTR_BUF + 19] = meta[384:403]      # scr_restore_6400
    cpu.call(S['hide'])                              # o refresh que envia a tela restaurada
    r = select(names[100])                           # browser_draw_list do mesmo jogo
    check(r['pending'] == 1 and r['reads'] == 7, 'capa recarregada sozinha depois do menu')
    verify(100, names[100])
    i = names.index('Super Mario Bros. 3 (USA).nes')

    print('\n== sair para uma pasta: fundo da capa some (buffer e PPU)')
    r = select('Jogos')
    check(nt_rows(mem, NT_BUF) == bytes(96) and nt_rows(ppu['vram'], NT_BUF - 0x4000) == bytes(96), 'nametable limpa')
    check(bytes(ppu['vram'][0x23CD:0x23E0]) == bytes(19), 'atributos limpos na PPU')
    check(r['after_draw'][-1:] == [0x0A] and r['reads'] == 0, 'sprites escondidos, sem leitura')

    print('\n== voltar ao mesmo jogo: recarrega (o fundo tinha sido limpo)')
    r = select('Super Mario Bros. 3 (USA).nes')
    verify(i, 'Super Mario Bros. 3 (USA).nes')

    print('\n== mesmo jogo de novo sem nada no meio (ex.: depois de um popup): sem leitura')
    r = select('Super Mario Bros. 3 (USA).nes')
    check(r['reads'] == 0 and r['after_draw'] == [0x1E], 'mostra direto')

    print('\n== redesenho completo (troca de página): recarrega')
    show_name(mem, 'Super Mario Bros. 3 (USA).nes'); ppu['reads'] = 0
    cpu.call(S['mask_entry']); cpu.call(S['idle_hook'])
    check(ppu['reads'] == 7, 'recarregou')

    print('\n== jogo sem capa / .fds')
    r = select('Jogo Sem Capa.nes')
    check(r['reads'] == 1 and r['after_idle'][-1:] == [0x0A], 'só o índice, sem capa')
    r = select('Zelda.fds')
    check(r['reads'] == 0 and r['pending'] == 0, '.fds ignorado')

    print('\n== fragmentado / sem COVERS.BIN')
    bad = bytearray(covers); bad[(256 + 8 * i) * 512 + 284] ^= 0xFF
    cpu, mem, ppu = setup(buf, bytes(bad)); cpu.call(S['init_hook'])
    r = select('Super Mario Bros. 3 (USA).nes')
    check(r['reads'] == 2 and r['after_idle'][-1:] == [0x0A] and nt_rows(mem, NT_BUF) == bytes(96), 'recusado, nada desenhado')
    cpu, mem, ppu = setup(buf, None); cpu.call(S['init_hook'])
    check(mem[S['enabled']] == 0, 'sem COVERS.BIN: desligado')

    print('\nRESULTADO:', 'TUDO OK' if ok else 'HÁ FALHAS')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
