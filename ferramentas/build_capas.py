"""Firmware com CAPAS lidas do SD (/EDFC/COVERS.BIN) — build base do clone EDFC.

uso:  python build_capas.py
saida: capas_sd/EDFC/OS.BIN

Parte da PoC (build_poc.build): sprites 8x16, nome da lista com 21 colunas, gancho no fim do
browser_draw_list e capa escondida nos menus. Por cima disso:
  $81C5  hook_cursor/draw_hook: filtro .nes -> crc_part ; idle_hook ; hide
  $D0C6  (Device Info + About, $D0C6-$D329) info_screen, init_hook, crc_part, load_cover
  $FBD4  cover_show: vblank, OAMDMA $0200, PPUMASK=$1E
  $F79B  (textos do About, $F79B-$F895) sub-rotinas + variáveis + strings
  $BB4A  JSR file_find_by_name (MAPROUT) -> JSR init_hook (procura também COVERS.BIN)
  $D9EB  JSR $AB25 (espera ociosa do navegador) -> JSR idle_hook (carrega a capa pendente)
  $CCFC  JSR $D2B9 (About) -> JSR $D0C6 (info_screen; Device Info já chama $D0C6)

Formato do COVERS.BIN: ver ferramentas/gerar_covers.py.
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from build_poc import build, ROOT, cpu2file, PROFILES
from asm6502 import assemble

COMMON = r'''
UPDCUR   = $83E6        ; ppu_update_cursor_column
WAITVB   = $8393        ; ppu_wait_vblank
IDLE     = $AB25        ; espera ociosa do laço do navegador
FINDNAME = $9DE0        ; file_find_by_name(u32 dir, char* nome8.3, u32* tam, u32* cluster)
CL2LBA   = $96B3        ; fat_cluster_to_lba(u32 cluster) -> A/X/sreg
RDSEC    = $C53F        ; fat_read_sector_cached(u32 lba) -> buffer *(FATBUF), A=erro
PUSHEAX  = $F21B
PUSHAX   = $F3F7
PUSH0    = $F3F3
SCR_BACKUP  = $8441
SCR_CLEAR   = $83C5
PUTS        = $839C
REFRESH     = $8326
WAITKEY     = $9F0B
SCR_RESTORE = $845F
SREG     = $2A
TP       = $92          ; ponteiro de texto do OS
T0       = $30          ; CRC (temporários do cc65: ptr1/ptr2)
T1       = $31
T2       = $32
T3       = $33
P        = $34          ; ponteiro no buffer (ptr3)
FATBUF   = $04E9        ; ponteiro para o buffer de setor do FAT
EDFC_CL  = $04FF        ; cluster da pasta /edfc (u32)
NAMEROWS = $6320        ; buffer de tela, linhas 25-26: nome completo do selecionado
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
hide:   LDA #$0A                ; fundo ligado, sprites desligados
        STA $2001
        RTS
f_yes:  LDA enabled
        BEQ no_cover
        JMP crc_part
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
        RTS
'''

SEG_MAIN = 0xD0C6, 0xD32A, r'''
; ---------------------------------------------------------------- Device Info / About
info_screen:
        JSR SCR_BACKUP
        JSR SCR_CLEAR
        LDA #<$6082
        STA TP
        LDA #>$6082
        STA TP+1
        LDA #<s_info
        LDX #>s_info
        JSR PUTS
        LDA #<$60C2
        STA TP
        LDA #>$60C2
        STA TP+1
        LDA #<s_ok
        LDX #>s_ok
        LDY enabled
        BNE is_pr
        LDA #<s_nf
        LDX #>s_nf
is_pr:  JSR PUTS
        JSR REFRESH
        JSR WAITKEY
        JSR SCR_RESTORE
        JMP REFRESH

; ---------------------------------------------------------------- os_init: depois do MAPROUT.BIN
init_hook:
        JSR FINDNAME            ; a busca original do MAPROUT.BIN (argumentos já empilhados)
        PHA
        LDA #0
        STA enabled
        STA pending
        STA has
        STA base
        STA base+1
        STA base+2
        STA base+3
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
        LDA has
        BEQ c_hide
        JMP cover_show
c_diff: LDX #3                  ; outra: marca como pendente (carrega quando o cursor parar)
c_st:   LDA T0,X
        STA want,X
        DEX
        BPL c_st
        LDA #1
        STA pending
c_hide: JMP hide

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
l_found: LDA (P),Y              ; setor = 256 + idx*4
        STA sec
        INY
        LDA (P),Y
        ASL sec
        ROL A
        ASL sec
        ROL A
        CLC
        ADC #1
        STA sec+1
        LDA sec                 ; setor de metadados: OAM[256] paleta[16] verificação[3]
        LDX sec+1
        JSR lba_read
        BNE l_fail0
        JSR setP
        INC P+1
        LDY #16
        JSR cmp3                ; bytes 272-274 = CRC: protege contra arquivo fragmentado
        BNE l_fail0
        DEC P+1
        LDY #0
l_oam:  LDA (P),Y
        STA $0200,Y
        INY
        BNE l_oam
        INC P+1
        JSR WAITVB
        LDA #$3F
        STA $2006
        LDA #$10
        STA $2006
        LDY #0
l_pal:  LDA (P),Y
        STA $2007
        INY
        CPY #16
        BNE l_pal
        JSR scroll0
        LDA #$00                ; tiles: 3 setores -> PPU $1000, 128 bytes por vblank
        STA pdst
        LDA #$10
        STA pdst+1
        LDA #3
        STA cnt
l_tile: INC sec
        BNE l_t1
        INC sec+1
l_t1:   LDA sec
        LDX sec+1
        JSR lba_read
        BNE l_fail
        LDA FATBUF
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
        DEC cnt
        BNE l_tile
        LDA #1
        STA has
        JMP cover_show
l_fail: RTS
src = l_up+1
src2 = l_up+8

'''

SEG_C = 0xF79B, 0xF896, r'''
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
setP:   LDA FATBUF
        STA P
        LDA FATBUF+1
        STA P+1
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
scroll0: LDA #$A0
        STA $2000
        LDA #0
        STA $2005
        STA $2005
        RTS

; ---------------------------------------------------------------- dados (PRG é RAM)
s_info: .asciz "EDFC CAPAS v1"
s_ok:   .asciz "COVERS.BIN: OK"
s_nf:   .asciz "COVERS.BIN: nao achado"
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
'''

SEGMENTS = [SEG_A, SEG_D, SEG_MAIN, SEG_C]


def assemble_all():
    """Monta os segmentos com tabela de símbolos compartilhada (itera até estabilizar)."""
    syms = {}
    for _ in range(6):
        new = {}
        for org, end, src in SEGMENTS:
            new.update(assemble(COMMON + src, org, syms, strict=False)[1])
        if new == syms:
            break
        syms = new
    out = [(org, end, assemble(COMMON + src, org, syms)[0]) for org, end, src in SEGMENTS]
    for org, end, code in out:
        assert org + len(code) <= end, 'segmento $%04X: %d bytes não cabem (limite %d)' % (org, len(code), end - org)
    return out, syms


def patch(buf, addr, old, new):
    o = cpu2file(addr)
    assert buf[o:o + len(old)] == bytes(old), 'bytes inesperados em $%04X: %s' % (addr, buf[o:o + len(old)].hex())
    buf[o:o + len(new)] = bytes(new)


def jsr(a): return [0x20, a & 0xFF, a >> 8]


def main():
    orig, buf, info = build('base')
    segs, S = assemble_all()
    assert S['hook_cursor'] == 0x81C5 and S['draw_hook'] == 0x81C8   # alvos já gravados pela PoC
    # a área do Device Info + About precisa ser a original
    o = cpu2file(0xD0C6)
    assert orig[o:o + 5] == bytes([0xA9, 0x06, 0x20, 0xE1, 0xF3]), 'Device Info não confere'
    assert orig[cpu2file(0xD2B9):cpu2file(0xD2B9) + 3] == bytes([0x20, 0x6D, 0xEF]), 'About não confere'
    assert orig[cpu2file(0xF79B):cpu2file(0xF79B) + 5] == b'EDN8\0', 'textos do About não conferem'
    assert orig[cpu2file(0xF892):cpu2file(0xF892) + 4] == b'SN:\0', 'fim dos textos do About não confere'
    for org, end, code in segs:
        o = cpu2file(org)
        buf[o:o + len(code)] = code
    patch(buf, 0x833D, buf[cpu2file(0x833D):cpu2file(0x833D) + 3], jsr(S['hide']))
    patch(buf, 0xBB4A, jsr(0x9DE0), jsr(S['init_hook']))
    patch(buf, 0xD9EB, jsr(0xAB25), jsr(S['idle_hook']))
    patch(buf, 0xCCFC, jsr(0xD2B9), jsr(S['info_screen']))
    assert S['info_screen'] == 0xD0C6          # Device Info ($CCE1) já chama $D0C6

    out_dir = os.path.join(ROOT, 'capas_sd', 'EDFC')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, 'OS.BIN')
    open(out, 'wb').write(buf)
    print('gerado:', out)
    print('SHA1:', hashlib.sha1(buf).hexdigest())
    for org, end, code in segs:
        print('  $%04X-$%04X  %3d de %3d bytes' % (org, org + len(code) - 1, len(code), end - org))
    for k in ('hide', 'idle_hook', 'init_hook', 'crc_part', 'load_cover', 'cover_show', 'base', 'enabled'):
        print('  %-12s $%04X' % (k, S[k]))
    return buf, S


if __name__ == '__main__':
    main()
