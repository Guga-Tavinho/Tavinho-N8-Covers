# Guia para desenvolvedores

Este repositório tem o código-fonte completo do **NES N8 Everdrive Covers editor**: a ferramenta (Python), os
builders da firmware (patches no `OS.BIN` do EverDrive N8 clone), o conversor de imagens e os testes no PC.

📄 **Leia primeiro:** [`docs/AUDITORIA-DESENVOLVEDOR.pdf`](docs/AUDITORIA-DESENVOLVEDOR.pdf) (ou a versão
[`.md`](docs/AUDITORIA-DESENVOLVEDOR.md)). Ela tem a arquitetura, o mapa de memória, os endereços do OS, todos os
patches da v15, o formato do `COVERS.BIN`, os algoritmos, os testes, os bugs e as lições. O diário da
investigação, versão por versão, está em [`NOTAS-TECNICAS-FIRMWARE.md`](NOTAS-TECNICAS-FIRMWARE.md).

## Estrutura

```
README.md                      para o usuário final
DESENVOLVEDORES.md             este guia
NOTAS-TECNICAS-FIRMWARE.md     diário técnico (seções 0-39)
docs/
  AUDITORIA-DESENVOLVEDOR.pdf  auditoria técnica (gerada por gerar_pdf_auditoria.py)
  AUDITORIA-DESENVOLVEDOR.md   o texto da auditoria
  gerar_pdf_auditoria.py       md -> PDF (reportlab), com a tabela de símbolos e as notas
  simbolos_v15.json            tabela de símbolos da v15 (242), usada se o OS original não estiver presente
  ferramenta.png               captura da janela
ferramentas/
  gerador_firmware_capas.py    a ferramenta (janela tkinter)
  gerar_covers_v10.py          gera o COVERS.BIN (linha de comando; a ferramenta usa este)
  conv_capa_grande.py          conversor do fundo (paletas por bloco, pontilhado, cor 3)
  conv_sprites_grande.py       sprites por cima da capa + flicker
  capa_grande_cores.py         edição de cores (conta-gotas), prévia, simulação de TV
  associar_roms.py             associação ROM <-> imagem pelo nome
  copiar_sd.py                 cópia contínua para o cartão (confere com fsutil)
  compilar_exe.py              o .exe (PyInstaller)
  build_poc.py                 base de todos os builders (lê o OS original, cpu2file, paleta NES)
  build_capas*.py              firmware v1..v15 (cada uma importa a anterior)
  build_poc_*.py               montam pastas EDFC de teste (POCs)
  asm6502.py dis6502.py        montador e disassembler 6502
  emu6502.py ciclos6502.py     emulador 6502 + ciclos
  ppu_tempo.py                 modelo de tempo da PPU para os testes
  teste_*.py                   testes (ver a auditoria, seção 10)
  sim_*.py                     simulações/comparações de conversão
  firmwares/OS_v15.BIN         a firmware v15 pronta (a que a ferramenta usa)
  firmwares/MOD_v10.BIN        o módulo de 1 KB (vai dentro do COVERS.BIN)
  palette_lab/                 laboratório de paletas (capa pequena v1-v3) + nes_core
  ghidra_scripts/              DumpNES.java + nomes das funções (Ghidra headless)
analise_base/mapa_funcoes.txt  funções do OS v1.26 -> build do clone
firmware_base/EDFC/            coloque aqui o SEU OS.BIN original (não incluído)
imagens/Named_Boxarts/         capas para os testes (não incluídas)
```

## Começar

```
pip install -r requirements.txt
python ferramentas/gerador_firmware_capas.py
```

A ferramenta só precisa de `ferramentas/firmwares/OS_v15.BIN` e `MOD_v10.BIN` (incluídos).

## Reconstruir a firmware a partir do OS original

O `OS.BIN` original do cartucho é de terceiros e **não está no repositório**. Para refazer a firmware (ou criar
uma v16):

1. Copie o `OS.BIN` original do seu clone para `firmware_base/EDFC/OS.BIN`. O SHA-1 tem que ser
   `dbea89d33eacd7ae72ee24d2652727b0cb5740ae` (o `build_poc.py` confere).
2. `python ferramentas/build_capas_v15.py` mostra o SHA-1 da v15 montada: `caa12ed797d374341a40a76a7d2124ee3ce51e8a`
   (= `ferramentas/firmwares/OS_v15.BIN`).
3. Uma versão nova: crie `build_capas_v16.py` importando a v15 e aplicando só a diferença (o padrão de todo o
   projeto), e um `build_poc_capa_grande_v16.py` para montar a pasta de teste.

Espaço livre: o residente está praticamente esgotado (veja a auditoria, seção 5.2); o módulo tem 37 bytes.

## Testes

Rodar dentro de `ferramentas/`. Pré-requisitos dos testes de capa:

- o OS original em `firmware_base/EDFC/OS.BIN` (passo acima);
- as capas em `imagens/Named_Boxarts/` (conjunto *Named_Boxarts* do
  [libretro-thumbnails](https://github.com/libretro-thumbnails/Nintendo_-_Nintendo_Entertainment_System)):
  `Super Mario Bros. 3 (USA).png`, `Mega Man 2 (USA).png`, `Castlevania (USA).png`, `Contra (USA).png`,
  `Legend of Zelda, The (USA).png`;
- as POCs tiram os nomes das ROMs de `firmware_gerada/previews/*.png` (a ferramenta grava as prévias lá ao gerar).
  Sem uma geração, basta criar arquivos vazios com os nomes, ex.: `Super Mario Bros 3 (U) (PRG 1).png`,
  `Mega Man 2 (U).png`, `Castlevania (U) (PRG 0).png`, `Contra (U).png`, `Legend of Zelda, The (U) (PRG 0).png`;
- `teste_ligar_v15.py` lê `firmware_gerada/EDFC/COVERS.BIN` com as ROMs `Contra (U).nes`, `Mega Man 2 (U).nes` e
  `Super Mario Bros 3 (U) (PRG 0).nes`: gere com
  `python gerar_covers_v10.py ../imagens/Named_Boxarts --roms <pasta com essas ROMs> -o ../firmware_gerada/EDFC/COVERS.BIN`
  (para o teste, as ROMs podem ser arquivos quaisquer com esses nomes).

```
python teste_ligar_v15.py          # boot com a WRAM suja: v14 trava, v15 relê o módulo
python teste_pagina_v14.py         # navegação do OS no emulador (12.232 casos)
python -c "import teste_capas_v10_emu as T; T.main('build_poc_capa_grande_v15', 'v15.png')"   # tempo real
python teste_gerador_gui_v10.py    # a janela de verdade, geração idêntica à POC
```

**Regra do projeto:** nada vai para o aparelho sem passar no teste de tempo real (`ppu_tempo.py`), que acusa
qualquer escrita na PPU fora do vblank.

## Compilar o .exe

```
pip install -r requirements-dev.txt
python ferramentas/compilar_exe.py
```

## Regenerar o PDF da auditoria

```
python docs/gerar_pdf_auditoria.py
```

(Windows: usa as fontes Arial/Consolas de `C:\Windows\Fonts`.)
