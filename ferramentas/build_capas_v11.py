"""POC v11: a v10 (estável no aparelho) + o texto "@tavinho.games" fixo no navegador, embaixo da capa.

O texto fica na linha 23 da tela, colunas 17-30: centralizado embaixo da imagem da capa (x 136-247), logo acima da
barra cinza. Como na POC de texto da v3 (seção 20 das notas): o wrapper w82fa do redesenho completo do OS
($CB83: JSR $82FA) copia o texto para o buffer de tela logo antes de o OS enviar a tela inteira para a PPU; popups
e menus restauram o buffer, e a linha 23 não é tocada pela lista. Tile = código ASCII (fonte do OS); a linha 23
(pontos 184-191) fica no banco do grupo 6 da capa, que tem a fonte inteira (as capas usam só $01-$1F e $80-$9F).

Atributos: a linha de atributos 5 (linhas 20-23, colunas 16-31) é da capa. Com a capa à vista os atributos dela
já deixam as linhas 22-23 na paleta 0 (a do texto), mas para ESCONDER a capa (espera, carga, ROM sem capa) o módulo
escrevia $55 (paleta 1, preta) na linha inteira e o texto sumia. Agora, nessa linha, escreve $05: as linhas 20-21
pretas (são da capa), as 22-23 na paleta 0. (+6 bytes no módulo: a impressão digital muda, e o COVERS.BIN precisa
do módulo novo; os registros das capas são os mesmos da v10.)
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import cpu2file
from build_capas import patch, jsr
import build_capas_v10 as V10

TEXTO = '@tavinho.games'
LINHA, COLUNA = 23, 17
assert len(TEXTO) <= 14 and all(32 <= ord(c) < 127 for c in TEXTO)

V10.SEG_C = (V10.SEG_C[0], V10.SEG_C[1], V10.SEG_C[2] + r'''
w82fa:  LDX #%d                 ; redesenho completo do OS: texto fixo na linha %d do buffer (vai junto no envio)
wt_l:   LDA s_txt,X
        STA $%04X,X
        DEX
        BPL wt_l
        JMP GFX_FULL
s_txt:  .text "%s"
''' % (len(TEXTO) - 1, LINHA, 0x6000 + LINHA * 32 + COLUNA, TEXTO))
V10.MOD_SRC = V10.sub(V10.MOD_SRC, '''        BPL ap_w
        LDA #$55
ap_w:   STA $2007''', '''        BPL ap_w
        LDA #$55
        CPX #40                 ; linha de atributos 5 (linhas 20-23): só as 20-21 são da capa
        BCC ap_w
        LDA #$05                ; 22-23 na paleta 0: o texto embaixo da capa não some
ap_w:   STA $2007''')


def main(log=print):
    buf, S, modulo = V10.main(log=lambda *a: None)
    patch(buf, 0xCB83, jsr(0x82FA), jsr(S['w82fa']))
    log('OS.BIN v11 SHA1 %s' % hashlib.sha1(buf).hexdigest())
    for org, end, code in V10.assemble_all()[0]:
        log('  $%04X-$%04X  %3d de %3d bytes (livres %d)' % (org, org + len(code) - 1, len(code), end - org,
                                                           end - org - len(code)))
    log('  espera: byte espq em $%04X = posição %d do OS.BIN; módulo SHA1 %s'
        % (S['espq'], cpu2file(S['espq']), hashlib.sha1(modulo).hexdigest()))
    return buf, S, modulo


if __name__ == '__main__':
    main()
