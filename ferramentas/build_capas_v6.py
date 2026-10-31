"""POC v6: a v5 (capa grande com fundo + sprites, estável no aparelho) carregando MAIS RÁPIDO.

Muda só a carga (módulo em $6400):
  1. espera o vblank pelo NMI do OS ($9E) em vez do WAITVB ($8393): o WAITVB lê $2002, que o NMI do OS também lê
     e apaga, então muitas vezes perdia o vblank e esperava 2-3 quadros
  2. sprites: em vez de mandar par por par (2 por vblank, decidindo os bancos na hora), cada bloco de sprites
     recebe a sua faixa contínua de pares, já gravada em sequência no COVERS.BIN, em pedaços de 128 bytes como o
     fundo (conv_capa_grande.v6_de_v5)
  3. fundo: só os pedaços de 128 bytes que têm slots usados pela nametable do grupo (contados no gerador)
O resto (trocas de banco, aparecimento, esconder, formato do índice, fonte) é igual à v5.
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
from build_capas import patch, jsr
import build_capas_v5 as V5
from asm6502 import assemble

MOD2 = V5.MOD2
HEAD = V5.HEAD + r'''
CHT      = $7F60        ; pedaços de 128 bytes de cada grupo de fundo (7 x A, B)
STB      = $7F70        ; tabela dos blocos de sprite (7 x setor, pedaços, destino lo, hi)
gi       = $7F55
nch      = $7F56
ntot     = $7F57
vbt      = $7F58
'''
sub = V5.sub

SEG_A, SEG_D, SEG_MAIN, SEG_C, SEG_E = V5.SEG_A, V5.SEG_D, V5.SEG_MAIN, V5.SEG_C, V5.SEG_E

r = V5.MOD_SRC
# nametable lida: P aponta para o byte 353 do setor 0 -> guarda a tabela de pedaços do fundo
r = sub(r, '''l_n1:   JSR q_next
        DEX
        BNE l_nr
        LDA #1                  ; tiles: grupo g -> banco 2g+1, 2 setores ($0000 e $0800)
        STA grp
l_g:    LDA #$00
        STA pdst+1
        JSR l_sec
        LDA #$08
        STA pdst+1
        JSR l_sec
        INC grp                 ; bancos ímpares 1, 3, ..., 13
        INC grp''', '''l_n1:   JSR q_next
        DEX
        BNE l_nr
        LDY #13                 ; pedaços de cada grupo (bytes 353-366 do setor 0)
l_ct:   LDA (P),Y
        STA CHT,Y
        DEY
        BPL l_ct
        LDA #1                  ; tiles: grupo g -> banco 2g+1 ($0000 e $0800), só os pedaços usados
        STA grp
        LDA #0
        STA gi
l_g:    LDA #0
        STA pdst
        STA pdst+1
        LDX gi
        LDA CHT,X
        STA nch
        JSR l_sec
        LDA #0
        STA pdst
        LDA #$08
        STA pdst+1
        LDX gi
        LDA CHT+1,X
        STA nch
        JSR l_sec
        INC gi
        INC gi
        INC grp                 ; bancos ímpares 1, 3, ..., 13
        INC grp''')
r = sub(r, '''        JSR spr_load            ; tiles dos sprites; OAM (com o sprite 0) em $0200
        JSR WAITVB''', '''        JSR spr_load            ; tiles dos sprites; OAM (com o sprite 0) em $0200
        JSR vbw''')
# l_sec: nch pedaços (0 = nem lê o setor), destino inteiro dado por quem chama, espera pelo NMI
r = sub(r, '''l_sec:  INC sec                 ; próximo setor -> PPU pdst no banco grp (4 vblanks de 128 bytes)
        BNE l_s1
        INC sec+1
l_s1:   LDA sec''', '''l_sec:  INC sec                 ; próximo setor -> PPU pdst no banco grp (nch vblanks de 128 bytes)
        BNE l_s0
        INC sec+1
l_s0:   LDA nch
        BEQ l_sr
l_s1:   LDA sec''')
r = sub(r, '''        LDA #0
        STA pdst
        LDX #4
l_chunk:''', '''        LDX nch
l_chunk:''')
r = sub(r, '''        JSR WAITVB
        LDY #$82
        STY $4400
        LDA grp''', '''        JSR vbw
        LDY #$82
        STY $4400
        LDA grp''')
r = sub(r, '''l_c2:   DEX
        BNE l_chunk
        RTS''', '''l_c2:   DEX
        BNE l_chunk
l_sr:   RTS''')
# sprites: cabeçalho no setor 15, faixas contínuas por bloco
i = r.index('; ---------------------------------------------------------------- carga dos sprites')
r = r[:i] + r'''; ---------------------------------------------------------------- carga dos sprites (setor 15 + faixas por bloco)
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
sl_m:   LDA (P),Y               ; paletas (16) + tabela dos blocos (28)
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
        STA grp
        LDA #0
        STA gi
sp_g:   LDX gi
        LDA STB+1,X             ; pedaços deste bloco (0 = nenhum par)
        BEQ sp_n
        STA ntot
        LDA STB,X               ; setor = csec + relativo - 1 (o l_sec avança antes de ler)
        CLC
        ADC csec
        STA sec
        LDA csec+1
        ADC #0
        STA sec+1
        LDA sec
        BNE sp_d
        DEC sec+1
sp_d:   DEC sec
        LDA STB+2,X
        STA pdst
        LDA STB+3,X
        STA pdst+1
sp_s:   LDA ntot                ; até 4 pedaços por setor
        CMP #4
        BCC sp_l
        LDA #4
sp_l:   STA nch
        JSR l_sec
        LDA ntot
        SEC
        SBC nch
        STA ntot
        BNE sp_s
sp_n:   LDA gi
        CLC
        ADC #4
        STA gi
        INC grp
        INC grp
        LDA grp
        CMP #15
        BNE sp_g
        RTS
'''
MOD_SRC = r + '''
vbw:    LDA #0                  ; espera o próximo vblank pelo NMI do OS (certeiro; o WAITVB às vezes perde)
        STA NMIF
        LDA #24                 ; limite ~2 quadros (preserva X)
        STA vbt
        LDY #0
vb1:    LDA NMIF
        BNE vb_r
        DEY
        BNE vb1
        DEC vbt
        BNE vb1
        JMP WAITVB              ; sem NMI (não deveria acontecer): o jeito antigo, em vez de travar
vb_r:   RTS
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
    V5.assemble_all = assemble_all                     # o main da v5 com os segmentos da v6
    try:
        buf, S, modulo = V5.main(log=lambda *a: None)
    finally:
        import importlib; importlib.reload(V5)
    log('OS.BIN v6 SHA1 %s' % hashlib.sha1(buf).hexdigest())
    segs, _ = assemble_all()
    for org, end, code in segs:
        log('  $%04X-$%04X  %3d de %3d bytes (livres %d)' % (org, org + len(code) - 1, len(code), end - org,
                                                           end - org - len(code)))
    return buf, S, modulo


if __name__ == '__main__':
    main()
