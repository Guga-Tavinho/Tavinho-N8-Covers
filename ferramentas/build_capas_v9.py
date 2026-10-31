"""POC v9: a v8 (capa grande + flicker opcional) + UMA COR LIVRE A MAIS: a 3ª cor da paleta 3.

A paleta 3 é a da barra cinza: cor 1 = branco (nome do jogo), cor 2 = cinza (fundo), cor 3 = amarelo ($28), que
só aparece no nome de PASTA na barra. Enquanto a capa está na tela (um jogo selecionado), essa cor 3 vira uma cor
escolhida para a capa (byte 367 do setor 0; o conversor só a usa se melhorar a capa). Ela volta ao amarelo
sempre que a capa some: botão (sp_hide -> pal_wr), menu/redesenho ($833D -> hide).
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
import build_capas_v5 as V5
import build_capas_v8 as V8
from asm6502 import assemble

MOD2 = V8.MOD2
HEAD = V8.HEAD + r'''
COR3     = $7F6E        ; 3ª cor da paleta 3 desta capa (byte 367 do setor 0, logo depois da tabela CHT)
'''
sub = V5.sub

SEG_A, SEG_D, SEG_MAIN, SEG_E = V8.SEG_A, V8.SEG_D, V8.SEG_MAIN, V8.SEG_E
# espaço: os 4 bytes da marca do módulo vão para $81C5
_mg = 'lm_mg:  .byte 0,0,0,0              ; impressão digital do módulo (preenchida na montagem)\n'
assert SEG_MAIN[2].count(_mg) == 1
SEG_MAIN = (SEG_MAIN[0], SEG_MAIN[1], SEG_MAIN[2].replace(_mg, ''))
SEG_A = (SEG_A[0], SEG_A[1], SEG_A[2] + '\n' + _mg)

c = V8.SEG_C[2]
c = sub(c, '''hd_pal: STA $2007
        DEX
        BNE hd_pal''', '''hd_pal: STA $2007
        DEX
        BNE hd_pal
        LDX #12                 ; paleta 3 do OS de volta (o amarelo $28 da barra)
hd_p3:  LDA $825F,X
        STA $2007
        INX
        CPX #16
        BNE hd_p3''')
SEG_C = (V8.SEG_C[0], V8.SEG_C[1], c)

r = V8.MOD_SRC
r = sub(r, '''        LDY #13                 ; pedaços de cada grupo (bytes 353-366 do setor 0)''',
        '''        LDY #14                 ; pedaços de cada grupo (bytes 353-366) + a cor 3 da paleta 3 (367)''')
r = sub(r, '''        LDA #$09
        STA $2006
pw3:    LDY #3''', '''        LDA #$09
        STA $2006
        JSR pw3
        LDA #$3F                ; 3ª cor da paleta 3: a da capa, ou o amarelo $28 de volta
        STA $2006
        LDA #$0F
        STA $2006
        LDA COR3
        BIT amode
        BPL pw_c
        LDA #$28
pw_c:   STA $2007
        RTS
pw3:    LDY #3''')
r = sub(r, '''        LDA frm
        EOR #1
        STA frm
ft_r:   RTS''', '''        JMP frm_tg              ; (troca o quadro: na firmware residente, por espaço)
ft_r:   RTS''')
# espaço: sp_all antes do spr_load (o "JMP sp_oam" some: cai direto nele)
i = r.index('sp_all: LDA #1')
j = r.index('sp_oam: ', i)
k = r.rindex('        RTS\n', i, j) + len('        RTS\n')
corpo = r[i:k]
r = r[:i] + r[k:]
r = sub(r, 'sl_f:   JMP sp_oam\n', 'sl_f:\n')
r = sub(r, 'sl_r0:  RTS\nspr_load:', corpo + 'sl_r0:  RTS\nspr_load:')
MOD_SRC = r
SEG_E = (SEG_E[0], SEG_E[1], SEG_E[2] + '''
frm_tg: LDA frm                 ; flicker: o outro quadro
        EOR #1
        STA frm
        RTS
''')
qn = '''q_next: LDA Q                   ; Q += 32 (próxima linha do buffer)
        CLC
        ADC #32
        STA Q
        BCC qn_r
        INC Q+1
qn_r:   RTS
'''
assert SEG_C[2].count(qn) == 1
SEG_C = (SEG_C[0], SEG_C[1], SEG_C[2].replace(qn, ''))
SEG_MAIN = (SEG_MAIN[0], SEG_MAIN[1], SEG_MAIN[2] + '\n' + qn)


def assemble_all():
    segs_src = [SEG_A, SEG_D, SEG_MAIN, SEG_C, SEG_E, (MOD2, MOD2 + 0x3FC, MOD_SRC)]
    syms = {}
    for _ in range(8):
        new = {}
        for org, end, src in segs_src:
            new.update(assemble(HEAD + src, org, syms, strict=False)[1])
        if new == syms: break
        syms = new
    return [(org, end, assemble(HEAD + src, org, syms)[0]) for org, end, src in segs_src], syms


def main(log=print):
    V5.assemble_all = assemble_all
    try:
        buf, S, modulo = V5.main(log=lambda *a: None)
    finally:
        import importlib; importlib.reload(V5)
    marca = hashlib.sha1(modulo).digest()[:4]
    modulo = modulo.ljust(0x3FC, b'\0') + marca
    o = cpu2file(S['lm_mg'])
    buf[o:o + 4] = marca
    log('OS.BIN v9 SHA1 %s' % hashlib.sha1(buf).hexdigest())
    segs, _ = assemble_all()
    for org, end, code in segs:
        log('  $%04X-$%04X  %3d de %3d bytes (livres %d)' % (org, org + len(code) - 1, len(code), end - org,
                                                           end - org - len(code)))
    return buf, S, modulo


if __name__ == '__main__':
    main()
