"""Teste no PC da POC v4 (capa grande no navegador + tela cheia), no emulador 6502 com uma PPU simplificada.

Confere:
  - chr_all: a fonte do OS nos blocos 0-7 ($826F com $82 = 0..7); init: módulo do setor 257 em $7F00;
  - carga: nametable/atributos da capa no buffer de tela, tiles de cada grupo no bloco certo, OAM só com o sprite 0,
    as células da capa continuam vazias na PPU (nada de lixo enquanto carrega);
  - aparecimento: atributos -> paleta 1, 4 linhas por quadro, e no fim atributos e paletas de verdade;
  - cada quadro: banco 1 no vblank e as 6 trocas (bancos 2-7) com os CICLOS contados no código montado, dentro das
    janelas (linhas compartilhadas); a tela reconstruída = a capa convertida, com a troca em qualquer linha das
    janelas, e o texto da lista igual;
  - botão: esconde já (atributos -> $55, paletas 1 e 2 pretas, has = 0);
  - 180 quadros: tela cheia (dados do registro da capa), saída: fonte refeita (chr_all) e capa pendente;
  - menu ($833D): paletas pretas e a capa sai do buffer.
Gera debug/poc_capa_grande_exemplo.png (a tela inteira reconstruída do emulador).
uso: python teste_capas_v4_emu.py
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teste_capas_emu import setup, show_name, ROOT
from teste_poc_bancos_emu import ciclos, CIC
from build_poc import NES_RGB
import build_poc_capa_grande as B
import conv_capa_grande as G
import sim_navegador_grande as N

for op, c in ((0xAC, 4), (0xEE, 6), (0xC9, 2), (0x8C, 4)): CIC[op] = c
NES = {i: ((c >> 16) & 255, (c >> 8) & 255, c & 255) for i, c in enumerate(NES_RGB)}
ROM = 'Super Mario Bros 3 (U) (PRG 1).nes'
OUTRAS = ['Mega Man 2 (U).nes', 'Castlevania (U) (PRG 0).nes']


def main():
    ok = True

    def check(c, m):
        nonlocal ok
        print(('  OK   ' if c else '  FALHA') + ' ' + m); ok &= bool(c)

    nomes = B.roms_da_firmware()
    buf, S, covers, VS, fila = B.main(180, log=lambda *a: None, roms=[ROM] + OUTRAS, jobs=3, escrever=False)
    idx = next(i for i, (r, c, crc) in enumerate(fila) if r == ROM)
    reg = covers[(512 + 64 * idx) * 512:(512 + 64 * idx + 64) * 512]
    capa = fila[idx][1]
    cpu, mem, ppu = setup(buf, covers)
    v = ppu['vram']
    chr_os = bytes(buf[0:0x2000])
    pal_os = bytes(buf[0x6000 + 0x825F - 0x8000:][:16])
    est = dict(banco=0, idx=None, bancos=[], chr=bytearray(10 * 4096), initchr=[], nmi_on=True)
    ow = cpu.on_write

    def on_write(a, val):
        if a == 0x4400: est['idx'] = val; return True
        if a == 0x4401:
            if est['idx'] == 0x82: est['banco'] = val; est['bancos'].append(val)
            return True
        if a == 0x2000: est['nmi_on'] = bool(val & 0x80); return True
        if a == 0x2007 and ppu['addr'] < 0x2000:
            est['chr'][est['banco'] * 4096 + ppu['addr']] = val; ppu['addr'] += 1; return True
        return ow(a, val)
    cpu.on_write = on_write

    def initchr(c):
        b = est['banco']; est['initchr'].append(b)
        est['chr'][b * 4096:b * 4096 + 0x2000] = chr_os
        v[0x3F00:0x3F10] = pal_os
    cpu.stubs[0x826F] = initchr
    cpu.stubs[0x82FA] = lambda c: v.__setitem__(slice(0x2000, 0x2400), mem[0x6000:0x6400])
    cpu.stubs[0xAB25] = lambda c: None

    print('== fonte e init')
    cpu.call(S['chr_all'])
    check(est['initchr'] == list(range(8)) and est['banco'] == 0, '$826F com os bancos 0..7, termina no 0')
    check(all(bytes(est['chr'][b * 4096:(b + 1) * 4096]) == chr_os[:4096] for b in range(8)), 'fonte nos blocos 0-7')
    cpu.call(S['init_hook'])
    check(mem[S['enabled']] == 1 and bytes(mem[0x7F00:0x7FFF]) == covers[257 * 512:257 * 512 + 255],
          'COVERS.BIN achado e módulo (setor 257) em $7F00-$7FFE')

    # tela do navegador como o OS desenha (nomes com 14 colunas)
    sel = nomes.index(ROM); ini = max(0, sel - 7); lista = nomes[ini:ini + 21]
    mem[0x6000:0x6400] = bytes(0x400)
    for i, n in enumerate(lista):
        row = 2 + i
        if n == ROM: mem[0x6000 + row * 32 + 1] = ord('>')
        for k, ch in enumerate(n[:14]): mem[0x6000 + row * 32 + 2 + k] = ord(ch) + (0x80 if n == ROM else 0)
    show_name(mem, ROM)
    for k in range(8): mem[0x63F0 + k] = 0xFF
    texto0 = bytes(mem[0x6000:0x6400])
    v[0x2000:0x2400] = texto0
    v[0x3F00:0x3F10] = pal_os

    print('\n== carga da capa grande')
    cpu.call(S['draw_hook'])
    check(mem[S['pending']] == 1, 'pendente')
    mem[0x9E] = 0
    cpu.call(S['idle_hook'])                                    # carga; o split desiste (sem NMI no teste)
    check(mem[S['has']] == 1 and mem[S['rev']] == 1, 'carregada: has = 1, aparecimento pendente (rev = 1)')
    nt = reg[33:353]
    regiao = lambda m: b''.join(bytes(m[0x6050 + r * 32:0x6050 + r * 32 + 16]) for r in range(20))
    check(regiao(mem) == nt, 'nametable da capa no buffer (linhas 2-21, colunas 16-31)')
    at = b''.join(bytes(mem[0x63C4 + r * 8:0x63C4 + r * 8 + 4]) for r in range(6))
    check(at == reg[9:33], 'atributos no buffer')
    grupos_ok = all(bytes(est['chr'][(g + 1) * 4096:(g + 1) * 4096 + 512]) == reg[512 + g * 1024:512 + g * 1024 + 512] and
                    bytes(est['chr'][(g + 1) * 4096 + 0x800:(g + 1) * 4096 + 0xA00]) == reg[1024 + g * 1024:1024 + g * 1024 + 512]
                    for g in range(7))
    check(grupos_ok, 'tiles dos 7 grupos nos blocos 1-7 (slots $00-$1F e $80-$9F)')
    fonte_ok = all(bytes(est['chr'][b * 4096 + 0x200:b * 4096 + 0x800]) == chr_os[0x200:0x800] and
                   bytes(est['chr'][b * 4096 + 0xA00:b * 4096 + 0x1000]) == chr_os[0xA00:0x1000] for b in range(1, 8))
    check(fonte_ok, 'a fonte continua inteira em todos os blocos')
    check(ppu['oam'][0:4] == bytes([15, 0x1F, 0x20, 0]) and set(ppu['oam'][4::4]) == {0xF0}, 'OAM: só o sprite 0 de sincronia')
    check(bytes(v[0x2000:0x2400]) == texto0, 'PPU: células da capa ainda vazias (sem lixo durante a carga)')

    # quadros: roda o idle_hook passo a passo, simulando NMI, sprite 0 e controle
    def quadro(joy=0, contar=True):
        st = dict(q=0, n=0)
        orr = cpu.on_read

        def on_read(a):
            if a == 0x9E:
                st['q'] += 1
                if est['nmi_on'] and st['q'] == 3: mem[0x9E] = 1; st['n'] = 0
                return None
            if a == 0x2002:
                ppu['latch'] = 0; st['n'] += 1
                return 0x40 if st['n'] <= 3 else (0x00 if st['n'] <= 6 else 0x40)
            if a == 0x0515: return joy
            return orr(a) if orr else None
        cpu.on_read = on_read
        est['bancos'].clear()
        cpu.push(0xFF); cpu.push(0xEF)
        cpu.stubs[0xAB25] = lambda c: setattr(c, 'pc', 0xFFF0)
        cpu.pc = S['idle_hook']
        t, contando, marcas, passos = 0, False, [], 0
        while cpu.pc != 0xFFF0 and passos < 2_000_000:
            pc, op = cpu.pc, mem[cpu.pc]
            nb = len(est['bancos'])
            if pc == S['sw3']: contando, t = True, 3
            cpu.step(); passos += 1
            if contando and len(marcas) == 6: contando = False                  # depois da última troca
            if contando:
                t += ciclos(cpu, pc, op)
                if len(est['bancos']) > nb: marcas.append(t)
        cpu.on_read = orr
        cpu.stubs[0xAB25] = lambda c: None
        return marcas

    print('\n== aparecimento (um quadro por passo)')
    m1 = quadro()
    att = b''.join(bytes(v[0x23C4 + r * 8:0x23C8 + r * 8]) for r in range(6))
    check(att == bytes([0x55]) * 24 and mem[S['rev']] == 2, 'quadro 1: atributos da capa -> paleta 1 (preta)')
    for k in range(5): quadro()
    check(b''.join(bytes(v[0x2050 + r * 32:0x2060 + r * 32]) for r in range(20)) == nt and mem[S['rev']] == 7,
          'quadros 2-6: nametable na PPU (4 linhas por quadro), atributos ainda pretos')
    m = quadro()
    att = b''.join(bytes(v[0x23C4 + r * 8:0x23C8 + r * 8]) for r in range(6))
    check(att == reg[9:33] and bytes(v[0x3F05:0x3F08]) == reg[3:6] and bytes(v[0x3F09:0x3F0C]) == reg[6:9]
          and mem[S['rev']] == 0, 'quadro 7: atributos e paletas de verdade (a capa aparece)')

    print('\n== quadro com a capa (ciclos do sprite 0 até cada troca)')
    m = quadro()
    check(est['bancos'] == [1, 2, 3, 4, 5, 6, 7], 'bancos no quadro: %s' % est['bancos'])
    lin = lambda c: divmod(16 * 341 + 1 + c * 3, 341)
    linhas = []
    for k, c in enumerate(m):
        r = 3 * (k + 1)                                      # linha compartilhada (da capa)
        y0 = 8 * (2 + r)
        l, p = lin(c)
        dentro = (y0 - 1, 257) <= (l, p) and (l, p + 33) <= (y0 + 7, 320)
        linhas.append(l)
        check(dentro, 'banco %d na linha %d, ponto %d (+0..33): janela %d(257)-%d(320)' % (k + 2, l, p, y0 - 1, y0 + 7))

    nt_ppu, at_ppu, pal = bytes(v[0x2000:0x23C0]), bytes(v[0x23C0:0x2400]), bytes(v[0x3F00:0x3F10])

    def render(trocas):
        img = np.zeros((240, 256, 3), np.uint8)
        for y in range(240):
            b = 1 + sum(1 for t in trocas if y >= t)
            for tx in range(32):
                t = nt_ppu[(y // 8) * 32 + tx]
                pp = est['chr'][b * 4096 + t * 16:][:16]
                a = at_ppu[(y // 32) * 8 + tx // 4] >> ((2 if tx & 2 else 0) + (4 if (y // 16) & 1 else 0)) & 3
                for x in range(8):
                    c = (pp[y & 7] >> (7 - x) & 1) | (pp[8 + (y & 7)] >> (7 - x) & 1) << 1
                    img[y, tx * 8 + x] = NES[pal[a * 4 + c] if c else pal[0]]
        return img
    reg_, vista, info = G.converter(os.path.join(G.N.ROOT, 'imagens', 'Named_Boxarts', capa), 0, 180)
    certo = render(linhas)
    check((certo[16:176, 128:256] == vista).all(), 'tela reconstruída: a capa = a imagem convertida')
    inicio = [8 * (2 + 3 * (k + 1)) for k in range(6)]          # troca no começo da linha compartilhada
    fim = [8 * (2 + 3 * (k + 1)) + 8 for k in range(6)]         # e logo depois dela
    check((render(inicio)[16:176, 128:256] == vista).all() and (render(fim)[16:176, 128:256] == vista).all(),
          'igual com a troca no começo ou no fim de cada linha compartilhada (folga de 8 linhas)')
    check(not (render([t - 9 for t in inicio])[16:176, 128:256] == vista).all(), 'controle: trocando 9 linhas antes, quebra')
    so_texto = np.zeros_like(certo)
    for y in range(240):
        for tx in range(16):
            t = texto0[(y // 8) * 32 + tx]
            pp = chr_os[t * 16:t * 16 + 16]
            for x in range(8):
                c = (pp[y & 7] >> (7 - x) & 1) | (pp[8 + (y & 7)] >> (7 - x) & 1) << 1
                pl = 3 if (y // 16) >= 12 and (y // 16) <= 13 else 0
                so_texto[y, tx * 8 + x] = NES[pal_os[pl * 4 + c] if c else pal_os[0]]
    check((certo[:, :128] == so_texto[:, :128]).all(), 'texto da lista (colunas 0-15) intacto em todos os bancos')

    # imagem de exemplo
    Z = 3
    im = Image.fromarray(certo).resize((256 * Z, 240 * Z), Image.Resampling.NEAREST)
    d = ImageDraw.Draw(im, 'RGBA')
    d.rectangle((0, 0, 256 * Z - 1, 8 * Z - 1), fill=(255, 60, 60, 50))
    d.rectangle((0, 232 * Z, 256 * Z - 1, 240 * Z - 1), fill=(255, 60, 60, 50))
    folha = Image.new('RGB', (256 * Z + 40, 240 * Z + 100), (20, 17, 15))
    folha.paste(im, (20, 60))
    dd = ImageDraw.Draw(folha)
    try: f = lambda t: ImageFont.truetype('segoeui.ttf', t); f(10)
    except OSError: f = lambda t: ImageFont.load_default()
    dd.text((20, 12), 'POC v4: capa grande no navegador (reconstruída do emulador, nitidez 180%)', fill=(217, 164, 65), font=f(20))
    dd.text((20, 240 * Z + 68), 'Trocas de banco nas linhas %s. Em vermelho: faixas que a TV de tubo pode esconder.' % linhas,
            fill=(141, 130, 115), font=f(13))
    saida = os.path.join(ROOT, 'debug', 'poc_capa_grande_exemplo.png')
    folha.save(saida)

    print('\n== botão: esconde na hora')
    quadro(joy=0x04)
    att = b''.join(bytes(v[0x23C4 + r * 8:0x23C8 + r * 8]) for r in range(6))
    check(att == bytes([0x55]) * 24 and bytes(v[0x3F05:0x3F08]) == b'\x0f' * 3 and bytes(v[0x3F09:0x3F0C]) == b'\x0f' * 3
          and mem[S['has']] == 0 and ppu['mask'][-1] == 0x0A, 'atributos -> paleta 1, paletas 1 e 2 pretas, has = 0, sprites desligados')
    cpu.call(S['draw_hook'])                                    # o navegador redesenha: mesma capa (has = 0) -> recarrega
    check(mem[S['pending']] == 1 and regiao(mem) == bytes(320), 'troca de item: a capa sai do buffer e fica pendente')

    print('\n== tela cheia depois de 180 quadros parado')
    cpu.call(S['idle_hook'])
    for k in range(7): quadro()
    check(mem[S['rev']] == 0 and mem[S['has']] == 1, 'capa de volta')
    lidas = []
    rd0 = cpu.stubs[0xC53F]
    cpu.stubs[0xC53F] = lambda c: (lidas.append(int.from_bytes(mem[(mem[0x28] | mem[0x29] << 8):][:4], 'little')), rd0(c))
    n = 0
    while mem[S['fs_t']] < 179 and n < 300: quadro(); n += 1
    check(mem[S['fs_t']] == 179 and not lidas, '179 quadros com a capa pronta: ainda não (fs_t = %d)' % mem[S['fs_t']])
    est['initchr'].clear()
    # quadro 180: o visualizador roda com o seu próprio laço (NMI, sprite 0, botão no 3º quadro)
    st = dict(q=0, n=0, quadros=0)
    orr = cpu.on_read

    def on_read(a):
        if a == 0x9E:
            st['q'] += 1
            if est['nmi_on'] and st['q'] % 3 == 0 and mem[0x9E] == 0:
                mem[0x9E] = 1; st['n'] = 0; st['quadros'] += 1
            return None
        if a == 0x2002:
            ppu['latch'] = 0; st['n'] += 1
            return 0x40 if st['n'] <= 3 else (0x00 if st['n'] <= 6 else 0x40)
        if a == 0x0515: return 0x80 if st['quadros'] in (6, 7) else 0
        return orr(a) if orr else None
    cpu.on_read = on_read
    cpu.push(0xFF); cpu.push(0xEF)
    cpu.stubs[0xAB25] = lambda c: setattr(c, 'pc', 0xFFF0)
    cpu.pc = S['idle_hook']; passos = 0; foto = None
    while cpu.pc != 0xFFF0 and passos < 5_000_000:
        if cpu.pc == VS['v_loop'] and foto is None: foto = (bytes(v), bytes(est['chr']))
        cpu.step(); passos += 1
    cpu.on_read = orr
    base = int.from_bytes(mem[S['base']:S['base'] + 4], 'little')
    rel = [l - base for l in lidas]
    csec = 512 + 64 * idx
    check(rel[:2] == [256, csec + 15], 'lê o visualizador (256) e o setor "TELA" do registro da capa (%d): %s' % (csec + 15, rel[:3]))
    tc = reg[15 * 512:42 * 512]
    check(foto is not None and foto[0][0x2000:0x2400] == tc[512:1536] and foto[1][2 * 4096:5 * 4096] == tc[3 * 512:27 * 512],
          'tela cheia: nametable e blocos 2-4 com os dados da capa')
    check(est['initchr'] == list(range(8)), 'na volta: fonte refeita nos blocos 0-7 (%s)' % est['initchr'])
    check(mem[S['pending']] == 1 and regiao(mem) == bytes(320), 'na volta: a capa grande fica pendente (recarrega)')

    print('\n== menu ($833D)')
    cpu.stubs[0xC53F] = rd0
    cpu.stubs[0xAB25] = lambda c: None
    cpu.call(S['idle_hook'])
    for k in range(7): quadro()
    cpu.call(S['hide'])
    check(bytes(v[0x3F04:0x3F0C]) == b'\x0f' * 8 and regiao(mem) == bytes(320) and mem[S['has']] == 0,
          'paletas 1 e 2 pretas, a capa sai do buffer, has = 0')
    print('imagem:', saida)
    print('\nRESULTADO:', 'TUDO OK' if ok else 'HÁ FALHAS')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
