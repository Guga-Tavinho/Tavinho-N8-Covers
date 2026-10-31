"""Modelo de TEMPO da PPU para os testes no emulador 6502 (NTSC: 262 linhas de 341 pontos, 3 pontos por ciclo).

Cada instrução avança o relógio (ciclos6502). Ao cruzar as linhas:
  Y+1  o sprite 0 "acerta" (flag V de $2002) na linha dele (OAM[0]+1) se fundo e sprites estão ligados
  241  começa o vblank (flag de $2002, bit 7) e, com o NMI ligado ($2000 bit 7), o NMI de verdade do OS roda
       interrompendo o código (empilha PC/P e pula para o vetor $FFFA), como no console
  261  pré-render: as flags de vblank e do sprite 0 se apagam
Ler $2002 devolve as flags, apaga a do vblank e zera a "meia escrita" do $2006 (latch) — o que o NMI do OS faz.
Escrita na PPU ($2005/$2006/$2007/$4014) com a tela ligada fora do vblank vira uma VIOLAÇÃO (lixo no aparelho).
WAITVB ($8393) vira um salto do relógio até o próximo vblank (o NMI roda no caminho).
"""
import ciclos6502

LINHA = 341 / 3
QUADRO = 262 * LINHA


class Tempo:
    def __init__(self, cpu, mem, ppu, est, custo_cartao=3000):
        self.cpu, self.mem, self.ppu, self.est = cpu, mem, ppu, est
        est.update(t=0.0, vbl=0, s0=0, nmi_on=True, mask=0x0A, joy=0, jread=0, viol=[], eventos=[], nmis=0)
        passo = cpu.step

        def step():
            pc = cpu.pc
            op = mem[pc]
            stub = pc in cpu.stubs
            t0 = est['t']
            passo()
            if not stub and op in ciclos6502.OPS:
                est['t'] += ciclos6502.ciclos(cpu, pc, op)
            self.eventos(t0, est['t'])
        cpu.step = step
        self.custo_cartao = custo_cartao
        ow, orr = cpu.on_write, cpu.on_read

        def on_read(a):
            if a == 0x2002:
                v = est['vbl'] << 7 | est['s0'] << 6
                est['vbl'] = 0
                ppu['latch'] = 0
                return v
            if a == 0x4016:
                apertado = est['joy'] or (est.get('joy_em') is not None and est['t'] >= est['joy_em'])
                b = 1 if (apertado and est['jread'] == 0) else 0
                est['jread'] += 1
                return b
            if a == 0x4017: return 0
            return orr(a) if orr else None

        def on_write(a, v):
            if a in (0x2005, 0x2006, 0x2007, 0x4014): self.confere(a)
            if a == 0x4014: est['t'] += 513
            if a == 0x4016: est['jread'] = 0
            if a == 0x2000: est['nmi_on'] = bool(v & 0x80)
            if a == 0x2001:
                antes, depois = bool(est['mask'] & 0x18), bool(v & 0x18)
                if antes != depois: est['eventos'].append(('liga' if depois else 'desliga', self.linha(), est.get('fase')))
                est['mask'] = v
            return ow(a, v) if ow else False
        cpu.on_read, cpu.on_write = on_read, on_write

    def linha(self, t=None):
        t = self.est['t'] if t is None else t
        return (t % QUADRO) / LINHA

    def no_vblank(self):
        return 241 <= self.linha() < 261

    def confere(self, a):
        e = self.est
        if not e['mask'] & 0x18: return                              # tela desligada: tudo bem
        if not self.no_vblank():
            e['viol'].append((e.get('fase'), '$%04X' % a, round(self.linha(), 1), '$%04X' % self.cpu.pc))

    def eventos(self, t0, t1):
        """Processa as linhas 16, 241 e 261 cruzadas entre t0 e t1, em ordem."""
        e = self.est
        q0 = int(t0 // QUADRO)
        for q in range(q0, int(t1 // QUADRO) + 1):
            oam = self.ppu.get('oam') or b''
            ls0 = oam[0] + 1 if len(oam) >= 4 and oam[0] < 239 else 999   # linha do sprite 0 (Y+1)
            for linha, nome in sorted(((ls0, 's0'), (241, 'vbl'), (261, 'pre'))):
                tl = q * QUADRO + linha * LINHA
                if not t0 < tl <= t1: continue
                if nome == 's0':
                    if e['mask'] & 0x18 == 0x18: e['s0'] = 1                  # (o fundo atrás é opaco)
                elif nome == 'vbl':
                    e['vbl'] = 1
                    if e['nmi_on']: self.nmi()
                else:
                    e['vbl'] = 0; e['s0'] = 0

    def nmi(self):
        cpu, e = self.cpu, self.est
        e['nmis'] += 1
        cpu.push(cpu.pc >> 8); cpu.push(cpu.pc & 0xFF); cpu.push(cpu.p() & ~0x10 | 0x20)
        cpu.i = 1
        cpu.pc = cpu.rd16(0xFFFA)
        e['t'] += 7

    def ate_vblank(self):
        """WAITVB: pula o relógio até o início do próximo vblank (o NMI roda ao cruzar a linha 241)."""
        e = self.est
        t = e['t']
        alvo = (int(t // QUADRO) * QUADRO) + 241 * LINHA
        if alvo <= t: alvo += QUADRO
        e['t'] = alvo + 1                                            # o step() processa as linhas cruzadas

    def cartao(self):
        self.est['t'] += self.custo_cartao
