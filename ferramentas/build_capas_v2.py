"""EXPERIMENTAL v2: capas com sprites (4 paletas) + camada de FUNDO (3 paletas extras).

uso:  python build_capas_v2.py
saida: experimento_v2/EDFC/OS.BIN   (COVERS.BIN no formato v2: gerar_covers.py --v2)

Parte da v1 (build_capas.py) e muda:
  - capa na coluna 22 (x=176), linhas 4-15 (y=32): alinhada à grade de atributos 16x16
  - nome na lista com 20 colunas ($CB29: $1D -> $14)
  - fundo: nametable $2096.. (12 linhas x 8) + atributos $23CD-$23DF, escritos também no
    buffer de tela do OS ($6096.. / $63CD..), para o OS preservar em redesenhos/popups
  - tiles do fundo nos slots livres da fonte: $01-$1F e $80-$9F (tabela 0)
  - Device Info e About: não fazem nada (o espaço da tela de info foi usado)
Formato v2 do COVERS.BIN: 8 setores por capa (ver gerar_covers.py).
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from build_poc import build, ROOT, cpu2file
from build_capas import COMMON, patch, jsr
from asm6502 import assemble

COMMON2 = COMMON + r'''
NT_BUF   = $6096        ; buffer de tela: linha 4, coluna 22
ATTR_BUF = $63CD        ; atributos: linha 1 col 5 .. linha 3 col 7 (19 bytes contíguos)
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
i_done: JMP IDLE
ext:    .text ".nes"
'''

SEG_D = 0xFBD4, 0xFC00, r'''
cover_show: JSR WAITVB
        LDA #0
        STA $2003
        LDA #2
        STA $4014               ; OAMDMA da página $0200
        LDA #$1E
        STA $2001               ; fundo + sprites
        LDA #1
        STA bgshown
        RTS
scroll0: LDA #$A0
        STA $2000
        LDA #0
        STA $2005
        STA $2005
        RTS
'''

SEG_MAIN = 0xD0C6, 0xD32A, r'''
; ---------------------------------------------------------------- os_init: depois do MAPROUT.BIN
init_hook:
        JSR FINDNAME            ; a busca original do MAPROUT.BIN (argumentos já empilhados)
        PHA
        LDA #0
        STA enabled
        STA pending
        STA has
        STA bgshown
        LDX #3
in_clr: STA base,X
        DEX
        BPL in_clr
        LDA EDFC_CL+3           ; file_find_by_name(edfc, "COVERS  BIN", NULL, &base)
        STA SREG+1
        LDA EDFC_CL+2
        STA SREG
        LDX EDFC_CL+1
        LDA EDFC_CL
        JSR PUSHEAX
        LDA #<s_cov
        LDX #>s_cov
        JSR PUSHAX
        JSR PUSH0
        LDA #<base
        LDX #>base
        JSR PUSHAX
        JSR FINDNAME
        LDA base                ; cluster 0 = não achou
        ORA base+1
        ORA base+2
        ORA base+3
        BEQ in_done
        LDA base+3              ; base = primeiro setor do arquivo
        STA SREG+1
        LDA base+2
        STA SREG
        LDX base+1
        LDA base
        JSR PUSHEAX
        JSR CL2LBA
        STA base
        STX base+1
        LDA SREG
        STA base+2
        LDA SREG+1
        STA base+3
        INC enabled
in_done: PLA
        RTS

setP:   LDA FATBUF
        STA P
        LDA FATBUF+1
        STA P+1
        RTS

; ---------------------------------------------------------------- desenho da lista: CRC32 do nome
crc_part:
        LDA #$FF
        STA T0
        STA T1
        STA T2
        STA T3
        LDX #0
c_loop: LDA NAMEROWS,X
        BEQ c_next
        ORA #$20
        EOR T0
        STA T0
        LDY #8
c_bit:  LSR T3
        ROR T2
        ROR T1
        ROR T0
        BCC c_nb
        LDA T3
        EOR #$ED
        STA T3
        LDA T2
        EOR #$B8
        STA T2
        LDA T1
        EOR #$83
        STA T1
        LDA T0
        EOR #$20
        STA T0
c_nb:   DEY
        BNE c_bit
c_next: INX
        CPX #$40
        BNE c_loop
        LDX #3
c_cmp:  LDA T0,X
        CMP cur,X
        BNE c_diff
        DEX
        BPL c_cmp
        LDA #0                  ; mesma capa que está carregada
        STA pending
        LDA has                 ; v2: has=0 também quando o fundo foi limpo -> recarrega
        BEQ c_diff
        JMP cover_show
c_diff: LDX #3                  ; outra: marca como pendente (carrega quando o cursor parar)
c_st:   LDA T0,X
        STA want,X
        DEX
        BPL c_st
        LDA #1
        STA pending
c_hide: JMP hide_draw

; ---------------------------------------------------------------- espera ociosa: carrega a capa
l_fail0: RTS                    ; saída de erro ao alcance dos desvios do início
load_cover:
        LDX #3
l_cp:   LDA want,X
        STA cur,X
        DEX
        BPL l_cp
        LDA #0
        STA pending
        STA has
        LDA want                ; balde = byte baixo do CRC -> setor 0..255
        LDX #0
        JSR lba_read
        BNE l_fail0
        JSR setP
l_scan: LDY #4
        LDA (P),Y
        CMP #$FF                ; fim do balde
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
l_found: LDA (P),Y              ; setor = 256 + idx*8
        STA sec
        INY
        LDA (P),Y
        ASL sec
        ROL A
        ASL sec
        ROL A
        ASL sec
        ROL A                   ; idx < 8160 (limite da ferramenta): o carry aqui é sempre 0
        ADC #1
        STA sec+1
        LDA sec                 ; metadados: OAM[256] paletas[28] verif[3] - NT[96] atr[19]
        LDX sec+1
        JSR lba_read
        BNE l_fail0
        JSR setP
        INC P+1
        LDY #28
        JSR cmp3                ; bytes 284-286 = CRC: protege contra arquivo fragmentado
        BNE l_fail0
        DEC P+1
        LDY #0
l_oam:  LDA (P),Y
        STA $0200,Y
        INY
        BNE l_oam
        INC P+1
        JSR WAITVB
        LDA #$3F                ; paletas $3F04-$3F1F (fundo 1-3 + sprites)
        STA $2006
        LDA #$04
        STA $2006
        LDY #0
l_pal:  LDA (P),Y
        STA $2007
        INY
        CPY #28
        BNE l_pal
        JSR scroll0
        LDA #<NT_BUF            ; nametable -> buffer de tela (vai à PPU no fim)
        STA Q
        LDA #>NT_BUF
        STA Q+1
        LDX #0
        LDY #32
l_nt:   LDA (P),Y
        STA (Q,X)
        INC Q
        INY
        TYA
        AND #7
        BNE l_nt
        LDA Q
        CLC
        ADC #24
        STA Q
        BCC l_nt1
        INC Q+1
l_nt1:  CPY #128
        BNE l_nt
l_at:   LDA (P),Y               ; atributos -> buffer ($63CD-$63DF)
        STA ATTR_BUF,X
        INY
        INX
        CPX #19
        BNE l_at
        LDA #$00                ; tiles: 3 setores -> $1000, depois $0000 e $0800 (fundo)
        STA pdst
        LDA #$10
        STA pdst+1
        LDA #5
        STA cnt
l_tile: INC sec
        BNE l_t1
        INC sec+1
l_t1:   LDA sec
        LDX sec+1
        JSR lba_read
        BEQ l_t2
        RTS                     ; erro de leitura
l_t2:   LDA FATBUF
        STA src
        LDA FATBUF+1
        STA src+1
        LDX #4
l_chunk: LDA src
        STA src2
        LDA src+1
        STA src2+1
        JSR WAITVB
        LDA pdst+1
        STA $2006
        LDA pdst
        STA $2006
        LDY #0
l_up:   LDA $FFFF,Y             ; operandos automodificados (src, src2); 2 bytes por volta
        STA $2007               ; ~11,5 ciclos/byte: 128 bytes + NMI do OS cabem no vblank
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
        LDA pdst+1              ; fim dos sprites ($1600) -> tiles de fundo em $0000; fim ($0200) -> $0800
        CMP #$16
        BNE l_d1
        LDA #$00
        STA pdst+1
l_d1:   CMP #$02
        BNE l_d2
        LDA #$08
        STA pdst+1
l_d2:   DEC cnt
        BEQ l_done
        JMP l_tile
l_done: JSR upload_bg
        LDA #1
        STA has
        JMP cover_show
src = l_up+1
src2 = l_up+8
'''

# textos da Device Info ($F75F-$F79A) + do About ($F79B-$F895)
SEG_C = 0xF75F, 0xF896, r'''
; ---------------------------------------------------------------- menus ($833D)
; Chamada logo depois do 1º vblank de TODO refresh do OS (inclusive o que restaura a lista depois
; do menu). O OS envia o buffer em 8 quadros e os atributos chegam por último: sem isso, o fundo
; da capa aparecia "quebrado" (tiles já vazios com as cores antigas) por alguns quadros.
hide:   LDA #$3F                ; 1) no vblank: paletas 1 e 2 (da capa) pretas -> o fundo some já
        STA $2006
        LDA #$04
        STA $2006
        LDA #$0F
        LDX #8
hd_pal: STA $2007
        DEX
        BNE hd_pal
        JSR scroll0             ; 2) rolagem de volta (o $2006 mexeu nela)
        JSR bg_clear            ; 3) limpa a capa no buffer (preserva o texto e a paleta 3 do menu)
        JSR WAITVB              ; 4) devolve ao OS no começo de um vblank
        JMP h_inv               ;    e a capa passa a "não carregada"
; ---------------------------------------------------------------- camada de fundo
hide_draw: LDA bgshown          ; troca de item: limpa o fundo da capa (buffer + PPU) e esconde sprites
        BEQ h_mask
        JSR bg_clear
        JSR upload_bg
h_inv:  LDA #0
        STA bgshown
        STA has                 ; o fundo sumiu: voltar a este jogo recarrega a capa
h_mask: LDA #$0A
        STA $2001
        RTS

bg_clear: JSR q_init            ; zera tiles da capa ($01-$1F/$80-$9F) e os atributos
bc_row: LDY #7
bc_col: LDA (Q),Y
        AND #$60                ; texto ($20-$7F, $A0-$FF) fica
        BNE bc_k
        STA (Q),Y
bc_k:   DEY
        BPL bc_col
        JSR q_next
        DEX
        BNE bc_row
        LDX #18
bc_at:  LDA ATTR_BUF,X          ; cada campo de 2 bits: 3 (paleta dos menus do OS) fica, o resto vira 0
        LSR A
        AND ATTR_BUF,X
        AND #$55
        STA T0
        ASL A
        ORA T0
        STA ATTR_BUF,X
        DEX
        BPL bc_at
        RTS

upload_bg: JSR q_init           ; buffer -> PPU: 6 linhas por vblank, depois os atributos
ub_row: CPX #12
        BEQ ub_vb
        CPX #6
        BNE ub_go
ub_vb:  JSR WAITVB
ub_go:  LDA Q+1
        SEC
        SBC #$40
        STA $2006
        LDA Q
        STA $2006
        LDY #0
ub_col: LDA (Q),Y
        STA $2007
        INY
        CPY #8
        BNE ub_col
        JSR q_next
        DEX
        BNE ub_row
        LDA #$23
        STA $2006
        LDA #$CD
        STA $2006
ub_at:  LDA ATTR_BUF,X          ; X = 0 aqui
        STA $2007
        INX
        CPX #19
        BNE ub_at
        JMP scroll0

q_init: LDA #<NT_BUF            ; Q = início da capa no buffer de tela, X = 12 linhas
        STA Q
        LDA #>NT_BUF
        STA Q+1
        LDX #12
        RTS
q_next: LDA Q                   ; Q += 32 (próxima linha do buffer)
        CLC
        ADC #32
        STA Q
        BCC qn_r
        INC Q+1
qn_r:   LDA #0
        RTS

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
cmp3:   LDX #1                  ; (P),Y.. == want+1..want+3 ? (Z=1); Y avança 3 se igual
cm:     LDA (P),Y
        CMP want,X
        BNE cm_r
        INY
        INX
        CPX #4
        BNE cm
cm_r:   RTS

; ---------------------------------------------------------------- dados (PRG é RAM)
s_cov:  .asciz "COVERS  BIN"
base:   .byte 0,0,0,0
want:   .byte 0,0,0,0
cur:    .byte 0,0,0,0
sec:    .byte 0,0
pdst:   .byte 0,0
enabled: .byte 0
pending: .byte 0
has:    .byte 0
cnt:    .byte 0
bgshown: .byte 0
'''

EXTRA_CONST = r'''
Q        = $36          ; ponteiro destino (ptr4 do cc65)
'''

SEGMENTS = [SEG_A, SEG_D, SEG_MAIN, SEG_C]


def assemble_all():
    head = COMMON2 + EXTRA_CONST
    syms = {}
    for _ in range(6):
        new = {}
        for org, end, src in SEGMENTS:
            new.update(assemble(head + src, org, syms, strict=False)[1])
        if new == syms:
            break
        syms = new
    out = [(org, end, assemble(head + src, org, syms)[0]) for org, end, src in SEGMENTS]
    for org, end, code in out:
        assert org + len(code) <= end, 'segmento $%04X: %d bytes não cabem (limite %d)' % (org, len(code), end - org)
    return out, syms


def main():
    orig, buf, info = build('base')
    segs, S = assemble_all()
    assert S['hook_cursor'] == 0x81C5 and S['draw_hook'] == 0x81C8
    o = cpu2file(0xD0C6)
    assert orig[o:o + 5] == bytes([0xA9, 0x06, 0x20, 0xE1, 0xF3]), 'Device Info não confere'
    assert orig[cpu2file(0xD2B9):cpu2file(0xD2B9) + 3] == bytes([0x20, 0x6D, 0xEF]), 'About não confere'
    assert orig[cpu2file(0xF79B):cpu2file(0xF79B) + 5] == b'EDN8\0', 'textos do About não conferem'
    assert orig[cpu2file(0xF75F):cpu2file(0xF75F) + 11] == b'OS ver: 1.\0', 'textos da Device Info não conferem'
    for org, end, code in segs:
        o = cpu2file(org)
        buf[o:o + len(code)] = code
    patch(buf, 0x833D, buf[cpu2file(0x833D):cpu2file(0x833D) + 3], jsr(S['hide']))
    patch(buf, 0xBB4A, jsr(0x9DE0), jsr(S['init_hook']))
    patch(buf, 0xD9EB, jsr(0xAB25), jsr(S['idle_hook']))
    patch(buf, 0xCB8B, jsr(S['draw_hook']), jsr(S['mask_entry']))     # redesenho completo
    patch(buf, 0xCB29, [0xA9, 0x15], [0xA9, 0x14])                      # nome: 20 colunas
    patch(buf, 0xCCE1, jsr(0xD0C6), jsr(S['cm_r']))                     # Device Info -> nada (RTS)
    patch(buf, 0xCCFC, jsr(0xD2B9), jsr(S['cm_r']))                     # About -> nada (RTS)

    out_dir = os.path.join(ROOT, 'experimento_v2', 'EDFC')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, 'OS.BIN')
    open(out, 'wb').write(buf)
    print('gerado:', out)
    print('SHA1:', hashlib.sha1(buf).hexdigest())
    for org, end, code in segs:
        print('  $%04X-$%04X  %3d de %3d bytes' % (org, org + len(code) - 1, len(code), end - org))
    return buf, S


if __name__ == '__main__':
    main()
