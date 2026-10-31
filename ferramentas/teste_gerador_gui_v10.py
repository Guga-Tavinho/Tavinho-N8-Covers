"""Teste automático do modo CAPA GRANDE (v10) do gerador_firmware_capas.py (abre a janela e gera de verdade).

Com as 5 capas e as ROMs da POC v10 (nitidez 180, flicker em SMB3, Mega Man 2 e Castlevania) e espera de 0,5 s,
OS.BIN e COVERS.BIN gerados têm que ser idênticos aos da poc_capa_grande_v10 (testada no aparelho).
Depois: espera de 1,2 s muda só o byte espq; flicker por capa salvo no capas_config.json.
uso: python teste_gerador_gui_v10.py <pasta_de_saida_temporaria>
"""
import hashlib, json, os, shutil, sys, time
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gerador_firmware_capas as g
import build_poc_capa_grande_v10 as P

SHA_OS = 'caa12ed797d374341a40a76a7d2124ee3ce51e8a'             # v15 (estável)
SHA_COV = '0e495260ce6784e882e6750e997d572ac052eb38'


def main(saida):
    shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
    msgs, erros = [], []
    messagebox.showinfo = lambda t, m: msgs.append(('ok', m))
    messagebox.showerror = lambda t, m: msgs.append(('erro', m))
    messagebox.askyesno = lambda t, m: True
    messagebox.showwarning = lambda t, m: msgs.append(('aviso', m))
    capas, roms = os.path.join(saida, 'capas'), os.path.join(saida, 'roms')
    os.makedirs(capas); os.makedirs(roms)
    for r in P.roms_teste(): open(os.path.join(roms, r), 'wb').close()
    for c in ('Super Mario Bros. 3 (USA).png', 'Mega Man 2 (USA).png', 'Castlevania (USA).png', 'Contra (USA).png',
              'Legend of Zelda, The (USA).png'):
        shutil.copy(os.path.join(P.CAPAS, c), capas)
    json.dump(dict(nitidez_padrao=True, nitidez_forca_padrao=180), open(os.path.join(capas, 'capas_config.json'), 'w'))
    g.ARQ_PREFS = os.path.join(saida, 'prefs_teste.json')
    json.dump(dict(capas=capas, saida=os.path.join(saida, 'fw'), roms=[roms]), open(g.ARQ_PREFS, 'w'))
    root = tk.Tk()
    root.report_callback_exception = lambda *a: erros.append(a)
    app = g.App(root)
    root.title('TESTE AUTOMÁTICO v10 — não fechar (~5 min)')
    ok = True

    def check(c, m):
        nonlocal ok
        print(('  OK   ' if c else '  FALHA') + ' ' + m, flush=True); ok &= bool(c)

    def esperar(cond, seg):
        t = time.time()
        while not cond() and time.time() - t < seg:
            root.update(); time.sleep(0.02)
        return cond()

    check(not hasattr(app, 'formato') and not hasattr(app, 'barra'), 'só a capa grande (sem a v3)')
    check(app.espera.get() == '0.5', 'espera padrão 0,5 s')
    check(esperar(lambda: app.prev_grande(False) is not None, 60), 'prévia sem flicker de %s' % app.capa_teste.get())
    root.update()
    check(app.atual is not None and 'ΔE' in app.info.cget('text'), 'info: ' + app.info.cget('text'))
    # flicker por capa: liga em SMB3, MM2 e Castlevania (como a POC)
    for c in ('Super Mario Bros. 3 (USA).png', 'Mega Man 2 (USA).png', 'Castlevania (USA).png'):
        app.lista.selection_set(c); root.update(); esperar(lambda: app.capa_teste.get() == c and app.g_src.endswith(c), 5)
        app.flicker.set(True); app.trocar_flicker()
    cfg = json.load(open(os.path.join(capas, 'capas_config.json'), encoding='utf-8'))
    check(sorted(cfg.get('flicker_grande', {})) == sorted(P.FLICKER), 'flicker_grande salvo: %s' % cfg.get('flicker_grande'))
    check('· flicker' in app.lista.item('Castlevania (USA).png', 'text'), 'lista marca as capas com flicker')
    check(esperar(lambda: app.prev_grande(True) is not None, 400), 'prévia com flicker (Castlevania) calculada')
    root.update()
    a, b = app.prev_grande(True)['A'], app.prev_grande(True)['B']
    check(app.atual['A'] is not app.atual['B'] and (a != b).any(), 'com flicker: quadros A e B diferentes (alternam)')
    check('GERAR FIRMWARE (5 capas p/ %d ROMs · 3 com flicker · 2 sem)' % len(P.roms_teste())
          == app.b_gerar.cget('text'), 'botão: ' + app.b_gerar.cget('text'))
    # liga e desliga numa capa: volta ao padrão (sem entrada própria)
    app.lista.selection_set('Contra (USA).png'); esperar(lambda: app.g_src.endswith('Contra (USA).png'), 5)
    app.flicker.set(True); app.trocar_flicker(); app.flicker.set(False); app.trocar_flicker()
    cfg = json.load(open(os.path.join(capas, 'capas_config.json'), encoding='utf-8'))
    check('Contra (USA).png' not in cfg['flicker_grande'], 'Contra liga/desliga: volta a seguir o padrão')

    def gerar(espera):
        msgs.clear(); app.espera.set(espera); app.trocar_espera(); app.gerar()
        check(esperar(lambda: not app.gerando, 900) and msgs and msgs[-1][0] == 'ok', 'gerou (espera %s s): %s'
              % (espera, (msgs[-1][1].splitlines()[0] if msgs else 'sem mensagem')))
        e = os.path.join(saida, 'fw', 'EDFC')
        return open(os.path.join(e, 'OS.BIN'), 'rb').read(), open(os.path.join(e, 'COVERS.BIN'), 'rb').read()
    os_, cov = gerar('0.5')
    check(hashlib.sha1(os_).hexdigest() == SHA_OS, 'OS.BIN = o da v15 (testada no aparelho)')
    check(hashlib.sha1(cov).hexdigest() == SHA_COV, 'COVERS.BIN = o da POC v10 (a v15 usa o mesmo)')
    leia = open(os.path.join(saida, 'fw', 'LEIA-ME.txt'), encoding='utf-8').read()
    check('espera de 0.5 s' in leia and '3 capa(s) com flicker' in leia, 'LEIA-ME com o formato e a espera')
    check(len(os.listdir(os.path.join(saida, 'fw', 'previews'))) == len(P.roms_teste()), 'prévias geradas')
    os2, cov2 = gerar('1.2')
    dif = [i for i in range(len(os_)) if os_[i] != os2[i]]
    check(dif == [g.ESPQ] and os2[g.ESPQ] == 73 and cov2 == cov, 'espera 1,2 s: só o byte espq muda (73 = 72 quadros + 1)')
    prefs = json.load(open(g.ARQ_PREFS, encoding='utf-8'))
    check(prefs.get('espera') == 1.2, 'preferências: espera lembrada')

    print('\n== conta-gotas', flush=True)
    import capa_grande_cores as CC, sim_navegador_grande as N
    from types import SimpleNamespace
    from gerar_covers import name_crc

    def clique(x, y):
        z = app.zoom.get(); w = app.telas['nes']
        return SimpleNamespace(x=(w.winfo_width() - 112 * z) // 2 + x * z + z // 2,
                               y=(w.winfo_height() - 160 * z) // 2 + y * z + z // 2)

    def ponto(est, pals, quadro, tipo):
        return next((x, y) for y in range(160) for x in range(112)
                    if isinstance(CC.espaco(est, pals, quadro, x, y), tuple) and CC.espaco(est, pals, quadro, x, y)[0] == tipo)
    app.lista.selection_set('Contra (USA).png'); esperar(lambda: app.prev_grande(False) is not None, 60); root.update()
    r = app.prev_grande(False); est = r['est']
    x, y = ponto(est, r['orig'], 'A', 'bg')
    alvo = CC.espaco(est, r['orig'], 'A', x, y)
    app.sobre_capa(clique(x, y))
    check('clique para trocar' in app.dica.cget('text'), 'mouse sobre a capa: ' + app.dica.cget('text'))
    xf, yf = next((x_, y_) for y_ in range(160) for x_ in range(112) if isinstance(CC.espaco(est, r['orig'], 'A', x_, y_), str))
    app.sobre_capa(clique(xf, yf))
    check('não dá para trocar' in app.dica.cget('text'), 'cor fixa: ' + app.dica.cget('text'))
    app.conta_gotas(clique(x, y))
    check(app.picker is not None and app.picker.winfo_exists(), 'conta-gotas abre o seletor de cores')
    nova = 0x16 if CC.cor(r['orig'], alvo) != 0x16 else 0x2A
    app.trocar_cor([alvo], nova); root.update()
    arq = CC.arquivo(capas, os.path.join(capas, 'Contra (USA).png'), 180, False)
    check(os.path.exists(arq) and app.picker is None, 'edição salva em ' + os.path.basename(arq))
    P_ = app.imagens(app.chave_atual())[2]
    check(tuple(P_[y, x]) == tuple(N.NES[nova]) and 'cores editadas' in app.info.cget('text'),
          'a prévia mostra a cor nova ($%02X) no ponto' % nova)
    check(app.marcas_capa['Contra (USA).png'][1], 'lista: ícone de cores editadas na capa')
    app.desfazer_cor(); root.update()
    check(not os.path.exists(arq) and 'cores editadas' not in app.info.cget('text'), 'Desfazer: volta ao original')
    app.trocar_cor([('c3',)], 0x21); app.restaurar_cores(); root.update()
    check(not os.path.exists(arq), 'Restaurar originais')
    app.trocar_cor([alvo], nova)
    # Castlevania com flicker: uma cor de sprite só do quadro B
    app.lista.selection_set('Castlevania (USA).png'); esperar(lambda: app.g_src.endswith('Castlevania (USA).png'), 5)
    esperar(lambda: app.prev_grande(True) is not None, 400); root.update()
    r2 = app.prev_grande(True)
    xb, yb = ponto(r2['est'], r2['orig'], 'B', 'sp')
    alvo_b = CC.espaco(r2['est'], r2['orig'], 'B', xb, yb)
    nova_b = 0x2C if CC.cor(r2['orig'], alvo_b) != 0x2C else 0x1C
    app.trocar_cor([alvo_b], nova_b); root.update()
    check(os.path.exists(CC.arquivo(capas, os.path.join(capas, 'Castlevania (USA).png'), 180, True)),
          'edição do quadro B (flicker) salva: %s' % CC.nome(alvo_b))
    os3, cov3 = gerar('0.5')
    leia_log = app.log.get('1.0', 'end')
    check('cores editadas: Contra (USA).png' in leia_log and 'cores editadas: Castlevania (USA).png' in leia_log,
          'log da geração cita as capas com cores editadas')

    def registro(c, rom):
        crc = name_crc(rom)
        sec = c[(crc & 0xFF) * 512:(crc & 0xFF) * 512 + 512]
        for k in range(0, 510, 5):
            if sec[k:k + 3] == bytes([(crc >> 8) & 255, (crc >> 16) & 255, (crc >> 24) & 255]):
                idx = sec[k + 3] | sec[k + 4] << 8
                return (512 + 64 * idx) * 512
    dif = [i for i in range(len(cov)) if cov[i] != cov3[i]]
    esperados = []
    for rom in P.roms_teste():
        o = registro(cov3, rom)
        if rom.startswith('Contra'): esperados.append(o + 3 + alvo[1] * 3 + alvo[2])
        if rom.startswith('Castlevania'): esperados.append(o + 15 * 512 + 304 + alvo_b[2] * 4 + 1 + alvo_b[3])
    check(sorted(dif) == sorted(esperados) and all(cov3[i] in (nova, nova_b) for i in dif),
          'COVERS.BIN: só os bytes das cores editadas mudaram (%d bytes: Contra + as 2 ROMs de Castlevania)' % len(dif))

    print('\n== nível do flicker (λ)', flush=True)
    app.lista.selection_set('Mega Man 2 (USA).png'); esperar(lambda: app.g_src.endswith('Mega Man 2 (USA).png'), 5)
    root.update()
    check(app.flicker.get() and 'disabled' not in app.barra_lam.state() and 'λ 0.05' in app.info.cget('text'),
          'capa com flicker: barra de nível ligada, no padrão 0,05')
    app.escolher_lam(4); root.update()
    cfg = json.load(open(os.path.join(capas, 'capas_config.json'), encoding='utf-8'))
    check(cfg.get('flicker_grande_lambda') == {'Mega Man 2 (USA).png': 0.15}, 'nível salvo por capa: %s'
          % cfg.get('flicker_grande_lambda'))
    check(esperar(lambda: app.prev_grande(True) is not None, 900), 'prévia do nível 5 (λ 0,15) calculada')
    root.update()
    r15 = app.prev_grande(True)
    app.escolher_lam(2); esperar(lambda: app.prev_grande(True) is not None, 900); r05 = app.prev_grande(True)
    check(r15['tremido'] < r05['tremido'], 'λ 0,15 treme menos que 0,05 (%.1f < %.1f)' % (r15['tremido'], r05['tremido']))
    app.passo_lam(1); app.passo_lam(1); root.update()
    check(app.i_lam == 4 and 'λ 0.15' in app.lista.item('Mega Man 2 (USA).png', 'text'),
          'botão > anda o nível; a lista mostra o λ da capa')
    os4, cov4 = gerar('0.5')
    check('flicker: Mega Man 2 (USA).png (λ 0.15)' in app.log.get('1.0', 'end'), 'a geração usa o λ da capa')
    o_mm = registro(cov4, 'Mega Man 2 (U).nes')
    outros = [rom for rom in P.roms_teste() if not rom.startswith('Mega Man 2')]
    check(cov4[o_mm:o_mm + 64 * 512] != cov3[o_mm:o_mm + 64 * 512] and
          all(cov4[registro(cov4, r_):registro(cov4, r_) + 64 * 512] == cov3[registro(cov3, r_):registro(cov3, r_) + 64 * 512]
              for r_ in outros), 'COVERS.BIN: só o registro do Mega Man 2 mudou')
    app.usar_padrao(); root.update()
    cfg = json.load(open(os.path.join(capas, 'capas_config.json'), encoding='utf-8'))
    check(not cfg.get('flicker_grande_lambda') and app.i_lam == 2, '"Usar o padrão nesta capa" volta ao λ 0,05')

    print('\n== pontilhado', flush=True)
    zelda = 'Legend of Zelda, The (USA).png'
    app.lista.selection_set(zelda); esperar(lambda: app.g_src.endswith(zelda), 5)
    esperar(lambda: app.prev_grande(False) is not None, 60); root.update()
    sem_p = app.prev_grande(False)
    app.pontilhado.set(True); app.trocar_pontilhado(); root.update()
    cfg = json.load(open(os.path.join(capas, 'capas_config.json'), encoding='utf-8'))
    check(cfg.get('pontilhado') == {zelda: True}, 'pontilhado salvo por capa')
    check(esperar(lambda: app.prev_grande(False) is not None, 120), 'prévia com pontilhado calculada')
    root.update()
    com_p = app.prev_grande(False)
    check(com_p['est']['pontilhado'] and (com_p['est']['ind'] != sem_p['est']['ind']).any() and
          'pontilhado' in app.info.cget('text') and 'pontilhado' in app.lista.item(zelda, 'text'),
          'fundo pontilhado (índices diferentes), info e lista marcam')
    os5, cov5 = gerar('0.5')
    check('pontilhado: ' + zelda in app.log.get('1.0', 'end'), 'a geração usa o pontilhado da capa')
    zs = [rom for rom in P.roms_teste() if rom.startswith('Legend of Zelda')]
    # o Mega Man 2 fica de fora: "Usar o padrão nesta capa" tirou o ajuste dele inteiro (o padrão é sem flicker)
    outros = [rom for rom in P.roms_teste() if rom not in zs and not rom.startswith('Mega Man 2')]
    reg = lambda c, rom: c[registro(c, rom):registro(c, rom) + 64 * 512]
    # referência: a geração de antes do λ (cov3)
    check(all(reg(cov5, r_) != reg(cov3, r_) for r_ in zs) and all(reg(cov5, r_) == reg(cov3, r_) for r_ in outros),
          'COVERS.BIN: só os registros do Zelda mudaram (%d ROMs)' % len(zs))
    app.pontilhado.set(False); app.trocar_pontilhado(); root.update()
    cfg = json.load(open(os.path.join(capas, 'capas_config.json'), encoding='utf-8'))
    check(not cfg.get('pontilhado'), 'desligar o pontilhado volta ao padrão')

    print('\n== só acrescentar capas novas a um COVERS.BIN existente', flush=True)
    anterior = os.path.join(saida, 'COVERS_do_cartao.BIN')
    shutil.copyfile(os.path.join(saida, 'fw', 'EDFC', 'COVERS.BIN'), anterior)     # o cov5 (com pontilhado no Zelda)
    nova = 'Mega Man 2 (Europe).nes'
    open(os.path.join(roms, nova), 'wb').close()                                   # uma ROM nova no "cartão"
    app.acrescentar.set(True); app.base.set(anterior); app.mostrar_base()
    check('11 capa(s) nele' in app.lbl_base.cget('text'), 'mostra o COVERS.BIN escolhido: ' + app.lbl_base.cget('text'))
    os6, cov6 = gerar('0.5')
    n5 = (len(cov5) // 512 - 512) // 64
    check(cov6[512 * 512:] [:n5 * 64 * 512] == cov5[512 * 512:] and (len(cov6) // 512 - 512) // 64 == n5 + 1,
          'as %d capas anteriores ficaram byte a byte iguais; 1 nova no fim' % n5)
    check(registro(cov6, nova) is not None and 'acrescentada' in msgs[-1][1],
          'a ROM nova ganhou capa: %s' % msgs[-1][1].splitlines()[0])
    check(open(os.path.join(saida, 'fw', 'COVERS_anterior.BIN'), 'rb').read() == cov5, 'cópia do COVERS.BIN de antes guardada')
    msgs.clear(); app.base.set(os.path.join(saida, 'fw', 'EDFC', 'COVERS.BIN')); app.gerar(); root.update()
    check(msgs and msgs[-1][0] == 'ok' and 'nada' in msgs[-1][1] and not app.gerando,
          'sem ROMs novas: avisa que não há nada para acrescentar')
    app.acrescentar.set(False); app.mostrar_base()
    check(not erros, 'sem exceções na janela%s' % ('' if not erros else ': %r' % (erros[:2],)))
    app.fechar()
    print('\nTUDO OK' if ok else '\nHOUVE FALHAS')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get('TEMP', '.'), 'teste_gui_v10')) else 1)
