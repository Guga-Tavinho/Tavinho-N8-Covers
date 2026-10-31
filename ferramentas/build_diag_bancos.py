"""DIAGNÓSTICO: o registrador $82 do cartucho (banco de CHR) muda o que a PPU mostra enquanto o MENU roda?

Firmware = a v3 normal (capas 64x96) + um acréscimo: com a lista parada (espera ociosa do navegador), o banco de
CHR alterna entre 0 e 1 a cada 64 quadros (~1 s). No console:
  - a tela pisca entre normal e lixo/apagada  -> a troca de banco funciona no menu (caminho para mais tiles);
  - nada muda                                  -> o $82 não afeta a PPU no menu.
Se só o texto mudar e a capa (sprites, tabela $1000) não, o banco cobre só $0000-$0FFF (4 KB).
A troca é feita na espera ociosa (fora do NMI), para não atrapalhar escritas do OS em $4400/$4401.
No reset e ao carregar um jogo o próprio OS escreve o $82.

uso:  python build_diag_bancos.py      saída: teste_bancos_chr/EDFC/OS.BIN (+ COVERS.BIN da firmware_gerada)
"""
import hashlib, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
from build_capas import patch, jsr
import build_capas_v3 as V3
from asm6502 import assemble

sub = V3.sub
SEG_A = (V3.SEG_A[0], V3.SEG_A[1], sub(V3.SEG_A[2], '''i_done: JMP IDLE''', '''i_done: JMP diag'''))
SEG_E = (V3.SEG_E[0], V3.SEG_E[1], sub(V3.SEG_E[2], '''nmi_flk: LDA flk                ; (o NMI do OS já salvou A e leu o joypad)''',
                                       '''nmi_flk: INC tick               ; DIAGNÓSTICO: conta os quadros
        LDA flk                 ; (o NMI do OS já salvou A e leu o joypad)''') + r'''
diag:   LDA tick                ; DIAGNÓSTICO: banco de CHR = 1 na metade de cada ciclo de 128 quadros
        AND #$40
        BEQ dg0
        LDA #1
dg0:    CMP banco
        BEQ dg_r
        STA banco
        LDX #$82
        STX $4400
        STA $4401
dg_r:   JMP IDLE
tick:   .byte 0
banco:  .byte 0
''')
SEGMENTS = [SEG_A, V3.SEG_D, V3.SEG_MAIN, V3.SEG_C, SEG_E]


def assemble_all():
    syms = {}
    for _ in range(6):
        new = {}
        for org, end, src in SEGMENTS:
            new.update(assemble(V3.HEAD + src, org, syms, strict=False)[1])
        if new == syms:
            break
        syms = new
    out = [(org, end, assemble(V3.HEAD + src, org, syms)[0]) for org, end, src in SEGMENTS]
    for org, end, code in out:
        assert org + len(code) <= end, 'segmento $%04X: %d bytes não cabem (limite %d)' % (org, len(code), end - org)
    return out, syms


def main():
    orig, buf, info = build('base')
    segs, S = assemble_all()
    for org, end, code in segs:
        o = cpu2file(org)
        buf[o:o + len(code)] = code
    patch(buf, 0x833D, buf[cpu2file(0x833D):cpu2file(0x833D) + 3], jsr(S['hide']))
    patch(buf, 0xBB4A, jsr(0x9DE0), jsr(S['init_hook']))
    patch(buf, 0xD9EB, jsr(0xAB25), jsr(S['idle_hook']))
    patch(buf, 0xCB8B, jsr(S['draw_hook']), jsr(S['mask_entry']))
    patch(buf, 0xCB83, jsr(0x82FA), jsr(S['w82fa']))
    patch(buf, 0xCB29, [0xA9, 0x15], [0xA9, 0x14])
    patch(buf, 0xCCE1, jsr(0xD0C6), jsr(S['cm_r']))
    patch(buf, 0xCCFC, jsr(0xD2B9), jsr(S['cm_r']))
    patch(buf, 0x80E6, [0xAD, 0x02, 0x20], [0x4C, S['nmi_flk'] & 0xFF, S['nmi_flk'] >> 8])
    out_dir = os.path.join(ROOT, 'teste_bancos_chr', 'EDFC')
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, 'OS.BIN'), 'wb').write(buf)
    cov = os.path.join(ROOT, 'firmware_gerada', 'EDFC', 'COVERS.BIN')
    if os.path.exists(cov): shutil.copyfile(cov, os.path.join(out_dir, 'COVERS.BIN'))
    print('gerado:', out_dir, 'SHA1', hashlib.sha1(buf).hexdigest())
    for org, end, code in segs:
        print('  $%04X-$%04X  %3d de %3d bytes' % (org, org + len(code) - 1, len(code), end - org))
    return buf, S


if __name__ == '__main__':
    main()
