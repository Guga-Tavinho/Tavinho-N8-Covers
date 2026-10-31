"""Ciclos de CPU por instrução do 6502 (NES), para o emulador de teste medir o tempo das escritas na PPU.

Conservador: leituras indexadas (abx, aby, izy) contam sempre +1 (como se cruzassem página); desvios contam o
ciclo extra de página de verdade. Usado para conferir que tudo o que é escrito na PPU cabe no vblank.
"""
from dis6502 import OPS

RMW = {'ASL', 'LSR', 'ROL', 'ROR', 'INC', 'DEC'}
STORES = {'STA', 'STX', 'STY'}
IMP = {'PHA': 3, 'PHP': 3, 'PLA': 4, 'PLP': 4, 'RTS': 6, 'RTI': 6, 'BRK': 7}


def ciclos(cpu, pc, op):
    """Ciclos da instrução em pc (opcode op) que acabou de rodar (cpu.pc já é o seguinte)."""
    m, mode = OPS[op]
    if mode == 'rel':
        if cpu.pc == pc + 2: return 2
        return 3 + (1 if (cpu.pc & 0xFF00) != ((pc + 2) & 0xFF00) else 0)
    if mode in ('imp', 'acc'): return IMP.get(m, 2)
    if mode == 'imm': return 2
    if mode == 'zp': return 5 if m in RMW else 3
    if mode in ('zpx', 'zpy'): return 6 if m in RMW else 4
    if mode == 'abs':
        if m == 'JMP': return 3
        if m == 'JSR': return 6
        return 6 if m in RMW else 4
    if mode in ('abx', 'aby'):
        if m in RMW: return 7
        return 5                                   # leitura: 4 (+1 se cruzar página, contado sempre); escrita: 5
    if mode == 'izx': return 6
    if mode == 'izy': return 6                     # leitura 5 (+1), escrita 6
    if mode == 'ind': return 5
    raise ValueError('modo %s' % mode)


def medir(cpu, est):
    """Liga a contagem de ciclos no cpu: est['t'] = ciclos acumulados (stubs contam 0)."""
    passo = cpu.step

    def step():
        pc = cpu.pc
        op = cpu.m[pc]
        stub = pc in cpu.stubs
        passo()
        if not stub and op in OPS: est['t'] += ciclos(cpu, pc, op)
    cpu.step = step
