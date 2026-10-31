"""Testes de isolamento 2 (o travamento ao abrir pastas da v12 = v10 + T + M + P).

  T = o gancho do texto "@tavinho.games" (w82fa no SEG_C + JSR em $CB83)
  M = a mudança do módulo (esconder a capa com $05 na linha de atributos 5)
  P = 20 jogos por página
  C1 = v10 + T + P (módulo da v10: usa o COVERS.BIN da v10)
  C2 = v10 + M + P (sem o texto: usa o COVERS.BIN da v11/v12)
uso: python build_teste_isolamento2.py C1|C2 <saída_EDFC>
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_capas import patch, jsr
import build_capas_v10 as V10

TEXTO, LINHA, COLUNA = '@tavinho.games', 23, 17


def com_texto():
    V10.SEG_C = (V10.SEG_C[0], V10.SEG_C[1], V10.SEG_C[2] + r'''
w82fa:  LDX #%d                 ; redesenho completo do OS: texto fixo na linha %d do buffer (vai junto no envio)
wt_l:   LDA s_txt,X
        STA $%04X,X
        DEX
        BPL wt_l
        JMP GFX_FULL
s_txt:  .text "%s"
''' % (len(TEXTO) - 1, LINHA, 0x6000 + LINHA * 32 + COLUNA, TEXTO))


def com_modulo_novo():
    V10.MOD_SRC = V10.sub(V10.MOD_SRC, '''        BPL ap_w
        LDA #$55
ap_w:   STA $2007''', '''        BPL ap_w
        LDA #$55
        CPX #40                 ; linha de atributos 5 (linhas 20-23): só as 20-21 são da capa
        BCC ap_w
        LDA #$05                ; 22-23 na paleta 0: o texto embaixo da capa não some
ap_w:   STA $2007''')


if __name__ == '__main__':
    qual, saida = sys.argv[1], sys.argv[2]
    if qual == 'C1': com_texto()
    if qual == 'C2': com_modulo_novo()
    buf, S, modulo = V10.main(log=lambda *a: None)
    if qual == 'C1': patch(buf, 0xCB83, jsr(0x82FA), jsr(S['w82fa']))
    from build_poc import cpu2file                              # os 13 bytes da v12 (sem importar a v12/v11,
    for a, op, antigo in ((0xC9A3, 0xA9, 21), (0xC9AB, 0xA9, 21), (0xC9DB, 0xC9, 21), (0xDA0F, 0xA9, 21),  # que mexem
                          (0xDA17, 0xA9, 21), (0xDA48, 0xA9, 20), (0xDA9E, 0xC9, 21), (0xDAE5, 0xC9, 22),  # na v10)
                          (0xDAFC, 0xA9, 21), (0xDB55, 0xC9, 21), (0xDB62, 0xA9, 21), (0xDB6A, 0xA9, 21),
                          (0xDBA6, 0xE9, 21)):
        o = cpu2file(a)
        assert buf[o] == op and buf[o + 1] == antigo
        buf[o + 1] = antigo - 1
    os.makedirs(saida, exist_ok=True)
    open(os.path.join(saida, 'OS.BIN'), 'wb').write(buf)
    print(qual, 'OS.BIN', hashlib.sha1(buf).hexdigest(), 'módulo', hashlib.sha1(modulo).hexdigest())
