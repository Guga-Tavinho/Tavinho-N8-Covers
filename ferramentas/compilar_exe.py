"""Compila a ferramenta num .exe (PyInstaller, pasta única: o .exe + _internal) e faz o .zip para compartilhar.

uso: python compilar_exe.py
saída: ../compilado/dist/NES N8 Covers Editor/ (com o LEIA-ME.txt) e ../compilado/NES N8 Covers Editor.zip
Requer: python -m pip install --user pyinstaller
Testes do .exe (sem abrir a janela):
  "NES N8 Covers Editor.exe" --gerar-covers <capas> --roms <roms> -o <saída.bin> ...   (o gerador, direto)
  "NES N8 Covers Editor.exe" --testar-geracao <log.txt> <capas> --roms ... -o ...     (o caminho que a janela usa)
"""
import os, shutil, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(os.path.dirname(AQUI), 'compilado')
NOME = 'NES N8 Covers Editor'


def main():
    os.makedirs(SAIDA, exist_ok=True)
    leia = os.path.join(SAIDA, 'dist', NOME, 'LEIA-ME.txt')
    texto = open(leia, encoding='utf-8').read() if os.path.exists(leia) else None
    sep = ';'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
                    '--name', NOME, '--icon', os.path.join(AQUI, 'icone.ico'),
                    '--add-data', os.path.join(AQUI, 'icone.ico') + sep + '.',          # (o ícone da janela)
                    '--paths', os.path.join(AQUI, 'palette_lab'),
                    '--add-data', os.path.join(AQUI, 'firmwares', 'OS_v15.BIN') + sep + 'firmwares',
                    '--add-data', os.path.join(AQUI, 'firmwares', 'MOD_v10.BIN') + sep + 'firmwares',
                    '--distpath', os.path.join(SAIDA, 'dist'), '--workpath', os.path.join(SAIDA, 'build'),
                    '--specpath', SAIDA, os.path.join(AQUI, 'gerador_firmware_capas.py')], check=True, cwd=AQUI)
    if texto: open(leia, 'w', encoding='utf-8').write(texto)            # (o --clean apaga a pasta)
    zipf = os.path.join(SAIDA, NOME)
    if os.path.exists(zipf + '.zip'): os.remove(zipf + '.zip')
    shutil.make_archive(zipf, 'zip', os.path.join(SAIDA, 'dist'), NOME)
    print('pronto:', zipf + '.zip')


if __name__ == '__main__':
    main()
