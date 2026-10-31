# Custom Firmware para o Everdrive NES N8.

Essa firmware mostra a **capa do jogo** ao lado da lista de jogos no navegador do **EverDrive N8** para NES.
Foi criado um programa que converte as suas imagens de capa para o NES e gera a firmware do cartucho (`OS.BIN` + `COVERS.BIN`),
pronta para copiar para o cartão SD.

## Features da Custom Firmware/Programa

- Capa de **112×160 pontos** à direita da lista, com fundo + sprites do NES (até 62 sprites)
- **20 jogos por página** — a lista fica da mesma altura da capa
- **← →** agora trocam de página com o cursor no topo(na firmware original, ela mantinha a posição do cursor da pagina anterior)
- A capa carrega só quando o cursor **para** no jogo (espera configurável); qualquer botão cancela a carga
- Ajustes **por capa**: nitidez, pontilhado (dithering), flicker nos sprites (7 níveis) e troca de cores com
  conta-gotas
- Associação automática ROM ↔ imagem pelo nome (não precisa renomear tudo à mão)
- Pode **acrescentar** capas novas a um `COVERS.BIN` que você já tem, sem reconverter as antigas

---

## Requisitos

- Um **EverDrive N8 clone** com a pasta `EDFC` no cartão SD.
- As imagens das capas em **PNG** (veja [Imagens das capas](#imagens-das-capas)).

> ⚠️ **Faça backup da pasta `EDFC` do seu cartão antes** (principalmente o `OS.BIN` original). A ferramenta
> grava um `OS.BIN` modificado; para voltar ao original, é só copiar o seu de volta.

---

## Instalação

1. Baixe o `NES N8 Covers Editor.zip` da página de *Releases*.
2. Extraia em qualquer pasta.
3. Abra **`NES N8 Covers Editor.exe`**.

Obs: O Cache da ferramenta fica armazenada em: `%APPDATA%\NES N8 Covers editor\`.

---

## Como usar

### 1. Capas, ROMs e saída
- **Pasta das capas (PNG):** a pasta com as imagens.
- **Pastas de ROMs (.nes):** onde estão as suas ROMs. Pode ser a pasta do próprio cartão SD (ex.: `F:\`); as
  subpastas também são lidas. Cada ROM recebe a imagem de nome mais parecido.
- **Pasta de saída:** onde a firmware é gerada.
- **Só acrescentar capas novas ao COVERS.BIN:** escolha um `COVERS.BIN` que você já gerou. As capas que já estão
  nele ficam exatamente como estão e só as ROMs novas são convertidas. (Uma cópia do arquivo de antes fica em
  `<saída>\COVERS_anterior.BIN`.)

Na lista à esquerda, **"Mostrar só capas das minhas ROMs"** filtra as imagens que serão usadas, e **"Ver ROMs sem
capa…"** mostra as ROMs que não acharam imagem.

### 2. Prévia da capa
Clique numa capa da lista para ver como ela fica no NES.

| Opção | O que faz |
|---|---|
| **Espera antes de carregar a capa** | Segundos com o cursor parado em cima do nome do jogo até a capa carregar (0 a 4 s; padrão 0,5 s). Vale para todas as capas. |
| **Nitidez** (10–200%) | Realça os contornos ao reduzir a imagem. **Definir padrão** aplica a todas as capas sem ajuste próprio. |
| **Pontilhado** | Mistura duas cores em xadrez nos degradês (céu, pele, sombras). Fica melhor em TV de tubo / vídeo composto; em cabos muito nítidos o xadrez pode aparecer. |
| **Flicker nos sprites** + **nível** | Os sprites alternam entre dois quadros a cada 1/60 s e o olho vê a mistura: mais cores e mais fidelidade. Nível 1 = mais fiel e treme mais; nível 7 = treme pouco. Algumas TVs mostram o tremido mais que outras. |
| **Paletas desta capa / conta-gotas** | Clique numa cor da capa (ou num quadrado da paleta) para trocá-la por uma das cores do NES. **Desfazer** e **Restaurar originais** voltam atrás. |
| **mostrar / zoom** | Só a exibição da prévia (alternando como no NES, a média, ou cada quadro). |

"Definir como padrão" e "Usar o padrão nesta capa" valem para o flicker (ligado/desligado e o nível).

Os ícones na lista indicam as capas com **nitidez** e com **cores editadas**; o texto ao lado do nome mostra
"flicker" e "pontilhado" quando ligados.

### 3. Gerar
1. Clique em **GERAR FIRMWARE**. Sai `<saída>\EDFC\OS.BIN` e `<saída>\EDFC\COVERS.BIN` (e as prévias em
   `<saída>\previews`).
2. Copie para o cartão com **Copiar agora** — ou use **Adicionar caminho…** com o cartão SD: aí a firmware já vai
   direto para ele ao gerar.

> ⚠️ **Use sempre o "Copiar agora" (ou o caminho do cartão).** O EverDrive lê o `COVERS.BIN` direto pelos setores
> do cartão e ele precisa ficar **contínuo** (sem fragmentar). Copiado pelo Windows, o arquivo pode ficar em
> pedaços e o console **trava ao abrir uma pasta**. O botão apaga o arquivo antigo, grava contínuo e confere.

> `OS.BIN` e `COVERS.BIN` andam juntos: copie sempre os dois da mesma geração.

### No console
- Pare o cursor em cima de um jogo: depois da espera, a capa carrega (cerca de 1 segundo).
- Apertar qualquer botão durante a carga cancela; ela recomeça quando o cursor parar de novo.

---

## Imagens das capas

- Formato **PNG**, de qualquer tamanho. A imagem é cortada no centro na proporção **0,7** (largura/altura, a de uma
  caixa de NES) e reduzida para 112×160 — imagens já nessa proporção não perdem nada.
- O nome da imagem deve ser o nome do jogo (ex.: `Contra (USA).png`). Não precisa ser idêntico ao da ROM: a
  ferramenta associa pelo nome mais parecido (`001 Contra (U).nes` recebe `Contra (USA).png`). Várias ROMs podem
  usar a mesma imagem.
- Uma boa fonte de capas com esse padrão de nomes são os conjuntos *Named_Boxarts* do projeto
  [libretro-thumbnails](https://github.com/libretro-thumbnails/Nintendo_-_Nintendo_Entertainment_System).

---

## Limites

| Limite | Valor | Por quê |
|---|---|---|
| Capas por `COVERS.BIN` | **1015 ROMs** | O endereço de cada capa no cartão é de 16 bits na firmware. Cada ROM conta, mesmo que várias usem a mesma imagem. |
| Itens por pasta no cartão | **254** (arquivos + subpastas) | Limite da firmware original do cartucho: o navegador para de ler a pasta aí. Em pastas maiores, divida as ROMs em subpastas (ex.: `A-F`, `G-M`, …). |
| Tamanho do `COVERS.BIN` | **32 KB por ROM** | 822 ROMs ≈ 26 MB. |
| Tipos de arquivo com capa | só **`.nes`** | |
| Nome da ROM | até **60 caracteres**, **sem acentos** | O navegador mostra o nome em 2 linhas de 30 colunas; nomes com acento ou maiores são pulados (aparecem como aviso no log). |
| Nome da ROM | começar com **letra maiúscula** | Um nome todo em minúsculas (ex.: `contra.nes`) aparece errado no navegador do cartucho (`contanes`) e a capa não carrega. Use `Contra.nes`. |
| Espera antes de carregar | **0 a 4 s** | |

---

## Cores e qualidade

O NES tem uma paleta fixa e poucas cores por área da tela. Na região da capa:

- **Fundo:** 2 paletas de 3 cores escolhidas para cada capa (+ o preto), uma paleta por bloco de 16×16 pontos.
- **Sprites:** 62 sprites com 4 paletas de 3 cores, no máximo 8 por linha.
- **Cores fixas:** o preto do fundo, as cores do texto da lista e o branco/cinza da barra são da firmware (a
  lista também usa) e não podem ser trocadas no conta-gotas.

O **flicker** é o que mais aumenta a fidelidade (a alternância dobra as cores dos sprites); o **pontilhado** ajuda
nos degradês. A conversão de uma capa leva ~1 s sem flicker e ~12 s com flicker (as prévias com flicker calculam os
7 níveis em segundo plano, com uma barra de andamento).

---

## Problemas conhecidos

- **O console trava ao abrir uma pasta:** o `COVERS.BIN` ficou fragmentado no cartão, ou o `OS.BIN` e o
  `COVERS.BIN` são de gerações diferentes. Copie de novo os dois com **Copiar agora**.
- **O nome do jogo aparece "colado" (ex.: `contanes`) e a capa não carrega:** o arquivo da ROM está com o nome todo
  em minúsculas. Renomeie começando com letra maiúscula (`contra.nes` → `Contra.nes`).
- **Um "chuvisco" de ~0,5 s ao ligar o console**, antes da tela de carga: é só visual (a firmware prepara a memória
  de vídeo em vários bancos) e some sozinho.
- **Pastas com mais de 254 itens** mostram só os primeiros (limite da firmware original).
- Se uma capa com flicker tremer demais na sua TV, desligue o flicker dela (ou use um nível mais à direita) e gere
  de novo.

---

## Créditos

Feito por **TavinhoGames** — [GitHub](https://github.com/Guga-Tavinho) ·
[Instagram](https://www.instagram.com/tavinho.games) · [YouTube](https://www.youtube.com/@tavinho-games)

Projeto de fã, sem vínculo com a Nintendo nem com os fabricantes do EverDrive. As capas dos jogos pertencem aos seus
donos e não são distribuídas com o programa. Use por sua conta e risco — e mantenha o backup da sua pasta `EDFC`.
