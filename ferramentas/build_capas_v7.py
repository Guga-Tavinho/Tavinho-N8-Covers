"""POC v7: a v6 (estável no aparelho) carregando ~2x mais rápido.

Muda só a carga:
  1. "vblank estendido": cada envio espera o sprite 0 da linha 200 (na carga, um sprite 0 com o tile $00 — sólido
     em todos os bancos de fonte — atrás da coluna 0 da barra cinza), conta até a linha ~226 (abaixo da barra cinza, nas linhas
     28-29 que já são pretas e a TV de tubo esconde), DESLIGA a tela e o NMI, manda 256 bytes (2 pedaços de 128)
     e liga tudo de novo antes da linha 261 (pré-render), com a rolagem refeita: 1 envio por quadro.
     (1ª versão: contava a partir do NMI -> 1 envio a cada 2 quadros; e o NMI do OS, na linha 241, caía no meio
     das escritas do $2006 da nametable e mandava linhas para o lugar errado: o lixo das fotos testev7.)
     Sem o sprite 0 (não deveria acontecer): espera o NMI, apaga a tela o quadro todo e religa no vblank seguinte.
  2. a nametable e os atributos da capa também vão durante a carga (com os atributos na paleta 1 e as paletas 1 e
     2 pretas: invisível) -> o aparecimento é 1 quadro só (atributos e paletas de verdade), em vez de 7
  3. o módulo de 1 KB só é lido de novo do cartão se foi apagado (marca "M7OK" no fim dele)
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
from build_capas import patch, jsr
import build_capas_v5 as V5
import build_capas_v6 as V6
from asm6502 import assemble

MOD2 = V6.MOD2
MAGIC = b'M7OK'
LINHA_DESLIGA = 225                      # linha da tela em que a tela é desligada (barra cinza termina na 223)
PONTO_DESLIGA = 280                      # no intervalo horizontal (pontos 257-320): desligar no meio da linha pode
                                         # corromper a OAM (avaliação dos sprites)
C_LINHA = 341 / 3
LINHA_SYNC = 200                         # sprite 0 da carga: coluna 0 da barra cinza (célula $00, opaca)
ESPERA_DESLIGA = round(((LINHA_DESLIGA - LINHA_SYNC) * 341 + PONTO_DESLIGA - 18) / 3 - 6)   # do sprite 0 até lá
YD, AD = V5.V4.espera(ESPERA_DESLIGA)

HEAD = V6.HEAD + r'''
xsx      = $7F59        ; X guardado durante a espera
xfb      = $7F5A        ; 1 = janela sem o sprite 0 (tela apagada o quadro todo)
'''
sub = V5.sub

SEG_A, SEG_D, SEG_E = V6.SEG_A, V6.SEG_D, V6.SEG_E
SEG_C = (V6.SEG_C[0], V6.SEG_C[1], V6.SEG_C[2] + r'''
nt_hid: LDA #<NT0               ; nametable + atributos da capa, escondidos (3 quadros)
        STA rq
        LDA #>NT0
        STA rq+1
        JSR xvb
        LDA #$80
        STA amode
        JSR at_ppu              ; atributos -> paleta 1 e paletas 1 e 2 pretas
        JSR pal_wr
        LDA #6
        JSR nt_rows
        JSR xvb_fim
        JSR xvb
        LDA #7
        JSR nt_rows
        JSR xvb_fim
        JSR xvb
        LDA #7
        JSR nt_rows
        JMP xvb_fim
''')

# ---------------------------------------------------------------- residente: módulo reaproveitado + vblank estendido
m = V6.SEG_MAIN[2]
m = sub(m, '''lmod:   LDA #<%d                ; setores 257-258 -> $6400-$67FF; Z=1 se ok''' % V5.SETOR_MODULO,
        '''lmod:   LDX #3                  ; módulo ainda inteiro na memória (marca no fim)? então não lê de novo
lm_k:   LDA MOD2+$3FC,X
        CMP lm_mg,X
        BNE lm_go
        DEX
        BPL lm_k
        LDA #0
        RTS
lm_mg:  .byte 0,0,0,0              ; impressão digital do módulo (preenchida na montagem)
lm_go:  LDA #<%d                ; setores 257-258 -> $6400-$67FF; Z=1 se ok''' % V5.SETOR_MODULO)
m += r'''
; ---------------------------------------------------------------- vblank estendido (só durante a carga)
xvb:    STX xsx                 ; sprite 0 (linha 200) -> linha ~226: desliga tela e NMI (preserva X)
        LDA #0
        STA xfb
        TAX
        LDY #$20
xw1:    BIT $2002               ; flag do sprite 0 apaga no pré-render
        BVC xw2
        DEX
        BNE xw1
        DEY
        BNE xw1
        BEQ x_fb
xw2:    LDY #$20
xw3:    BIT $2002               ; e acende na linha 200
        BVS xw4
        DEX
        BNE xw3
        DEY
        BNE xw3
        BEQ x_fb
xw4:    LDY #%d
        LDA #%d
        JSR dly
x_off:  LDA #0
        STA $2001
        LDA #$20                ; NMI desligado na janela (o $2002 dele quebraria os pares do $2006)
        STA $2000
        LDA #0                  ; OAM da carga renovada (o sprite 0 da linha 200 nunca se perde)
        STA $2003
        LDA #2
        STA $4014
        LDX xsx
        RTS
x_fb:   JSR vbw                 ; sem sprite 0: apaga a tela no vblank e religa no próximo
        INC xfb
        BNE x_off
xvb_fim: BIT $2002              ; rolagem e tela de volta antes do pré-render (linha 261)
        LDA xfb
        BEQ xf_1
xf_0:   BIT $2002               ; (sem sprite 0: espera o vblank com o NMI desligado: sem corrida)
        BPL xf_0
xf_1:   LDA #0
        STA $2005
        STA $2005
        LDA #$1E                ; fundo e sprites (o sprite 0 da carga marca o próximo quadro)
        STA $2001
        LDA #$A0                ; NMI de volta (a flag de vblank já foi lida: não dispara agora)
        STA $2000
        RTS
ld_oam: LDA #$F0                ; começo da carga: OAM só com o sprite 0 da carga (tile $00, atrás do fundo)
        LDX #0
lo_1:   STA $0200,X
        INX
        BNE lo_1
        LDA #%d                 ; Y: linha 200, na barra cinza (a leitura do cartão cabe antes dela)
        STA $0200
        LDA #$00
        STA $0201
        LDA #$20
        STA $0202
        LDA #0
        STA $0203
        JSR vbw                 ; (a página já montada: o OAMDMA vai logo no começo do vblank)
        LDA #0
        STA $2003
        LDA #2
        STA $4014
        JSR scroll0
        LDA #$1E
        STA $2001
        RTS
''' % (YD, AD, LINHA_SYNC - 1)
SEG_MAIN = (V6.SEG_MAIN[0], V6.SEG_MAIN[1], m)

# ---------------------------------------------------------------- módulo: 256 bytes por quadro, nametable escondida
r = V6.MOD_SRC
r = sub(r, """sl_o:   LDA (P),Y               ; OAM -> $0200 (sprite 0 de sincronia + os da capa)
        STA $0200,Y
        INY
        BNE sl_o
        INC P+1""", """        INC P+1                 ; (a OAM vai para $0200 só no fim: até lá fica a da carga)""")
r = sub(r, """sp_n:   LDA gi
        CLC
        ADC #4
        STA gi
        INC grp
        INC grp
        LDA grp
        CMP #15
        BNE sp_g
        RTS""", """sp_n:   LDA gi
        CLC
        ADC #4
        STA gi
        INC grp
        INC grp
        LDA grp
        CMP #15
        BNE sp_g
        LDA csec                ; agora a OAM de verdade (setor 15 de novo)
        CLC
        ADC #15
        TAY
        LDA csec+1
        ADC #0
        TAX
        TYA
        JSR lba_read
        BNE sp_r
        JSR setP
        LDY #0
sp_o:   LDA (P),Y
        STA $0200,Y
        INY
        BNE sp_o
sp_r:   RTS""")
r = sub(r, '''        LDA #1                  ; tiles: grupo g -> banco 2g+1 ($0000 e $0800), só os pedaços usados''',
        '''        JSR ld_oam              ; sprite 0 da carga (marca a linha 16 de cada quadro)
        LDA #1                  ; tiles: grupo g -> banco 2g+1 ($0000 e $0800), só os pedaços usados''')
r = sub(r, '''        JSR spr_load            ; tiles dos sprites; OAM (com o sprite 0) em $0200
        JSR vbw''', '''        JSR nt_hid              ; nametable e atributos já na PPU (escondidos)
        JSR spr_load            ; tiles dos sprites; no fim, a OAM de verdade em $0200
        JSR vbw''')
r = sub(r, '''        LDA #1
        STA rev                 ; o split mostra a capa nos próximos quadros
        STA has''', '''        LDA #7
        STA rev                 ; só falta o último passo: atributos e paletas de verdade
        LDA #1
        STA has''')
i, j = r.index('        LDX nch\nl_chunk:'), r.index('l_sr:   RTS')
r = r[:i] + '''        LDX nch
l_fr:   JSR xvb                 ; linha ~226: tela desligada até a linha 261
        LDY #$82
        STY $4400
        LDA grp
        STA $4401
        LDA pdst+1
        STA $2006
        LDA pdst
        STA $2006
        JSR up128
        DEX
        BEQ l_fe
        JSR up128               ; 2º pedaço (endereço da PPU continua)
        DEX
l_fe:   JSR xvb_fim
        TXA
        BNE l_fr
''' + r[j:]
r = sub(r, '''src = l_up+1
src2 = l_up+8''', '''up128:  LDA src                 ; 128 bytes de src -> $2007; src e pdst avançam 128
        STA src2
        LDA src+1
        STA src2+1
        LDY #0
l_up:   LDA $FFFF,Y             ; operandos automodificados (src, src2)
        STA $2007
        INY
        LDA $FFFF,Y
        STA $2007
        INY
        BPL l_up
        LDA src
        CLC
        ADC #$80
        STA src
        BCC l_c1
        INC src+1
l_c1:   LDA pdst
        CLC
        ADC #$80
        STA pdst
        BCC l_c2
        INC pdst+1
l_c2:   RTS
src = l_up+1
src2 = l_up+8''')
MOD_SRC = r + r'''
nt_rows: STA cnt                ; A linhas do buffer (a partir de rq) -> PPU
        LDA rq
        STA Q
        LDA rq+1
        STA Q+1
nr_r:   LDA Q+1
        SEC
        SBC #$40
        STA $2006
        LDA Q
        STA $2006
        LDY #0
nr_c:   LDA (Q),Y
        STA $2007
        INY
        CPY #16
        BNE nr_c
        JSR q_next
        DEC cnt
        BNE nr_r
        LDA Q
        STA rq
        LDA Q+1
        STA rq+1
        RTS
'''


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
    V5.assemble_all = assemble_all                     # o main da v5 com os segmentos da v7
    try:
        buf, S, modulo = V5.main(log=lambda *a: None)
    finally:
        import importlib; importlib.reload(V5)
    marca = hashlib.sha1(modulo).digest()[:4]               # muda a cada versão do módulo
    modulo = modulo.ljust(0x3FC, b'\0') + marca
    o = cpu2file(S['lm_mg'])
    buf[o:o + 4] = marca
    log('OS.BIN v7 SHA1 %s' % hashlib.sha1(buf).hexdigest())
    segs, _ = assemble_all()
    for org, end, code in segs:
        log('  $%04X-$%04X  %3d de %3d bytes (livres %d)' % (org, org + len(code) - 1, len(code), end - org,
                                                           end - org - len(code)))
    log('  tela desligada na linha ~%d: espera Y%d A%d' % (LINHA_DESLIGA, YD, AD))
    return buf, S, modulo


if __name__ == '__main__':
    main()
