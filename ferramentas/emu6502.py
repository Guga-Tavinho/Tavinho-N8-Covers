"""Emulador 6502 mínimo (opcodes oficiais) para testar patches do OS no PC.

Não emula PPU/APU/cartucho: leituras/escritas de I/O passam por hooks opcionais.
Uso típico:
    cpu = CPU(mem)                      # mem: bytearray(65536)
    cpu.stubs[0x8326] = lambda c: None  # rotina substituída: só retorna (RTS implícito)
    cpu.call(0xD0C6)                    # roda até o RTS final
"""
from dis6502 import OPS, LEN


class CPU:
    def __init__(self, mem):
        self.m = mem
        self.a = self.x = self.y = 0
        self.sp = 0xFD
        self.pc = 0
        self.c = self.z = self.i = self.d = self.v = self.n = 0
        self.stubs = {}          # endereço -> função(cpu); simula a rotina e retorna
        self.on_read = None      # função(addr) -> valor ou None
        self.on_write = None     # função(addr, valor) -> True se tratou
        self.steps = 0

    # ---- memória
    def rd(self, a):
        a &= 0xFFFF
        if self.on_read:
            v = self.on_read(a)
            if v is not None: return v & 0xFF
        return self.m[a]

    def wr(self, a, v):
        a &= 0xFFFF
        if self.on_write and self.on_write(a, v & 0xFF): return
        self.m[a] = v & 0xFF

    def rd16(self, a): return self.rd(a) | self.rd(a + 1) << 8

    def push(self, v): self.m[0x100 + self.sp] = v & 0xFF; self.sp = (self.sp - 1) & 0xFF
    def pop(self): self.sp = (self.sp + 1) & 0xFF; return self.m[0x100 + self.sp]

    def p(self):
        return (self.n << 7) | (self.v << 6) | 0x20 | (self.d << 3) | (self.i << 2) | (self.z << 1) | self.c

    def setp(self, v):
        self.n, self.v, self.d, self.i, self.z, self.c = (v >> 7) & 1, (v >> 6) & 1, (v >> 3) & 1, (v >> 2) & 1, (v >> 1) & 1, v & 1

    def zn(self, v):
        v &= 0xFF; self.z = int(v == 0); self.n = v >> 7; return v

    # ---- execução
    def call(self, addr, max_steps=5_000_000):
        """JSR addr e roda até ele retornar."""
        ret = 0xFFFF  # endereço sentinela
        self.push((ret - 1) >> 8); self.push((ret - 1) & 0xFF)
        self.pc = addr
        while self.pc != ret:
            self.step()
            if self.steps > max_steps: raise RuntimeError('passos demais em $%04X' % self.pc)

    def step(self):
        self.steps += 1
        if self.pc in self.stubs:
            self.stubs[self.pc](self)
            lo = self.pop(); hi = self.pop(); self.pc = ((hi << 8) | lo) + 1
            return
        pc = self.pc
        op = self.m[pc]
        if op not in OPS: raise RuntimeError('opcode inválido %02X em $%04X' % (op, pc))
        name, mode = OPS[op]; ln = LEN[mode]
        b1 = self.m[(pc + 1) & 0xFFFF]; b2 = self.m[(pc + 2) & 0xFFFF]
        self.pc = (pc + ln) & 0xFFFF
        # endereço efetivo
        ea = None
        if mode == 'zp': ea = b1
        elif mode == 'zpx': ea = (b1 + self.x) & 0xFF
        elif mode == 'zpy': ea = (b1 + self.y) & 0xFF
        elif mode == 'abs': ea = b1 | b2 << 8
        elif mode == 'abx': ea = ((b1 | b2 << 8) + self.x) & 0xFFFF
        elif mode == 'aby': ea = ((b1 | b2 << 8) + self.y) & 0xFFFF
        elif mode == 'izx': z = (b1 + self.x) & 0xFF; ea = self.m[z] | self.m[(z + 1) & 0xFF] << 8
        elif mode == 'izy': ea = ((self.m[b1] | self.m[(b1 + 1) & 0xFF] << 8) + self.y) & 0xFFFF
        elif mode == 'ind':
            a = b1 | b2 << 8; ea = self.rd(a) | self.rd((a & 0xFF00) | ((a + 1) & 0xFF)) << 8
        elif mode == 'rel': ea = (self.pc + (b1 - 256 if b1 > 127 else b1)) & 0xFFFF
        val = lambda: b1 if mode == 'imm' else (self.a if mode == 'acc' else self.rd(ea))

        def store_rmw(v):
            v &= 0xFF
            if mode == 'acc': self.a = v
            else: self.wr(ea, v)
            return self.zn(v)

        n = name
        if n == 'LDA': self.a = self.zn(val())
        elif n == 'LDX': self.x = self.zn(val())
        elif n == 'LDY': self.y = self.zn(val())
        elif n == 'STA': self.wr(ea, self.a)
        elif n == 'STX': self.wr(ea, self.x)
        elif n == 'STY': self.wr(ea, self.y)
        elif n == 'TAX': self.x = self.zn(self.a)
        elif n == 'TAY': self.y = self.zn(self.a)
        elif n == 'TXA': self.a = self.zn(self.x)
        elif n == 'TYA': self.a = self.zn(self.y)
        elif n == 'TSX': self.x = self.zn(self.sp)
        elif n == 'TXS': self.sp = self.x
        elif n == 'PHA': self.push(self.a)
        elif n == 'PLA': self.a = self.zn(self.pop())
        elif n == 'PHP': self.push(self.p() | 0x10)
        elif n == 'PLP': self.setp(self.pop())
        elif n in ('ADC', 'SBC'):
            v = val()
            if n == 'SBC': v ^= 0xFF
            r = self.a + v + self.c
            self.v = int(((self.a ^ r) & (v ^ r) & 0x80) != 0)
            self.c = int(r > 0xFF); self.a = self.zn(r)
        elif n == 'AND': self.a = self.zn(self.a & val())
        elif n == 'ORA': self.a = self.zn(self.a | val())
        elif n == 'EOR': self.a = self.zn(self.a ^ val())
        elif n in ('CMP', 'CPX', 'CPY'):
            r = {'CMP': self.a, 'CPX': self.x, 'CPY': self.y}[n]; v = val()
            self.c = int(r >= v); self.zn(r - v)
        elif n == 'BIT':
            v = val(); self.z = int((self.a & v) == 0); self.n = v >> 7; self.v = (v >> 6) & 1
        elif n == 'INC': store_rmw(self.rd(ea) + 1)
        elif n == 'DEC': store_rmw(self.rd(ea) - 1)
        elif n == 'INX': self.x = self.zn(self.x + 1)
        elif n == 'INY': self.y = self.zn(self.y + 1)
        elif n == 'DEX': self.x = self.zn(self.x - 1)
        elif n == 'DEY': self.y = self.zn(self.y - 1)
        elif n == 'ASL': v = val(); self.c = v >> 7; store_rmw(v << 1)
        elif n == 'LSR': v = val(); self.c = v & 1; store_rmw(v >> 1)
        elif n == 'ROL': v = val(); c = self.c; self.c = v >> 7; store_rmw((v << 1) | c)
        elif n == 'ROR': v = val(); c = self.c; self.c = v & 1; store_rmw((v >> 1) | (c << 7))
        elif n == 'JMP': self.pc = ea
        elif n == 'JSR':
            r = (self.pc - 1) & 0xFFFF; self.push(r >> 8); self.push(r & 0xFF); self.pc = ea
        elif n == 'RTS': lo = self.pop(); hi = self.pop(); self.pc = (((hi << 8) | lo) + 1) & 0xFFFF
        elif n == 'RTI': self.setp(self.pop()); lo = self.pop(); hi = self.pop(); self.pc = (hi << 8) | lo
        elif n in ('BPL', 'BMI', 'BVC', 'BVS', 'BCC', 'BCS', 'BNE', 'BEQ'):
            flag = {'BPL': not self.n, 'BMI': self.n, 'BVC': not self.v, 'BVS': self.v,
                    'BCC': not self.c, 'BCS': self.c, 'BNE': not self.z, 'BEQ': self.z}[n]
            if flag: self.pc = ea
        elif n == 'CLC': self.c = 0
        elif n == 'SEC': self.c = 1
        elif n == 'CLI': self.i = 0
        elif n == 'SEI': self.i = 1
        elif n == 'CLD': self.d = 0
        elif n == 'SED': self.d = 1
        elif n == 'CLV': self.v = 0
        elif n == 'NOP': pass
        elif n == 'BRK': raise RuntimeError('BRK em $%04X' % pc)
        else: raise RuntimeError('não implementado: ' + n)
