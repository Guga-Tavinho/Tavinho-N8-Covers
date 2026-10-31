"""POC v10: a v9 (estável no aparelho) + ESPERA antes de carregar + CANCELAMENTO da carga por botão.

  1. Espera: com o cursor parado num jogo, conta ESPERA_QUADROS quadros (padrão 30 = 0,5 s) antes de carregar a
     capa; o cursor andando recomeça a contagem (o OS põe pending = 1 a cada movimento; pending vira o contador).
     O valor fica num byte da firmware (símbolo `espq`): a ferramenta poderá trocá-lo sem mexer no resto.
  3. Atributos da capa fora do buffer do OS (cópia em $7F00, enviada direto à PPU): o buffer de atributos volta a
     ser só do OS. Antes, a limpeza da capa zerava os atributos da região e apagava o cinza (paleta 3) da metade
     direita das caixas de menu (File Menu) — o bug da foto imagens/novos testes/4.jpeg.
  2. Cancelamento: durante a carga o NMI do OS fica desligado nas janelas e não lê o controle; então, antes de
     cada envio, a carga lê o controle direto ($4016). Botão apertado -> desiste: desfaz a pilha até o começo da
     carga, sprites desligados, capa escondida (has = 0), pending = 1 (recarrega quando parar de novo).
Espaço: o aparecimento antigo (passos 1-6: a nametable agora vai na carga, desde a v7) sai do módulo, e o
split espera o vblank pelo vbw do módulo (o módulo sempre está carregado quando há capa na tela).
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_poc import build, ROOT, cpu2file
import build_capas_v5 as V5
import build_capas_v9 as V9
from asm6502 import assemble

ESPERA_QUADROS = 30
MOD2 = V9.MOD2
HEAD = V9.HEAD + r'''
ab_sp    = $7F5D        ; pilha no começo da carga (para desistir de qualquer ponto)
ATC      = $7F00        ; atributos da capa (6 x 4, de 8 em 8): só na PPU, nunca no buffer do OS
'''
sub = V5.sub

SEG_D, SEG_MAIN = V9.SEG_D, V9.SEG_MAIN

# ---------------------------------------------------------------- espera (idle_hook) — a marca do módulo vai para $F753
a = V9.SEG_A[2]
_mg = 'lm_mg:  .byte 0,0,0,0              ; impressão digital do módulo (preenchida na montagem)\n'
a = sub(a, _mg, '')
a = sub(a, '''idle_hook: LDA pending
        BEQ i_done
        JSR load_cover''', '''idle_hook: LDA pending
        BEQ i_done
        JSR i_wait              ; cursor parado há espq quadros?
        BCC i_done
        JSR load_cover''')
SEG_A = (V9.SEG_A[0], V9.SEG_A[1], a)
c = V9.SEG_C[2]
c = sub(c, '''        LDX #40                 ; atributos da região -> paleta 0
bc_a:   LDA #0
        STA AT0,X
        STA AT0+1,X
        STA AT0+2,X
        STA AT0+3,X
        TXA
        SEC
        SBC #8
        TAX
        BPL bc_a
        RTS''', '''        RTS                     ; (atributos: o buffer é só do OS — os da capa ficam em ATC)''')
SEG_C = (V9.SEG_C[0], V9.SEG_C[1], c + '\n' + _mg)

# ---------------------------------------------------------------- split: espera o vblank pelo vbw; i_wait
e = V9.SEG_E[2]
e = sub(e, '''split:  LDA has
        BEQ sp_out
        LDA #0
        STA NMIF
        TAX
        LDY #$10
sw0:    LDA NMIF                ; espera o NMI (com limite)
        BNE sw_v
        DEX
        BNE sw0
        DEY
        BNE sw0
sp_out: JMP IDLE
sw_hd:  JMP sp_hide
sw_v:''', '''split:  LDA has
        BNE sp_go
sp_out: JMP IDLE
sw_hd:  JMP sp_hide
sp_go:  JSR vbw                 ; espera o NMI (vbw do módulo: com limite)
sw_v:''')
e += r'''
i_wait: LDA NMIF                ; um quadro a mais com o cursor parado (pending conta de 1 em diante)
        BEQ iw_1
        LSR NMIF
        INC pending
iw_1:   LDA pending
        CMP espq                ; C = 1: já esperou
        RTS
espq:   .byte %d                ; quadros de espera + 1 (a ferramenta pode trocar)
''' % (ESPERA_QUADROS + 1)
SEG_E = (V9.SEG_E[0], V9.SEG_E[1], e)

# ---------------------------------------------------------------- módulo: sem o aparecimento antigo; cancelamento
r = V9.MOD_SRC
r = sub(r, '''        STA AT0,X''', '''        STA ATC,X''')
r = sub(r, '''ap_c:   LDA AT0,X''', '''ap_c:   LDA ATC,X''')
i, j = r.index('reveal: LDA rev\n'), r.index('rv_fim: LDA #0')
r = r[:i] + 'reveal:                         ; (desde a v7 só resta o último passo: rev = 7)\n' + r[j:]
r = sub(r, '''lc_rest:
''', '''lc_rest: TSX                    ; pilha daqui: para desistir de qualquer ponto da carga
        STX ab_sp
''')
r = sub(r, '''l_fr:   JSR xvb                 ; linha ~226: tela desligada''', '''l_fr:   JSR joyp                ; botão apertado? desiste da carga
        BEQ l_fok
        JMP l_desiste
l_fok:  JSR xvb                 ; linha ~226: tela desligada''')
r += r'''
joyp:   LDA #1                  ; lê o controle direto (Z = 0: algum botão); preserva X
        STA $4016
        LSR A
        STA $4016
        LDY #8
jp_l:   LDA $4016
        AND #3
        BNE jp_r
        DEY
        BNE jp_l
jp_r:   RTS
l_desiste: LDX ab_sp            ; volta para quem chamou a carga (a tela está ligada: entre envios)
        TXS
        LDA #$0A                ; sprites desligados; capa escondida e pendente
        STA $2001
        LDA #0
        STA has
        STA rev
        LDA #1
        STA pending
        STA bgshown
        RTS
'''
MOD_SRC = r


def assemble_all():
    segs_src = [SEG_A, SEG_D, SEG_MAIN, SEG_C, SEG_E, (MOD2, MOD2 + 0x3FC, MOD_SRC)]
    syms = {}
    for _ in range(8):
        new = {}
        for org, end, src in segs_src:
            new.update(assemble(HEAD + src, org, syms, strict=False)[1])
        if new == syms: break
        syms = new
    return [(org, end, assemble(HEAD + src, org, syms)[0]) for org, end, src in segs_src], syms


def main(log=print):
    V5.assemble_all = assemble_all
    try:
        buf, S, modulo = V5.main(log=lambda *a: None)
    finally:
        import importlib; importlib.reload(V5)
    marca = hashlib.sha1(modulo).digest()[:4]
    modulo = modulo.ljust(0x3FC, b'\0') + marca
    o = cpu2file(S['lm_mg'])
    buf[o:o + 4] = marca
    log('OS.BIN v10 SHA1 %s' % hashlib.sha1(buf).hexdigest())
    segs, _ = assemble_all()
    for org, end, code in segs:
        log('  $%04X-$%04X  %3d de %3d bytes (livres %d)' % (org, org + len(code) - 1, len(code), end - org,
                                                           end - org - len(code)))
    log('  espera: %d quadros (byte espq em $%04X = posição %d do OS.BIN)' % (ESPERA_QUADROS, S['espq'],
                                                                         cpu2file(S['espq'])))
    return buf, S, modulo


if __name__ == '__main__':
    main()
