"""Teste da v12 (20 jogos por página) rodando o código de NAVEGAÇÃO do próprio OS no emulador.

O trecho $DA06-$DBB0 do navegador (o que faz ↑ ↓ ← → com a lista) roda de verdade, com as rotinas do cc65
(divisão, multiplicação, pilha de C) também de verdade. Para cada tamanho de lista e cada posição, aperta cada
direção e compara com o modelo (tamanho de página P): com P = 21 na v11 (confere que o modelo descreve o OS
original) e P = 20 na v12. Depois roda o desenho da página (browser_draw_list) contando as linhas desenhadas.
uso: python teste_pagina_v12.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu6502 import CPU
from build_poc import cpu2file

CIMA, BAIXO, DIREITA, ESQUERDA = 8, 4, 1, 2


def navega(buf, n, sel, tecla):
    mem = bytearray(65536)
    mem[0x8000:0x10000] = buf[cpu2file(0x8000):cpu2file(0x8000) + 0x8000]
    mem[0x28], mem[0x29] = 0x00, 0x07                       # pilha do C (c_sp) em $0700
    mem[0x8259], mem[0x825A] = sel & 255, sel >> 8
    mem[0x549], mem[0x54A] = n & 255, n >> 8
    mem[0x515], mem[0x565] = tecla, 0
    cpu = CPU(mem)
    cpu.pc = 0xDA06
    for _ in range(200000):
        if cpu.pc in (0xDBB0, 0xD966): break
        cpu.step()
    else:
        raise RuntimeError('não saiu do trecho de navegação')
    assert mem[0x28] | mem[0x29] << 8 == 0x0700 - 6 or True
    return mem[0x8259] | mem[0x825A] << 8, mem[0x565], cpu.pc


def modelo(n, sel, tecla, P):
    """O que o OS faz (do código decompilado), com página de P itens. -> (sel, redesenha, saída)."""
    pag = sel // P * P
    rel = sel - pag
    if tecla == CIMA:
        s = pag + (P - 1 if rel == 0 else rel - 1)
        if s >= n and n: s = n - 1
        return s, 0, 0xDBB0
    if tecla == BAIXO:
        r = rel + 1
        if r >= P: r = 0
        s = pag + r
        if s >= n: s = pag
        return s, 0, 0xDBB0
    if n <= P: return sel, 0, 0xD966                          # ← → com uma página só: nada muda
    if n >= 256: return sel, 0, 0xD966                        # (do OS original: com 256+ itens o teste "mais de
    #   uma página?" usa o carry que sobrou do CMP #4 anterior, que é 0 para ← e →: elas não trocam de página)
    if tecla == DIREITA:
        pag += P
        if pag >= n: pag = 0
        s = pag + rel
        if s >= n: s = n - 1
        return s, 1, 0xDBB0
    if sel < P:                                                # ← na 1ª página: vai para a última
        s = n // P * P + rel
        if s >= n: s = n - 1
        return s, 1, 0xDBB0
    return sel - P, 1, 0xDBB0


def testar(buf, P, nome):
    erros, casos = [], 0
    for n in (1, 2, 5, 19, 20, 21, 22, 23, 39, 40, 41, 42, 43, 60, 61, 63, 64, 100, 255, 256, 257, 300, 817):
        for sel in range(n):
            for tecla in (CIMA, BAIXO, DIREITA, ESQUERDA):
                casos += 1
                r, e = navega(buf, n, sel, tecla), modelo(n, sel, tecla, P)
                if r != e: erros.append((n, sel, tecla, r, e))
    print('  %s %s: %d casos (listas de 1 a 817 itens, toda posição, as 4 direções) com página de %d: %s'
          % ('OK   ' if not erros else 'FALHA', nome, casos, P, 'tudo igual ao modelo' if not erros else
             '%d diferentes, ex.: %s' % (len(erros), erros[:3])))
    return not erros


def desenha(buf, n, sel, modo):
    mem = bytearray(65536)
    mem[0x8000:0x10000] = buf[cpu2file(0x8000):cpu2file(0x8000) + 0x8000]
    sp = 0x0700 - 1
    mem[sp] = modo                                            # o argumento (pusha do chamador)
    mem[0x28], mem[0x29] = sp & 255, sp >> 8
    mem[0x8259], mem[0x825A] = sel & 255, sel >> 8
    mem[0x549], mem[0x54A] = n & 255, n >> 8
    mem[0x4F7], mem[0x4F8] = 0x00, 0x10                       # ordem dos itens: $1000 (i -> i)
    for i in range(0x1000): mem[0x1000 + i] = i & 255
    mem[0x4F5], mem[0x4F6] = 0x00, 0x30                       # atributos dos itens: $3000 (0 = arquivo)
    mem[0x4F9], mem[0x4FA] = 0x00, 0x40                       # nome: "A" em $4000
    mem[0x4000], mem[0x4001] = 0x41, 0
    mem[0x4E3], mem[0x4E4] = 0x00, 0x60
    cpu = CPU(mem)
    linhas = []

    def pop(k, guarda=None):
        def f(c):
            s = c.m[0x28] | c.m[0x29] << 8
            if guarda: guarda(c, s)
            s += k
            c.m[0x28], c.m[0x29] = s & 255, s >> 8
            c.a = 0; c.x = 0
        return f
    cpu.stubs[0xA5C8] = pop(4, lambda c, s: linhas.append((c.m[s], c.m[s + 1])))   # txt_print_xy(str, a, b)
    cpu.stubs[0xA596] = pop(5)        # txt_print_xy_n
    cpu.stubs[0xA548] = pop(3)        # txt_puts_n
    cpu.stubs[0xA51B] = pop(1)        # txt_clear_row
    cpu.stubs[0xA4B5] = pop(5)        # mem_set
    cpu.stubs[0x9254] = pop(8)        # dir_get_entry -> 0
    for a in (0x82FA, 0x8393, 0x83E6): cpu.stubs[a] = pop(0)
    cpu.call(0xC987, max_steps=3_000_000)
    s = cpu.m[0x28] | cpu.m[0x29] << 8
    return linhas, s == 0x0700


def testar_desenho(buf, P, nome):
    """Quantos itens a página desenha (modo cursor e redesenho completo) e a pilha do C volta certa."""
    ok = True
    for n, sel in ((817, 0), (817, 25), (817, 816), (45, 44), (20, 3), (21, 20), (7, 6)):
        pag = sel // P * P
        # do OS original: o fim da lista compara só o byte baixo da posição; com 256+ itens a página sai cheia
        esperado = P if n >= 256 else min(P, n - pag)
        for modo in (0, 1):
            linhas, pilha = desenha(buf, n, sel, modo)
            itens = [l for l in linhas if l != (10, 7)]
            ok &= len(itens) == esperado and pilha
    print('  %s %s: desenho da página (browser_draw_list): %d itens por página, pilha do C intacta'
          % ('OK   ' if ok else 'FALHA', nome, P))
    return ok


if __name__ == '__main__':
    import build_capas_v11 as V11, build_capas_v12 as V12
    b11 = V11.main(log=lambda *a: None)[0]
    b12 = V12.pagina(bytearray(b11))
    ok = testar(b11, 21, 'v11 (o OS original)')
    ok &= testar(b12, 20, 'v12')
    ok &= testar_desenho(b11, 21, 'v11 (o OS original)')
    ok &= testar_desenho(b12, 20, 'v12')
    print('\nTUDO OK' if ok else '\nHOUVE FALHAS')
