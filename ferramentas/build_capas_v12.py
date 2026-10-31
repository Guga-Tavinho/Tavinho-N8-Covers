"""POC v12: a v11 (estável) + o navegador com 20 jogos por página (o OS mostra 21).

A lista passa a ocupar as linhas 2-21 da tela: exatamente a altura da capa grande (a linha 22 fica livre).
O OS foi escrito em C (cc65) e o 21 é uma constante espalhada pelo código do navegador; aqui ela é trocada no
lugar (só bytes de operandos, nenhum código novo):
  browser_draw_list ($C987): início da página = sel / 21 * 21 ($C9A3, $C9AB) e o laço das 21 linhas ($C9DB)
  navegação ($D953):  início da página ($DA0F, $DA17); ↑ na 1ª linha vai para a última (20 -> 19, $DA48);
                      ↓ depois da última volta para a 1ª ($DA9E); ← → só trocam de página com mais de uma página
                      (22 itens -> 21, $DAE5); → +21 ($DAFC); ← na 1ª página vai para a última ($DB55, $DB62,
                      $DB6A) e senão -21 ($DBA6)
Ficam como estão os 20/21/22 que não são da página (o atraso da repetição do direcional em $D9CD/$D9FB, as
linhas da tela de cheats, o sistema de arquivos...). O módulo do COVERS.BIN não muda: os COVERS.BIN da v11 valem.
(A tentativa v12b de tirar o "lixo" ao ligar foi abandonada a pedido do usuário: estragou as capas. Ver as notas.)
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import cpu2file
import build_capas_v11 as V11

POR_PAGINA = 20
# (endereço da instrução, opcode, valor antigo, valor novo)
TROCAS = [(0xC9A3, 0xA9, 21, POR_PAGINA), (0xC9AB, 0xA9, 21, POR_PAGINA), (0xC9DB, 0xC9, 21, POR_PAGINA),
          (0xDA0F, 0xA9, 21, POR_PAGINA), (0xDA17, 0xA9, 21, POR_PAGINA), (0xDA48, 0xA9, 20, POR_PAGINA - 1),
          (0xDA9E, 0xC9, 21, POR_PAGINA), (0xDAE5, 0xC9, 22, POR_PAGINA + 1), (0xDAFC, 0xA9, 21, POR_PAGINA),
          (0xDB55, 0xC9, 21, POR_PAGINA), (0xDB62, 0xA9, 21, POR_PAGINA), (0xDB6A, 0xA9, 21, POR_PAGINA),
          (0xDBA6, 0xE9, 21, POR_PAGINA)]


def pagina(buf, n=POR_PAGINA):
    """Troca o tamanho da página do navegador (21 do OS) por n, conferindo cada instrução."""
    for a, op, antigo, novo in TROCAS:
        o = cpu2file(a)
        assert buf[o] == op and buf[o + 1] == antigo, 'bytes inesperados em $%04X: %s' % (a, buf[o:o + 2].hex())
        buf[o + 1] = antigo - 21 + n
    return buf


def main(log=print):
    buf, S, modulo = V11.main(log=lambda *a: None)
    pagina(buf)
    log('OS.BIN v12 SHA1 %s  (%d jogos por página; módulo SHA1 %s, o mesmo da v11)'
        % (hashlib.sha1(buf).hexdigest(), POR_PAGINA, hashlib.sha1(modulo).hexdigest()))
    return buf, S, modulo


if __name__ == '__main__':
    main()
