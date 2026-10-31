"""POC v3: capas com sprites + fundo + ALTERNÂNCIA de quadros (fidelidade máxima).

uso:  python build_capas_v3.py
saida: experimento_v3/EDFC/OS.BIN   (COVERS.BIN v3: gerar_covers.py --v3)

Parte da v2 estável (build_capas_v2.py) e acrescenta:
  - NMI ($80E6 -> nmi_flk): a cada quadro, se a capa está visível (flk=1) e o OS não está enviando
    a tela ($A2=0): grava as 28 cores $3F04-$3F1F do quadro, faz o OAMDMA de $0200, refaz a rolagem e,
    fora do vblank, troca os tiles da OAM para o outro quadro (tile EOR $80: A = 1..95, B = 129..223)
  - tabelas de paleta dos quadros A e B na WRAM ($7F00, 56 bytes; o heap do OS fica abaixo de ~$7E84)
  - flk = 0 antes de qualquer desenho do OS: hide/hide_draw, load_cover e o JSR $82FA do redesenho
    completo ($CB83 -> w82fa); 8326/83E6 já marcam $A2=1
  - COVERS.BIN v3: 16 setores por capa (setor = 256 + idx*16); tiles B em $1800, fundo em $0000/$0800
Espaço novo: $A680-$A706 (rotinas de imprimir hexa sem nenhuma chamada — só o About usava $A680) e
$F753-$F75E (título da Device Info removida).
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from build_poc import build, ROOT, cpu2file
from build_capas import patch, jsr
import build_capas_v2 as V2
from asm6502 import assemble


def sub(src, old, new):
    assert src.count(old) == 1, 'trecho não encontrado (ou repetido): ' + old[:70]
    return src.replace(old, new)


HEAD = V2.COMMON2 + V2.EXTRA_CONST + r'''
PALTAB   = $7F00        ; paletas $3F04-$3F1F do quadro A (0-27) e do B (28-55), na WRAM
LDEAXI   = $F14C        ; cc65: carrega 32 bits de (A/X)
GFX_FULL = $82FA        ; ppu_upload_nametable_full
'''

# ---------------------------------------------------------------- $81C5: igual à v2
SEG_A = V2.SEG_A

# ---------------------------------------------------------------- $FBD4: cover_show liga a alternância
SEG_D = (V2.SEG_D[0], V2.SEG_D[1], sub(V2.SEG_D[2], '''        LDA #1
        STA bgshown
        RTS''', '''        LDA #1
        STA bgshown
        STA flk                 ; v3: liga a alternância (o NMI cuida das paletas e da OAM)
        RTS'''))

# ---------------------------------------------------------------- $D0C6: carga da capa v3
m = V2.SEG_MAIN[2]
m = sub(m, '''        LDA EDFC_CL+3           ; file_find_by_name(edfc, "COVERS  BIN", NULL, &base)
        STA SREG+1
        LDA EDFC_CL+2
        STA SREG
        LDX EDFC_CL+1
        LDA EDFC_CL
        JSR PUSHEAX''', '''        LDA #<EDFC_CL           ; file_find_by_name(edfc, "COVERS  BIN", NULL, &base)
        LDX #>EDFC_CL
        JSR LDEAXI
        JSR PUSHEAX''')
m = sub(m, '''        LDA base+3              ; base = primeiro setor do arquivo
        STA SREG+1
        LDA base+2
        STA SREG
        LDX base+1
        LDA base
        JSR PUSHEAX''', '''        LDA #<base              ; base = primeiro setor do arquivo
        LDX #>base
        JSR LDEAXI
        JSR PUSHEAX''')
m = sub(m, '''crc_part:
        LDA #$FF
        STA T0
        STA T1
        STA T2
        STA T3
        LDX #0''', '''crc_part:
        LDA #$FF
        LDX #3
c_ini:  STA T0,X
        DEX
        BPL c_ini
        LDX #0''')
m = sub(m, '''        LDA #0
        STA pending
        STA has
        LDA want                ; balde''', '''        LDA #0
        STA pending
        STA has
        STA flk                 ; v3: alternância parada durante a carga
        STA frame               ;     e a OAM nova começa no quadro A
        LDA want                ; balde''')
m = sub(m, '''l_found: LDA (P),Y              ; setor = 256 + idx*8
        STA sec
        INY
        LDA (P),Y
        ASL sec
        ROL A
        ASL sec
        ROL A
        ASL sec
        ROL A                   ; idx < 8160 (limite da ferramenta): o carry aqui é sempre 0''',
        '''l_found: LDA (P),Y              ; setor = 256 + idx*16
        STA sec
        INY
        LDA (P),Y
        ASL sec
        ROL A
        ASL sec
        ROL A
        ASL sec
        ROL A
        ASL sec
        ROL A                   ; idx < 4080 (limite da ferramenta): o carry aqui é sempre 0''')
m = sub(m, '''        LDY #28
        JSR cmp3                ; bytes 284-286 = CRC: protege contra arquivo fragmentado''',
        '''        LDY #56
        JSR cmp3                ; bytes 312-314 = CRC: protege contra arquivo fragmentado''')
m = sub(m, '''        INC P+1
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
''', '''        INC P+1
        LDY #55                 ; v3: paletas dos quadros A e B -> WRAM (o NMI grava na PPU a cada quadro)
l_pc:   LDA (P),Y
        STA PALTAB,Y
        DEY
        BPL l_pc
''')
m = sub(m, '''        LDX #0
        LDY #32
l_nt:''', '''        LDX #0
        LDY #64
l_nt:''')
m = sub(m, '''l_nt1:  CPY #128''', '''l_nt1:  CPY #160''')
m = sub(m, '''        LDA #$00                ; tiles: 3 setores -> $1000, depois $0000 e $0800 (fundo)
        STA pdst
        LDA #$10
        STA pdst+1
        LDA #5
        STA cnt''', '''        LDA #$00                ; tiles: A $1000, B $1800 (3+3 setores), fundo $0000 e $0800
        STA pdst
        LDA #$10
        STA pdst+1
        LDA #8
        STA cnt''')
m = sub(m, '''        LDA pdst+1              ; fim dos sprites ($1600) -> tiles de fundo em $0000; fim ($0200) -> $0800
        CMP #$16
        BNE l_d1
        LDA #$00
        STA pdst+1
l_d1:   CMP #$02
        BNE l_d2
        LDA #$08
        STA pdst+1
l_d2:''', '''        LDA pdst+1              ; fim de A ($1600) -> B em $1800; fim de B ($1E00) -> $0000; $0200 -> $0800
        CMP #$16
        BNE l_d0
        LDA #$18
        STA pdst+1
l_d0:   CMP #$1E
        BNE l_d1
        LDA #$00
        STA pdst+1
l_d1:   CMP #$02
        BNE l_d2
        LDA #$08
        STA pdst+1
l_d2:''')
SEG_MAIN = (V2.SEG_MAIN[0], V2.SEG_MAIN[1], m)

# ---------------------------------------------------------------- $F753 (+ título da Device Info): dados e camada de fundo
c = V2.SEG_C[2]
c = sub(c, '''hide_draw: LDA bgshown          ; troca de item: limpa o fundo da capa (buffer + PPU) e esconde sprites
        BEQ h_mask''', '''hide_draw: LDA #0                ; troca de item: alternância parada antes de mexer na PPU
        STA flk
        LDA bgshown             ; limpa o fundo da capa (buffer + PPU) e esconde sprites
        BEQ h_mask''')
c = sub(c, '''h_inv:  LDA #0
        STA bgshown
        STA has''', '''h_inv:  LDA #0
        STA bgshown
        STA flk
        STA has''')
c = sub(c, '''bgshown: .byte 0''', '''bgshown: .byte 0
flk:    .byte 0                 ; 1 = capa visível: o NMI alterna os quadros
frame:  .byte 0                 ; 0 = quadro A na OAM, 28 = quadro B (índice em PALTAB)''')
SEG_C = (0xF753, V2.SEG_C[1], c)

# ---------------------------------------------------------------- $A680: NMI da alternância + desvio do $82FA
SEG_E = 0xA680, 0xA707, r'''
nmi_flk: LDA flk                ; (o NMI do OS já salvou A e leu o joypad)
        BEQ nf_end
        LDA $A2                 ; o OS está enviando a tela (8326/83E6): não mexe
        BNE nf_end
        TXA
        PHA
        TYA
        PHA
        LDA #$3F                ; vblank: paletas do quadro atual
        STA $2006
        LDA #$04
        STA $2006
        LDX frame
        LDY #28
nf_pal: LDA PALTAB,X
        STA $2007
        INX
        DEY
        BNE nf_pal
        LDA #2                  ; OAMDMA ($2003 já é 0 depois da renderização)
        STA $4014
        JSR scroll0
        LDX #0                  ; já fora do vblank: OAM do próximo quadro (tile EOR $80)
nf_t:   LDA $0201,X
        EOR #$80
        STA $0201,X
        INX
        INX
        INX
        INX
        CPX #192
        BNE nf_t
        LDA frame
        EOR #28
        STA frame
        PLA
        TAY
        PLA
        TAX
nf_end: LDA $2002               ; final original do NMI
        PLA
        RTI
w82fa:  LDA #0                  ; redesenho completo do OS: alternância parada antes
        STA flk
        JMP GFX_FULL
'''

SEGMENTS = [SEG_A, SEG_D, SEG_MAIN, SEG_C, SEG_E]


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


def main():
    orig, buf, info = build('base')
    segs, S = assemble_all()
    assert S['hook_cursor'] == 0x81C5 and S['draw_hook'] == 0x81C8
    o = cpu2file(0xD0C6)
    assert orig[o:o + 5] == bytes([0xA9, 0x06, 0x20, 0xE1, 0xF3]), 'Device Info não confere'
    assert orig[cpu2file(0xD2B9):cpu2file(0xD2B9) + 3] == bytes([0x20, 0x6D, 0xEF]), 'About não confere'
    assert orig[cpu2file(0xF753):cpu2file(0xF753) + 12] == b'Device Info\0', 'título da Device Info não confere'
    assert orig[cpu2file(0xF79B):cpu2file(0xF79B) + 5] == b'EDN8\0', 'textos do About não conferem'
    assert orig[cpu2file(0xA680):cpu2file(0xA680) + 3] == bytes([0x20, 0x43, 0xF1]), '$A680 não confere'
    assert orig[cpu2file(0xA704):cpu2file(0xA707)] == bytes([0x4C, 0x49, 0xF0]), 'fim de $A706 não confere'
    assert orig[cpu2file(0xF14C):cpu2file(0xF14C) + 2] == bytes([0xA0, 0x03]), 'ldeaxi não confere'
    for org, end, code in segs:
        o = cpu2file(org)
        buf[o:o + len(code)] = code
    patch(buf, 0x833D, buf[cpu2file(0x833D):cpu2file(0x833D) + 3], jsr(S['hide']))
    patch(buf, 0xBB4A, jsr(0x9DE0), jsr(S['init_hook']))
    patch(buf, 0xD9EB, jsr(0xAB25), jsr(S['idle_hook']))
    patch(buf, 0xCB8B, jsr(S['draw_hook']), jsr(S['mask_entry']))     # redesenho completo
    patch(buf, 0xCB83, jsr(0x82FA), jsr(S['w82fa']))                    # v3: alternância parada antes do $82FA
    patch(buf, 0xCB29, [0xA9, 0x15], [0xA9, 0x14])                      # nome: 20 colunas
    patch(buf, 0xCCE1, jsr(0xD0C6), jsr(S['cm_r']))                     # Device Info -> nada (RTS)
    patch(buf, 0xCCFC, jsr(0xD2B9), jsr(S['cm_r']))                     # About -> nada (RTS)
    patch(buf, 0x80E6, [0xAD, 0x02, 0x20], [0x4C, S['nmi_flk'] & 0xFF, S['nmi_flk'] >> 8])   # v3: NMI

    out_dir = os.path.join(ROOT, 'experimento_v3', 'EDFC')
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
