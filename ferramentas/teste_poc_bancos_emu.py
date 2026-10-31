"""Teste no PC da POC de troca de banco de CHR no meio da tela (build_poc_bancos.py).

Confere a lógica no emulador 6502 (a PPU de verdade só no console):
  - chr2: a cópia da fonte ($826F) roda com o banco 0 e depois com o banco 2, e termina no banco 0;
  - a carga da capa grava os tiles com o banco 2 e volta ao banco 0; OAM[0] = sprite de sincronia, OAM[48] = o
    sprite 0 da capa;
  - split: espera o NMI, a flag do sprite 0 apagar e acender, escreve banco 2 e depois banco 0; CONTA OS CICLOS
    reais do código montado do sprite 0 até cada escrita;
  - sem sprite 0 (menu aberto etc.): desiste sem escrever e sem travar.
uso: python teste_poc_bancos_emu.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teste_capas_emu import setup, show_name, ROOT
import build_poc_bancos as P

CIC = {0xA9: 2, 0xA0: 2, 0xA2: 2, 0x20: 6, 0x60: 6, 0xAA: 2, 0xCA: 2, 0x88: 2, 0x8D: 4, 0x8E: 4, 0x2C: 4,
       0xA5: 3, 0x85: 3, 0xAD: 4, 0x4C: 3}
DESVIOS = {0xD0, 0xF0, 0x70, 0x50, 0x10, 0x30, 0x90, 0xB0}


def ciclos(cpu, pc, op):
    """Ciclos da instrução que acabou de rodar (só as do caminho temporizado)."""
    if op in DESVIOS:
        if cpu.pc == pc + 2: return 2
        return 3 + (1 if (cpu.pc & 0xFF00) != ((pc + 2) & 0xFF00) else 0)
    assert op in CIC, 'opcode $%02X sem tabela de ciclos em $%04X' % (op, pc)
    return CIC[op]


def main():
    ok = True

    def check(c, m):
        nonlocal ok
        print(('  OK   ' if c else '  FALHA') + ' ' + m); ok &= bool(c)

    buf, S = P.main()
    covers = open(os.path.join(ROOT, 'poc_bancos', 'EDFC', 'COVERS.BIN'), 'rb').read()
    cpu, mem, ppu = setup(buf, covers)
    estado = dict(banco=0, idx=None, regs=[], chr_bancos=set(), initchr=[])
    ow = cpu.on_write

    def on_write(a, v):
        if a == 0x4400: estado['idx'] = v; return True
        if a == 0x4401:
            estado['regs'].append((estado['idx'], v))
            if estado['idx'] == 0x82: estado['banco'] = v
            return True
        if a == 0x2007 and ppu['addr'] < 0x2000: estado['chr_bancos'].add(estado['banco'])
        return ow(a, v)
    cpu.on_write = on_write

    print('== chr2 (fonte nos bancos 0 e 2)')
    cpu.stubs[0x826F] = lambda c: estado['initchr'].append(estado['banco'])
    cpu.call(S['chr2'])
    check(estado['initchr'] == [0, 2] and estado['banco'] == 0, '$826F com o banco 0, depois com o 2; termina no 0')

    print('\n== carga da capa no banco 2')
    cpu.call(S['init_hook'])
    show_name(mem, 'Super Mario Bros. 3 (USA).nes')
    cpu.call(S['draw_hook'])
    estado['chr_bancos'].clear()
    mem[0x9E] = 0
    # a espera ociosa chama lc2 e depois o split; o split desiste (sem NMI no teste) e volta ao IDLE
    cpu.stubs[0xAB25] = lambda c: None
    cpu.call(S['idle_hook'])
    check(mem[S['has']] == 1, 'capa carregada')
    check(estado['chr_bancos'] == {2}, 'tiles da capa gravados só com o banco 2 (bancos usados: %s)' % estado['chr_bancos'])
    check(estado['banco'] == 0, 'depois da carga: banco 0')
    check(bytes(mem[0x0200:0x0204]) == bytes([15, 0x61, 0x20, 0]), 'OAM[0] = sprite de sincronia (Y 15, tile $61, atrás do fundo, X 0)')
    meta0 = covers[(256 + 8 * 7) * 512:(256 + 8 * 7) * 512 + 4]
    check(bytes(mem[0x02C0:0x02C4]) == meta0, 'OAM[48] = sprite 0 da capa')
    check(ppu['oam'][0:4] == bytes([15, 0x61, 0x20, 0]), 'OAMDMA feito de novo com o sprite de sincronia')

    print('\n== split (um quadro), contando ciclos')
    seq = {'n': 0}

    def le2002():
        seq['n'] += 1
        return 0x40 if seq['n'] <= 3 else (0x00 if seq['n'] <= 6 else 0x40)   # V: aceso, apaga, acende (sprite 0)
    leituras = {'9e': 0}
    orr = cpu.on_read

    def on_read(a):
        if a == 0x2002: return le2002()
        if a == 0x9E:
            leituras['9e'] += 1
            if leituras['9e'] == 4: mem[0x9E] = 1                     # o NMI chega
        return orr(a) if orr else None
    cpu.on_read = on_read
    estado['regs'].clear()
    cpu.push(0xFF); cpu.push(0xEF)                                       # retorno falso para o JMP IDLE
    cpu.stubs[0xAB25] = lambda c: setattr(c, 'pc', 0xFFF0)
    cpu.pc = S['split']
    contando, t, marcas = False, 0, []
    while cpu.pc != 0xFFF0:
        pc, op = cpu.pc, mem[cpu.pc]
        n_regs = len(estado['regs'])
        if pc == S['sw3']: contando, t = True, 3                         # BVS tomado = 3 ciclos já contados
        cpu.step()
        if contando:
            t += ciclos(cpu, pc, op)
            if len(estado['regs']) > n_regs: marcas.append(t)
    check(estado['regs'] == [(0x82, 2), (0x82, 0)], 'escreve banco 2 e depois banco 0: %s' % estado['regs'])
    d1 = marcas[0] if marcas else None
    d2 = marcas[1] - marcas[0] if len(marcas) > 1 else None
    check(d1 == 3 + 1753 + 12, 'do sprite 0 até o banco 2: %s ciclos (esperado 1768 = 3 + 1753 + 12)' % d1)
    check(d2 == 10935, 'do banco 2 até o banco 0: %s ciclos (esperado 10935 = 96 linhas + 70 pontos)' % d2)
    lin = lambda c: divmod(16 * 341 + 1 + c * 3, 341)
    check(lin(d1)[0] == 31 and 190 <= lin(d1)[1] <= 223 - 33 + 33, 'banco 2 na linha %d, ponto %d (+0..33)' % lin(d1))
    check(lin(d1 + d2)[0] == 127 and 257 <= lin(d1 + d2)[1] <= 300, 'banco 0 na linha %d, ponto %d (+0..33)' % lin(d1 + d2))

    print('\n== sem sprite 0 (menu aberto): desiste sem escrever')
    cpu.on_read = lambda a: 0x00 if a == 0x2002 else (1 if a == 0x9E else (orr(a) if orr else None))
    estado['regs'].clear()
    cpu.push(0xFF); cpu.push(0xEF)
    cpu.pc = S['split']; passos = 0
    while cpu.pc != 0xFFF0 and passos < 200000:
        cpu.step(); passos += 1
    check(cpu.pc == 0xFFF0 and estado['regs'] == [], 'voltou ao IDLE sem trocar de banco (%d instruções)' % passos)

    print('\nRESULTADO:', 'TUDO OK' if ok else 'HÁ FALHAS')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
