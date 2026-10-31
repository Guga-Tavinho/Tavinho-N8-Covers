"""POC: capa em TELA CHEIA no console (176x240, troca de banco de CHR no meio do quadro), sobre a firmware v3.

Como usar no console: pare o cursor num jogo que tenha capa de tela cheia por ~3 segundos -> a capa ocupa a tela.
Qualquer botão volta para a lista (a firmware espera o botão ser solto, para o navegador não receber o aperto).

Como funciona:
  - OS (v3 normal) + 2 mudanças: a espera ociosa conta os quadros com a capa pequena na tela ($9E = NMI) e, no
    quadro 180, lê o setor FULL_SEC do COVERS.BIN e pula para ele (JMP ($04E9)); a carga da capa zera o contador.
  - O setor FULL_SEC é o VISUALIZADOR (código de até 512 bytes): ele se copia para $6400 (o backup da tela do OS,
    sem uso enquanto o navegador está aberto), procura a capa no índice (setor FULL_SEC+1: [CRC do nome 4, setor 2]),
    desliga a tela e o NMI, envia nametable + 3 blocos de tiles (bancos 2/3 do registrador $82) + paletas, e mostra:
    a cada quadro, banco 2 no vblank; sprite 0 (atrás do fundo, no 1º pixel não preto do topo) -> espera -> banco 3
    perto da linha 75 -> espera -> banco 4 perto da linha 155. As linhas de tiles 9 e 19 existem nos dois bancos
    vizinhos, então a troca pode cair em qualquer ponto de 8 linhas de pixels.
  - Saída: espera soltar o botão, banco 0, paleta do OS ($825F), nametable do buffer ($82FA) e refaz a capa pequena
    (mask_entry, como no redesenho completo).
Dados de cada capa: ver conv_tela_cheia.py (27 setores, começando pelo setor com "TELA").

uso:  python build_poc_tela_cheia.py      saída: poc_tela_cheia/EDFC/OS.BIN + COVERS.BIN (= o da firmware_gerada
      + o visualizador + as capas de tela cheia no fim)
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
from build_capas import patch, jsr
import build_capas_v3 as V3
from asm6502 import assemble
from gerar_covers import name_crc
import associar_roms
import conv_tela_cheia as C

ESPERA_QUADROS = 180                      # 3 s parado no jogo
VIEWER = 0x6400
FORCA = 120
COVERS_BASE = os.path.join(ROOT, 'firmware_gerada', 'EDFC', 'COVERS.BIN')
CAPAS = os.path.join(ROOT, 'imagens', 'Named_Boxarts')
JOGOS = ['Super Mario Bros 3 (U) (PRG 0).nes', 'Super Mario Bros 3 (U) (PRG 1).nes',
         'Super Mario Bros 3 (U) (PRG 1) [a1].nes', 'Super Mario Bros 3 (U) (PRG 1) [a2].nes',
         'Super Mario Bros 3 (U) (PRG 1) [a3].nes', 'Mega Man 2 (U).nes', 'Castlevania (U) (PRG 0).nes',
         'Castlevania (U) (PRG 1).nes', 'Contra (U).nes', 'Legend of Zelda, The (U) (PRG 0).nes',
         'Legend of Zelda, The (U) (PRG 1).nes', 'Metroid (U).nes', "Kirby's Adventure (U) (PRG 0).nes",
         "Kirby's Adventure (U) (PRG 1) [!].nes", 'Ninja Gaiden (U).nes', 'Duck Tales (U).nes', 'Punch-Out!! (U).nes',
         'Teenage Mutant Ninja Turtles (U).nes']

HEAD = V3.HEAD + r'''
NMIF     = $9E          ; o NMI do OS põe 1 aqui a cada quadro
JOY      = $0515        ; botões apertados (lidos pelo NMI do OS)
OSPAL    = $825F        ; paleta de fundo do OS (16 bytes)
vn       = $67E0        ; variáveis do visualizador (fim do backup da tela, depois do código)
vtmp     = $67E1
vcnt     = $67E2
vsec     = $67E3        ; 2 bytes
vmeta    = $67E5        ; 24 bytes: paletas 16, sprite 0 (4), esperas (Y1, A1, Y2, A2)
'''


def segmentos(full_sec):
    """Segmentos da v3 com o contador da espera ociosa e o carregador do visualizador."""
    a = V3.sub(V3.SEG_A[2], '''        JSR load_cover
i_done: JMP IDLE''', '''        JSR load_cover
        LDA #0                  ; capa nova: o contador da tela cheia recomeça
        STA fs_t
i_done: JMP fs_hook''')
    e = V3.SEG_E[2] + r'''
; ---------------------------------------------------------------- POC tela cheia: espera 3 s e chama o visualizador
fs_hook: LDA has                ; só com a capa pequena na tela
        BEQ fh_i
        LDA NMIF                ; conta quadros (o NMI do OS põe 1)
        BEQ fh_i
        LSR NMIF
        INC fs_t
        LDA fs_t
        CMP #%d
        BNE fh_i
        LDA #<%d                ; setor do visualizador no COVERS.BIN
        LDX #>%d
        JSR lba_read
        BNE fh_i
        JSR fh_go
fh_i:   JMP IDLE
fh_go:  JMP ($04E9)             ; roda o setor lido (ele se copia para $6400)
fs_t:   .byte 0
''' % (ESPERA_QUADROS, full_sec, full_sec)
    return [(V3.SEG_A[0], V3.SEG_A[1], a), V3.SEG_D, V3.SEG_MAIN, V3.SEG_C, (V3.SEG_E[0], V3.SEG_E[1], e)]


VIEWER_SRC = r'''
; ======== visualizador de tela cheia (roda em $6400; os primeiros bytes rodam de dentro do buffer do setor)
v_ini:  LDA FATBUF              ; copia o setor (512 bytes) para $6400 — só endereços absolutos e desvios
        STA P
        LDA FATBUF+1
        STA P+1
        LDY #0
v_c1:   LDA (P),Y
        STA $6400,Y
        INY
        BNE v_c1
        INC P+1
v_c2:   LDA (P),Y
        STA $6500,Y
        INY
        BNE v_c2
        JMP v_main
v_main: LDA #<IDXSEC            ; índice: [n] e n x [CRC do nome (4), setor (2)]
        LDX #>IDXSEC
        JSR lba_read
        BNE v_ret
        JSR setP
        LDY #0
        LDA (P),Y
        BEQ v_ret
        STA vn
        INY
v_find: LDX #0
v_f1:   LDA (P),Y
        CMP cur,X
        BNE v_next
        INY
        INX
        CPX #4
        BNE v_f1
        LDA (P),Y
        STA vsec
        INY
        LDA (P),Y
        STA vsec+1
        JMP v_load
v_next: STX vtmp                ; Y = início da entrada + X -> próxima entrada = Y + 6 - X
        TYA
        CLC
        ADC #6
        SEC
        SBC vtmp
        TAY
        DEC vn
        BNE v_find
v_ret:  RTS
v_load: LDA vsec                ; setor 0 da capa: "TELA", paletas, sprite 0, esperas
        LDX vsec+1
        JSR lba_read
        BNE v_ret
        JSR setP
        LDY #3
v_m1:   LDA (P),Y
        CMP v_mag,Y
        BNE v_ret
        DEY
        BPL v_m1
        LDY #4
        LDX #0
v_m2:   LDA (P),Y
        STA vmeta,X
        INY
        INX
        CPX #24
        BNE v_m2
        LDA #0
        STA flk                 ; alternância da capa pequena parada
        JSR WAITVB
        LDA #0
        STA $2001               ; tela desligada
        LDA #$20
        STA $2000               ; NMI desligado durante a carga (a leitura de $2002 dele quebraria o $2006)
        LDA #$20                ; nametable + atributos: 2 setores
        LDX #2
        JSR v_up
        LDA #2                  ; blocos 2 e 3 (PPU $0000-$1FFF com o banco 2): 16 setores
        JSR v_bank
        LDA #$00
        LDX #16
        JSR v_up
        LDA #3                  ; bloco 4 (PPU $1000-$1FFF com o banco 3): 8 setores
        JSR v_bank
        LDA #$10
        LDX #8
        JSR v_up
        BIT $2002
        LDA #$3F                ; paletas: fundo e sprites (as mesmas 16 cores)
        STA $2006
        LDA #$00
        STA $2006
        LDX #0
v_p:    TXA
        AND #15
        TAY
        LDA vmeta,Y
        STA $2007
        INX
        CPX #32
        BNE v_p
        LDA #$F0                ; OAM: só o sprite 0 (sincronia); os outros fora da tela
        LDX #0
v_o:    STA $0200,X
        INX
        BNE v_o
        LDX #3
v_o2:   LDA vmeta+16,X
        STA $0200,X
        DEX
        BPL v_o2
        LDA #2
        JSR v_bank
        JSR WAITVB
        LDA #0
        STA $2003
        LDA #2
        STA $4014
        JSR scroll0             ; $2000 = $A0 (NMI ligado), rolagem 0
        LDA #$1E
        STA $2001               ; fundo + sprites, sem cortar a borda esquerda
v_loop: LDA #0
        STA NMIF
v_w0:   LDA NMIF                ; espera o NMI (vblank)
        BEQ v_w0
        LDA JOY                 ; qualquer botão: sai
        BNE v_exit
        LDA #2                  ; topo da tela: banco 2
        JSR v_bank
        LDX #0
        LDY #$10
v_w1:   BIT $2002               ; flag do sprite 0 apaga no fim do vblank
        BVC v_w2
        DEX
        BNE v_w1
        DEY
        BNE v_w1
        BEQ v_loop
v_w2:   LDY #$10
v_w3:   BIT $2002               ; sprite 0 (topo da capa)
        BVS v_hit
        DEX
        BNE v_w3
        DEY
        BNE v_w3
        BEQ v_loop
v_hit:  LDY vmeta+20
        LDA vmeta+21
        JSR v_dly
        LDA #3
        JSR v_bank              ; ~linha 75: banco 3
        LDY vmeta+22
        LDA vmeta+23
        JSR v_dly
        LDA #4
        JSR v_bank              ; ~linha 155: banco 4
        JMP v_loop
v_exit: LDA #0                  ; espera soltar o botão
        STA NMIF
v_x1:   LDA NMIF
        BEQ v_x1
        LDA #0
        STA NMIF
        LDA JOY
        BNE v_x1
        JSR WAITVB
        LDA #0
        STA $2001
        JSR v_bank              ; banco 0 (a fonte do OS)
        LDA #$20
        STA $2000               ; NMI desligado durante o envio
        BIT $2002
        LDA #$3F
        STA $2006
        LDA #$00
        STA $2006
        LDX #0
v_x2:   TXA
        AND #15
        TAY
        LDA OSPAL,Y
        STA $2007
        INX
        CPX #32
        BNE v_x2
        JSR GFX_FULL            ; a tela do navegador de volta (buffer $6000)
        JSR scroll0
        LDA #$0A
        STA $2001
        JMP mask_entry          ; refaz a capa pequena (carrega na espera ociosa)
v_bank: LDX #$82                ; banco de CHR = A
        STX $4400
        STA $4401
        RTS
v_dly:  TAX                     ; Y*(5A+6) + 15 ciclos (com o LDY/LDA/JSR de quem chama)
v_dl:   DEX
        BNE v_dl
        DEY
        BNE v_dly
        RTS
v_up:   BIT $2002               ; A = endereço alto na PPU, X = setores (os seguintes a vsec)
        STA $2006
        LDA #0
        STA $2006
        STX vcnt
v_u1:   INC vsec
        BNE v_u2
        INC vsec+1
v_u2:   LDA vsec
        LDX vsec+1
        JSR lba_read
        JSR setP
        LDX #2
        LDY #0
v_u3:   LDA (P),Y
        STA $2007
        INY
        BNE v_u3
        INC P+1
        DEX
        BNE v_u3
        DEC vcnt
        BNE v_u1
        RTS
v_mag:  .text "TELA"
'''


def montar_viewer(S, idx_sec):
    syms = {k: v for k, v in S.items()}
    syms['IDXSEC'] = idx_sec
    code, vs = assemble(HEAD + VIEWER_SRC, VIEWER, syms, strict=False)
    code, vs = assemble(HEAD + VIEWER_SRC, VIEWER, {**syms, **vs})
    assert len(code) <= 512, 'visualizador com %d bytes (máx. 512)' % len(code)
    for rot in ('v_dly', 'v_dl', 'v_w3', 'v_hit'):                  # laços temporizados sem cruzar página
        assert vs[rot] >> 8 == (vs[rot] + 8) >> 8, 'laço %s perto do fim de página' % rot
    return code, vs


def assemble_all(full_sec):
    segs_src = segmentos(full_sec)
    syms = {}
    for _ in range(6):
        new = {}
        for org, end, src in segs_src:
            new.update(assemble(HEAD + src, org, syms, strict=False)[1])
        if new == syms: break
        syms = new
    out = [(org, end, assemble(HEAD + src, org, syms)[0]) for org, end, src in segs_src]
    for org, end, code in out:
        assert org + len(code) <= end, 'segmento $%04X: %d bytes não cabem (limite %d)' % (org, len(code), end - org)
    return out, syms


def dados_tela_cheia(log=print):
    """Índice + capas (setores) para os JOGOS, com as capas associadas pelo nome."""
    capas = associar_roms.listar_capas(CAPAS, ('capas_config.json',))
    assoc = associar_roms.associar(JOGOS, capas)
    slots, entradas, info = [], [], {}
    cache = {}
    for rom in JOGOS:
        capa, n = assoc[rom]
        assert capa, 'sem capa para ' + rom
        if capa not in cache:
            r = C.converter(os.path.join(CAPAS, capa), FORCA)
            setores = bytearray(r['setores']); setores[0:4] = b'TELA'
            cache[capa] = len(slots); slots.append(bytes(setores)); info[capa] = r
            log('  %-40s <- %s  tiles %s' % (rom, capa, r['tiles']))
        entradas.append((rom, name_crc(rom), cache[capa]))
    return entradas, slots, info


def main(log=print):
    covers = open(COVERS_BASE, 'rb').read()
    covers += bytes(-len(covers) % 512)
    full_sec = len(covers) // 512
    entradas, slots, info = dados_tela_cheia(log)
    orig, buf, _ = build('base')
    segs, S = assemble_all(full_sec)
    for org, end, code in segs:
        o = cpu2file(org)
        buf[o:o + len(code)] = code
    patch(buf, 0x833D, buf[cpu2file(0x833D):cpu2file(0x833D) + 3], jsr(S['hide']))
    patch(buf, 0xBB4A, jsr(0x9DE0), jsr(S['init_hook']))
    patch(buf, 0xD9EB, jsr(0xAB25), jsr(S['idle_hook']))
    patch(buf, 0xCB8B, jsr(S['draw_hook']), jsr(S['mask_entry']))
    patch(buf, 0xCB83, jsr(0x82FA), jsr(S['w82fa']))
    patch(buf, 0xCB29, [0xA9, 0x15], [0xA9, 0x14])
    patch(buf, 0xCCE1, jsr(0xD0C6), jsr(S['cm_r']))
    patch(buf, 0xCCFC, jsr(0xD2B9), jsr(S['cm_r']))
    patch(buf, 0x80E6, [0xAD, 0x02, 0x20], [0x4C, S['nmi_flk'] & 0xFF, S['nmi_flk'] >> 8])
    viewer, VS = montar_viewer(S, full_sec + 1)
    assert len(entradas) <= 42
    indice = bytearray(512); indice[0] = len(entradas)
    for k, (rom, crc, slot) in enumerate(entradas):
        sec = full_sec + 2 + slot * C.SETORES
        indice[1 + k * 6:7 + k * 6] = crc.to_bytes(4, 'little') + sec.to_bytes(2, 'little')
    assert full_sec + 2 + len(slots) * C.SETORES < 65536
    extra = viewer.ljust(512, b'\0') + bytes(indice) + b''.join(slots)
    out_dir = os.path.join(ROOT, 'poc_tela_cheia', 'EDFC')
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, 'OS.BIN'), 'wb').write(buf)
    open(os.path.join(out_dir, 'COVERS.BIN'), 'wb').write(covers + extra)
    log('gerado: %s  OS.BIN SHA1 %s' % (out_dir, hashlib.sha1(buf).hexdigest()))
    log('  visualizador: %d de 512 bytes (setor %d), %d jogos, %d capas de tela cheia, COVERS.BIN %d KB'
        % (len(viewer), full_sec, len(entradas), len(slots), (len(covers) + len(extra)) // 1024))
    for org, end, code in segs:
        log('  $%04X-$%04X  %3d de %3d bytes (livres %d)' % (org, org + len(code) - 1, len(code), end - org,
                                                           end - org - len(code)))
    return buf, S, covers + extra, VS, entradas, info, full_sec


if __name__ == '__main__':
    main()
