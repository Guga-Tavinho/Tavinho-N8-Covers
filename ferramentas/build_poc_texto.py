"""POC: texto fixo na tela do navegador ("Instagram: @tavinho.games"), sobre a firmware v3 normal.

No navegador o OS escreve texto nas linhas 2-22 (lista) e 25-26 (nome completo); as linhas 0-1 e 23-24 não são
usadas (a linha 1 ficou escondida pela borda da TV de tubo). O texto vai para a linha 23 do buffer de tela
(logo acima da barra cinza), centralizado, no wrapper do redesenho completo (w82fa, que já
existia para parar a alternância): toda vez que o OS envia a tela inteira para a PPU, o texto vai junto. Popups e
menus restauram o buffer, e a linha 23 não é tocada.
Na fonte do OS o tile = código ASCII (o OS soma txt_color $FF com carry = o próprio código).

uso:  python build_poc_texto.py      saída: poc_texto/EDFC/OS.BIN (+ COVERS.BIN da firmware_gerada)
"""
import hashlib, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
from build_capas import patch, jsr
import build_capas_v3 as V3
from asm6502 import assemble

TEXTO = 'Instagram: @tavinho.games'
LINHA = 23                                       # logo acima da barra cinza (a linha 1 fica escondida na TV de tubo)
COLUNA = (32 - len(TEXTO)) // 2
assert len(TEXTO) <= 30 and all(32 <= ord(c) < 127 for c in TEXTO)

SEG_E = (V3.SEG_E[0], V3.SEG_E[1], V3.sub(V3.SEG_E[2], '''w82fa:  LDA #0                  ; redesenho completo do OS: alternância parada antes
        STA flk
        JMP GFX_FULL''', '''w82fa:  LDA #0                  ; redesenho completo do OS: alternância parada antes
        STA flk
        LDX #%d                 ; POC: texto fixo na linha %d do buffer de tela (vai junto no envio completo)
wt_l:   LDA s_txt,X
        STA $%04X,X
        DEX
        BPL wt_l
        JMP GFX_FULL
s_txt:  .text "%s"''' % (len(TEXTO) - 1, LINHA, 0x6000 + LINHA * 32 + COLUNA, TEXTO)))
SEGMENTS = [V3.SEG_A, V3.SEG_D, V3.SEG_MAIN, V3.SEG_C, SEG_E]


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
    out_dir = os.path.join(ROOT, 'poc_texto', 'EDFC')
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, 'OS.BIN'), 'wb').write(buf)
    cov = os.path.join(ROOT, 'firmware_gerada', 'EDFC', 'COVERS.BIN')
    if os.path.exists(cov): shutil.copyfile(cov, os.path.join(out_dir, 'COVERS.BIN'))
    print('gerado:', out_dir, 'SHA1', hashlib.sha1(buf).hexdigest())
    for org, end, code in segs:
        print('  $%04X-$%04X  %3d de %3d bytes (livres %d)' % (org, org + len(code) - 1, len(code), end - org,
                                                             end - org - len(code)))
    return buf, S


if __name__ == '__main__':
    main()
