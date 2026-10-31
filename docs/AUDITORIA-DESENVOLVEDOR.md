# Auditoria técnica — NES N8 Everdrive Covers editor (firmware v15)

Documento para **desenvolvedores**: o que foi feito, o que foi descoberto no OS do cartucho, os endereços (ponteiros),
os patches, o formato dos arquivos, os algoritmos, os testes, os bugs e as ferramentas usadas.
Data: **30/10/2026**. Autor do projeto: **TavinhoGames** (análise e código feitos com o Claude Code).

| Item | Valor |
|---|---|
| Versão estável | firmware **v15** + ferramenta "NES N8 Covers Editor" (Python / .exe) |
| `OS.BIN` v15 (com a espera padrão de 0,5 s) | SHA-1 `caa12ed797d374341a40a76a7d2124ee3ce51e8a` |
| Módulo das capas (`MOD_v10.BIN`, 1 KB) | SHA-1 `6e5e9cbfe33f9ff11185bb6a5e818528b4595650` |
| OS original do clone (base de todos os patches) | SHA-1 `dbea89d33eacd7ae72ee24d2652727b0cb5740ae` (57.344 bytes; **não distribuído**) |
| Hardware | EverDrive N8 **clone** (pasta `EDFC`) num NES/Famicom NTSC |
| Testado no aparelho | 817 capas, várias pastas, liga/desliga repetido, navegação, cancelamento |

Legenda de confiança usada nas notas: **[OBS]** visto no código/bytes · **[INF]** inferido com boa evidência ·
**[?]** hipótese.

---

## 1. Resumo

O cartucho roda um "OS" de 6502 (escrito em C e compilado com **cc65**) carregado de `/EDFC/OS.BIN`. O projeto
modifica esse arquivo (patches no lugar + código novo em áreas recuperadas) para mostrar, no navegador de
arquivos, a **capa do jogo selecionado** (112×160 pontos) ao lado da lista. As capas ficam num pacote
`/EDFC/COVERS.BIN` gerado no PC por uma ferramenta em Python que converte PNGs para o formato do NES.

Pontos principais da solução:

- **Capa = fundo + sprites.** O fundo usa 2 paletas próprias por capa (bloco de 16×16) e tiles em **7 bancos de
  CHR trocados no meio do quadro** (split por sprite 0). Por cima, até **62 sprites 8×16** com 4 paletas, e
  **flicker** opcional (2 quadros alternados a 60 Hz) para mais cores.
- **Código em duas partes:** ~1,2 KB **residente** dentro do OS.BIN (em código morto e nas telas "Device Info" e
  "About", removidas) + um **módulo de 1 KB** que fica no `COVERS.BIN` (setores 257–258) e é carregado na WRAM
  `$6400–$67FF` quando preciso.
- **Carga em ~45–65 quadros** (~1 s): a tela é desligada só abaixo da barra de status, numa "janela" de vblank
  estendido (linha 226 até o pré-render), sincronizada pelo sprite 0.
- **Espera configurável** antes de carregar (o cursor parado em cima do jogo) e **cancelamento** por qualquer botão.
- **20 jogos por página**, `← →` levam o cursor para o topo da página nova, `@tavinho.games` embaixo da capa.
- Tudo verificado por **testes no PC** com um emulador 6502 próprio e um **modelo de tempo da PPU**
  (`ppu_tempo.py`), antes de ir para o aparelho.

---

## 2. Linha do tempo das versões

| Versão | O que mudou | `OS.BIN` (SHA-1) | No aparelho |
|---|---|---|---|
| PoC base | capa fixa 64×96 em sprites, gravada no próprio OS.BIN | — | funcionou |
| v1 (`capas_sd`) | capas 64×96 lidas do SD (`COVERS.BIN` v1, índice por CRC) | `7c9f4886…` | funcionou (favorita da época) |
| v2 | sprites + camada de fundo | `c0a74aea…` | funcionou |
| v3 | alternância de quadros (capa pequena) | `5b23f07e…` | funcionou |
| v4 | **capa grande 112×160** só de fundo, split de bancos de CHR | — | funcionou |
| v5 | + até 62 sprites por cima; módulo de 1 KB em `$6400` | `79894e96…` | lixo ao trocar de capa → 2 pares por vblank |
| v6 | carga mais rápida (`vbw` pelo flag `$9E` do NMI do OS) | — | ok |
| v7 | **vblank estendido** (janela pelo sprite 0); marca do módulo = SHA-1 | — | funcionou (depois das correções) |
| v8 | flicker opcional nos sprites, por capa | — | funcionou |
| v9 | cor livre na paleta 3 | — | funcionou |
| v10 | espera + cancelamento; atributos da capa fora do buffer do OS | `4c7281b9…` | **funcionou** (estável até 30/10) |
| v11 | `@tavinho.games` + mudança no módulo (`$05`) | `dfede28f…` | ok, **abandonada** (mudança no módulo era desnecessária) |
| v12 | v11 + 20 por página | `768f9cc1…` | travava ao abrir pastas (causa real: ver v15) |
| v12b | tentativa de tirar o "lixo" ao ligar | `6c27725b…` | capas bugaram → **abandonada** |
| v13 | v10 + texto + 20 por página (sem mexer no módulo) | `96d89601…` | funcionou |
| v14 | `← →` levam o cursor ao topo da página | `876d21bf…` | — |
| **v15** | v14 + **correção do travamento após ligar** | `caa12ed7…` | **funcionou — ESTÁVEL** |

Os builders são **incrementais**: `build_capas_v15.py` importa a v14, que importa a v13, … até `build_poc.py`, que
lê o OS original. Cada versão só descreve a diferença para a anterior.

---

## 3. O hardware e o OS original

### 3.1 Layout do `OS.BIN` (57.344 bytes)

| Offset no arquivo | Conteúdo | Destino |
|---|---|---|
| `0x0000–0x0FFF` | CHR tabela 0: duas cópias da fonte (`$00–$7F` normal, `$80–$FF` destaque) | PPU `$0000` |
| `0x1000–0x1FFF` | CHR tabela 1 (sem uso pelo menu original) | PPU `$1000` |
| `0x2000–0x5FFF` | preenchimento (`$AA` / `$00`), **não é carregado** pela BIOS | — |
| `0x6000–0xDFFF` | PRG (32 KB, código 6502 do cc65) | CPU `$8000–$FFFF` |

Conversão: **`offset = endereço_CPU − 0x8000 + 0x6000`** (`build_poc.cpu2file`). Vetores: NMI `$80B4`,
RESET `$8000`, IRQ `$80EB`. O PRG roda **em RAM**: pode ser patchado e ter variáveis dentro de `$8000–$FFFF`.

### 3.2 Registradores do cartucho

Banco indexado: escreve-se o índice em **`$4400`** e o valor em **`$4401`**.

| Índice | Uso |
|---|---|
| `$09` | o que aparece em `$8000–$FFFF` (RAM do OS / flash da BIOS) |
| `$80` | banco de PRG ao carregar o jogo |
| `$81` | `$08` = WRAM normal em `$6000`; `$09` = mapeia o banco que contém o CHR do OS.BIN |
| `$82` | **banco de CHR**: janela de 8 KB começando em valor × 4 KB (usado pela capa para trocar de banco no meio do quadro) |
| `$83`, `$86`, `$88`, `$8B`, `$8C` | configuração do jogo (mapper, mirroring, save) |

> Não mexer nos stubs de flash `$847D`, `$84C0`, `$84F3`: eles mapeiam a flash da BIOS e enviam comandos de
> apagamento — risco de brick. O OS base tem também uma verificação anti-clone em `$B255`
> ("ERROR 5FA1.Clone detected!") que **não** foi tocada.

### 3.3 Mapa de memória em tempo de execução

| Faixa | Uso |
|---|---|
| `$0000–$00FF` | zero page. cc65: `c_sp=$28/$29`, `sreg=$2A`, `ptr1..ptr4=$30..$37`, `tmp1=$38`. OS: `$92/$93` ponteiro de texto, `$9E` flag do NMI, `$9F` cor do texto, `$A0` joypad, `$A2` NMI ocupado. A BIOS usa `$80–$8A` |
| `$0100–$01FF` | pilha do 6502 |
| `$0200–$02FF` | **sem uso no OS** → página de OAM dos sprites da capa |
| `$0300–$049A` | DATA do cc65 (copiado de `$FA39` no boot) |
| `$049B–…` | BSS; tabela da API da BIOS copiada de `$FC00` |
| `$0600–$07FF` | pilha de software do C (cresce para baixo a partir de `$0800`) |
| `$6000–$63FF` | **buffer da tela** (espelho da nametable `$2000`; atributos em `$63C0`) |
| `$6400–$67FF` | **módulo das capas** (WRAM com **bateria**!). O OS usa `$6400–$66FF` como rascunho no boot |
| `$6800–$7EFF` | heap do OS (tabelas do diretório, buffers de setor) |
| `$7F00–$7FFF` | variáveis da capa (atributos `ATC`, contadores, cópia dos metadados dos sprites) |
| `$FBA2–$FBFF` (build base: `$FBD4–$FBFF`) | livre no arquivo |
| `$FC00–$FFF9` | **preenchido pela BIOS** em tempo de execução (API, driver de SD) — NÃO está livre |

### 3.4 Vídeo (PPU) no OS original

- `PPUCTRL=$80`, `PPUMASK=$0A` (fundo ligado, **sprites desligados**: o OS nunca usa sprites).
- Paleta do fundo em `$825F`: `0F 10 0F 28 | 0F 0F 0F 0F | 0F 0F 0F 0F | 0F 30 00 28`. Paleta 0 = lista
  (cor 3 = amarelo de pastas/cursor), paleta 3 = barra (branco/cinza/amarelo). Paletas 1 e 2 ficam livres.
- A CHR é **RAM**: `INITCHR $826F` espera o vblank, desliga a tela, zera e copia os 8 KB da fonte, e religa
  (`$82F0: LDA #$0A / STA $2001`).
- Texto: tudo é desenhado no buffer `$6000` e enviado por `GFX_FULL $82FA` (redesenho completo), `REFRESH $8326`
  (128 bytes por vblank, usado pelos menus) ou `UPDCUR $83E6` (só a coluna do cursor).
- O NMI do OS gasta ~315–330 ciclos; sobram **~1.850 ciclos** úteis de vblank (NTSC, 2.273 no total).

---

## 4. Ponteiros do OS base (build do clone, SHA-1 `dbea89d3…`)

### 4.1 Rotinas

| Endereço | Nome | O que faz / como chamar |
|---|---|---|
| `$8000` | reset | init do hardware, `copydata`/`zerobss`, `c_sp=$0800` |
| `$80B4` | nmi | lê o joypad se `$A2==0`; põe `$9E` |
| `$826F` | `INITCHR` / ppu_screen_init_upload_chr | espera vblank, desliga a tela, zera e copia a CHR, religa |
| `$82FA` | `GFX_FULL` | envia a nametable inteira do buffer `$6000` |
| `$8326` | `REFRESH` | redesenho progressivo (menus/popups) |
| `$833D` | (fim do REFRESH) | `JMP $8343` — ponto do gancho `hide` |
| `$8393` | `WAITVB` / ppu_wait_vblank | espera o vblank lendo `$2002` |
| `$839C` | `PUTS` | |
| `$83C5` | `SCR_CLEAR` | zera `$6000–$63FF` |
| `$83E6` | `UPDCUR` | atualiza só a coluna do cursor |
| `$8441` / `$845F` | scr_backup / scr_restore | copia 1 KB da tela para `$6400` e volta |
| `$84C0` | flash_cmd_stub_save_ram | **chamado sempre no boot** (`$BBB1`): usa `$6400–$66FF` como rascunho |
| `$8DC2` | fat_dir_scan | lê a pasta para o cache; **para em 254 entradas** (`0xfd < count`) |
| `$9254` | dir_get_entry | nome/infos da entrada N |
| `$96B3` | `CL2LBA` / fat_cluster_to_lba | u32 cluster → LBA (A/X/sreg) |
| `$9DE0` | `FINDNAME` / file_find_by_name | (u32 dir, "NOME8   EXT", u32* tam, u32* cluster); remove 10 bytes da pilha do C |
| `$9F0B` | `WAITKEY` | |
| `$A5C8` | txt_print_xy | |
| `$AB25` | `IDLE` | espera ociosa do laço do navegador (ponto do gancho `idle_hook`) |
| `$BB4A` | (os_init) | `JSR FINDNAME` do `MAPROUT.BIN` → gancho `init_hook` |
| `$BBB1` | (os_init) | `JSR $84C0` sem condição |
| `$B255` | verificação anti-clone | não mexer |
| `$C53F` | `RDSEC` / fat_read_sector_cached | u32 LBA → `*($04E9)`; cache do LBA em `$0529–$052C` |
| `$C822` | ordenação da lista | |
| `$C987` | browser_draw_list | desenha a página (21 itens no original) |
| `$CB29` | (draw) | `LDA #$1D`: largura do nome na lista (29 → 14 colunas) |
| `$CB83` | (draw) | `JSR $82FA`: redesenho completo → gancho `w82fa` (texto) |
| `$CB8B` | (draw) | `LDA #$0A / STA $2001` → gancho `mask_entry` |
| `$CB94` | (draw) | `JSR $83E6` → gancho `hook_cursor` |
| `$D953` | laço do navegador | |
| `$D9CD`, `$D9FB` | repetição do direcional | atraso de 20 quadros (não é o tamanho da página) |
| `$DA06–$DBB0` | navegação | ↑ ↓ ← → (página, linha, wrap) |
| `$ECDB`, `$ED7B` | (main) | `JSR $826F` → `chr_all` (fonte em todos os bancos) |
| `$ED50` | main | |

Runtime do cc65 usado: `pushax $F3F7`, `push0 $F3F3`, `pusheax $F21B`, `ldaxysp $F145`, `staxysp $F4AB`,
`udiv $F54F`, `umul $F36D`.

### 4.2 Variáveis e dados

| Endereço | O que é |
|---|---|
| `$8259/$825A` | índice selecionado (16 bits, posição na lista ordenada) |
| `$0549/$054A` | número de itens da pasta |
| `$0515` | joypad (botões) |
| `$04E9` | ponteiro para o buffer de setor do FAT (`FATBUF`) |
| `$0529–$052C` | LBA do setor no cache |
| `$04FF–$0502` | cluster da pasta `/edfc` |
| `$6320–$635F` | nome completo do item selecionado (linhas 25–26 do buffer) — base do CRC da capa |
| `$FB39` | tabela de ponteiros do menu (copiada para a RAM) |
| `$F6CF` | string "About" |
| `$F753–$F895` | strings do Device Info / About (reaproveitadas: SEG_C) |
| `$D0C6–$D329` | código das telas Device Info + About (reaproveitado: SEG_MAIN) |

---

## 5. Arquitetura da firmware v15

### 5.1 Mapa completo dos patches (diferença byte a byte v15 × original)

| Endereço | Original → v15 | Função |
|---|---|---|
| `$81C5–$820C` | 72 bytes (rotina de checksum **sem chamador**) | SEG_A: `hook_cursor`, `draw_hook` (filtro `.nes`), `no_cover`, `mask_entry`, `idle_hook` |
| `$82EC`, `$841B`, `$BB9C` | `80 → A0` | `PPUCTRL` com sprites 8×16 |
| `$8400` | `84 → A4` | idem (modo de coluna) |
| `$833D` | `JMP $8343 → JSR $F753` | `hide`: esconde a capa quando um menu redesenha |
| `$A680–$A706` | 135 bytes | SEG_E: `split`, `frm_tg`, `i_wait`, **`espq` em `$A706`** |
| `$BB4A` | `JSR $9DE0 → JSR $D0C6` | `init_hook`: acha `MAPROUT.BIN` **e** `COVERS.BIN` |
| `$C9A4/$C9AC/$C9DC` | `15 → 14` | página de 20 itens (desenho) |
| `$CB2A` | `1D → 0E` | nome com 14 colunas na lista |
| `$CB84` | `JSR $82FA → JSR $F879` | `w82fa`: escreve `@tavinho.games` antes do redesenho |
| `$CB8B` | `LDA #$0A/STA $2001 → JSR $81EE/NOP/NOP` | `mask_entry` |
| `$CB95` | `JSR $83E6 → JSR $81C5` | `hook_cursor` |
| `$CCE2`, `$CCFD` | Device Info / About → `$D215` | as duas opções do menu viram `RTS` (`cm_r`) |
| `$D0C6–$D326` | 609 bytes | SEG_MAIN (ver 5.2) |
| `$D9EC` | `JSR $AB25 → JSR $81F9` | `idle_hook` |
| `$DA10 $DA18 $DA49 $DA9F $DAE6 $DAFD $DB56 $DB63 $DB6B` | `−1` | página de 20 (navegação) |
| `$DB17`, `$DB73` | `LDY #3/JSR $F145 → LDA #0/TAX/NOP/NOP` | `← →`: linha 0 na página nova |
| `$DBA2` | `LDA $8259/SEC/SBC #$15 → LDY #4/LDA ($28),Y/SBC #$14` | `←`: início da página − 20 |
| `$ECDC`, `$ED7C` | `JSR $826F → JSR $D216` | `chr_all`: fonte em todos os bancos de CHR |
| `$F753–$F894` | 322 bytes | SEG_C (ver 5.2) |
| `$FBD4–$FBFE` | 43 bytes | SEG_D: `scroll0`, `banco`, `dly`, `setP` |
| arquivo `0x1000–0x15FF`, `0x1EF0–0x1FFF` | CHR tabela 1 | **resto da capa de teste da PoC v1** (sem uso desde a v4; inofensivo — a limpeza foi tentada na v12b e abandonada) |

### 5.2 Segmentos residentes e espaço livre

| Segmento | Faixa | Usado / total | Livre | Conteúdo |
|---|---|---|---|---|
| SEG_A | `$81C5–$820F` | 72 / 75 | 3 | ganchos do desenho e da espera |
| SEG_E | `$A680–$A706` | 135 / 135 | 0 | split, troca de quadro do flicker, espera (`espq`) |
| SEG_MAIN | `$D0C6–$D329` | 609 / 612 | 3 | `init_hook`, `crc_part`, `load_cover`, `lmod`, `chr_all`, `xvb`/`xvb_fim`, `ld_oam`, `nt_rows`, `q_next` |
| SEG_C | `$F753–$F895` | 322 / 323 | 1 | `hide`, `bg_clear`, `lba_read`, variáveis, `flk_vb`, `lm_mg`, `w82fa` + texto |
| SEG_D | `$FBD4–$FBFF` | 42 / 44 | 2 | `scroll0`, `banco`, `dly`, `setP` |
| Módulo (WRAM) | `$6400–$67FB` | 983 / 1020 | 37 | carga da capa, sprites, atributos, paletas, flicker, cancelamento |

O espaço residente está praticamente **esgotado**; código novo deve ir para o módulo (37 bytes livres) ou exigir
liberar outra área (ver as notas técnicas, seção 3 e 11, para candidatas).

### 5.3 Endereços principais do código novo (v15)

| Endereço | Símbolo | Papel |
|---|---|---|
| `$81C5` | `hook_cursor` | no lugar do `JSR $83E6`: cursor andou → marca a capa como pendente |
| `$81C8` | `draw_hook` | filtro: o nome termina em `.nes`? senão `no_cover` (`$81DE`) |
| `$81EE` | `mask_entry` | `PPUMASK` do redesenho (com ou sem sprites) |
| `$81F9` | `idle_hook` | a cada volta ociosa: `i_wait` → `load_cover` |
| `$A680` | `split` | troca dos bancos de CHR durante o desenho (sprite 0 na linha 16, depois de 24 em 24 linhas) |
| `$A6ED` | `frm_tg` | alterna o quadro do flicker |
| `$A6F6` | `i_wait` | conta os quadros com o cursor parado |
| **`$A706`** | **`espq`** | **quadros de espera + 1** (offset **34566** no OS.BIN; padrão 31 = 0,5 s) |
| `$D0C6` | `init_hook` | boot: acha `MAPROUT.BIN` e `/EDFC/COVERS.BIN` (cluster → LBA base) |
| `$D12E` | `crc_part` | CRC-32 do nome (linhas 25–26) |
| `$D19A` | `load_cover` | busca no índice e carrega a capa |
| `$D1B8` / **`$D1BA`** | `lmod` / **`lm_k`** | confere o módulo na WRAM (**`LDA $66FC,X`** na v15) e relê os setores 257–258 se precisar |
| `$D216` | `chr_all` | `$826F` nos bancos 0, 1, 3 … 13 (a fonte em todos os bancos usados) |
| `$D240` / `$D28E` | `xvb` / `xvb_fim` | abre/fecha a janela de vblank estendido |
| `$D2AE` | `ld_oam` | monta a OAM da carga |
| `$D2E2` | `nt_rows` | nametable da capa (escondida) |
| `$F753` | `hide` | esconde a capa (menus), regrava as paletas do OS |
| `$F799` | `bg_clear` | limpa as células da capa no buffer |
| `$F7B7` | `lba_read` | lê um setor do `COVERS.BIN` (base + deslocamento) |
| `$F7E5…$F808` | variáveis | `base`, `want`, `cur`, `sec`, `csec`, `pending`, `has`, `bgshown`, `rev`, … |
| `$F83E` | `flk_vb` | no vblank: paletas e OAMDMA do quadro do flicker |
| **`$F875`** | **`lm_mg`** | assinatura do módulo (4 bytes = módulo[`$2FC:$300`] = `04 8D 55 7F`) |
| `$F879` | `w82fa` | copia "@tavinho.games" para `$62F1` (linha 23, colunas 17–30) e salta para `$82FA` |
| `$FBD4` | `scroll0` | zera o scroll |
| `$FBE2` | `banco` | escreve `$82` no registrador de CHR |
| `$FBEB` | `dly` | atraso calibrado (janela) |
| `$FBF3` | `setP` | ponteiro |
| `$6401` | `lc_rest` | começo da carga no módulo (guarda a pilha em `ab_sp $7F5D`) |
| `$65A5` | `up128` | envia 128 bytes à PPU (laço desenrolado, ~11,5 ciclos/byte) |
| `$65FE` | `at_ppu` | atributos da capa direto na PPU (cópia em `ATC $7F00`) |
| `$6629` | `pal_wr` | paletas (inclui a cor 3 da paleta 3, `$3F0F`) |
| `$670F` | `spr_load` | carrega os tiles dos sprites (faixas A e B) |
| `$6773` | `vbw` | espera o vblank pelo flag `$9E` do NMI do OS |
| `$67A7` | `joyp` | lê `$4016` direto (o NMI fica desligado nas janelas) |
| `$67BD` | `l_desiste` | cancela: restaura a pilha, religa a tela, `pending=1` |

A tabela completa (242 símbolos) está no **Apêndice A**.

### 5.4 Fluxo de execução

1. **Boot** — `os_init` chama `init_hook` (`$BB4A`): faz a busca original do `MAPROUT.BIN` e procura
   `COVERS  BIN` na pasta `/edfc`, guardando o LBA do primeiro setor. Sem o arquivo, a firmware se comporta como o
   OS original (sem capas). `main` chama `chr_all` no lugar do `$826F`: a fonte é copiada para todos os bancos
   de CHR usados pela capa.
2. **Desenho da lista** — `browser_draw_list` termina em `hook_cursor`/`draw_hook`: se o item selecionado é
   `.nes`, a capa fica **pendente** (`pending = 1`), senão é escondida.
3. **Espera** — a cada volta ociosa do navegador, `idle_hook` → `i_wait`: `pending` vira contador de quadros e a
   carga começa quando chega em `espq` (o OS volta `pending` para 1 a cada movimento do cursor).
4. **Carga** — `load_cover`: `crc_part` calcula o CRC do nome (linhas 25–26 do buffer, `|$20`), lê o setor do
   balde (`crc & $FF`) do índice, acha o número da capa e confere os 3 bytes de verificação do registro.
   `lmod` garante o módulo na WRAM (confere `$66FC–$66FF` contra `lm_mg`; se não bater, relê os setores 257–258).
   O módulo carrega: setor 0 (paletas, atributos, nametable), grupos de tiles do fundo nos bancos ímpares,
   tiles de sprite nos bancos pares, OAM e paletas dos sprites — tudo dentro das janelas de vblank estendido.
5. **Exibição** — a cada quadro, `split` troca o banco de CHR em 6 pontos da tela (sincronizado pelo sprite 0
   na linha 16); com flicker, `flk_vb`/`frm_tg` alternam as paletas e os tiles dos sprites a cada quadro.
6. **Saída** — qualquer menu/popup redesenha via `REFRESH $8326` e passa por `hide` (`$833D`): sprites
   desligados, paletas do OS regravadas. Botão durante a carga → `joyp` → `l_desiste`.

### 5.5 Técnicas de vídeo (por que funciona)

- **Mais tiles que a PPU permite:** a capa precisa de ~400 tiles; cada banco de 4 KB tem só 63 slots livres na
  fonte (`$01–$1F` e `$80–$9F`). Solução: 7 grupos de linhas, cada um num banco (`$82` = 1, 3, 5 … 13), com a
  fonte copiada em todos; o `split` troca de banco durante o desenho. As linhas de fronteira existem nos dois
  bancos vizinhos (a troca pode cair em qualquer ponto delas).
- **Sincronia pelo sprite 0:** um sprite opaco atrás do texto (coluna 0) marca a linha; o código espera o flag V
  de `$2002`.
- **Vblank estendido na carga (`xvb`):** espera o sprite 0 da carga na linha 200, atrasa até a linha 226 (abaixo
  da barra, que acaba na 223), desliga a tela **no intervalo horizontal** (ponto ~280; no meio da linha a PPU
  pode corromper a OAM) e o NMI (`$2000=$20`), envia vários pedaços de 128 bytes, e `xvb_fim` religa antes do
  pré-render. O NMI fica desligado porque ele lê `$2002` e zeraria o latch do `$2006` no meio das escritas.
- **Orçamento de ciclos:** toda escrita na PPU com a tela ligada precisa acabar dentro do vblank (~1.850 ciclos
  depois do NMI do OS). Os testes medem isso instrução por instrução.
- **Flicker:** quadro A e quadro B dos sprites (tiles `2p+1 EOR $80`, paletas próprias) alternando a 60 Hz; o olho
  vê a média — dobra as combinações de cor.
- **Atributos da capa fora do buffer do OS** (`ATC $7F00`, enviados direto à PPU): o buffer de atributos é só do
  OS, senão a limpeza da capa apagava o cinza das caixas de menu (bug da v10).

---

## 6. Formato do `COVERS.BIN`

Setores de 512 bytes. O arquivo tem que estar **contínuo no cartão**: a firmware lê "LBA base + deslocamento",
sem seguir a cadeia de clusters do FAT.

| Setores | Conteúdo |
|---|---|
| 0–255 | **índice**: um setor por balde (`crc & $FF`); entradas de 5 bytes `[crc>>8, crc>>16, crc>>24, idx_lo, idx_hi]`, fim = `idx_hi $FF`; até 101 entradas por balde (`PER_BUCKET`) |
| 256 | zerado |
| 257–258 | **módulo** de 1 KB (vai para `$6400–$67FF`) |
| 512 + 64·i … | **registro da capa i** (64 setores = 32 KB) |

- **CRC:** CRC-32 do zlib **sem o XOR final**, sobre o nome como o navegador mostra nas linhas 25–26 (≤ 60
  caracteres), cada byte `| $20` (`gerar_covers.name_crc`).
- **Limite de 1015 capas:** o setor é de 16 bits no 6502 (`512 + 64·1014 + 63 < 65536`).
- **Registro (v8–v15):** setor 0 = verificação (3 bytes) + paletas 1 e 2 (`[3:9]`) + atributos + nametable +
  pedaços usados por grupo (`[353:367]`) + cor 3 da paleta 3 (`[367]`); setores 1–14 = tiles do fundo (7 grupos);
  setor 15 = OAM A (`[0:256]`) + paletas A (`[256:272]`) + faixas A (`[272:300]`) + flag do flicker (`[300]`) +
  paletas B (`[304:320]`) + faixas B (`[320:]`); setores 16+ = tiles dos sprites em faixas contínuas. A referência
  exata é `conv_capa_grande.converter_v9` / `converter_v8`.
- **Assinatura do módulo:** v15 compara `módulo[$2FC:$300]` (`048d557f` no `MOD_v10.BIN`). O mesmo `COVERS.BIN`
  serve para v10, v13, v14 e v15 (o módulo é o mesmo).
- **Modo "só acrescentar"** (`gerar_covers_v10.py --base`): lê o índice antigo, copia os registros byte a byte,
  converte só as ROMs novas, acrescenta no fim e refaz o índice; recusa se o módulo for de outra firmware.

---

## 7. Os patches das últimas versões em detalhe

### 7.1 Texto `@tavinho.games` (v13)
`$CB83: JSR $82FA` → `JSR w82fa` (`$F879`): `LDX #13 / LDA s_txt,X / STA $62F1,X / DEX / BPL / JMP $82FA` — copia
14 caracteres para a linha 23, colunas 17–30 do buffer, antes de o OS enviar a tela. Os atributos da capa já põem
as linhas 22–23 na paleta 0 (texto), então ele aparece com e sem capa.

### 7.2 20 jogos por página (v13) — 13 operandos trocados no lugar

| Endereço (opcode) | Antes → depois | Papel |
|---|---|---|
| `$C9A3 LDA #` / `$C9AB LDA #` | 21 → 20 | início da página = sel/21·21 |
| `$C9DB CMP #` | 21 → 20 | laço das linhas |
| `$DA0F` / `$DA17 LDA #` | 21 → 20 | início da página (navegação) |
| `$DA48 LDA #` | 20 → 19 | ↑ na 1ª linha vai para a última |
| `$DA9E CMP #` | 21 → 20 | ↓ depois da última |
| `$DAE5 CMP #` | 22 → 21 | ← → só com mais de uma página |
| `$DAFC LDA #` | 21 → 20 | → avança uma página |
| `$DB55 CMP #` / `$DB62` / `$DB6A LDA #` | 21 → 20 | ← da 1ª página vai para a última |
| `$DBA6 SBC #` | 21 → 20 | ← volta uma página |

Não confundir com `$D9CD/$D9FB` (atraso da repetição, 20 quadros) nem com `$858D/$85A1`, `$920B`, `$B954`,
`$CCBA`, `$CF76` (outros 21/20 que não são da página).

### 7.3 `← →` no topo da página (v14)
O OS faz `sel = início da página nova + linha` (a linha fica em `c_sp[2..3]`). `$DB17` e `$DB73`:
`A0 03 20 45 F1` (`LDY #3 / JSR ldaxysp`) → `A9 00 AA EA EA` (`LDA #0 / TAX / NOP / NOP`). `$DBA2`:
`AD 59 82 38` (`LDA $8259 / SEC`) → `A0 04 B1 28` (`LDY #4 / LDA ($28),Y`, o início da página; o carry já é 1).

### 7.4 Correção do travamento após ligar (v15)
O módulo mora na WRAM **com bateria** e sobrevive ao desligar. Em todo boot, `os_init` (`$BBB1`) chama
`$84C0`, que usa `$6400–$66FF` como rascunho e estraga os primeiros 768 bytes do módulo — mas não toca em
`$67FC`, onde ficava a assinatura. Assinatura intacta + corpo estragado → o `lmod` não relia e a primeira carga
saltava para lixo (trava). Abrir um jogo apagava a WRAM inteira, por isso "funcionava num boot e travava no
outro". Correção (3 bytes + a assinatura, sem mudar o módulo): `lm_k` (`$D1BA`) `BD FC 67` → `BD FC 66`
(`LDA $66FC,X`) e `lm_mg` = `módulo[$2FC:$300]`.

---

## 8. Conversor de imagens (PC)

| Etapa | Arquivo / função | Algoritmo |
|---|---|---|
| Associação ROM ↔ capa | `associar_roms.py` | títulos "limpos" (sem número de lista, `(...)`/`[...]`, "The", acentos; II..VIII = 2..8), `difflib` com limiar 0,84; números do título têm que bater; empate decide pela região da ROM (senão EUA > Mundo > Europa > Japão) e evita Beta/Proto/Pirata. Várias ROMs podem usar a mesma imagem |
| Recorte e redução | `gerar_covers_v10` / `sim_tela_cheia` | corte central na proporção 0,7, redução para 112×160 |
| Nitidez | `sim_tela_cheia` (`UnsharpMask`, raio 1) + `conv_v3` (configuração por capa) | força por capa de 10–200% (padrão 180 nas POCs) |
| Fundo | `conv_capa_grande.quantizar` | 2 paletas livres (3 cores + preto) escolhidas para a capa, uma paleta por bloco 16×16; opcional a cor 3 da paleta 3 (`converter_v9` fica com o melhor dos dois) |
| Pontilhado | `conv_capa_grande.pontilhar` | xadrez Bayer 2×2: cada ponto mistura 2 cores do bloco em 0/25/50/75/100%; custo ΔE² + 0,05·ΔE²(c1,c2)·4t(1−t) |
| Sprites | `conv_sprites_grande.py` | até 62 sprites 8×16 (grade de 16 linhas × 8 pontos, máx. 8 por faixa, 7 na faixa do sprite 0), 4 paletas; cada ponto transparente ou cor, só onde reduz o erro |
| Flicker | `conv_sprites_grande.otimizar_flicker` | quadro B por sprite; ponto = média na luz de A e B; custo ΔE² + λ·ΔE²(A,B); 7 níveis λ = 0 / 0,02 / **0,05** / 0,10 / 0,15 / 0,20 / 0,25. A busca testa as 54 candidatas de uma vez (`busca()`): ~8× mais rápido, resultado idêntico |
| Edição de cores | `capa_grande_cores.py` | recolorir = só trocar bytes de paleta (setor 0 `[3:9]`, `[367]`; setor 15 `[256:272]`, `[304:320]`); prévia idêntica ao conversor |
| Erro de cor | `sim_tela_cheia.lab`, `palette_lab/nes_core.rgb2lab` | ΔE no espaço CIELAB, sobre as cores RGB da paleta do NES (`build_poc.NES_RGB`) |

Tempo típico: ~1 s por capa sem flicker, ~12 s com flicker (7 níveis calculados em segundo plano na prévia).

---

## 9. A ferramenta (`ferramentas/gerador_firmware_capas.py`)

- **Interface:** tkinter. Seções: (1) capas, ROMs, saída e "Só acrescentar"; (2) prévia da capa (espera, nitidez,
  pontilhado, flicker + nível, paletas/conta-gotas, zoom, barra de progresso); (3) gerar e copiar para o SD.
- **Firmware de referência:** `firmwares/OS_v15.BIN` + `firmwares/MOD_v10.BIN`, conferidos pelo SHA-1. A espera é
  o **único byte** que a ferramenta muda no OS (`ESPQ = 34566`, valor = quadros + 1).
- **Configurações:** `gerador_config.json` (ao lado da ferramenta, ou em `%APPDATA%\NES N8 Covers editor\` no
  .exe); por pasta de capas, `capas_config.json` (nitidez, flicker, nível, pontilhado por capa) e
  `paletas_editadas_grande/` (edições de cor). Cache das conversões com flicker em `cache_flicker/`.
- **Geração:** `gerar_covers_v10.py` (também roda sozinho pela linha de comando). No .exe roda num
  `multiprocessing.Process` do próprio programa (`linhas_gerador`/`_gerador_processo`), com
  `freeze_support()`; fora dele, como subprocesso Python (`GERADOR_EM_PROCESSO=1` força o modo do .exe).
- **Cópia para o SD:** `copiar_sd.py` apaga o antigo, reserva o tamanho inteiro, grava, confere com
  `fsutil file queryextents` (1 trecho = contínuo) e só então troca.
- **.exe:** `compilar_exe.py` (PyInstaller `--onedir --windowed`, ícone `icone.ico`, embute `OS_v15.BIN`,
  `MOD_v10.BIN` e o ícone; preserva o `LEIA-ME.txt`; gera o .zip). Modos escondidos para teste:
  `--gerar-covers …` e `--testar-geracao <log> …`.

---

## 10. Testes (no PC, antes do aparelho)

Infraestrutura própria:

- `emu6502.py` — emulador 6502 (opcodes oficiais) com *stubs* para rotinas do OS e *hooks* de leitura/escrita.
- `ciclos6502.py` — ciclos por instrução (inclui página cruzada).
- `ppu_tempo.py` — **modelo de tempo da PPU** (NTSC 262×341): NMI de verdade do OS na linha 241, sprite 0,
  `$2002` apagando vblank e latch, `WAITVB` como salto até o vblank, joypad lido pelo NMI, botão a partir de um
  instante (`joy_em`). Qualquer escrita na PPU com a tela ligada fora do vblank é uma **violação**.
- `asm6502.py` (montador com símbolos e expressões) e `dis6502.py` (disassembler).

| Teste | Verifica |
|---|---|
| `teste_capas_v10_emu.py` | tempo real da v10–v15 (`main('build_poc_capa_grande_v15', …)`): carga, tela = conversor, nenhuma escrita fora do vblank, espera, cancelamento, assinatura do módulo |
| `teste_ligar_v15.py` | WRAM com o módulo da sessão anterior e `$6400–$66FF` estragados: v14 trava, v15 relê e carrega |
| `teste_pagina_v14.py` / `teste_pagina_v12.py` | roda a navegação `$DA06–$DBB0` do próprio OS para listas de 1 a 254 itens, toda posição, 4 direções (12.232 casos) |
| `teste_abrir_pasta.py` | abrir pastas no emulador |
| `teste_gerador_gui_v10.py` | a janela de verdade: prévias, opções salvas, geração = POC idêntica (`COVERS.BIN` `0e495260…`), espera muda só o byte `espq` |
| `teste_capas_emu.py`, `teste_capas_v2..v9_emu.py`, `teste_poc_*.py`, `teste_paletas_editadas.py` | histórico das versões anteriores |

Os testes de capa usam 5 capas reais em `imagens/Named_Boxarts/` (libretro-thumbnails; não incluídas) e o OS
original em `firmware_base/EDFC/OS.BIN` (não incluído).

---

## 11. Bugs encontrados, causas e lições

| Sintoma no aparelho | Causa real | Lição |
|---|---|---|
| Lixo ao trocar de capa (v5) | escritas na PPU passavam do vblank (3 pares por vblank + laço das máscaras: até 2.203 ciclos) | medir ciclos de **toda** escrita na PPU; 2 pares por vblank |
| Lixo na linha 0 / na lista (1ª v7) | a janela atravessava a linha 241; o NMI do OS lia `$2002` e zerava o latch do `$2006` | NMI desligado na janela; sincronizar pelo sprite 0; testar com o NMI **de verdade** (`ppu_tempo`) |
| Travava ao parar num jogo (2ª v7) | módulo velho na WRAM com a mesma marca "M7OK" | assinatura derivada do conteúdo do módulo |
| Caixa do File Menu pela metade (1ª v10) | a limpeza da capa zerava atributos no buffer do OS | estado da capa fora das estruturas do OS (`ATC`) |
| Travava ao abrir pasta (v12) | atribuído à fragmentação do `COVERS.BIN` e depois a T+M+P; a causa mais provável era a do v15 | isolar com builds C1/C2 ajudou, mas a hipótese "fragmentação" foi aceita cedo demais |
| Lixo de ~0,5 s ao ligar | `chr_all` troca de banco com a tela ligada entre chamadas do `$826F` | correção (v12b) quebrou as capas; **cosmético, deixado como está** |
| Travava depois de ligar, alternando entre boots (v10–v14) | o OS estraga `$6400–$66FF` (WRAM com bateria) em todo boot; a assinatura ficava fora dessa faixa | conferir a assinatura **dentro** da área que pode ser estragada; testar "cold boot" com WRAM suja |
| Nome "colado" (`contanes`) e sem capa | ROM com nome todo em minúsculas (o navegador mostra o nome errado, o CRC não bate) | exigir nome com maiúscula no início |

Lições gerais: emular o **tempo** (não só a lógica) da PPU; toda memória persistente (WRAM com bateria) pode
estar suja; mudanças pequenas e isoláveis por versão; backup estável antes de cada experimento.

---

## 12. Limites e quirks

| Limite | Valor | Origem |
|---|---|---|
| Capas por `COVERS.BIN` | 1015 | setor de 16 bits na firmware |
| Itens por pasta | 254 | `fat_dir_scan` do OS original |
| Tipos com capa | só `.nes` | filtro `draw_hook` |
| Nome da ROM | ≤ 60 caracteres, sem acentos, começa com maiúscula | linhas 25–26 (2×30) + CRC; nome todo minúsculo aparece errado |
| Tamanho | 32 KB por ROM (817 ROMs ≈ 26 MB) | registro de 64 setores |
| Espera | 0–4 s | byte `espq` |
| Paletas fixas | paleta 0 (lista), branco/cinza da barra, preto | compartilhadas com o OS |

Quirks herdados do OS original: com 256+ itens `← →` não trocam de página (o `BCS` de `$DAE7` usa o carry do
`CMP #4` de `$DA8D`) e a última página sai cheia; `←` na 1ª página com n múltiplo de 20 cai numa página vazia e
o cursor vai para o último jogo.

---

## 13. Aplicações e ferramentas usadas

| Ferramenta | Uso |
|---|---|
| **Ghidra 12.1.4** (headless, processador `6502:LE:16:default`, base `$8000`) | disassembly/decompilação do OS; `ghidra_scripts/DumpNES.java` + `nomes_base.txt` renomeiam ~180 funções e exportam listagem, pseudo-C e referências de I/O |
| REA (MCP de engenharia reversa) | tentado primeiro; **não suporta 6502** (formato/arquitetura recusados) |
| **Python 3.15** + **numpy** + **Pillow** + **tkinter** | ferramenta, conversor, builders, testes |
| Emulador/montador próprios | `emu6502.py`, `asm6502.py`, `dis6502.py`, `ciclos6502.py`, `ppu_tempo.py` |
| Conhecimento do **cc65** | convenções de chamada (pilha de software em `$28`, `pushax`, `ldaxysp`), runtime em `$ED50–$F532` |
| `map_funcs.py` | casa as funções do v1.26 (krikzz) com o build do clone (169 funções) |
| **PyInstaller 6.22.3** | o .exe (`compilar_exe.py`) |
| **ffmpeg** | extrair quadros dos vídeos do aparelho (diagnóstico do lixo ao ligar) |
| `fsutil file queryextents` (Windows) | conferir se o `COVERS.BIN` ficou contínuo |
| **reportlab** | este PDF |
| Palette Lab (próprio) | laboratório de paletas da capa pequena (v1–v3) |
| libretro-thumbnails *Named_Boxarts* | fonte das capas de teste |
| Claude Code | análise, código e testes junto com o autor |
| Hardware | EverDrive N8 clone + NES NTSC; fotos/vídeos em `imagens/` e `debug/` |

---

## 14. Como reconstruir tudo

1. Python 3 com `numpy` e `Pillow` (`pip install -r requirements.txt`).
2. Rodar a ferramenta: `python ferramentas/gerador_firmware_capas.py` (usa `ferramentas/firmwares/OS_v15.BIN`).
3. Reconstruir a firmware a partir do zero: copie o **seu** `OS.BIN` original do clone (SHA-1 `dbea89d3…`) para
   `firmware_base/EDFC/OS.BIN` e rode `python ferramentas/build_capas_v15.py` (mostra o SHA-1; tem que dar
   `caa12ed7…` com a espera padrão). `build_poc_capa_grande_v15.py` monta uma pasta `EDFC` de teste (precisa das
   capas em `imagens/Named_Boxarts`).
4. Testes: `python ferramentas/teste_ligar_v15.py`, `python ferramentas/teste_pagina_v14.py`, e o tempo real
   `python -c "import teste_capas_v10_emu as T; T.main('build_poc_capa_grande_v15', 'v15.png')"` dentro de
   `ferramentas/`.
5. .exe: `pip install pyinstaller` e `python ferramentas/compilar_exe.py`.

O histórico completo da investigação (seções 0–39, com todas as versões) está em `NOTAS-TECNICAS-FIRMWARE.md`
(**Apêndice B** deste PDF).
