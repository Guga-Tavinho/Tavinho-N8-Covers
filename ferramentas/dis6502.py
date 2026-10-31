"""Disassembler 6502 simples (linear) para trechos do OS.BIN do EverDrive N8.
uso: python dis6502.py OS.BIN <cpu_addr_hex> <len_hex> [run_addr_hex]
cpu_addr: endereço no PRG ($8000-$FFFF). run_addr: endereço onde o trecho executa (stubs copiados p/ RAM)."""
import sys
OPS = {}
def op(code, m, mode): OPS[code] = (m, mode)
tbl = """00 BRK imp|01 ORA izx|05 ORA zp|06 ASL zp|08 PHP imp|09 ORA imm|0A ASL acc|0D ORA abs|0E ASL abs|10 BPL rel|11 ORA izy|15 ORA zpx|16 ASL zpx|18 CLC imp|19 ORA aby|1D ORA abx|1E ASL abx|20 JSR abs|21 AND izx|24 BIT zp|25 AND zp|26 ROL zp|28 PLP imp|29 AND imm|2A ROL acc|2C BIT abs|2D AND abs|2E ROL abs|30 BMI rel|31 AND izy|35 AND zpx|36 ROL zpx|38 SEC imp|39 AND aby|3D AND abx|3E ROL abx|40 RTI imp|41 EOR izx|45 EOR zp|46 LSR zp|48 PHA imp|49 EOR imm|4A LSR acc|4C JMP abs|4D EOR abs|4E LSR abs|50 BVC rel|51 EOR izy|55 EOR zpx|56 LSR zpx|58 CLI imp|59 EOR aby|5D EOR abx|5E LSR abx|60 RTS imp|61 ADC izx|65 ADC zp|66 ROR zp|68 PLA imp|69 ADC imm|6A ROR acc|6C JMP ind|6D ADC abs|6E ROR abs|70 BVS rel|71 ADC izy|75 ADC zpx|76 ROR zpx|78 SEI imp|79 ADC aby|7D ADC abx|7E ROR abx|81 STA izx|84 STY zp|85 STA zp|86 STX zp|88 DEY imp|8A TXA imp|8C STY abs|8D STA abs|8E STX abs|90 BCC rel|91 STA izy|94 STY zpx|95 STA zpx|96 STX zpy|98 TYA imp|99 STA aby|9A TXS imp|9D STA abx|A0 LDY imm|A1 LDA izx|A2 LDX imm|A4 LDY zp|A5 LDA zp|A6 LDX zp|A8 TAY imp|A9 LDA imm|AA TAX imp|AC LDY abs|AD LDA abs|AE LDX abs|B0 BCS rel|B1 LDA izy|B4 LDY zpx|B5 LDA zpx|B6 LDX zpy|B8 CLV imp|B9 LDA aby|BA TSX imp|BC LDY abx|BD LDA abx|BE LDX aby|C0 CPY imm|C1 CMP izx|C4 CPY zp|C5 CMP zp|C6 DEC zp|C8 INY imp|C9 CMP imm|CA DEX imp|CC CPY abs|CD CMP abs|CE DEC abs|D0 BNE rel|D1 CMP izy|D5 CMP zpx|D6 DEC zpx|D8 CLD imp|D9 CMP aby|DD CMP abx|DE DEC abx|E0 CPX imm|E1 SBC izx|E4 CPX zp|E5 SBC zp|E6 INC zp|E8 INX imp|E9 SBC imm|EA NOP imp|EC CPX abs|ED SBC abs|EE INC abs|F0 BEQ rel|F1 SBC izy|F5 SBC zpx|F6 INC zpx|F8 SED imp|F9 SBC aby|FD SBC abx|FE INC abx"""
for e in tbl.split('|'):
    c, m, mode = e.split(); op(int(c, 16), m, mode)
LEN = dict(imp=1, acc=1, imm=2, zp=2, zpx=2, zpy=2, izx=2, izy=2, rel=2, abs=3, abx=3, aby=3, ind=3)
FMT = dict(imp='', acc='A', imm='#${:02X}', zp='${:02X}', zpx='${:02X},X', zpy='${:02X},Y', izx='(${:02X},X)',
           izy='(${:02X}),Y', rel='${:04X}', abs='${:04X}', abx='${:04X},X', aby='${:04X},Y', ind='(${:04X})')

def dis(buf, base):
    i, out = 0, []
    while i < len(buf):
        c = buf[i]
        if c not in OPS:
            out.append('%04X  %02X        .db $%02X' % (base + i, c, c)); i += 1; continue
        m, mode = OPS[c]; n = LEN[mode]; b = buf[i:i + n]
        if len(b) < n: break
        if mode in ('abs', 'abx', 'aby', 'ind'): v = b[1] | b[2] << 8
        elif mode == 'rel': v = (base + i + 2 + (b[1] - 256 if b[1] > 127 else b[1])) & 0xFFFF
        elif n == 2: v = b[1]
        else: v = None
        txt = m + (' ' + FMT[mode].format(v) if FMT[mode] and v is not None else (' A' if mode == 'acc' else ''))
        out.append('%04X  %-8s  %s' % (base + i, ' '.join('%02X' % x for x in b), txt)); i += n
    return out

if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    a = int(sys.argv[2], 16); ln = int(sys.argv[3], 16)
    run = int(sys.argv[4], 16) if len(sys.argv) > 4 else a
    off = a - 0x8000 + 0x6000
    print('\n'.join(dis(d[off:off + ln], run)))
