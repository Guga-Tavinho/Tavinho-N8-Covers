"""Teste no PC da POC de tela cheia (build_poc_tela_cheia.py), no emulador 6502 com uma PPU simplificada.

Confere:
  - a espera ociosa conta 180 quadros com a capa pequena e só então chama o visualizador (a carga zera o contador);
  - jogo sem capa de tela cheia: o visualizador volta sem mexer na tela;
  - jogo com capa: tiles nos blocos 2/3/4 da CHR (pelo registrador $82), nametable, paletas, OAM só com o sprite 0;
  - a cada quadro: banco 2 no vblank, banco 3 e banco 4 depois do sprite 0 — CICLOS contados no código montado,
    convertidos em linha/ponto da tela, dentro das janelas (linhas 71-79 e 151-159);
  - a tela reconstruída da PPU (com a troca em QUALQUER linha das janelas) = a imagem convertida;
  - saída: espera soltar o botão, banco 0, paleta do OS, nametable do buffer, capa pequena pendente.
Gera debug/poc_tela_cheia_exemplo.png (tela reconstruída do emulador, ao lado da capa original).
uso: python teste_poc_tela_cheia.py
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teste_capas_emu import setup, show_name, ROOT
from teste_poc_bancos_emu import ciclos, CIC
import build_poc_tela_cheia as P
import conv_tela_cheia as C
import sim_tela_cheia as SIM

CIC[0xAC] = 4                                    # LDY abs (esperas lidas de vmeta)


def main():
    ok = True

    def check(c, m):
        nonlocal ok
        print(('  OK   ' if c else '  FALHA') + ' ' + m); ok &= bool(c)

    buf, S, covers, VS, entradas, info, full_sec = P.main(log=lambda *a: None)
    cpu, mem, ppu = setup(buf, covers)
    est = dict(banco=0, idx=None, bancos=[], chr=bytearray(8 * 4096), full=0, q=0, j=0, nmi_on=True)
    ow = cpu.on_write

    def on_write(a, v):
        if a == 0x4400: est['idx'] = v; return True
        if a == 0x4401:
            if est['idx'] == 0x82: est['banco'] = v; est['bancos'].append(v)
            return True
        if a == 0x2000: est['nmi_on'] = bool(v & 0x80); return True
        if a == 0x2007 and ppu['addr'] < 0x2000:
            est['chr'][est['banco'] * 4096 + ppu['addr']] = v; ppu['addr'] += 1; return True
        return ow(a, v)
    cpu.on_write = on_write
    cpu.stubs[0x82FA] = lambda c: est.__setitem__('full', est['full'] + 1)
    cpu.stubs[0xAB25] = lambda c: None

    cpu.call(S['init_hook'])

    def carregar(rom):
        show_name(mem, rom)
        cpu.call(S['draw_hook'])
        cpu.call(S['idle_hook'])
        return mem[S['has']]

    print('== contador da espera ociosa')
    check(carregar('Contra Force (U).nes') == 1 and mem[S['fs_t']] == 0, 'capa pequena carregada, contador zerado')
    lidas = []
    rd0 = cpu.stubs[0xC53F]
    cpu.stubs[0xC53F] = lambda c: (lidas.append(int.from_bytes(mem[(mem[0x28] | mem[0x29] << 8):][:4], 'little')), rd0(c))
    for q in range(179):
        mem[0x9E] = 1; cpu.call(S['idle_hook'])
    check(mem[S['fs_t']] == 179 and not lidas, '179 quadros: ainda não chamou (fs_t = %d)' % mem[S['fs_t']])
    m0 = list(ppu['mask'])
    mem[0x9E] = 1; cpu.call(S['idle_hook'])
    base = int.from_bytes(mem[S['base']:S['base'] + 4], 'little')
    check([l - base for l in lidas] == [full_sec, full_sec + 1], 'quadro 180: lê o visualizador e o índice (setores %s)'
          % [l - base for l in lidas])
    check(ppu['mask'] == m0 and est['bancos'] == [], 'Contra Force não tem tela cheia: volta sem mexer na tela')
    check(bytes(mem[0x6400:0x6400 + 16]) == covers[full_sec * 512:full_sec * 512 + 16], 'visualizador copiado para $6400')
    cpu.stubs[0xC53F] = rd0

    print('\n== Super Mario Bros 3: carga da tela cheia')
    rom = 'Super Mario Bros 3 (U) (PRG 1) [a2].nes'
    check(carregar(rom) == 1 and mem[S['fs_t']] == 0, 'capa pequena carregada (outra capa: contador zerado)')
    for q in range(179):
        mem[0x9E] = 1; cpu.call(S['idle_hook'])
    # quadro 180: roda passo a passo simulando a PPU (NMI, sprite 0, controle)
    r = info['Super Mario Bros. 3 (USA).png']
    hy, hx = r['sprite0']
    est['bancos'].clear(); ppu['mask'].clear()
    leituras = dict(q=0, n2002=0, quadros=0)
    orr = cpu.on_read

    def on_read(a):
        if a == 0x9E:                                   # o NMI chega a cada 3 leituras (só com o NMI ligado)
            leituras['q'] += 1
            if est['nmi_on'] and leituras['q'] % 3 == 0 and mem[0x9E] == 0:
                mem[0x9E] = 1; leituras['quadros'] += 1; leituras['n2002'] = 0
            return None
        if a == 0x2002:
            ppu['latch'] = 0
            leituras['n2002'] += 1
            n = leituras['n2002']
            return 0x40 if n <= 3 else (0x00 if n <= 6 else 0x40)
        if a == 0x0515:                                 # botão A apertado no quadro 4 e 5, solto no 6
            return 0x80 if leituras['quadros'] in (4, 5) else 0
        return orr(a) if orr else None
    cpu.on_read = on_read
    mem[0x9E] = 1
    cpu.push(0xFF); cpu.push(0xEF)
    cpu.pc = S['idle_hook']
    contando, t, marcas, por_quadro = False, 0, [], []
    passos = 0
    while cpu.pc != 0xFFF0 and passos < 3_000_000:
        pc, op = cpu.pc, mem[cpu.pc]
        nb = len(est['bancos'])
        if pc == VS['v_hit']: contando, t = True, 3
        if pc == VS['v_loop'] and 'foto' not in est: est['foto'] = bytes(ppu['vram'])     # a PPU durante a exibição
        if pc == VS['v_loop'] and marcas: por_quadro.append(marcas); marcas = []; contando = False
        cpu.step(); passos += 1
        if contando:
            t += ciclos(cpu, pc, op)
            if len(est['bancos']) > nb: marcas.append(t)
        if pc == 0xFFEF or cpu.pc == 0xFFF0: break
    cpu.on_read = orr
    check(passos < 3_000_000, 'o visualizador terminou (%d instruções)' % passos)
    blocos = {b: bytes(est['chr'][b * 4096:(b + 1) * 4096]) for b in (2, 3, 4)}
    dados = r['setores']
    check(blocos[2] == dados[3 * 512:3 * 512 + 4096] and blocos[3] == dados[3 * 512 + 4096:3 * 512 + 8192]
          and blocos[4] == dados[19 * 512:27 * 512], 'tiles nos blocos 2, 3 e 4 da CHR (bancos 2 e 3 na carga)')
    foto = est['foto']
    check(foto[0x2000:0x2400] == dados[512:1536], 'nametable + atributos em $2000')
    check(foto[0x3F00:0x3F10] == r['pal16'] and foto[0x3F10:0x3F20] == r['pal16'], 'paletas de fundo e de sprite')
    check(blocos[3][C.TILE_SYNC * 16] == 0x80, 'tile $FE do bloco 3: sprite de sincronia (pixel 0,0)')
    check(ppu['oam'][0:4] == bytes([hy - 1, 0xFF, 0x20, hx]) and set(ppu['oam'][4::4]) == {0xF0},
          'OAM: só o sprite 0 (Y %d, tile $FF, atrás do fundo, X %d)' % (hy - 1, hx))
    print('\n== quadros (ciclos contados do sprite 0 até cada troca)')
    check(len(por_quadro) >= 3, '%d quadros mostrados antes do botão' % len(por_quadro))
    lin = lambda c: divmod(hy * 341 + hx + 1 + c * 3, 341)
    for k, m in enumerate(por_quadro[:1]):
        (l1, p1), (l2, p2) = lin(m[0]), lin(m[1])
        check(71 <= l1 <= 79 and not (l1 == 71 and p1 < 257) and not (l1 == 79 and p1 > 320),
              'banco 3 na linha %d, ponto %d (+0..33): janela 71(257)-79(320)' % (l1, p1))
        check(151 <= l2 <= 159 and not (l2 == 151 and p2 < 257) and not (l2 == 159 and p2 > 320),
              'banco 4 na linha %d, ponto %d (+0..33): janela 151(257)-159(320)' % (l2, p2))
    seq = est['bancos']
    check(seq[:9] == [2, 3, 2, 2, 3, 4, 2, 3, 4], 'ordem dos bancos: carga 2, 3; quadros 2-3-4 ...: %s' % seq[:12])
    print('\n== saída')
    check(seq[-1] == 0, 'banco 0 de volta')
    check(est['full'] == 1, 'nametable do navegador reenviada ($82FA)')
    check(bytes(ppu['vram'][0x3F00:0x3F10]) == bytes(buf[0x825F - 0x8000 + 0x6000:][:16]), 'paleta do OS de volta')
    check(mem[S['pending']] == 1 and est['nmi_on'], 'capa pequena pendente (recarrega na espera ociosa), NMI ligado')

    print('\n== tela reconstruída da PPU')
    from build_poc import NES_RGB
    nes = {i: ((c >> 16) & 255, (c >> 8) & 255, c & 255) for i, c in enumerate(NES_RGB)}
    pal = foto[0x3F00:0x3F10]

    def render(l1, l2):
        img = np.zeros((240, 256, 3), np.uint8)
        nt, at = foto[0x2000:0x23C0], foto[0x23C0:0x2400]
        for y in range(240):
            b = 2 if y < l1 else 3 if y < l2 else 4
            for tx in range(32):
                t = nt[(y // 8) * 32 + tx]
                p = est['chr'][b * 4096 + t * 16:][:16]
                a = at[(y // 32) * 8 + tx // 4] >> ((2 if tx & 2 else 0) + (4 if (y // 16) & 1 else 0)) & 3
                for x in range(8):
                    v = (p[y & 7] >> (7 - x) & 1) | (p[8 + (y & 7)] >> (7 - x) & 1) << 1
                    img[y, tx * 8 + x] = nes[pal[a * 4 + v]]
        return img
    ref = r['vista']
    iguais = [(l1, l2) for l1 in (72, 76, 80) for l2 in (152, 156, 160) if (render(l1, l2) == ref).all()]
    check(len(iguais) == 9, 'igual à imagem convertida com a troca em qualquer linha das janelas (%d de 9)' % len(iguais))
    errado = render(64, 152)
    check(not (errado == ref).all(), 'controle: trocando cedo demais (linha 64) a imagem quebra')
    tela = render(76, 156)
    orig = SIM.carregar(os.path.join(P.CAPAS, 'Super Mario Bros. 3 (USA).png'), C.W, C.H, 0).astype(np.uint8)
    t_orig = np.zeros((240, 256, 3), np.uint8); t_orig[:, C.X0:C.X0 + C.W] = orig
    from gerar_covers import cover_record
    hoje = np.array(cover_record(os.path.join(P.CAPAS, 'Super Mario Bros. 3 (USA).png'), 0, v3=True, lam=0.22,
                                 nitidez=70)[1], np.uint8)
    t_hoje = np.zeros((240, 256, 3), np.uint8)
    from build_poc import COVER_X, COVER_Y
    t_hoje[COVER_Y:COVER_Y + 96, COVER_X:COVER_X + 64] = hoje
    Z, gap = 2, 16
    folha = Image.new('RGB', (3 * 512 + 4 * gap, 480 + 70), (24, 21, 18))
    d = ImageDraw.Draw(folha)
    for k, (t_, nome) in enumerate([(t_orig, 'Original'), (t_hoje, 'Hoje: capa 64x96 ao lado da lista'),
                                     (tela, 'POC tela cheia (reconstruída do emulador)')]):
        folha.paste(Image.fromarray(t_).resize((512, 480), Image.Resampling.NEAREST), (gap + k * (512 + gap), 40))
        d.text((gap + k * (512 + gap), 14), nome, fill=(240, 230, 210))
    d.text((gap, 525), 'Tela inteira da TV (256x240). Sprite 0 na linha %d; troca de banco nas linhas %d e %d.'
           % (hy, lin(por_quadro[0][0])[0], lin(por_quadro[0][1])[0]), fill=(160, 150, 140))
    saida = os.path.join(ROOT, 'debug', 'poc_tela_cheia_exemplo.png')
    folha.save(saida)
    print('imagem:', saida)
    print('\nRESULTADO:', 'TUDO OK' if ok else 'HÁ FALHAS')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
