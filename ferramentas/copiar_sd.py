"""Copia OS.BIN e COVERS.BIN para /EDFC/ no cartão SD com o COVERS.BIN contínuo (não fragmentado).

A firmware lê o COVERS.BIN como um bloco contínuo de setores (primeiro setor + deslocamento), sem seguir a cadeia
de clusters do FAT. Se o arquivo ficar fragmentado no cartão, as capas depois da quebra não aparecem (a
verificação de cada capa falha e ela fica sem capa). Isso acontece, por exemplo, quando um COVERS.BIN é gravado
por cima de outro.

Aqui o arquivo novo é gravado com outro nome, reservando o tamanho inteiro de uma vez (o Windows tenta alocar
um bloco contínuo), conferido com `fsutil file queryextents` e só então trocado pelo antigo.

uso: python copiar_sd.py <pasta_com_EDFC> <unidade>      ex.: python copiar_sd.py ..\\firmware_gerada F:
"""
import os, re, shutil, subprocess, sys


def trechos(caminho):
    """Quantos pedaços (extents) o arquivo tem no cartão: 1 = contínuo. None se não deu para saber."""
    try:
        r = subprocess.run(['fsutil', 'file', 'queryextents', caminho], capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except OSError:
        return None
    n = len(re.findall(r'VCN:\s*0x[0-9a-fA-F]+', r.stdout.decode('latin-1')))
    return n or None


def gravar_continuo(dados, destino, tentativas=4):
    """Grava `dados` em `destino` (contínuo). Devolve o número de pedaços (1 = ok; None = não verificado)."""
    pasta = os.path.dirname(destino)
    if os.path.exists(destino): os.remove(destino)   # o antigo sai antes: o espaço dele volta a ficar livre
    temps = []
    try:
        for k in range(tentativas):
            tmp = os.path.join(pasta, 'COVERS%d.TMP' % k)
            with open(tmp, 'wb') as f:
                f.truncate(len(dados))            # reserva o tamanho todo de uma vez
                f.seek(0)
                f.write(dados)
            n = trechos(tmp)
            if n is None or n == 1 or k == tentativas - 1:      # contínuo (ou última tentativa): vira o arquivo
                os.replace(tmp, destino)
                return n
            temps.append(tmp)                     # fragmentado: fica ocupando o buraco e tenta de novo
        return None
    finally:
        for t in temps:
            if os.path.exists(t): os.remove(t)


def pasta_edfc(caminho):
    """Aceita a raiz do cartão (F:\\) ou a própria pasta EDFC (F:\\EDFC); devolve a pasta EDFC."""
    caminho = os.path.normpath(caminho)
    if os.path.basename(caminho).upper() == 'EDFC': return caminho
    if len(caminho) == 2 and caminho[1] == ':': caminho += os.sep
    return os.path.join(caminho, 'EDFC')


def copiar(pasta_firmware, cartao):
    """Copia EDFC/OS.BIN e EDFC/COVERS.BIN para a pasta EDFC do cartão (o COVERS.BIN antigo é apagado antes
    e o novo é gravado contínuo). Devolve (ok, mensagem)."""
    edfc_src = os.path.join(pasta_firmware, 'EDFC')
    edfc_dst = pasta_edfc(cartao)
    if not os.path.isdir(edfc_dst):
        return False, 'Não achei a pasta EDFC em %s (é o cartão SD do EverDrive?)' % cartao
    cov = open(os.path.join(edfc_src, 'COVERS.BIN'), 'rb').read()
    shutil.copyfile(os.path.join(edfc_src, 'OS.BIN'), os.path.join(edfc_dst, 'OS.BIN'))
    n = gravar_continuo(cov, os.path.join(edfc_dst, 'COVERS.BIN'))
    if open(os.path.join(edfc_dst, 'COVERS.BIN'), 'rb').read() != cov:
        return False, 'O COVERS.BIN copiado não confere com o original.'
    if n == 1:
        return True, 'OS.BIN e COVERS.BIN copiados para %s. COVERS.BIN contínuo no cartão (ok).' % edfc_dst
    if n is None:
        return True, 'Copiado para %s (não consegui conferir se o COVERS.BIN ficou contínuo).' % edfc_dst
    return False, ('Copiado, mas o COVERS.BIN ficou em %d pedaços no cartão: as capas depois da quebra não vão '
                   'aparecer. Libere espaço no cartão (ou copie tudo para outro cartão/formate) e copie de novo.' % n)


if __name__ == '__main__':
    ok, msg = copiar(sys.argv[1], sys.argv[2])
    print(msg)
    sys.exit(0 if ok else 1)
