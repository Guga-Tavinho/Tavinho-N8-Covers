"""POC v14: a v13 (texto + 20 por página) + ← → levam o cursor para o TOPO da página nova.

O OS mantém a linha do cursor ao trocar de página (sel = início da página nova + linha). Agora a linha vira 0,
trocando bytes no lugar (sem código novo):
  $DB17 (→)                  LDY #3 / JSR $F145 (a linha)  ->  LDA #0 / TAX / NOP / NOP (linha 0)
  $DB73 (← na 1ª página: vai para a última)        idem
  $DBA2 (← nas outras: sel - 20)  LDA sel / SEC  ->  LDY #4 / LDA (c_sp),Y (o início da página): início - 20
        (o SEC sai: só se chega aqui pelo BCS de $DB57, com o carry já 1; o byte alto não muda: a pasta tem no
        máximo 254 itens, e o início - 20 nunca fica negativo, porque aqui a página não é a 1ª)
O módulo não muda (o da v10): os COVERS.BIN da v10 valem.
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import cpu2file
import build_capas_v13 as V13

TOPO = [(0xDB17, bytes([0xA0, 0x03, 0x20, 0x45, 0xF1]), bytes([0xA9, 0x00, 0xAA, 0xEA, 0xEA])),
        (0xDB73, bytes([0xA0, 0x03, 0x20, 0x45, 0xF1]), bytes([0xA9, 0x00, 0xAA, 0xEA, 0xEA])),
        (0xDBA2, bytes([0xAD, 0x59, 0x82, 0x38]), bytes([0xA0, 0x04, 0xB1, 0x28]))]


def topo(buf):
    for a, antigo, novo in TOPO:
        o = cpu2file(a)
        assert bytes(buf[o:o + len(antigo)]) == antigo, 'bytes inesperados em $%04X' % a
        buf[o:o + len(novo)] = novo
    return buf


def main(log=print):
    buf, S, modulo = V13.main(log=lambda *a: None)
    topo(buf)
    log('OS.BIN v14 SHA1 %s  (módulo SHA1 %s = o da v10)' % (hashlib.sha1(buf).hexdigest(),
                                                             hashlib.sha1(modulo).hexdigest()))
    return buf, S, modulo


if __name__ == '__main__':
    main()
