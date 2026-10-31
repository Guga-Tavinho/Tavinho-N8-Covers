"""Teste da v14 (← → levam o cursor para o topo da página nova) com o código de navegação do OS no emulador.

Mesmo método do teste_pagina_v12: o trecho $DA06-$DBB0 do próprio OS, para listas de 1 a 254 itens (o máximo de
uma pasta), toda posição, as 4 direções. ↑ ↓ continuam como na v13; ← → vão para a 1ª linha da página nova.
uso: python teste_pagina_v14.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teste_pagina_v12 import navega, modelo, CIMA, BAIXO, DIREITA, ESQUERDA


def modelo_topo(n, sel, tecla, P=20):
    if tecla in (CIMA, BAIXO) or n <= P: return modelo(n, sel, tecla, P)
    pag = sel // P * P
    if tecla == DIREITA:
        pag += P
        if pag >= n: pag = 0
        return pag, 1, 0xDBB0
    if sel < P:                                                # ← na 1ª página: o topo da última
        s = n // P * P
        if s >= n: s = n - 1                                   # (n múltiplo de 20: a "última" ficaria vazia)
        return s, 1, 0xDBB0
    return pag - P, 1, 0xDBB0


if __name__ == '__main__':
    import build_capas_v14 as V14
    buf = V14.main(log=print)[0]
    erros, casos = [], 0
    for n in list(range(1, 45)) + [59, 60, 61, 99, 100, 101, 199, 200, 201, 240, 241, 253, 254]:
        for sel in range(n):
            for tecla in (CIMA, BAIXO, DIREITA, ESQUERDA):
                casos += 1
                r, e = navega(buf, n, sel, tecla), modelo_topo(n, sel, tecla)
                if r != e: erros.append((n, sel, tecla, r, e))
    print('  %s v14: %d casos (listas de 1 a 254 itens, toda posição, as 4 direções): %s'
          % ('OK   ' if not erros else 'FALHA', casos, 'tudo como esperado' if not erros else
             '%d diferentes, ex.: %s' % (len(erros), erros[:4])))
    print('TUDO OK' if not erros else 'HOUVE FALHAS')
