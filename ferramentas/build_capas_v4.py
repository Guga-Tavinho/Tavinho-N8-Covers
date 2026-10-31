"""POC v4: capa GRANDE (112x160) no navegador, ao lado da lista, + TELA CHEIA parando o cursor 3 s.

Parte do OS base com as peças da v2 (filtro .nes, CRC do nome, índice do COVERS.BIN, ganchos) e troca a capa:
  - capa só de fundo nas linhas 2-21, colunas 16-31 do buffer de tela ($6050..), atributos $63C4.. (6 x 4 bytes);
    nomes da lista com 14 colunas ($CB29 = $0E)
  - fonte do OS nos blocos 0-7 da CHR (chr_all: $826F com $82 = 0..7, no lugar das 2 chamadas do OS)
  - tiles da capa nos slots livres da fonte ($01-$1F/$80-$9F) dos blocos 1-7: 7 grupos de linhas, um por banco
  - a cada quadro (espera ociosa, split): banco 1 no vblank; sprite 0 (linha 16, coluna 0, atrás do texto) ->
    6 trocas de banco (2..7), uma a cada 24 linhas, no meio das linhas compartilhadas entre os grupos (folga de
    8 linhas de pixels em cada troca)
  - aparecer sem lixo: a carga só envia os tiles (as células da capa continuam vazias); depois, no vblank de cada
    quadro: atributos -> paleta 1 (preta), 4 linhas da nametable por quadro, e por fim os atributos e as paletas de
    verdade (a capa surge de uma vez)
  - botão apertado (visto no vblank, antes do navegador): esconde na hora (atributos -> paleta 1, paletas 1 e 2
    pretas), sem esperar o navegador mexer na tela
  - 180 quadros parado com a capa na tela: tela cheia (o visualizador no setor 256 do COVERS.BIN, igual à POC,
    lendo os dados no registro da própria capa); na volta, a fonte é refeita nos blocos e a capa recarrega
Formato do COVERS.BIN v4: índice (setores 0-255, igual), setor 256 = visualizador, capa i em 512 + 64*i
(ver conv_capa_grande.py).

uso:  python build_capas_v4.py   (só a firmware; o COVERS.BIN vem do build_poc_capa_grande.py)
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
from build_capas import patch, jsr
import build_capas_v2 as V2
import build_capas_v3 as V3
from asm6502 import assemble

ESPERA_TELA_CHEIA = 180
SETOR_VISUALIZADOR = 256
SETOR_MODULO = 257
MOD = 0x7F00
# temporização: sprite 0 na linha 16 (ponto ~1); trocas no meio das linhas 43, 67, ..., 163 (24 em 24)
LINHA_1, PASSO = 43, 24
CUSTO_VOLTA = 45                         # ciclos do laço fora da espera (conferido no teste)


def espera(ciclos):
    """(Y, A) com Y*(5A+6)+15 o mais perto possível."""
    melhor = None
    for a in range(1, 256):
        y = max(1, min(255, round((ciclos - 15) / (5 * a + 6))))
        e = abs(y * (5 * a + 6) + 15 - ciclos)
        if melhor is None or e < melhor[0]: melhor = (e, y, a)
    return melhor[1], melhor[2]


C_PASSO = PASSO * 341 / 3                                   # 2728 ciclos entre trocas
Y0, A0 = espera((LINHA_1 - 16) * 341 / 3 - C_PASSO - 20)    # do sprite 0 até o início do laço
YP, AP = espera(C_PASSO - CUSTO_VOLTA)

HEAD = V3.HEAD + r'''
NMIF     = $9E          ; o NMI do OS põe 1 aqui a cada quadro
JOY      = $0515        ; botões (lidos pelo NMI do OS)
INITCHR  = $826F        ; zera a CHR da janela, paleta do OS, copia a CHR do OS.BIN (fonte na 1ª metade)
GFX_FULL = $82FA
NT0      = $6050        ; buffer de tela: linha 2, coluna 16 (início da região da capa)
AT0      = $63C4        ; atributos: linha 0, coluna 4 (6 linhas de 4 bytes, de 8 em 8)
MOD      = $7F00        ; módulo carregado do COVERS.BIN (setor 257) na WRAM
'''

SEG_A = 0x81C5, 0x8210, r'''
hook_cursor: JSR UPDCUR         ; cursor andou: atualiza a coluna e cai no draw_hook
draw_hook:
        LDY #3                  ; os 4 últimos caracteres não-nulos precisam ser ".nes"
        LDX #$3F
f_loop: LDA NAMEROWS,X
        BEQ f_skip
        ORA #$20
        CMP ext,Y
        BNE no_cover
        DEY
        BMI f_yes
f_skip: DEX
        BPL f_loop
no_cover: LDA #0
        STA pending
        JMP hide_draw
f_yes:  LDA enabled
        BEQ no_cover
        JMP crc_part
mask_entry: LDA cur             ; redesenho completo: o OS apagou o buffer -> recarrega a capa
        EOR #$FF
        STA cur
        JMP draw_hook
idle_hook: LDA pending
        BEQ i_done
        JSR load_cover
i_done: JMP split
ext:    .text ".nes"
'''

SEG_D = 0xFBD4, 0xFC00, r'''
scroll0: LDA #$A0
        STA $2000
        LDA #0
        STA $2005
        STA $2005
        RTS
banco:  LDX #$82                ; banco de CHR = A
        STX $4400
        STA $4401
        RTS
fs_go:  JMP ($04E9)             ; roda o setor lido (o visualizador se copia para $6400)
dly:    TAX                     ; Y*(5A+6) + 15 ciclos (com o LDY/LDA/JSR de quem chama)
dl_i:   DEX
        BNE dl_i
        DEY
        BNE dly
        RTS
'''

m = V3.SEG_MAIN[2]
m = m[:m.index('; ---------------------------------------------------------------- espera ociosa')]
m = m.replace('''        INC enabled
in_done:''', '''        LDA #<%d                ; módulo (aparecimento, esconder, tela cheia) -> $7F00 (255 bytes)
        LDX #>%d
        JSR lba_read
        BNE in_done
        JSR setP
        LDY #0
in_m:   LDA (P),Y
        STA MOD,Y
        INY
        CPY #$FF
        BNE in_m
        INC enabled
in_done:''' % (SETOR_MODULO, SETOR_MODULO))
m = m.replace('''        LDA has                 ; v2: has=0 também quando o fundo foi limpo -> recarrega
        BEQ c_diff
        JMP cover_show''', '''        LDA has                 ; a mesma capa já está na tela: nada a fazer
        BEQ c_diff
        RTS''')
SEG_MAIN = 0xD0C6, 0xD32A, m + r'''
; ---------------------------------------------------------------- espera ociosa: carrega a capa grande
l_fail0: RTS
load_cover:
        LDX #3
l_cp:   LDA want,X
        STA cur,X
        DEX
        BPL l_cp
        LDA #0
        STA pending
        STA has
        STA rev
        LDA want                ; balde = byte baixo do CRC -> setor 0..255
        LDX #0
        JSR lba_read
        BNE l_fail0
        JSR setP
l_scan: LDY #4
        LDA (P),Y
        CMP #$FF
        BEQ l_fail0
        LDY #0
        JSR cmp3
        BEQ l_found
        LDA P
        CLC
        ADC #5
        STA P
        BCC l_scan
        INC P+1
        BNE l_scan
l_found: LDA (P),Y              ; setor = 512 + idx*64
        STA sec
        INY
        LDA (P),Y
        LDX #6
l_sh:   ASL sec
        ROL A
        DEX
        BNE l_sh
        CLC
        ADC #2
        STA sec+1
        STA csec+1
        LDA sec
        STA csec
        LDX sec+1
        JSR lba_read
        BNE l_fail0
        JSR setP
        LDY #0
        JSR cmp3                ; bytes 0-2 = CRC: protege contra arquivo fragmentado
        BNE l_fail0
        LDX #0                  ; paletas 1 e 2 (6 cores)
l_pc:   LDA (P),Y
        STA cpal,X
        INY
        INX
        CPX #6
        BNE l_pc
        LDX #0                  ; atributos -> buffer (6 linhas de 4, de 8 em 8)
l_at:   LDA (P),Y
        STA AT0,X
        INY
        INX
        TXA
        AND #4
        BEQ l_at
        TXA
        CLC
        ADC #4
        TAX
        CPX #48
        BNE l_at
        TYA                     ; nametable: P += 33, 20 linhas de 16 -> buffer
        CLC
        ADC P
        STA P
        BCC l_n0
        INC P+1
l_n0:   LDA #<NT0
        STA Q
        LDA #>NT0
        STA Q+1
        LDX #20
l_nr:   LDY #15
l_nc:   LDA (P),Y
        STA (Q),Y
        DEY
        BPL l_nc
        LDA P
        CLC
        ADC #16
        STA P
        BCC l_n1
        INC P+1
l_n1:   JSR q_next
        DEX
        BNE l_nr
        LDA #1                  ; tiles: grupo g -> banco g+1, 2 setores ($0000 e $0800)
        STA grp
l_g:    LDA #$00
        STA pdst+1
        JSR l_sec
        LDA #$08
        STA pdst+1
        JSR l_sec
        INC grp
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
        STA $2003
        LDA #2
        STA $4014
        JSR scroll0
        LDA #$1E                ; sprites ligados (o sprite 0 fica atrás do texto: invisível)
        STA $2001
        LDA #1
        STA rev                 ; o split mostra a capa nos próximos quadros
        STA has
        STA bgshown
        LDA #0
        STA fs_t
        RTS
sync0:  .byte 15, $1F, $20, 0   ; Y (linha 16), tiles $1E/$1F da tabela 1 (bloco 2), atrás do fundo, X 0

cmp3:   LDX #1                  ; (P),Y.. == want+1..want+3 ? (Z=1); Y avança 3 se igual
cm:     LDA (P),Y
        CMP want,X
        BNE cm_r
        INY
        INX
        CPX #4
        BNE cm
cm_r:   RTS
q_next: LDA Q                   ; Q += 32 (próxima linha do buffer)
        CLC
        ADC #32
        STA Q
        BCC qn_r
        INC Q+1
qn_r:   RTS

; ---------------------------------------------------------------- fonte em todos os blocos (0-7)
chr_all: LDA #0
        STA grp
ca_l:   LDA grp
        JSR banco
        JSR INITCHR
        INC grp
        LDA grp
        CMP #8
        BNE ca_l
        LDA #0
        JMP banco
'''

SEG_C = 0xF753, 0xF896, r'''
; ---------------------------------------------------------------- menus ($833D): depois do 1º vblank do refresh
hide:   LDA #$3F                ; paletas 1 e 2 pretas
        STA $2006
        LDA #$04
        STA $2006
        LDA #$0F
        LDX #8
hd_pal: STA $2007
        DEX
        BNE hd_pal
        JSR scroll0
        JSR bg_clear            ; limpa a capa no buffer (o refresh do OS envia tudo)
        JSR WAITVB
        JMP h_inv
hide_draw: LDA bgshown          ; troca de item: limpa a capa do buffer (na PPU ela já está escondida)
        BEQ h_mask
        JSR bg_clear
h_inv:  LDA #0
        STA bgshown
        STA has
        STA rev
h_mask: LDA #$0A
        STA $2001
        RTS
bg_clear: LDA #<NT0             ; células da capa ($01-$1F/$80-$9F) -> 0; texto fica
        STA Q
        LDA #>NT0
        STA Q+1
        LDX #20
bc_r:   LDY #15
bc_c:   LDA (Q),Y
        AND #$60
        BNE bc_k
        STA (Q),Y
bc_k:   DEY
        BPL bc_c
        JSR q_next
        DEX
        BNE bc_r
        LDX #40                 ; atributos da região -> paleta 0
bc_a:   LDA #0
        STA AT0,X
        STA AT0+1,X
        STA AT0+2,X
        STA AT0+3,X
        TXA
        SEC
        SBC #8
        TAX
        BPL bc_a
        RTS
; ---------------------------------------------------------------- carga: um setor -> PPU
l_sec:  INC sec                 ; próximo setor -> PPU pdst no banco grp (4 vblanks de 128 bytes)
        BNE l_s1
        INC sec+1
l_s1:   LDA sec
        LDX sec+1
        JSR lba_read
        BNE l_serr
        LDA FATBUF
        STA src
        LDA FATBUF+1
        STA src+1
        LDA #0
        STA pdst
        LDX #4
l_chunk: LDA src
        STA src2
        LDA src+1
        STA src2+1
        JSR WAITVB
        LDY #$82
        STY $4400
        LDA grp
        STA $4401
        LDA pdst+1
        STA $2006
        LDA pdst
        STA $2006
        LDY #0
l_up:   LDA $FFFF,Y             ; operandos automodificados (src, src2)
        STA $2007
        INY
        LDA $FFFF,Y
        STA $2007
        INY
        BPL l_up
        JSR scroll0
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
l_c2:   DEX
        BNE l_chunk
        RTS
l_serr: PLA                     ; erro de leitura: sai do load_cover
        PLA
        RTS
src = l_up+1
src2 = l_up+8
; ---------------------------------------------------------------- sub-rotinas
lba_read: CLC                   ; A/X = setor relativo -> lê base+AX para *(FATBUF); Z=1 se ok
        ADC base
        PHA
        TXA
        ADC base+1
        TAX
        LDA base+2
        ADC #0
        STA SREG
        LDA base+3
        ADC #0
        STA SREG+1
        PLA
        JSR PUSHEAX
        JSR RDSEC
        CMP #0
        RTS
; ---------------------------------------------------------------- dados (PRG é RAM)
s_cov:  .asciz "COVERS  BIN"
base:   .byte 0,0,0,0
want:   .byte 0,0,0,0
cur:    .byte 0,0,0,0
sec:    .byte 0,0
csec:   .byte 0,0               ; 1º setor do registro da capa (o visualizador lê a tela cheia em csec+15)
pdst:   .byte 0,0
rq:     .byte 0,0
cpal:   .byte 0,0,0,0,0,0
enabled: .byte 0
pending: .byte 0
has:    .byte 0
bgshown: .byte 0
rev:    .byte 0                 ; 0 = capa pronta; 1..7 = passos do aparecimento
fs_t:   .byte 0
grp:    .byte 0
amode:  .byte 0
cnt:    .byte 0
'''

SEG_E = 0xA680, 0xA707, r'''
; ---------------------------------------------------------------- cada quadro com a capa (espera ociosa)
split:  LDA has
        BEQ sp_out
        LDA #0
        STA NMIF
        TAX
        LDY #$10
sw0:    LDA NMIF                ; espera o NMI (com limite)
        BNE sw_v
        DEX
        BNE sw0
        DEY
        BNE sw0
sp_out: JMP IDLE
sw_hd:  JMP sp_hide
sw_v:   LDA JOY                 ; botão: esconde já (o navegador vai mexer na tela)
        BNE sw_hd
        LDA #1                  ; topo da tela: banco 1
        JSR banco
        LDA rev
        BEQ sw_1
        JSR reveal
sw_1:   LDY #$10
sw1a:   BIT $2002               ; flag do sprite 0 apaga no fim do vblank
        BVC sw2
        DEX
        BNE sw1a
        DEY
        BNE sw1a
        BEQ sp_out
sw2:    LDY #$10
sw2a:   BIT $2002               ; sprite 0 (linha 16)
        BVS sw3
        DEX
        BNE sw2a
        DEY
        BNE sw2a
        BEQ sp_out
sw3:    LDY #%d
        LDA #%d
        JSR dly
        LDA #2
        STA grp
sw_l:   LDY #%d                 ; 24 linhas
        LDA #%d
        JSR dly
        LDA grp
        JSR banco
        INC grp
        LDA grp
        CMP #8
        BNE sw_l
        LDA rev                 ; capa pronta e parada: conta para a tela cheia
        BNE sp_out
        INC fs_t
        LDA fs_t
        CMP #%d
        BNE sp_out
        JMP full
''' % (Y0, A0, YP, AP, ESPERA_TELA_CHEIA)

SEG_G_SRC = r'''
sp_hide: LDA #$80
        STA amode
        JSR at_ppu
        JSR pal_wr
        JSR scroll0
        LDA #0
        STA has
        STA rev
        LDA #$0A
        STA $2001
        JMP IDLE
; ---------------------------------------------------------------- vblank: atributos/paletas (amode bit 7 = esconder)
at_ppu: LDX #0                  ; atributos da região: do buffer, ou $55 (paleta 1) para esconder
ap_r:   LDA #$23
        STA $2006
        TXA
        CLC
        ADC #$C4
        STA $2006
        LDY #4
ap_c:   LDA AT0,X
        BIT amode
        BPL ap_w
        LDA #$55
ap_w:   STA $2007
        INX
        DEY
        BNE ap_c
        TXA
        CLC
        ADC #4
        TAX
        CPX #48
        BNE ap_r
        RTS
pal_wr: LDA #$3F                ; paletas 1 e 2: as da capa, ou pretas para esconder
        STA $2006
        LDA #$05
        STA $2006
        LDX #0
        JSR pw3
        LDA #$3F
        STA $2006
        LDA #$09
        STA $2006
pw3:    LDY #3
pw_l:   LDA cpal,X
        BIT amode
        BPL pw_w
        LDA #$0F
pw_w:   STA $2007
        INX
        DEY
        BNE pw_l
        RTS
; ---------------------------------------------------------------- aparecimento (no vblank, rev = 1..7)
reveal: LDA rev
        CMP #1
        BNE rv_2
        LDA #$80                ; 1: atributos da região -> paleta 1 (preta)
        STA amode
        JSR at_ppu
        LDA #<NT0
        STA rq
        LDA #>NT0
        STA rq+1
        BNE rv_n                ; (sempre: >NT0 != 0)
rv_2:   CMP #7
        BEQ rv_fim
        LDA rq                  ; 2-6: 4 linhas da nametable por quadro
        STA Q
        LDA rq+1
        STA Q+1
        LDA #4
        STA cnt
rv_r:   LDA Q+1
        SEC
        SBC #$40
        STA $2006
        LDA Q
        STA $2006
        LDY #0
rv_c:   LDA (Q),Y
        STA $2007
        INY
        CPY #16
        BNE rv_c
        JSR q_next
        DEC cnt
        BNE rv_r
        LDA Q
        STA rq
        LDA Q+1
        STA rq+1
rv_n:   INC rev
        JMP scroll0
rv_fim: LDA #0                  ; 7: atributos e paletas de verdade: a capa aparece
        STA amode
        JSR at_ppu
        JSR pal_wr
        LDA #0
        STA rev
        JMP scroll0
; ---------------------------------------------------------------- tela cheia
full:   LDA #<%d
        LDX #>%d
        JSR lba_read
        BNE fl_out
        JSR fs_go               ; C=1: mostrou (e já reenviou a nametable do navegador)
        BCC fl_out
        JSR chr_all             ; a tela cheia usou os blocos 2-4: fonte de novo em todos
        JMP mask_entry          ; (o scroll0 com sprites 8x16 vem na carga)          ; recarrega a capa grande
fl_out: JMP IDLE
''' % (SETOR_VISUALIZADOR, SETOR_VISUALIZADOR)


def assemble_all():
    segs_src = [SEG_A, SEG_D, SEG_MAIN, SEG_C, SEG_E, (MOD, MOD + 0xFF, SEG_G_SRC)]
    syms = {}
    for _ in range(8):
        new = {}
        for org, end, src in segs_src:
            new.update(assemble(HEAD + src, org, syms, strict=False)[1])
        if new == syms: break
        syms = new
    out = [(org, end, assemble(HEAD + src, org, syms)[0]) for org, end, src in segs_src]
    return out, syms


def main(log=print, conferir=True):
    orig, buf, info = build('base')
    segs, S = assemble_all()
    falta = [(hex(org), len(code) - (end - org)) for org, end, code in segs if org + len(code) > end]
    assert not falta, 'não cabem (segmento, bytes a mais): %s' % falta
    assert S['hook_cursor'] == 0x81C5 and S['draw_hook'] == 0x81C8
    for rot in ('dly', 'dl_i', 'sw2a', 'sw3', 'sw_l'):
        assert S[rot] >> 8 == (S[rot] + 8) >> 8, 'laço %s perto do fim de página' % rot
    o = cpu2file(0xD0C6)
    assert orig[o:o + 5] == bytes([0xA9, 0x06, 0x20, 0xE1, 0xF3]), 'Device Info não confere'
    assert orig[cpu2file(0xF753):cpu2file(0xF753) + 12] == b'Device Info\0'
    assert orig[cpu2file(0xA680):cpu2file(0xA680) + 3] == bytes([0x20, 0x43, 0xF1]), '$A680 não confere'
    modulo = None
    for org, end, code in segs:
        if org == MOD: modulo = code; continue
        o = cpu2file(org)
        buf[o:o + len(code)] = code
    patch(buf, 0x833D, buf[cpu2file(0x833D):cpu2file(0x833D) + 3], jsr(S['hide']))
    patch(buf, 0xBB4A, jsr(0x9DE0), jsr(S['init_hook']))
    patch(buf, 0xD9EB, jsr(0xAB25), jsr(S['idle_hook']))
    patch(buf, 0xCB8B, jsr(S['draw_hook']), jsr(S['mask_entry']))
    patch(buf, 0xCB29, [0xA9, 0x15], [0xA9, 0x0E])                      # nomes: 14 colunas
    patch(buf, 0xCCE1, jsr(0xD0C6), jsr(S['cm_r']))
    patch(buf, 0xCCFC, jsr(0xD2B9), jsr(S['cm_r']))
    patch(buf, 0xECDB, jsr(0x826F), jsr(S['chr_all']))                  # fonte nos blocos 0-7
    patch(buf, 0xED7B, jsr(0x826F), jsr(S['chr_all']))
    log('OS.BIN v4 SHA1 %s' % hashlib.sha1(buf).hexdigest())
    for org, end, code in segs:
        log('  $%04X-$%04X  %3d de %3d bytes (livres %d)' % (org, org + len(code) - 1, len(code), end - org,
                                                           end - org - len(code)))
    log('  esperas: sprite 0 -> laço Y%d A%d, entre trocas Y%d A%d' % (Y0, A0, YP, AP))
    return buf, S, modulo


if __name__ == '__main__':
    main()
