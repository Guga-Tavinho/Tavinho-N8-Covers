"""POC v15: a v14 + correção do travamento ao carregar capas depois de ligar o console.

O módulo das capas fica na WRAM do cartucho ($6400-$67FF), que tem BATERIA: ele sobrevive ao desligar. Em TODA
inicialização o OS (os_init, $BBB1: flash_cmd_stub_save_ram $84C0) usa $6400-$66FF como rascunho e estraga os
primeiros 768 bytes do módulo, mas não toca no fim ($6700-$67FF), onde fica a marca de 4 bytes que o lmod conferia
($67FC). Com a marca intacta o lmod achava o módulo inteiro, não relia do cartão e rodava código estragado: travava
na 1ª capa. (Depois de abrir um jogo, o jogo apagava a marca também e o boot seguinte relia: daí o "alterna".)
Correção sem mudar o módulo nem gastar espaço: o lmod passa a conferir 4 bytes de DENTRO da área que o OS estraga
($66FC-$66FF = módulo[$2FC:$300]); o lm_mg guarda esses 4 bytes do módulo certo. Os COVERS.BIN da v10/v13 valem.
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import cpu2file
import build_capas_v14 as V14

CONFERE = 0x2FC                                   # módulo[$2FC:$300] = $66FC-$66FF (dentro de $6400-$66FF)


def conferencia(buf, S, modulo):
    o = cpu2file(S['lm_k'])
    assert bytes(buf[o:o + 3]) == bytes([0xBD, 0xFC, 0x67]), 'lm_k: %s' % buf[o:o + 3].hex()   # LDA MOD2+$3FC,X
    buf[o + 1:o + 3] = bytes([(0x6400 + CONFERE) & 255, (0x6400 + CONFERE) >> 8])               # LDA MOD2+$2FC,X
    m = cpu2file(S['lm_mg'])
    buf[m:m + 4] = modulo[CONFERE:CONFERE + 4]
    return buf


def main(log=print):
    buf, S, modulo = V14.main(log=lambda *a: None)
    conferencia(buf, S, modulo)
    log('OS.BIN v15 SHA1 %s  (módulo SHA1 %s = o da v10; confere $%04X-$%04X = %s)'
        % (hashlib.sha1(buf).hexdigest(), hashlib.sha1(modulo).hexdigest(), 0x6400 + CONFERE,
           0x6403 + CONFERE, modulo[CONFERE:CONFERE + 4].hex()))
    return buf, S, modulo


if __name__ == '__main__':
    main()
