"""Teste + imagem de exemplo da POC do texto no topo (build_poc_texto.py).

Monta a tela como o OS: lista nas linhas 2-22 (nomes de F:\\roms, se houver), nome completo nas linhas 25-26 (barra
cinza, paleta 3), chama o redesenho completo da firmware (w82fa -> envia o buffer para a PPU), carrega a capa do
Mario 3 e reconstrói a tela inteira a partir da PPU (fundo + sprites, média dos quadros A e B).
Gera debug/poc_texto_exemplo.png.
uso: python teste_poc_texto.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont
from teste_capas_emu import setup, show_name, ROOT
from teste_capas_v3_emu import nmi
from build_poc import rgb
from sim_flicker import avg_color
import build_poc_texto as P


def tela(v, oam):
    """Tela 256x240 (índices NES) como a PPU desenharia."""
    for m in (0x3F10, 0x3F14, 0x3F18, 0x3F1C): v[m - 0x10] = v[m]
    img = [[v[0x3F00]] * 256 for _ in range(240)]
    for y in range(240):
        for x in range(256):
            t = v[0x2000 + (y // 8) * 32 + x // 8]
            a = v[0x23C0 + (y // 32) * 8 + x // 32]
            p = (a >> (((x // 16) & 1) * 2 + ((y // 16) & 1) * 4)) & 3
            lo, hi = v[t * 16 + y % 8], v[t * 16 + 8 + y % 8]
            c = ((lo >> (7 - x % 8)) & 1) | (((hi >> (7 - x % 8)) & 1) << 1)
            img[y][x] = v[0x3F00] if c == 0 else v[0x3F00 + p * 4 + c]
    for k in range(63, -1, -1):
        sy, t, at, sx = oam[k * 4:k * 4 + 4]
        if sy >= 0xEF: continue
        base = (0x1000 if t & 1 else 0) + (t & 0xFE) * 16
        for r in range(16):
            for cx in range(8):
                x, y = sx + cx, sy + 1 + r
                if x > 255 or y > 239: continue
                tb = base + (16 if r >= 8 else 0)
                lo, hi = v[tb + r % 8], v[tb + 8 + r % 8]
                c = ((lo >> (7 - cx)) & 1) | (((hi >> (7 - cx)) & 1) << 1)
                if c and not (at & 0x20): img[y][x] = v[0x3F10 + (at & 3) * 4 + c]
    return img


def main():
    buf, S = P.main()
    covers = open(os.path.join(ROOT, 'poc_texto', 'EDFC', 'COVERS.BIN'), 'rb').read()
    cpu, mem, ppu = setup(buf, covers)
    v = ppu['vram']
    v[0x0000:0x2000] = buf[0x0000:0x2000]                                # fonte do OS (como o $826F faz)
    v[0x3F00:0x3F10] = buf[0x6000 + 0x825F - 0x8000:0x6000 + 0x826F - 0x8000]
    cpu.call(S['init_hook'])
    try:
        nomes = sorted(f for f in os.listdir('F:/roms') if f.lower().endswith('.nes'))
    except OSError:
        nomes = ['Contra.nes', 'Super Mario Bros. 3 (USA).nes', 'Zelda.nes']
    sel = next((i for i, n in enumerate(nomes) if n.startswith('Super Mario')), 0)
    mem[0x6000:0x6400] = bytes(0x400)
    for i, n in enumerate(nomes[:21]):                                    # a lista como o OS desenha
        row = 2 + i
        if i == sel: mem[0x6000 + row * 32 + 1] = ord('>')
        for k, ch in enumerate(n[:20]): mem[0x6000 + row * 32 + 2 + k] = ord(ch) + (0x80 if i == sel else 0)
    show_name(mem, nomes[sel])                                            # nome completo nas linhas 25-26
    for k in range(8): mem[0x63C0 + 6 * 8 + k] = 0xFF                     # barra de baixo na paleta 3
    ok = True

    def check(c, m):
        nonlocal ok
        print(('  OK   ' if c else '  FALHA') + ' ' + m); ok &= bool(c)

    def gfx_full(c):                                                      # o $82FA de verdade: buffer -> PPU
        v[0x2000:0x2400] = mem[0x6000:0x6400]
    cpu.stubs[0x82FA] = gfx_full
    mem[S['flk']] = 1
    cpu.call(S['w82fa'])
    linha1 = bytes(v[0x2000 + P.LINHA * 32:0x2000 + P.LINHA * 32 + 32]).decode('latin-1')
    check(P.TEXTO in linha1 and mem[S['flk']] == 0, 'redesenho completo: "%s" na linha %d da tela' % (linha1.strip('\0').strip(), P.LINHA))
    outras = [r for r in range(30) if r != P.LINHA]
    check(all(bytes(v[0x2000 + r * 32:0x2020 + r * 32]) == bytes(mem[0x6000 + r * 32:0x6020 + r * 32]) for r in outras), 'resto da tela igual ao buffer do OS (nada mais mudou)')
    cpu.call(S['draw_hook']); cpu.call(S['idle_hook'])
    check(mem[S['has']] == 1, 'capa do Mario 3 carregada')
    mem[0xA2] = 0
    fr = []
    for _ in range(2):
        nmi(cpu)
        fr.append(tela(v, ppu['oam']))
    check(bytes(v[0x2000 + P.LINHA * 32:0x2020 + P.LINHA * 32]).decode('latin-1').find(P.TEXTO) >= 0, 'o texto continua lá depois da capa')
    media = [[avg_color(fr[0][y][x], fr[1][y][x]) for x in range(256)] for y in range(240)]

    S3 = 3
    im = Image.new('RGB', (256, 240)); im.putdata([c for row in media for c in row])
    im = im.resize((256 * S3, 240 * S3), Image.Resampling.NEAREST)
    d = ImageDraw.Draw(im, 'RGBA')
    d.rectangle((0, 0, 256 * S3 - 1, 8 * S3 - 1), fill=(255, 60, 60, 60))   # faixa que muitas TVs cortam
    d.rectangle((0, 232 * S3, 256 * S3 - 1, 240 * S3 - 1), fill=(255, 60, 60, 60))
    out = Image.new('RGB', (256 * S3 + 40, 240 * S3 + 110), (20, 17, 15))
    out.paste(im, (20, 70))
    dd = ImageDraw.Draw(out)
    f = lambda t: ImageFont.truetype('segoeui.ttf', t)
    dd.text((20, 10), 'POC: texto fixo no navegador (linha %d da tela, acima da barra de baixo)' % P.LINHA, fill=(217, 164, 65), font=f(20))
    dd.text((20, 40), 'Imagem reconstruída do emulador (código da firmware). Em vermelho: as 8 linhas de cima/baixo que '
                      'muitas TVs de tubo escondem.', fill=(141, 130, 115), font=f(13))
    dd.text((20, 240 * S3 + 78), 'Linha %d = pontos %d a %d da tela: bem dentro da área visível da TV.' % (P.LINHA, P.LINHA * 8, P.LINHA * 8 + 7),
            fill=(141, 130, 115), font=f(13))
    caminho = os.path.join(ROOT, 'debug', 'poc_texto_exemplo.png')
    out.save(caminho)
    print('imagem:', caminho)
    print('\nRESULTADO:', 'TUDO OK' if ok else 'HÁ FALHAS')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
