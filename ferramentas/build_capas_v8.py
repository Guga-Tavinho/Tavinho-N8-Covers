"""POC v8: a v7 (capa grande, carga rápida — estável no aparelho) + FLICKER OPCIONAL nos sprites, por capa.

Capa com flicker (escolha no COVERS.BIN, byte 300 do setor 15): os sprites alternam a cada quadro entre dois
desenhos e duas paletas (como a v3): o olho vê a média -> mais cores onde há sprites. O fundo não pisca.
  - quadro B usa os pares p+64 (tile 2p+1 EOR $80), carregados nos mesmos blocos de sprite (faixas B)
  - a cada quadro, no vblank: paletas de sprite do quadro + OAMDMA ($0200); no fim do quadro (depois das trocas
    de banco): troca os tiles da OAM ($80) e o quadro. O sprite 0 (sincronia) não muda.
Capa sem flicker: igual à v7. Registro de 64 setores por capa (512 + 64*idx).
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
import build_capas_v5 as V5
import build_capas_v7 as V7
from asm6502 import assemble

MOD2 = V7.MOD2
HEAD = V7.HEAD + r'''
CAB      = $7F80        ; cópia dos bytes 256-347 do setor 15:
SPAL8    = $7F80        ;   paletas de sprite A (16)
STB8     = $7F90        ;   faixas A (28)
FLAG     = $7FAC        ;   1 = capa com flicker
SPALB8   = $7FB0        ;   paletas de sprite B (16)
STBB8    = $7FC0        ;   faixas B (28)
frm      = $7F5C        ; quadro atual (0 = A, 1 = B)
'''
sub = V5.sub

SEG_A, SEG_D = V7.SEG_A, V7.SEG_D

# ---------------------------------------------------------------- residente: flicker por quadro (SEG_C)
SEG_C = (V7.SEG_C[0], V7.SEG_C[1], V7.SEG_C[2] + r'''
; ---------------------------------------------------------------- flicker dos sprites (só capas com FLAG)
flk_vb: LDA rev                 ; vblank: paletas de sprite do quadro + OAMDMA
        BNE fv_r
        LDA FLAG
        BEQ fv_r
        LDA #$3F
        STA $2006
        LDA #$10
        STA $2006
        LDX #0
        LDA frm
        BEQ fv_1
        LDX #$30                ; SPALB8 = SPAL8 + $30
fv_1:   LDY #16
fv_l:   LDA SPAL8,X
        STA $2007
        INX
        DEY
        BNE fv_l
        LDA #0
        STA $2003
        LDA #2
        STA $4014
        JMP scroll0
fv_r:   RTS
''')
FLK_TG = '''
flk_tg: LDA FLAG                ; fim do quadro: tiles da OAM do outro quadro (menos o sprite 0)
        BEQ ft_r
        LDX #4
ft_l:   LDA $0201,X
        EOR #$80
        STA $0201,X
        INX
        INX
        INX
        INX
        BNE ft_l
        LDA frm
        EOR #1
        STA frm
ft_r:   RTS
'''

e = V7.SEG_E[2]
e = sub(e, '''        LDA #1                  ; topo da tela: banco 1
        JSR banco''', '''        LDA #1                  ; topo da tela: banco 1
        JSR banco
        JSR flk_vb              ; capa com flicker: paletas e sprites do quadro''')
e = sub(e, '''        CMP #15
        BNE sw_l
        JMP IDLE''', '''        CMP #15
        BNE sw_l
        JSR flk_tg              ; prepara o outro quadro
        JMP IDLE''')
SEG_E = (V7.SEG_E[0], V7.SEG_E[1], e)

# ---------------------------------------------------------------- módulo: registro de 64 setores, faixas B
r = V7.MOD_SRC
r = sub(r, '''l_found: LDA (P),Y              ; setor = 512 + idx*32
        STA sec
        INY
        LDA (P),Y
        LDX #5''', '''l_found: LDA (P),Y              ; setor = 512 + idx*64
        STA sec
        INY
        LDA (P),Y
        LDX #6''')
r = sub(r, '''sl_m:   LDA (P),Y               ; paletas (16) + tabela dos blocos (28)
        STA SPAL,Y
        INY
        CPY #44
        BNE sl_m
        LDY #27
sl_t:   LDA SPAL+16,Y
        STA STB,Y
        DEY
        BPL sl_t
        LDA #1
        STA grp''', '''sl_m:   LDA (P),Y               ; bytes 256-347: paletas A, faixas A, flicker, paletas B, faixas B
        STA CAB,Y
        INY
        CPY #92
        BNE sl_m
        JSR sp_all              ; faixas do quadro A
        LDA FLAG
        BEQ sl_f
        LDY #27                 ; e as do quadro B
sl_d:   LDA STBB8,Y
        STA STB8,Y
        DEY
        BPL sl_d
        JSR sp_all
sl_f:   JMP sp_oam
sp_all: LDA #1
        STA grp''')
r = r.replace('LDA STB+1,X', 'LDA STB8+1,X').replace('LDA STB,X ', 'LDA STB8,X ').replace(
    'LDA STB+2,X', 'LDA STB8+2,X').replace('LDA STB+3,X', 'LDA STB8+3,X')
r = sub(r, '''rv_sp:  LDA SPAL,X''', '''rv_sp:  LDA SPAL8,X''')
r = sub(r, '''        CMP #15
        BNE sp_g
        LDA csec                ; agora a OAM de verdade (setor 15 de novo)''', '''        CMP #15
        BNE sp_g
        RTS
sp_oam: LDA csec                ; agora a OAM de verdade (setor 15 de novo)''')
r = sub(r, '''        LDA #0
        STA rev
        JMP scroll0''', '''        LDA #0
        STA rev
        STA frm                 ; flicker começa no quadro A
        JMP scroll0''')
# nt_rows sai do módulo para a firmware residente (espaço)
i, j = r.index('nt_rows: STA cnt'), r.index("        RTS\n", r.index('nt_rows: STA cnt')) + len("        RTS\n")
NT_ROWS = r[i:j]
r = r[:i] + r[j:]
MOD_SRC = r + FLK_TG
SEG_MAIN = (V7.SEG_MAIN[0], V7.SEG_MAIN[1], V7.SEG_MAIN[2] + '\n' + NT_ROWS)


# ---------------------------------------------------------------- espaço: setP -> $FBD4, q_next -> $F753
def _mover():
    global SEG_MAIN, SEG_D, SEG_C
    m = SEG_MAIN[2]
    setp = 'setP:   LDA FATBUF\n        STA P\n        LDA FATBUF+1\n        STA P+1\n        RTS\n'
    qnext = ('q_next: LDA Q                   ; Q += 32 (próxima linha do buffer)\n        CLC\n        ADC #32\n'
             '        STA Q\n        BCC qn_r\n        INC Q+1\nqn_r:   RTS\n')
    assert m.count(setp) == 1 and m.count(qnext) == 1
    m = m.replace(setp, '').replace(qnext, '')
    SEG_MAIN = (SEG_MAIN[0], SEG_MAIN[1], m)
    SEG_D = (SEG_D[0], SEG_D[1], SEG_D[2] + '\n' + setp)
    SEG_C = (SEG_C[0], SEG_C[1], SEG_C[2] + '\n' + qnext)


_mover()


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
    log('OS.BIN v8 SHA1 %s' % hashlib.sha1(buf).hexdigest())
    segs, _ = assemble_all()
    for org, end, code in segs:
        log('  $%04X-$%04X  %3d de %3d bytes (livres %d)' % (org, org + len(code) - 1, len(code), end - org,
                                                           end - org - len(code)))
    return buf, S, modulo


if __name__ == '__main__':
    main()
