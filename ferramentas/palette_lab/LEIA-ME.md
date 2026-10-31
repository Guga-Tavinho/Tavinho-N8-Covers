# Palette Lab (local) — conversor de imagem para NES

Versão em Python + tkinter do **nesdevtools.com/palette-lab**, com as mesmas funções. O levantamento feito com o REA
está em `../../palette_lab_analise/FUNCIONALIDADES.md`. É uma implementação própria, em Python, dos mesmos algoritmos.
Roda 100% no computador.

## Abrir
- Dois cliques em **`Abrir Palette Lab.bat`**, ou `python palette_lab_gui.py [imagem ou projeto.json]`.
- Requer Python 3 com tkinter e o **Pillow** (`python -m pip install --user pillow`).

## Funções (equivalentes ao site)
| Site | Aqui |
|---|---|
| Drop zone / browse (PNG, JPG, GIF, WebP, .json) | **Abrir imagem ou projeto…** (também aceita BMP) ou passar o arquivo na linha de comando |
| Blank canvas 16/32/64/128 | botões de tela em branco (abre o editor) |
| Fit: Center crop / Stretch | **Ajuste**: Recortar no centro / Esticar |
| Output size: Auto, 128…16 | **Tamanho de saída** (Auto mantém ≤128 px no tamanho original, completando com preto) |
| Solver size: 16×16 BG / 8×8 SPR | **Bloco do solver** |
| Color match | **Fidelidade de cor** (0 = cinza, 100 = cor total; padrão 50) |
| Seam smooth | **Suavizar emendas** (padrão 35) |
| Dither | **Pontilhado** (Bayer 4×4) |
| Grid overlay | **Grade** (8×8 / 16×16 sobre a saída) |
| Re-solve / Lock / Undo | **Refazer** (mantém cores fixadas) / **Travar** / **Desfazer** (5 níveis, também Ctrl+Z) |
| Paletas: ON/OFF, clicar no espaço, arrastar cor para fixar, Unpin all | iguais: **ON/OFF**, clique abre o **seletor** (com "Auto (soltar)"), arraste da paleta mestre para **fixar** (📌), **Soltar todas** |
| NES master palette: clicar banir/permitir, Enable all | iguais (✕ = banida, contorno dourado = em uso, · = proibida, BK = fundo `$0F`), **Permitir todas** |
| Stats: modo, tiles, atributos, cores /13 | iguais |
| Download PNG / Export BMP (RGB) / Copy palettes (.byte) | **Salvar PNG** / **Exportar BMP (RGB)** (espaço 1 = vermelho, 2 = verde, 3 = azul, fundo = preto, para o NESmaker) / **Copiar paletas (.byte)** |
| Pixel editor: Paint, Auto-erase, Set palette, Undo, Grid 1/4/8/16, Clear paint, Done | **Pintar**, **Borracha automática**, **Definir paleta**, **Desfazer**, **Grade** (bordas dos blocos em vermelho), **Limpar pintura**, **Concluir**; clicar no pincel ativo troca a cor |
| Save project / New project (Save & new / Discard & new / Cancel) | **Salvar projeto** / **Novo projeto** (Salvar e novo / Descartar e novo / Cancelar) |

O **projeto .json** usa o mesmo formato do site (`app: "palette-lab", v: 2`), então dá para abrir aqui um projeto
salvo lá e vice-versa.

## Conta-gotas (extra, não existe no site)
- **Clique numa cor da "Saída NES"**: a ferramenta descobre a paleta e o espaço daquela cor, faz o espaço piscar
  no painel de paletas e **abre o seletor** ao lado do mouse. A cor escolhida troca todos os pixels daquele
  espaço (é assim no NES: o pixel guarda o espaço, não a cor). Passar o mouse mostra, na barra de status,
  `(x,y) · bloco · PAL · espaço · cor`.
- **No editor de pixels, botão direito** = pegar a cor clicada como pincel; botão direito de novo na mesma cor abre
  o seletor dela. O botão esquerdo continua pintando.
- Clicar no fundo `$0F` só avisa: o fundo é fixo.

## Capas da firmware EDFC (extra, não existe no site)
1. Abra a imagem da caixa, de preferência com o **mesmo nome da ROM** (ex.: `Contra (USA).png`).
2. **Tamanho de saída → "Capa EDFC 64×96"**: o bloco passa sozinho para **8×16 capa (SPR)**, o mesmo modelo
   da firmware (48 sprites 8×16, cada um com 1 de 4 paletas). O que você vê é exatamente o que o NES mostra.
   Se a fidelidade de cor estiver no padrão do site (50%), ela vai para 75%, que deu as cores mais fiéis nos testes.
3. Ajuste à vontade: cores fixadas, cores banidas, Refazer, editor de pixels.
4. **🎮 Salvar capa para o COVERS…** grava `<nome da ROM>.json` (o nome do arquivo tem que ser o da ROM).
5. **📦 Gerar COVERS.BIN…**: escolha a pasta das capas (PNG e/ou .json), opcionalmente as pastas das ROMs, e onde
   salvar. Para cada jogo, um **.json tem prioridade sobre o PNG** e entra **sem reconversão** (formato v1). No
   formato v2 (experimental), a imagem já convertida do .json serve de entrada.
6. Copie o `COVERS.BIN` para `/EDFC/` no cartão: v1 com o `OS.BIN` da favorita, v2 com o do experimento.

Teste de ponta a ponta (`palette_lab_analise/teste_gui/roteiro_capa.py`): projeto em modo capa com cor fixada e
pixels pintados à mão → janela Gerar → `COVERS.BIN`. O registro sai idêntico ao projeto, e a firmware v1 (favorita)
no emulador carrega exatamente esses tiles, essa paleta e essa OAM.

## Diferenças
- Arrastar um **arquivo** do Windows para a janela não é suportado (o tkinter não tem isso nativo): use o botão Abrir.
- O site sorteia o 1º centróide do k-means a cada conversão. Aqui a semente é fixa e muda a cada **Refazer**, então
  abrir a mesma imagem dá sempre o mesmo resultado.
