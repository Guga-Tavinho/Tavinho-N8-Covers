"""Teste no PC da POC v3 (sprites + fundo + alternância pelo NMI), com o emulador 6502.
Reconstrói cada quadro a partir do estado da PPU (OAM, paletas, nametable, atributos, tiles)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from teste_capas_emu import setup, show_name, ROOT
from build_capas_v3 import main as build_main
from build_poc import rgb, png_read
from sim_flicker import avg_color

NT_BUF, ATTR_BUF, PALTAB = 0x6096, 0x63CD, 0x7F00
NOME = 'Super Mario Bros. 3 (USA).nes'


def nmi(cpu):
    ret = 0xFFF0
    cpu.push(ret >> 8); cpu.push(ret & 0xFF); cpu.push(cpu.p())
    cpu.pc = 0x80B4
    while cpu.pc != ret:
        cpu.step()


def render(ppu, oam):
    """Imagem (índices NES) da área da capa como a PPU desenharia: sprites 8x16 da tabela 1 sobre o fundo."""
    v = ppu['vram']
    for m in (0x3F10, 0x3F14, 0x3F18, 0x3F1C):                    # espelhos do hardware: $3F1x -> $3F0x
        v[m - 0x10] = v[m]
    img = [[0x0F] * 64 for _ in range(96)]
    for y in range(96):                                          # fundo: linhas 4-15, colunas 22-29
        for x in range(64):
            sx, sy = 176 + x, 32 + y
            t = v[0x2000 + (sy // 8) * 32 + sx // 8]
            a = v[0x23C0 + (sy // 32) * 8 + sx // 32]
            p = (a >> (((sx // 16) & 1) * 2 + ((sy // 16) & 1) * 4)) & 3
            lo, hi = v[t * 16 + sy % 8], v[t * 16 + 8 + sy % 8]
            c = ((lo >> (7 - sx % 8)) & 1) | (((hi >> (7 - sx % 8)) & 1) << 1)
            img[y][x] = v[0x3F00] if c == 0 else v[0x3F00 + p * 4 + c]
    for k in range(64):                                           # sprites (prioridade: menor índice na frente)
        sy, t, at, sx = oam[k * 4:k * 4 + 4]
        if sy >= 0xEF: continue
        base = (0x1000 if t & 1 else 0) + (t & 0xFE) * 16
        for r in range(16):
            for cx in range(8):
                x, y = sx + cx - 176, sy + 1 + r - 32
                if not (0 <= x < 64 and 0 <= y < 96): continue
                tb = base + (16 if r >= 8 else 0)
                lo, hi = v[tb + r % 8], v[tb + 8 + r % 8]
                c = ((lo >> (7 - cx)) & 1) | (((hi >> (7 - cx)) & 1) << 1)
                if c and img[y][x] is not None and not getattr(render, '_done', None):
                    pass
        # desenha de trás para frente para respeitar a prioridade
    for k in range(63, -1, -1):
        sy, t, at, sx = oam[k * 4:k * 4 + 4]
        if sy >= 0xEF: continue
        base = (0x1000 if t & 1 else 0) + (t & 0xFE) * 16
        for r in range(16):
            for cx in range(8):
                x, y = sx + cx - 176, sy + 1 + r - 32
                if not (0 <= x < 64 and 0 <= y < 96): continue
                tb = base + (16 if r >= 8 else 0)
                lo, hi = v[tb + r % 8], v[tb + 8 + r % 8]
                c = ((lo >> (7 - cx)) & 1) | (((hi >> (7 - cx)) & 1) << 1)
                if c: img[y][x] = v[0x3F10 + (at & 3) * 4 + c]
    return img


def main(pasta='experimento_v3'):
    buf, S = build_main()
    covers = open(os.path.join(ROOT, pasta, 'EDFC', 'COVERS.BIN'), 'rb').read()
    names = [l.rstrip('\n')[17:] for l in open(os.path.join(ROOT, pasta, 'gerar.txt'), encoding='utf-8')
             if l[:5].strip().isdigit()]
    i = names.index(NOME)
    rec = covers[(256 + 16 * i) * 512:(256 + 16 * i + 16) * 512]
    meta = rec[:512]
    ok = True

    def check(c, msg):
        nonlocal ok
        print(('  OK   ' if c else '  FALHA') + ' ' + msg); ok &= bool(c)

    cpu, mem, ppu = setup(buf, covers)
    cpu.on_read_prev = cpu.on_read
    ppu['vram'][0x3F00:0x3F04] = bytes([0x0F, 0x10, 0x0F, 0x28])   # paleta 0 gravada pelo OS na inicialização
    cpu.call(S['init_hook'])
    check(mem[S['enabled']] == 1, 'COVERS.BIN encontrado')

    print('\n== carregar a capa do Mario (alternância)')
    show_name(mem, NOME); ppu['mask'].clear(); ppu['reads'] = 0
    cpu.call(S['draw_hook']); cpu.call(S['idle_hook'])
    v = ppu['vram']
    check(ppu['reads'] == 10, 'leituras: %d (índice + meta + 3+3 sprites + 2 fundo)' % ppu['reads'])
    check(bytes(v[0x1000:0x1600]) == rec[512:2048], 'tiles do quadro A em $1000')
    check(bytes(v[0x1800:0x1E00]) == rec[2048:3584], 'tiles do quadro B em $1800 (tile + 128)')
    check(bytes(v[0x0000:0x0200]) == rec[3584:4096] and bytes(v[0x0800:0x0A00]) == rec[4096:4608], 'tiles do fundo')
    check(bytes(mem[PALTAB:PALTAB + 56]) == meta[256:312], 'paletas A e B na WRAM ($7F00)')
    check(bytes(v[0x23CD:0x23E0]) == meta[416:435], 'atributos na PPU')
    check(mem[S['flk']] == 1 and mem[S['frame']] == 0, 'alternância ligada, começando no quadro A')
    check(ppu['oam'] == meta[0:256], 'OAM do quadro A')

    print('\n== NMI quadro a quadro')
    mem[0xA2] = 0
    frames = []
    for q in range(4):
        nmi(cpu)
        frames.append((bytes(v[0x3F04:0x3F20]), ppu['oam'], render(ppu, ppu['oam'])))
    check(frames[0][0] == meta[256:284] and frames[1][0] == meta[284:312], 'paletas: quadro A, depois B')
    check(frames[2][0] == frames[0][0] and frames[3][0] == frames[1][0], 'e continua alternando A, B, A, B')
    oamB = bytearray(meta[0:256])
    for k in range(48): oamB[k * 4 + 1] ^= 0x80
    check(frames[0][1] == meta[0:256] and frames[1][1] == bytes(oamB), 'OAM: tiles A, depois tiles + 128')
    check(frames[0][2] != frames[1][2], 'os dois quadros desenhados são diferentes')
    check(bytes(v[0x3F0C:0x3F10]) == bytes([0x0F, 0x30, 0x00, 0x28]), 'paleta 3 (barra/menus) intacta')
    # média percebida dos quadros reconstruídos = prévia do gerador
    w, h, prev = png_read(os.path.join(ROOT, pasta, 'previews', 'Super Mario Bros. 3 (USA).png'))
    prev = [[prev[y * 3][x * 3] for x in range(64)] for y in range(96)]
    perc = [[avg_color(frames[0][2][y][x], frames[1][2][y][x]) for x in range(64)] for y in range(96)]
    iguais = sum(1 for y in range(96) for x in range(64) if perc[y][x] == tuple(prev[y][x]))
    check(iguais == 64 * 96, 'média dos quadros reconstruídos = prévia do gerador (%d/%d pixels)' % (iguais, 64 * 96))

    print('\n== NMI não mexe quando não deve')
    before = (bytes(v[0x3F00:0x3F20]), mem[S['frame']])
    mem[0xA2] = 1; nmi(cpu)
    check((bytes(v[0x3F00:0x3F20]), mem[S['frame']]) == before, 'com o OS enviando a tela ($A2=1): nada')
    mem[0xA2] = 0
    cpu.call(S['hide'])
    check(mem[S['flk']] == 0, 'menu (hide): alternância desligada')
    before = (bytes(v[0x3F00:0x3F20]), mem[S['frame']]); nmi(cpu)
    check((bytes(v[0x3F00:0x3F20]), mem[S['frame']]) == before, 'desligada: o NMI não mexe')

    print('\n== redesenho completo passa pelo w82fa')
    chamado = []
    cpu.stubs[0x82FA] = lambda c: chamado.append(1)
    mem[S['flk']] = 1
    cpu.call(S['w82fa'])
    check(mem[S['flk']] == 0 and chamado, 'w82fa desliga a alternância e chama o $82FA original')

    print('\n== trocar de jogo e voltar')
    r_frame_before = mem[S['frame']]
    show_name(mem, names[5]); cpu.call(S['draw_hook']); cpu.call(S['idle_hook'])
    check(mem[S['flk']] == 1 and mem[S['frame']] == 0, 'outra capa: alternância religada no quadro A')
    show_name(mem, 'Jogos'); cpu.call(S['draw_hook'])
    check(mem[S['flk']] == 0 and ppu['mask'][-1] == 0x0A, 'pasta: sem capa, alternância desligada')

    print('\nRESULTADO:', 'TUDO OK' if ok else 'HÁ FALHAS')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main(*sys.argv[1:2]) else 1)
