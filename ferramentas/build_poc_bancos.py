"""POC: troca de banco de CHR no MEIO DA TELA (registrador $82 do cartucho), a partir da v2 estável (sem flicker).

Ideia: os tiles da capa (fundo e sprites) ficam SÓ no banco 2 (CHR $0000-$1FFF = blocos de 4 KB 2 e 3); o banco 0
tem só a fonte. A cada quadro, com a lista parada, a firmware troca para o banco 2 no fim da linha 31 (antes da
capa, que começa na linha 32) e volta para o banco 0 no fim da linha 127 (a capa termina na 127).
  - capa perfeita e lista normal      -> a troca no meio da tela funciona e é estável;
  - capa com lixo                     -> a troca não acontece (no banco 0 não há capa);
  - capa com linhas tremendo nas bordas (em cima/embaixo) -> o momento da troca precisa de ajuste.

Sincronia: sprite 0 invisível (atrás do fundo) na coluna 0, linhas 16-31 (toda a fonte é opaca: o "fundo" das
letras é a cor 2 = preto), com o tile $60 da tabela 1 (pixel 0,0 opaco). A espera roda na espera ociosa do
navegador (nunca no NMI, para não atrapalhar escritas do OS em $4400/$4401):
  1) espera o NMI do quadro ($9E), 2) espera a flag do sprite 0 apagar (fim do vblank), 3) espera o sprite 0
  (linha 16), 4) 1753 ciclos -> banco 2 (ponto ~190-223 da linha 31), 5) 10923 + 12 ciclos -> banco 0 (ponto
  ~260-293 da linha 127). A faixa de 33 pontos vem do laço que espera o sprite 0 (11 ciclos).
Temporização NTSC (341 pontos por linha, 3 pontos por ciclo); cada espera tem limite (não trava se o sprite 0 não
aparecer, por exemplo com um menu aberto).
- Fonte no banco 2: `$826F` (zera a CHR e copia a fonte) é chamada duas vezes (bancos 0 e 2) nos dois pontos
  em que o OS a chama ($ECDB e $ED7B).
- Carga da capa: no banco 2 (`lc2` em volta do load_cover); depois o sprite 0 da capa vai para a entrada 48 da
  OAM e a entrada 0 vira o sprite de sincronia.

uso:  python build_poc_bancos.py     saída: poc_bancos/EDFC/OS.BIN (COVERS.BIN no formato v2)
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
from build_capas import patch, jsr
import build_capas_v2 as V2
from asm6502 import assemble


def sub(src, old, new):
    assert src.count(old) == 1, 'trecho não encontrado: ' + old[:60]
    return src.replace(old, new)


HEAD = V2.COMMON2 + V2.EXTRA_CONST + r'''
NMIFLAG  = $9E          ; o NMI do OS põe 1 aqui a cada quadro (quando não está ocupado)
INITCHR  = $826F        ; ppu_screen_init_upload_chr
'''

# $81C5: a espera ociosa carrega a capa pelo lc2 (banco 2) e depois faz a troca de banco do quadro
SEG_A = (V2.SEG_A[0], V2.SEG_A[1], sub(V2.SEG_A[2], '''        JSR load_cover
i_done: JMP IDLE''', '''        JSR lc2
i_done: JMP split'''))

# $F753 (+ título da Device Info): o resto da v2 + lc2
SEG_C = (0xF753, V2.SEG_C[1], V2.SEG_C[2] + r'''
; ---------------------------------------------------------------- POC bancos: carga da capa no banco 2
lc2:    LDA #2
        JSR banco
        JSR load_cover
        LDA #0
        JSR banco
        LDA has
        BEQ lc_r
        LDX #3                  ; sprite 0 da capa -> entrada 48; entrada 0 = sprite de sincronia
lc_s:   LDA $0200,X
        STA $02C0,X
        LDA sync0,X
        STA $0200,X
        DEX
        BPL lc_s
        JMP cover_show          ; OAMDMA de novo (com o sprite de sincronia)
lc_r:   RTS
sync0:  .byte 15, $61, $20, 0   ; Y (linhas 16-31), tiles $60/$61 da tabela 1, atrás do fundo, X=0
''')

# $A680 (livre na v2): troca de banco no meio da tela + fonte no banco 2
SEG_E = 0xA680, 0xA707, r'''
split:  LDA has                 ; só com a capa na tela
        BEQ sp_out
        LDA #0
        STA NMIFLAG
        TAX
        LDY #$10
sw0:    LDA NMIFLAG             ; 1) espera o NMI (o vblank já começou: ler $2002 agora não atrapalha o NMI)
        BNE sw1
        DEX
        BNE sw0
        DEY
        BNE sw0
        BEQ sp_out
sw1:    LDY #$10
sw1a:   BIT $2002               ; 2) flag do sprite 0 apaga no fim do vblank
        BVC sw2
        DEX
        BNE sw1a
        DEY
        BNE sw1a
        BEQ sp_out
sw2:    LDY #$10
sw2a:   BIT $2002               ; 3) sprite 0 (linha 16): laço de 11 ciclos
        BVS sw3
        DEX
        BNE sw2a
        DEY
        BNE sw2a
sp_out: JMP IDLE
sw3:    LDY #158                ; 4) 158*(5*1+6)+15 = 1753 ciclos -> ponto ~190-223 da linha 31 (antes da busca
        LDA #1                  ;    dos sprites da linha 32, que começa no ponto 257; a fonte é igual nos 2 bancos)
        JSR dly
        LDA #$82
        STA $4400
        LDA #2
        STA $4401               ;    banco 2 (a capa)
        LDY #18                 ; 5) 18*(5*120+6)+15 = 10923 (+12) = 96 linhas + 70 pontos -> ponto ~260-293 da
        LDA #120                ;    linha 127 (depois do último pixel da capa; a linha 128 não tem sprites)
        JSR dly
        LDA #$82
        STA $4400
        LDA #0
        STA $4401               ;    banco 0 (só a fonte)
        JMP IDLE
dly:    TAX                     ; Y*(5*A+6) + 15 ciclos (com o LDY/LDA/JSR de quem chama)
dl_i:   DEX
        BNE dl_i
        DEY
        BNE dly
        RTS
chr2:   JSR INITCHR             ; fonte no banco 0 (como o OS faz)
        LDA #2
        JSR banco
        JSR INITCHR             ; e no banco 2 (os tiles da capa vão para lá)
        LDA #0
banco:  LDX #$82                ; banco de CHR = A
        STX $4400
        STA $4401
        RTS
'''

SEGMENTS = [SEG_A, V2.SEG_D, V2.SEG_MAIN, SEG_C, SEG_E]


def assemble_all():
    syms = {}
    for _ in range(6):
        new = {}
        for org, end, src in SEGMENTS:
            new.update(assemble(HEAD + src, org, syms, strict=False)[1])
        if new == syms:
            break
        syms = new
    out = [(org, end, assemble(HEAD + src, org, syms)[0]) for org, end, src in SEGMENTS]
    for org, end, code in out:
        assert org + len(code) <= end, 'segmento $%04X: %d bytes não cabem (limite %d)' % (org, len(code), end - org)
    return out, syms


def conferir_tempo(segs, S):
    """Confere que os laços de espera não cruzam página (o desvio custaria 1 ciclo a mais)."""
    for rot in ('dly', 'dl_i', 'sw2a', 'sw3'):
        assert S[rot] >> 8 == (S[rot] + 8) >> 8, 'laço %s perto de fim de página: ajustar' % rot
    d1 = 158 * (5 * 1 + 6) + 15
    d2 = 18 * (5 * 120 + 6) + 15
    return d1, d2


def main():
    orig, buf, info = build('base')
    segs, S = assemble_all()
    d1, d2 = conferir_tempo(segs, S)
    assert S['hook_cursor'] == 0x81C5 and S['draw_hook'] == 0x81C8
    assert orig[cpu2file(0xF753):cpu2file(0xF753) + 12] == b'Device Info\0'
    assert orig[cpu2file(0xA680):cpu2file(0xA680) + 3] == bytes([0x20, 0x43, 0xF1]), '$A680 não confere'
    for org, end, code in segs:
        o = cpu2file(org)
        buf[o:o + len(code)] = code
    patch(buf, 0x833D, buf[cpu2file(0x833D):cpu2file(0x833D) + 3], jsr(S['hide']))
    patch(buf, 0xBB4A, jsr(0x9DE0), jsr(S['init_hook']))
    patch(buf, 0xD9EB, jsr(0xAB25), jsr(S['idle_hook']))
    patch(buf, 0xCB8B, jsr(S['draw_hook']), jsr(S['mask_entry']))
    patch(buf, 0xCB29, [0xA9, 0x15], [0xA9, 0x14])
    patch(buf, 0xCCE1, jsr(0xD0C6), jsr(S['cm_r']))
    patch(buf, 0xCCFC, jsr(0xD2B9), jsr(S['cm_r']))
    patch(buf, 0xECDB, jsr(0x826F), jsr(S['chr2']))                     # POC: fonte nos bancos 0 e 2
    patch(buf, 0xED7B, jsr(0x826F), jsr(S['chr2']))
    out_dir = os.path.join(ROOT, 'poc_bancos', 'EDFC')
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, 'OS.BIN'), 'wb').write(buf)
    print('gerado:', out_dir, 'SHA1', hashlib.sha1(buf).hexdigest())
    print('esperas: %d ciclos até a troca para o banco 2, %d + 12 até a volta' % (d1, d2))
    for org, end, code in segs:
        print('  $%04X-$%04X  %3d de %3d bytes' % (org, org + len(code) - 1, len(code), end - org))
    return buf, S


if __name__ == '__main__':
    main()
