"""POC v5: capa grande no navegador com FUNDO + SPRITES (até 62 sprites 8x16, 4 paletas próprias) + tela cheia.

Parte da v4 (build_capas_v4.py, testada no aparelho) e muda:
  - fundo nos bancos ÍMPARES 1, 3, ..., 13 (grupo g -> banco 2g+1 -> bloco 2g+1); a metade de sprites da janela de
    cada banco (bloco 2g+2) fica só para os tiles dos sprites daquele trecho da tela. Fonte nos blocos 0, 1, 3..13
    (chr_all: $826F com $82 = 0, 1, 3, ..., 13)
  - sprites: o tile de cada sprite vai para todos os blocos de sprites que podem estar ativos nas linhas dele
    (máscara no COVERS.BIN), com o MESMO número -> a troca de banco continua podendo cair em qualquer ponto da
    linha compartilhada. Sprite 0 (sincronia) = par 0 do bloco 2 (tile $01)
  - quase toda a carga passa para um MÓDULO de 1 KB (setores 257-258) em $6400-$67FF (o backup da tela do OS,
    livre no navegador), recarregado a cada capa; na firmware fica só o carregador (lmod). Variáveis dos sprites
    em $7F00 (onde a v3 guardava as paletas)
  - a OAM vai direto para $0200 na carga, com as paletas de sprite pretas; no último passo do aparecimento entram
    as paletas de verdade (os sprites surgem junto com o fundo)
  - sem a tela cheia (o usuário não quis): registro de 32 setores por capa (capa i em 512 + 32*i), sem o
    visualizador e sem o contador da espera
COVERS.BIN: índice (0-255), módulo (257-258), registros (conv_capa_grande.converter_v5: sprites nos setores 15-19).
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
from build_capas import patch, jsr
import build_capas_v4 as V4
from asm6502 import assemble

ESPERA_TELA_CHEIA = V4.ESPERA_TELA_CHEIA
SETOR_MODULO = 257
MOD2 = 0x6400
CUSTO_VOLTA = 47                         # ciclos do laço das trocas fora da espera (v4: 41 medidos + 6 do INC a mais)
Y0, A0 = V4.Y0, V4.A0
YP, AP = V4.espera(V4.C_PASSO - CUSTO_VOLTA)

HEAD = V4.HEAD + r'''
MOD2     = $6400        ; módulo (setores 257-258, 1 KB), recarregado a cada capa
SPAL     = $7F00        ; paletas de sprite (16) e, logo depois, as máscaras dos 63 pares (WRAM, como a v3)
SMASK    = $7F10
wcnt     = $7F50        ; variáveis do módulo
pair     = $7F51
scnt     = $7F52
smk      = $7F53
sbank    = $7F54
'''


def sub(src, old, new, n=1):
    assert src.count(old) == n, 'trecho não encontrado (%d): %s' % (src.count(old), old[:70])
    return src.replace(old, new)


SEG_A = V4.SEG_A
SEG_D = (V4.SEG_D[0], V4.SEG_D[1], sub(V4.SEG_D[2],
         "fs_go:  JMP ($04E9)             ; roda o setor lido (o visualizador se copia para $6400)\n", ""))

# ---------------------------------------------------------------- $D0C6: init, CRC, início da carga, lmod, chr_all
m = V4.SEG_MAIN[2]
i, j = m.index('        LDA #<257'), m.index('        INC enabled\nin_done:')
m = m[:i] + m[j:]                                                      # init: sem o módulo de $7F00
i, j = m.index('        LDA want                ; balde'), m.index('cmp3:')
RESTO = m[i:j]                                                         # resto da carga -> módulo
m = m[:i] + '''        JSR lmod                ; módulo (1 KB) -> $6400
        BNE l_fail0
        JMP lc_rest
lmod:   LDA #<%d                ; setores 257-258 -> $6400-$67FF; Z=1 se ok
        STA sec
        LDA #>%d
        STA sec+1
        LDA #>MOD2
        STA lm_d+2
lm_s:   LDA sec
        LDX sec+1
        JSR lba_read
        BNE lm_r
        JSR setP
        LDX #2
        LDY #0
lm_c:   LDA (P),Y
lm_d:   STA MOD2,Y              ; endereço automodificado (página de destino)
        INY
        BNE lm_c
        INC P+1
        INC lm_d+2
        DEX
        BNE lm_c
        INC sec
        LDA lm_d+2
        CMP #$68
        BNE lm_s
        LDA #0
lm_r:   RTS
''' % (SETOR_MODULO, SETOR_MODULO) + m[j:]
m = sub(m, '''ca_l:   LDA grp
        JSR banco
        JSR INITCHR
        INC grp
        LDA grp
        CMP #8
        BNE ca_l''', '''ca_l:   LDA grp                 ; bancos 0, 1, 3, 5, ..., 13
        JSR banco
        JSR INITCHR
        LDA grp
        BNE ca_2
        INC grp
        BNE ca_l
ca_2:   INC grp
        INC grp
        LDA grp
        CMP #15
        BNE ca_l''')
SEG_MAIN = (V4.SEG_MAIN[0], V4.SEG_MAIN[1], m)

# ---------------------------------------------------------------- $F753: sem o l_sec (vai para o módulo), + full
c = V4.SEG_C[2]
i, j = c.index('; ---------------------------------------------------------------- carga: um setor'), \
    c.index('; ---------------------------------------------------------------- sub-rotinas')
LSEC = c[i:j]
c = c[:i] + c[j:]
SEG_C = (V4.SEG_C[0], V4.SEG_C[1], c)

# ---------------------------------------------------------------- $A680: split com os bancos ímpares
e = V4.SEG_E[2]
e = sub(e, '''        LDA #2
        STA grp
sw_l:''', '''        LDA #3
        STA grp
sw_l:''')
e = sub(e, '''        INC grp
        LDA grp
        CMP #8
        BNE sw_l''', '''        INC grp                 ; bancos 3, 5, ..., 13
        INC grp
        LDA grp
        CMP #15
        BNE sw_l''')
e = sub(e, 'sw_l:   LDY #%d                 ; 24 linhas\n        LDA #%d' % (V4.YP, V4.AP),
        'sw_l:   LDY #%d                 ; 24 linhas\n        LDA #%d' % (YP, AP))
e = sub(e, '''        LDA rev                 ; capa pronta e parada: conta para a tela cheia
        BNE sp_out
        INC fs_t
        LDA fs_t
        CMP #%d
        BNE sp_out
        JMP full''' % V4.ESPERA_TELA_CHEIA, '''        JMP IDLE''')
SEG_E = (V4.SEG_E[0], V4.SEG_E[1], e)

# ---------------------------------------------------------------- módulo ($6400, 1 KB)
r = RESTO.replace('l_fail0', 'l_fail1')
r = sub(r, '''l_found: LDA (P),Y              ; setor = 512 + idx*64
        STA sec
        INY
        LDA (P),Y
        LDX #6''', '''l_found: LDA (P),Y              ; setor = 512 + idx*32
        STA sec
        INY
        LDA (P),Y
        LDX #5''')
r = sub(r, '''        INC grp
        LDA grp
        CMP #8
        BNE l_g
        LDA #$F0                ; OAM: só o sprite de sincronia
        LDX #0
l_o:    STA $0200,X
        INX
        BNE l_o
        LDX #3
l_o2:   LDA sync0,X
        STA $0200,X
        DEX
        BPL l_o2
        JSR WAITVB
        LDA #0
        STA $2003''', '''        INC grp                 ; bancos ímpares 1, 3, ..., 13
        INC grp
        LDA grp
        CMP #15
        BNE l_g
        JSR spr_load            ; tiles dos sprites; OAM (com o sprite 0) em $0200
        JSR WAITVB
        LDA #$3F                ; paletas de sprite pretas até a capa aparecer
        STA $2006
        LDA #$10
        STA $2006
        LDA #$0F
        LDX #16
l_spb:  STA $2007
        DEX
        BNE l_spb
        LDA #0
        STA $2003''')
r = sub(r, 'sync0:  .byte 15, $1F, $20, 0   ; Y (linha 16), tiles $1E/$1F da tabela 1 (bloco 2), atrás do fundo, X 0\n', '')
r = r.replace('''        LDA #1                  ; tiles: grupo g -> banco g+1, 2 setores ($0000 e $0800)''',
              '''        LDA #1                  ; tiles: grupo g -> banco 2g+1, 2 setores ($0000 e $0800)''')
G = V4.SEG_G_SRC
G = G[:G.index('; ---------------------------------------------------------------- tela cheia')]
G = sub(G, '''rv_fim: LDA #0                  ; 7: atributos e paletas de verdade: a capa aparece
        STA amode
        JSR at_ppu
        JSR pal_wr''', '''rv_fim: LDA #0                  ; 7: atributos e paletas de verdade: a capa aparece
        STA amode
        JSR at_ppu
        JSR pal_wr
        LDA #$3F                ; paletas de sprite: os sprites aparecem junto
        STA $2006
        LDA #$10
        STA $2006
        LDX #0
rv_sp:  LDA SPAL,X
        STA $2007
        INX
        CPX #16
        BNE rv_sp''')
MOD_SRC = '''
; ======== módulo ($6400): resto da carga, aparecimento, esconder, sprites
l_fail1: RTS
lc_rest:
''' + r + LSEC + G + r'''
; ---------------------------------------------------------------- carga dos sprites (setores 15-19 do registro)
sl_r0:  RTS
spr_load: LDA csec
        CLC
        ADC #15
        STA sec
        LDA csec+1
        ADC #0
        STA sec+1
        LDX sec+1
        LDA sec
        JSR lba_read
        BNE sl_r0
        JSR setP
        LDY #0
sl_o:   LDA (P),Y               ; OAM -> $0200 (sprite 0 de sincronia + os da capa)
        STA $0200,Y
        INY
        BNE sl_o
        INC P+1
sl_m:   LDA (P),Y               ; paletas (16) + máscaras (63)
        STA SPAL,Y
        INY
        CPY #79
        BNE sl_m
        LDA #0
        STA pair
sl_s:   INC sec                 ; próximo setor de tiles (16 pares)
        BNE sl_s1
        INC sec+1
sl_s1:  LDA sec
        LDX sec+1
        JSR lba_read
        BNE sl_r
        LDA #0
        STA wcnt                ; depois de ler o cartão, espera um vblank novo
        LDA FATBUF
        STA Q
        LDA FATBUF+1
        STA Q+1
        LDA #16
        STA scnt
sl_p:   LDX pair
        LDA SMASK,X
        STA smk
        LDA #1
        STA sbank
sl_g:   LSR smk                 ; bit g -> bloco de sprites do grupo g (banco 2g+1, PPU $1000)
        BCC sl_n
        JSR sl_w
sl_n:   INC sbank
        INC sbank
        LDA sbank
        CMP #15
        BNE sl_g
        LDA Q
        CLC
        ADC #32
        STA Q
        BCC sl_q
        INC Q+1
sl_q:   INC pair
        LDA pair
        CMP #63
        BEQ sl_r
        DEC scnt
        BNE sl_p
        BEQ sl_s
sl_r:   RTS
sl_w:   LDA wcnt                ; 2 pares por vblank (3 passavam do vblank: lixo na tela)
        BNE sl_w1
        JSR WAITVB
        LDA #2
        STA wcnt
sl_w1:  DEC wcnt
        LDA sbank
        JSR banco
        LDA pair                ; PPU $1000 + par*32
        LSR A
        LSR A
        LSR A
        CLC
        ADC #$10
        STA $2006
        LDA pair
        ASL A
        ASL A
        ASL A
        ASL A
        ASL A
        STA $2006
        LDY #0
sl_c:   LDA (Q),Y
        STA $2007
        INY
        LDA (Q),Y
        STA $2007
        INY
        CPY #32
        BNE sl_c
        JMP scroll0
'''


def assemble_all():
    segs_src = [SEG_A, SEG_D, SEG_MAIN, SEG_C, SEG_E, (MOD2, MOD2 + 0x400, MOD_SRC)]
    syms = {}
    for _ in range(8):
        new = {}
        for org, end, src in segs_src:
            new.update(assemble(HEAD + src, org, syms, strict=False)[1])
        if new == syms: break
        syms = new
    return [(org, end, assemble(HEAD + src, org, syms)[0]) for org, end, src in segs_src], syms


def main(log=print):
    orig, buf, info = build('base')
    segs, S = assemble_all()
    falta = [(hex(org), len(code) - (end - org)) for org, end, code in segs if org + len(code) > end]
    assert not falta, 'não cabem (segmento, bytes a mais): %s' % falta
    assert S['hook_cursor'] == 0x81C5 and S['draw_hook'] == 0x81C8
    for rot in ('dly', 'dl_i', 'sw2a', 'sw3', 'sw_l'):
        assert S[rot] >> 8 == (S[rot] + 8) >> 8, 'laço %s perto do fim de página' % rot
    assert orig[cpu2file(0xD0C6):cpu2file(0xD0C6) + 5] == bytes([0xA9, 0x06, 0x20, 0xE1, 0xF3])
    assert orig[cpu2file(0xF753):cpu2file(0xF753) + 12] == b'Device Info\0'
    assert orig[cpu2file(0xA680):cpu2file(0xA680) + 3] == bytes([0x20, 0x43, 0xF1])
    modulo = None
    for org, end, code in segs:
        if org == MOD2: modulo = code; continue
        o = cpu2file(org)
        buf[o:o + len(code)] = code
    patch(buf, 0x833D, buf[cpu2file(0x833D):cpu2file(0x833D) + 3], jsr(S['hide']))
    patch(buf, 0xBB4A, jsr(0x9DE0), jsr(S['init_hook']))
    patch(buf, 0xD9EB, jsr(0xAB25), jsr(S['idle_hook']))
    patch(buf, 0xCB8B, jsr(S['draw_hook']), jsr(S['mask_entry']))
    patch(buf, 0xCB29, [0xA9, 0x15], [0xA9, 0x0E])
    patch(buf, 0xCCE1, jsr(0xD0C6), jsr(S['cm_r']))
    patch(buf, 0xCCFC, jsr(0xD2B9), jsr(S['cm_r']))
    patch(buf, 0xECDB, jsr(0x826F), jsr(S['chr_all']))
    patch(buf, 0xED7B, jsr(0x826F), jsr(S['chr_all']))
    log('OS.BIN v5 SHA1 %s' % hashlib.sha1(buf).hexdigest())
    for org, end, code in segs:
        log('  $%04X-$%04X  %3d de %3d bytes (livres %d)' % (org, org + len(code) - 1, len(code), end - org,
                                                           end - org - len(code)))
    return buf, S, modulo


if __name__ == '__main__':
    main()
