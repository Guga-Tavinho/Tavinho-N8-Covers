"""Progresso de um cálculo longo (conversão da capa / alternância), para a barra de porcentagem da ferramenta.

Quem calcula marca etapas e avanços; quem mostra define o callback. Sem callback, não custa nada.
    with etapa(0.0, 0.4):            # esta parte vale de 0% a 40% da etapa em que está
        for i in range(n): ...; avancar((i + 1) / n)
"""
_cb = None
_faixa = [(0.0, 1.0)]
_ult = -1


def definir(cb):
    """cb(v) com v de 0.0 a 1.0; chamado só quando a porcentagem inteira muda."""
    global _cb, _ult
    _cb, _ult = cb, -1
    _faixa[:] = [(0.0, 1.0)]


def avancar(f):
    global _ult
    if _cb is None: return
    ini, fim = _faixa[-1]
    v = ini + (fim - ini) * min(1.0, max(0.0, f))
    pct = int(v * 100)
    if pct > _ult:
        _ult = pct
        _cb(v)


class etapa:
    def __init__(self, a, b):
        self.a, self.b = a, b

    def __enter__(self):
        ini, fim = _faixa[-1]
        _faixa.append((ini + (fim - ini) * self.a, ini + (fim - ini) * self.b))
        avancar(0)

    def __exit__(self, *exc):
        avancar(1)
        _faixa.pop()
