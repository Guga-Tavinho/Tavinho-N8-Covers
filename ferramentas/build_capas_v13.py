"""POC v13: a v10 (estável) + o texto "@tavinho.games" embaixo da capa + 20 jogos por página.

É a "C1" dos testes de isolamento (poc_teste_isolamento), que funcionou no aparelho abrindo pastas, com o texto
aparecendo normalmente. Diferente da v11/v12: SEM a mudança no módulo (esconder a capa com $05) — ela se mostrou
desnecessária (o texto não some) e a v12 (texto + módulo + 20 por página) travava ao abrir qualquer pasta, sem
causa achada (cada parte e cada par funcionam). O módulo é o da v10: os COVERS.BIN da v10 valem.
  texto: wrapper w82fa no redesenho completo ($CB83: JSR $82FA -> JSR w82fa) copia o texto para a linha 23,
         colunas 17-30 do buffer, antes de o OS enviar a tela (12 bytes de código + 14 de texto no SEG_C)
  20 por página: os 13 operandos do navegador (ver build_capas_v12.TROCAS)
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import cpu2file
from build_capas import patch, jsr
import build_capas_v10 as V10

TEXTO, LINHA, COLUNA = '@tavinho.games', 23, 17
POR_PAGINA = 20
TROCAS = [(0xC9A3, 0xA9, 21), (0xC9AB, 0xA9, 21), (0xC9DB, 0xC9, 21), (0xDA0F, 0xA9, 21), (0xDA17, 0xA9, 21),
          (0xDA48, 0xA9, 20), (0xDA9E, 0xC9, 21), (0xDAE5, 0xC9, 22), (0xDAFC, 0xA9, 21), (0xDB55, 0xC9, 21),
          (0xDB62, 0xA9, 21), (0xDB6A, 0xA9, 21), (0xDBA6, 0xE9, 21)]

V10.SEG_C = (V10.SEG_C[0], V10.SEG_C[1], V10.SEG_C[2] + r'''
w82fa:  LDX #%d                 ; redesenho completo do OS: texto fixo na linha %d do buffer (vai junto no envio)
wt_l:   LDA s_txt,X
        STA $%04X,X
        DEX
        BPL wt_l
        JMP GFX_FULL
s_txt:  .text "%s"
''' % (len(TEXTO) - 1, LINHA, 0x6000 + LINHA * 32 + COLUNA, TEXTO))


def pagina(buf, n=POR_PAGINA):
    for a, op, antigo in TROCAS:
        o = cpu2file(a)
        assert buf[o] == op and buf[o + 1] == antigo, 'bytes inesperados em $%04X' % a
        buf[o + 1] = antigo - 21 + n
    return buf


def main(log=print):
    buf, S, modulo = V10.main(log=lambda *a: None)
    patch(buf, 0xCB83, jsr(0x82FA), jsr(S['w82fa']))
    pagina(buf)
    log('OS.BIN v13 SHA1 %s  (módulo SHA1 %s = o da v10)' % (hashlib.sha1(buf).hexdigest(),
                                                             hashlib.sha1(modulo).hexdigest()))
    return buf, S, modulo


if __name__ == '__main__':
    main()
