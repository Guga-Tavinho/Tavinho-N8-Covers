"""Teste no PC da POC v11 (v10 + "@tavinho.games" embaixo da capa) com TEMPO REAL (ppu_tempo): o NMI do OS interrompe o código na linha 241, o sprite 0
acerta na linha 16, $2002 apaga a meia escrita do $2006 — como no console.

Confere, nas 5 capas:
  - a carga: quantos quadros leva; a tela é desligada só abaixo da barra (linha >= 224) e religada antes do
    pré-render (linha 261); nenhuma escrita na PPU com a tela ligada fora do vblank;
  - a nametable INTEIRA na PPU (lista + capa) igual ao buffer do OS depois da carga e depois do aparecimento
    (pega endereço errado no $2006, como o lixo das fotos da v7);
  - as trocas de banco no quadro caem nas janelas; a tela reconstruída = a capa convertida;
  - botão (joypad lido pelo NMI do OS): esconde; recarga reaproveita o módulo; menu ($833D).
uso: python teste_capas_v11_emu.py
"""
import os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teste_capas_emu import setup, show_name, ROOT
from build_poc import NES_RGB
from ppu_tempo import Tempo, QUADRO, LINHA
import build_poc_capa_grande as B
import conv_capa_grande as G

NES = {i: ((c >> 16) & 255, (c >> 8) & 255, c & 255) for i, c in enumerate(NES_RGB)}
ROM = 'Super Mario Bros 3 (U) (PRG 1).nes'
BANCOS = [1, 3, 5, 7, 9, 11, 13]
BANCOS_FONTE = [0, 1, 3, 5, 7, 9, 11, 13]


ESCONDE = bytes([0x55]) * 20 + bytes([0x05]) * 4                  # v11: linhas 22-23 ficam na paleta 0 (o texto)


def main(modulo_poc='build_poc_capa_grande_v11', saida_img='poc_capa_grande_v11_exemplo.png'):
    import importlib
    P = importlib.import_module(modulo_poc)
    ok = True

    def check(c, m):
        nonlocal ok
        print(('  OK   ' if c else '  FALHA') + ' ' + m); ok &= bool(c)

    buf, S, covers, fila = P.main(180, log=lambda *a: None, roms=None, escrever=False)
    cpu, mem, ppu = setup(buf, covers)
    v = ppu['vram']
    chr_os = bytes(buf[0:0x2000])
    pal_os = bytes(buf[0x6000 + 0x825F - 0x8000:][:16])
    est = dict(banco=0, idx=None, bancos=[], chr=bytearray(16 * 4096), initchr=[], fase='init', lbas=[])
    base_w = cpu.on_write
    tempo = None

    def on_write(a, val):
        if a == 0x4400: est['idx'] = val; return True
        if a == 0x4401:
            if est['idx'] == 0x82: est['banco'] = val; est['bancos'].append((val, tempo.linha()))
            return True
        if a == 0x2007 and ppu['addr'] < 0x2000:
            est['chr'][est['banco'] * 4096 + ppu['addr']] = val; ppu['addr'] += 1; return True
        return base_w(a, val)
    cpu.on_write = on_write
    tempo = Tempo(cpu, mem, ppu, est)

    def initchr(c):
        b = est['banco']; est['initchr'].append(b)
        est['chr'][b * 4096:b * 4096 + 0x2000] = chr_os
        v[0x3F00:0x3F10] = pal_os
        est['nmi_on'], est['mask'] = True, 0x0A
    cpu.stubs[0x826F] = initchr
    cpu.stubs[0x82FA] = lambda c: v.__setitem__(slice(0x2000, 0x2400), mem[0x6000:0x6400])
    cpu.stubs[0xAB25] = lambda c: None
    cpu.stubs[0x8393] = lambda c: tempo.ate_vblank()
    rd0 = cpu.stubs[0xC53F]

    def rdsec(c):
        if est.get('t_sd') is None: est['t_sd'] = est['t']
        tempo.cartao()
        est['lbas'].append(int.from_bytes(mem[(mem[0x28] | mem[0x29] << 8):][:4], 'little'))
        rd0(c)
    cpu.stubs[0xC53F] = rdsec

    def quadro():
        cpu.push(0xFF); cpu.push(0xEF)
        cpu.stubs[0xAB25] = lambda c: setattr(c, 'pc', 0xFFF0)
        cpu.pc = S['idle_hook']; n = 0
        while cpu.pc != 0xFFF0 and n < 3_000_000:
            cpu.step(); n += 1
        cpu.stubs[0xAB25] = lambda c: None
        cpu.steps = 0

    def carregar(rom, desenhar=True):
        """Cursor para no jogo: chama a espera ociosa até a capa carregar. -> quadros de carga (espera em est)."""
        if desenhar:
            show_name(mem, rom)
            v[0x2320:0x2360] = mem[0x6320:0x6360]                   # o OS redesenha o nome na barra
            cpu.call(S['draw_hook'])
        est['eventos'].clear(); est['t_sd'] = None; t0 = est['t']
        cpu.stubs[S['split']] = lambda c: None                      # só a carga; o split é testado por quadro
        n = 0
        while not mem[S['has']] and n < 400000 and not est.get('parar'):
            cpu.call(S['idle_hook']); cpu.steps = 0; n += 1
            if est.get('desistiu_teste') and mem[S['pending']] == 1 and est['t_sd'] is not None: break
        del cpu.stubs[S['split']]
        est['espera'] = ((est['t_sd'] if est['t_sd'] is not None else est['t']) - t0) / QUADRO
        return (est['t'] - (est['t_sd'] or t0)) / QUADRO

    def janelas_ok():
        """Cada 'desliga' da carga: linha >= 224 e religa no mesmo quadro antes da 261."""
        ev = [x for x in est['eventos']]
        ruins = []
        for k, (o, l, f) in enumerate(ev):
            if o == 'desliga':
                prox = ev[k + 1] if k + 1 < len(ev) else None
                ponto = (l % 1) * 341
                if not (224 <= l < 241 and 257 <= ponto <= 320): ruins.append(('desliga', round(l, 2), round(ponto)))
                est['pontos'].append(round(ponto))
                if not prox or prox[0] != 'liga' or not (l < prox[1] < 261): ruins.append(('liga', prox and round(prox[1], 1)))
        return ruins, sum(1 for o, l, f in ev if o == 'desliga')

    def nt_igual(attrs_capa=None):
        """Células: PPU = buffer. Atributos: na região da capa a PPU tem os da capa (attrs_capa) e o buffer do OS
        fica com os dele (0 aqui); fora dela, PPU = buffer."""
        dif = [i for i in range(0x3C0) if v[0x2000 + i] != mem[0x6000 + i]]
        da = []
        for i in range(0x3C0, 0x400):
            r_, c_ = (i - 0x3C0) // 8, (i - 0x3C0) % 8
            na_capa = r_ < 6 and c_ >= 4
            esperado = attrs_capa[r_ * 4 + c_ - 4] if (na_capa and attrs_capa is not None) else mem[0x6000 + i]
            if v[0x2000 + i] != esperado or (na_capa and mem[0x6000 + i] != 0): da.append(i)
        return dif, da

    print('== fonte e init')
    cpu.call(S['chr_all'])
    check(sorted(est['initchr']) == sorted(BANCOS_FONTE), '$826F com os bancos %s' % est['initchr'])
    cpu.call(S['init_hook'])
    check(mem[S['enabled']] == 1, 'COVERS.BIN achado')
    nomes = B.roms_da_firmware()
    sel = nomes.index(ROM); ini = max(0, sel - 7)
    mem[0x6000:0x6400] = bytes(0x400)
    for i, n in enumerate(nomes[ini:ini + 21]):
        row = 2 + i
        if n == ROM: mem[0x6000 + row * 32 + 1] = ord('>')
        for k, ch in enumerate(n[:14]): mem[0x6000 + row * 32 + 2 + k] = ord(ch) + (0x80 if n == ROM else 0)
    for k in range(8): mem[0x63F0 + k] = 0xFF
    v[0x2000:0x2400] = mem[0x6000:0x6400]
    v[0x3F00:0x3F10] = pal_os
    ppu['oam'] = bytes([0xF0] * 256)

    print('\n== módulo velho na memória (a firmware anterior deixou o dela, com a marca antiga)')
    mem[0x6400:0x6800] = bytes([0xEA] * 0x3FC) + b'M7OK'
    marca = bytes(mem[S['lm_mg']:S['lm_mg'] + 4])
    check(marca != b'M7OK' and covers[257 * 512 + 0x3FC:257 * 512 + 0x400] == marca,
          'marca do módulo = impressão digital dele (%s), igual no COVERS.BIN' % marca.hex())
    est['lbas'].clear(); est['pontos'] = []

    print('\n== cargas (tempo real; leitura do cartão = %d ciclos)' % tempo.custo_cartao)
    capas_feitas, quadros = {}, {}
    usa3 = []
    for rom, capa, crc in [f for f in fila if f[0] == ROM] + fila:
        if capa in capas_feitas: continue
        est['fase'] = 'carga ' + capa[:12]
        q = carregar(rom)
        capas_feitas[capa] = rom; quadros[capa] = q
        if len(capas_feitas) == 1:
            base = int.from_bytes(mem[S['base']:S['base'] + 4], 'little')
            check(257 in [l - base for l in est['lbas']], '1ª carga relê o módulo do cartão (o velho tinha outra marca)')
        k = next(i for i, f in enumerate(fila) if f[0] == rom)
        reg = covers[(512 + 64 * k) * 512:(512 + 64 * k + 64) * 512]
        ruins, nj = janelas_ok()
        dif, da = nt_igual(ESCONDE)
        check(mem[S['has']] == 1 and not ruins and not dif and not da,
              '%s: %.1f quadros, %d janelas de tela desligada%s; nametable na PPU = buffer%s' % (
                  capa, q, nj, '' if not ruins else ' RUINS %s' % ruins[:3],
                  '' if not (dif or da) else ' — DIFERENTE em %d células e %d atributos (ex. %s)' % (len(dif), len(da), dif[:6])))
        quadro()                                                     # o aparecimento (1 quadro)
        dif, da = nt_igual(reg[9:33])
        check(mem[S['rev']] == 0 and not dif and not da, '   apareceu: nametable e atributos na PPU = buffer')
        c3 = reg[367]
        check(v[0x3F0F] == c3 and bytes(v[0x3F0D:0x3F0F]) == b'\x30\x00',
              '   paleta 3: cor 3 = $%02X (%s), branco e cinza da barra intactos' % (c3, 'a da capa' if c3 != 0x28 else
                                                                                   'o amarelo de sempre: não ajudava'))
        usa3.append((capa, c3))
        if capa == fila[[f[0] for f in fila].index(ROM)][1]: reg_mario = reg
    print('       média: %.1f quadros por capa; tela desligada no ponto %d-%d da linha 225 (intervalo: 257-320)'
          % (sum(quadros.values()) / len(quadros), min(est['pontos']), max(est['pontos'])))

    print('\n== quadro com a capa (Mario 3)')
    est['fase'] = 'quadro'
    carregar(ROM); quadro()
    quadro()
    oam_a, spal_a = bytes(ppu['oam']), bytes(v[0x3F10:0x3F20])          # quadro A (o flicker começa nele)
    est['bancos'].clear()
    quadro()
    oam_b, spal_b = bytes(ppu['oam']), bytes(v[0x3F10:0x3F20])          # quadro B
    troca_tiles = all(oam_b[k * 4 + 1] == oam_a[k * 4 + 1] ^ 0x80 for k in range(1, 64)) and oam_b[1] == oam_a[1]
    check(troca_tiles and spal_a != spal_b and [oam_a[k] for k in range(0, 256) if k % 4 != 1] ==
          [oam_b[k] for k in range(0, 256) if k % 4 != 1],
          'flicker: a cada quadro os tiles dos sprites trocam ($80, menos o sprite 0) e as paletas de sprite também')
    bs = [b for b, l in est['bancos']]
    check(bs == BANCOS, 'bancos no quadro: %s' % bs)
    trocas = []
    for k, (b, l) in enumerate(est['bancos'][1:]):
        y0 = 8 * (2 + 3 * (k + 1))
        trocas.append(l)
        check(y0 - 1 <= l <= y0 + 8, 'banco %d na linha %.1f (janela %d-%d)' % (b, l, y0 - 1, y0 + 8))
    nt_ppu, at_ppu, pal = bytes(v[0x2000:0x23C0]), bytes(v[0x23C0:0x2400]), bytes(v[0x3F00:0x3F10])

    def render(tr, oam, spal):
        img = np.zeros((240, 256, 3), np.uint8)
        banco = lambda y: 1 + 2 * sum(1 for t in tr if y >= t)
        for y in range(240):
            b = banco(y)
            for tx in range(32):
                t = nt_ppu[(y // 8) * 32 + tx]
                pp = est['chr'][b * 4096 + t * 16:][:16]
                a = at_ppu[(y // 32) * 8 + tx // 4] >> ((2 if tx & 2 else 0) + (4 if (y // 16) & 1 else 0)) & 3
                for x in range(8):
                    c = (pp[y & 7] >> (7 - x) & 1) | (pp[8 + (y & 7)] >> (7 - x) & 1) << 1
                    img[y, tx * 8 + x] = NES[pal[a * 4 + c] if c else pal[0]]
            bsp = banco(y - 1) + 1
            for k in range(63, -1, -1):
                sy, t, at, sx = oam[k * 4:k * 4 + 4]
                r = y - (sy + 1)
                if not 0 <= r < 16 or at & 0x20: continue
                bb = bsp * 4096 + (t & 0xFE) * 16 + (16 if r >= 8 else 0)
                lo, hi = est['chr'][bb + r % 8], est['chr'][bb + 8 + r % 8]
                for x in range(8):
                    c = (lo >> (7 - x) & 1) | (hi >> (7 - x) & 1) << 1
                    if c and sx + x < 256: img[y, sx + x] = NES[spal[(at & 3) * 4 + c]]
        return img
    import conv_sprites_grande as SPG
    _, vista, info8 = G.converter_v9(os.path.join(G.N.ROOT, 'imagens', 'Named_Boxarts', fila[[f[0] for f in fila].index(ROM)][1]), 0, 180, flicker=True)
    tr = [int(t) + 1 for t in trocas]
    qa, qb = render(tr, oam_a, spal_a), render(tr, oam_b, spal_b)
    par = lambda x, y: (x[16:176, 128:256] == info8['quadro_a']).all() and (y[16:176, 128:256] == info8['quadro_b']).all()
    check(par(qa, qb) or par(qb, qa), 'tela reconstruída: os 2 quadros = os do conversor (A e B, alternando)')
    tela = SPG._unlin((SPG._lin(qa) + SPG._lin(qb)) / 2).round().astype(np.uint8)
    dif = np.abs(tela[16:176, 128:256].astype(int) - vista.astype(int)).max()
    check(dif <= 1, 'o que o olho vê (média dos 2 quadros) = a imagem prevista (diferença máx. %d)' % dif)

    print('\n== capa sem flicker (Contra): nada pisca')
    rc = next(f[0] for f in fila if f[1].startswith('Contra'))
    carregar(rc); quadro(); quadro()
    o1, p1 = bytes(ppu['oam']), bytes(v[0x3F10:0x3F20])
    quadro()
    check(bytes(ppu['oam']) == o1 and bytes(v[0x3F10:0x3F20]) == p1, 'OAM e paletas de sprite iguais de um quadro para o outro')
    carregar(ROM); quadro()
    Image.fromarray(tela).resize((768, 720), Image.Resampling.NEAREST).save(os.path.join(ROOT, 'debug', saida_img))

    print('\n== espera antes de carregar')
    est['fase'] = 'espera'
    rc = next(f[0] for f in fila if f[1].startswith('Contra'))
    q = carregar(rc)
    quadro()
    espq = mem[S['espq']] - 1
    check(espq - 1.5 <= est['espera'] <= espq + 1.5 and mem[S['has']] == 1,
          'cursor parado: a carga começa depois de %.1f quadros (configurado: %d = %.2f s)' % (est['espera'], espq, espq / 60))
    show_name(mem, ROM); v[0x2320:0x2360] = mem[0x6320:0x6360]
    est['joy'] = 1; quadro(); est['joy'] = 0                         # botão: esconde (o navegador anda)
    cpu.call(S['draw_hook'])
    t0 = est['t']
    cpu.stubs[S['split']] = lambda c: None
    while est['t'] - t0 < 20 * QUADRO:                                # 20 quadros parado: ainda não carrega
        cpu.call(S['idle_hook']); cpu.steps = 0
    del cpu.stubs[S['split']]
    check(mem[S['has']] == 0 and est.get('t_sd') is None or est['t_sd'] < t0, 'com 20 quadros parado ainda não carregou')
    cpu.call(S['draw_hook'])                                         # o cursor andou de novo: a espera recomeça
    check(mem[S['pending']] == 1, 'cursor andou: contagem da espera recomeça (pending = 1)')

    print('\n== botão no meio da carga: desiste')
    est['fase'] = 'desiste'
    sp0 = cpu.sp
    est['joy_em'] = None
    est['eventos'].clear(); est['t_sd'] = None
    cpu.stubs[S['split']] = lambda c: None
    n = 0
    while est['t_sd'] is None and n < 400000:                         # até a carga começar
        cpu.call(S['idle_hook']); cpu.steps = 0; n += 1
        if est['t_sd'] is not None: break
    del cpu.stubs[S['split']]
    # a 1ª chamada que começou a carga já terminou: refaz com o botão no meio
    mem[S['has']] = 0; mem[S['pending']] = 1; cpu.call(S['draw_hook'])
    est['t_sd'] = None
    est['joy_em'] = est['t'] + (espq + 10) * QUADRO                   # aperta 10 quadros depois de começar a carregar
    t_ini = est['t']
    cpu.stubs[S['split']] = lambda c: None
    n = 0
    while n < 400000:
        cpu.call(S['idle_hook']); cpu.steps = 0; n += 1
        if est['t_sd'] is not None and mem[S['pending']] == 1 and not mem[S['has']] and est['t'] > est['joy_em']: break
        if mem[S['has']]: break
    del cpu.stubs[S['split']]
    dur = (est['t'] - est['joy_em']) / QUADRO
    texto = bytes(v[0x2000 + 64:0x2000 + 0x300])
    ok_texto = all(v[0x2000 + r * 32 + c] == mem[0x6000 + r * 32 + c] for r in range(2, 22) for c in range(16))
    check(not mem[S['has']] and mem[S['pending']] == 1 and est['mask'] == 0x0A and est['nmi_on'] and cpu.sp == sp0
          and dur < 2, 'botão no meio da carga: desistiu em %.1f quadro(s); capa escondida e pendente, tela e NMI '
          'ligados, pilha intacta' % dur)
    check(ok_texto, 'a lista continua intacta na tela')
    est['joy_em'] = None
    q = carregar(ROM, desenhar=False)
    quadro()
    kr = next(i for i, f in enumerate(fila) if f[0] == ROM)
    dif, da = nt_igual(covers[(512 + 64 * kr) * 512 + 9:(512 + 64 * kr) * 512 + 33])
    check(mem[S['has']] == 1 and mem[S['rev']] == 0 and not dif and not da,
          'solto o botão e parado de novo: a capa carrega inteira (%.1f quadros) e a tela = buffer' % q)

    print('\n== botão (o NMI do OS lê o controle)')
    est['fase'] = 'botao'
    est['joy'] = 1; quadro(); est['joy'] = 0
    att = b''.join(bytes(v[0x23C4 + r * 8:0x23C8 + r * 8]) for r in range(6))
    check(att == ESCONDE and bytes(v[0x3F05:0x3F08]) == b'\x0f' * 3 and mem[S['has']] == 0,
          'esconde: atributos -> paleta 1 (linhas 22-23: paleta 0, o texto), paletas pretas, has = 0')
    check(bytes(v[0x3F0C:0x3F10]) == bytes([0x0F, 0x30, 0x00, 0x28]), 'esconde: paleta 3 da barra de volta (amarelo $28)')
    est['lbas'].clear()
    q = carregar(ROM)
    base = int.from_bytes(mem[S['base']:S['base'] + 4], 'little')
    rel = [l - base for l in est['lbas']]
    check(257 not in rel and 258 not in rel and mem[S['has']] == 1, 'recarga em %.1f quadros, reaproveitando o módulo' % q)
    quadro()

    print('\n== File Menu por cima da capa (a caixa cinza é paleta 3 nos atributos do buffer do OS)')
    est['fase'] = 'menu-caixa'
    carregar(ROM); quadro()
    est['joy'] = 1; quadro(); est['joy'] = 0                         # A: esconde a capa (sp_hide)
    for r_ in range(1, 4):                                            # o OS desenha a caixa: linhas 1-3, colunas 2-6
        for c_ in range(2, 7): mem[0x63C0 + r_ * 8 + c_] = 0xFF        # (as colunas 4-6 caem na região da capa)
    tempo.ate_vblank(); cpu.call(S['hide'])                           # o refresh do OS chama o hide no 1º vblank
    v[0x2000:0x2400] = mem[0x6000:0x6400]                             # e envia o buffer
    caixa = all(v[0x23C0 + r_ * 8 + c_] == 0xFF and mem[0x63C0 + r_ * 8 + c_] == 0xFF for r_ in range(1, 4) for c_ in range(2, 7))
    check(caixa, 'caixa do menu cinza inteira, inclusive a metade sobre a área da capa (atributos do OS intactos)')
    for r_ in range(1, 4):
        for c_ in range(2, 7): mem[0x63C0 + r_ * 8 + c_] = 0                # o menu fecha (o OS restaura o buffer)
    v[0x2000:0x2400] = mem[0x6000:0x6400]
    carregar(ROM); quadro()
    dif, da = nt_igual(covers[(512 + 64 * kr) * 512 + 9:(512 + 64 * kr) * 512 + 33])
    check(mem[S['has']] == 1 and not dif and not da, 'menu fechado: a capa volta com os atributos dela só na PPU')

    print('\n== menu ($833D)')
    carregar(ROM); quadro()
    est['fase'] = 'menu'
    tempo.ate_vblank(); cpu.call(S['hide'])
    check(bytes(v[0x3F04:0x3F0C]) == b'\x0f' * 8 and mem[S['has']] == 0, 'paletas 1 e 2 pretas, has = 0')
    check(bytes(v[0x3F0C:0x3F10]) == bytes([0x0F, 0x30, 0x00, 0x28]), 'menu: paleta 3 da barra de volta (amarelo $28)')
    print('       capas que usam a cor livre: %s' % ', '.join('%s ($%02X)' % (c[:20], k) for c, k in usa3 if k != 0x28))

    print('\n== tempo das escritas')
    viol = est['viol']
    check(not viol, 'nenhuma escrita na PPU com a tela ligada fora do vblank%s' % ('' if not viol else ': %d, ex. %s' % (len(viol), viol[:4])))
    print('\nRESULTADO:', 'TUDO OK' if ok else 'HÁ FALHAS')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
