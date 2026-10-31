"""Build de DIAGNÓSTICO: PoC da capa + tela Device Info substituída por testes de memória.

uso:  python build_diag.py
saida: poc_diag/EDFC/OS.BIN
Abra: SELECT (menu principal) -> Device Info (ou About). Anote/fotografe a tela. Qualquer botão volta.
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from build_poc import build, ROOT, cpu2file
from asm6502 import assemble

DEVINFO = 0xD0C6          # tela Device Info no build base ($D0C6-$D2B8, sem argumentos, retorno ignorado)
DEVINFO_END = 0xD32A      # + tela About ($D2B9-$D329), que passa a abrir o diagnóstico também
ABOUT_CALL = 0xCCFC       # JSR $D2B9 (About) no menu principal -> JSR $D0C6

SRC = r'''
SCR_BACKUP  = $8441
SCR_CLEAR   = $83C5     ; zera o buffer $6000-$63FF
PUTS        = $839C     ; A/X = string terminada em 0, escreve em (TP)
REFRESH     = $8326     ; envia o buffer para a PPU (e esconde os sprites)
WAITKEY     = $9F0B
SCR_RESTORE = $845F
TP = $92                ; ponteiro de texto do OS
P  = $9A                ; ponteiro de varredura (o PUTS também usa $9A/$9B: só imprimir depois)
C  = $9C                ; contador 16 bits
cval  = $02C0           ; variáveis: fim da página OAM (sprites 48-63, sempre escondidos)
endhi = $02C1
lim   = $02C2
rown  = $02C3
cnt   = $02C4
t1    = $02C5
t2    = $02C6
r_lo  = $02C7
r_hi  = $02C8

diag:   JSR SCR_BACKUP
        JSR SCR_CLEAR
        LDX #0                  ; --- rótulos: tabela (linha, texto)
lbl:    LDA tbl,X
        BMI ldone
        TAY
        LDA #1
        JSR rowcol
        STX cnt
        LDA tbl+1,X
        PHA
        LDA tbl+2,X
        TAX
        PLA
        JSR PUTS
        LDX cnt
        INX
        INX
        INX
        BNE lbl
ldone:
        LDA #$00                ; --- 8 bytes em $4800 e em $5FF8
        LDX #$48
        LDY #2
        JSR dump8
        LDA #$F8
        LDX #$5F
        LDY #3
        JSR dump8

        LDA #$AA                ; --- quantos $AA em $4800-$5FFF
        LDX #$48
        LDY #$60
        JSR count0
        LDA #11
        LDY #4
        JSR rowcol
        JSR hexc

        LDA #6                  ; --- leitura/escrita (restaura o valor original)
        LDY #5
        JSR rowcol
        LDA #$00
        LDX #$48
        JSR rwtest
        LDA #$00
        LDX #$50
        JSR rwtest
        LDA #$FF
        LDX #$5F
        JSR rwtest

        LDA #8                  ; --- tabela da BIOS em $FC00 (32 palavras, 6 por linha)
        STA rown
        LDX #0
trow:   LDY rown
        LDA #1
        JSR rowcol
        LDA #6
        STA cnt
tw:     LDA $FC01,X
        JSR hex
        LDA $FC00,X
        JSR hex
        LDA #' '
        JSR putc
        INX
        INX
        CPX #64
        BEQ tdone
        DEC cnt
        BNE tw
        INC rown
        BNE trow
tdone:
        LDA #$F9                ; --- último não-zero em $FC00-$FFF9
        LDX #$FF
        LDY #$FC
        JSR lastnz
        LDA #14
        LDY #15
        JSR rowcol
        JSR hexr

        LDA #$00                ; --- zeros em $FC40-$FFFF
        STA P
        STA cval
        LDA #$FC
        STA P+1
        LDA #$00
        STA endhi
        JSR count
        LDA #14
        LDY #16
        JSR rowcol
        JSR hexc

        LDA #$FE                ; --- último não-zero em $7C00-$7FFE (topo da WRAM)
        LDX #$7F
        LDY #$7C
        JSR lastnz
        LDA #14
        LDY #17
        JSR rowcol
        JSR hexr

        JSR REFRESH
        JSR WAITKEY
        JSR SCR_RESTORE
        JMP REFRESH

; ---------------------------------------------------------------- sub-rotinas
rowcol: STA TP                  ; Y = linha, A = coluna -> TP = $6040 + Y*32 + A (preserva X)
        LDA #0
        STA TP+1
        TYA
        ASL A
        ASL A
        ASL A
        ASL A
        ROL TP+1
        ASL A
        ROL TP+1
        CLC
        ADC TP
        BCC rc1
        INC TP+1
        CLC
rc1:    ADC #$40
        STA TP
        LDA TP+1
        ADC #$60
        STA TP+1
        RTS

dump8:  STA P                   ; 8 bytes de (A/X) na linha Y, coluna 7
        STX P+1
        LDA #7
        JSR rowcol
        LDX #0
dl:     TXA
        TAY
        LDA (P),Y
        JSR hex
        INX
        CPX #8
        BNE dl
        RTS

hexc:   LDA C+1                 ; imprime o contador
        JSR hex
        LDA C
        JMP hex
hexr:   LDA r_hi                ; imprime o resultado do lastnz
        JSR hex
        LDA r_lo
hex:    PHA                     ; imprime A em hexadecimal (preserva X)
        LSR A
        LSR A
        LSR A
        LSR A
        JSR nib
        PLA
        AND #$0F
nib:    CMP #10
        BCC nd
        ADC #6
nd:     ADC #'0'
putc:   LDY #0
        STA (TP),Y
        INC TP
        BNE pd
        INC TP+1
pd:     RTS

count0: STA cval                ; A = valor, X = página inicial, Y = página final (exclusiva)
        STX P+1
        STY endhi
        LDA #0
        STA P
count:  LDA #0                  ; conta bytes == cval de (P) até endhi:00
        STA C
        STA C+1
        LDY #0
cl:     LDA (P),Y
        CMP cval
        BNE cn
        INC C
        BNE cn
        INC C+1
cn:     INC P
        BNE cl
        INC P+1
        LDA P+1
        CMP endhi
        BNE cl
        RTS

lastnz: STA P                   ; desce de (A/X) até a página Y procurando byte != 0
        STX P+1
        STY lim
        LDY #0
ll:     LDA (P),Y
        BNE lf
        LDA P
        BNE ld
        DEC P+1
ld:     DEC P
        LDA P+1
        CMP lim
        BCS ll
        LDA #0
        STA r_lo
        STA r_hi
        RTS
lf:     LDA P
        STA r_lo
        LDA P+1
        STA r_hi
        RTS

rwtest: STA P                   ; grava $5A e $A5, lê de volta, restaura o original
        STX P+1
        LDY #0
        LDA (P),Y
        PHA
        LDA #$5A
        STA (P),Y
        LDA (P),Y
        STA t1
        LDA #$A5
        STA (P),Y
        LDA (P),Y
        STA t2
        PLA
        STA (P),Y
        LDA t1
        JSR hex
        LDA t2
        JSR hex
        LDA #' '
        JMP putc

; ---------------------------------------------------------------- dados
tbl:    .byte 0
        .word s_title
        .byte 2
        .word s_4800
        .byte 3
        .word s_5ff8
        .byte 4
        .word s_aa
        .byte 5
        .word s_rw
        .byte 7
        .word s_tab
        .byte 15
        .word s_fc
        .byte 16
        .word s_z
        .byte 17
        .word s_w
        .byte 19
        .word s_key
        .byte $FF
s_title: .asciz "DIAG 1"
s_4800:  .asciz "4800:"
s_5ff8:  .asciz "5FF8:"
s_aa:    .asciz "AA 48-5F:"
s_rw:    .asciz "RW:"
s_tab:   .asciz "FC00:"
s_fc:    .asciz "UltNZ FC-FF:"
s_z:     .asciz "Zeros FC40+:"
s_w:     .asciz "UltNZ 7C-7F:"
s_key:   .asciz "Botao=sair"
'''


def main():
    orig, buf, info = build('base')
    code, syms = assemble(SRC, DEVINFO)
    assert DEVINFO + len(code) <= DEVINFO_END, 'diagnóstico não cabe na Device Info (%d bytes)' % len(code)
    o = cpu2file(DEVINFO)
    assert buf[o:o + 5] == bytes([0xA9, 0x06, 0x20, 0xE1, 0xF3]), 'Device Info não está onde esperado'
    buf[o:o + len(code)] = code
    a = cpu2file(ABOUT_CALL)
    assert buf[a:a + 3] == bytes([0x20, 0xB9, 0xD2]), 'chamada do About não está onde esperado'
    buf[a:a + 3] = bytes([0x20, DEVINFO & 0xFF, DEVINFO >> 8])
    out_dir = os.path.join(ROOT, 'poc_diag', 'EDFC')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, 'OS.BIN')
    open(out, 'wb').write(buf)
    print('gerado:', out)
    print('SHA1:', hashlib.sha1(buf).hexdigest())
    print('diagnóstico: $%04X-$%04X (%d de %d bytes)' % (DEVINFO, DEVINFO + len(code) - 1, len(code), DEVINFO_END - DEVINFO))


if __name__ == '__main__':
    main()
