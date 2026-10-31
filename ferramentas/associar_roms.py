"""Associação inteligente ROM <-> capa (não só o nome exato).

A firmware acha a capa pelo nome do arquivo da ROM (CRC do nome), então a capa precisa ser gravada com o nome exato
da ROM. Aqui cada ROM ganha a capa mais parecida, comparando os títulos "limpos":
  - sem extensão, sem número de lista no começo ("001 Contra (U)" -> "Contra"), sem (...) e [...] (região, versão,
    tradução, hack), sem "The"/", The", sem acentos e pontuação; "&" = "and"; II..VIII = 2..8
  - números do título precisam bater ("Lolo 2" nunca vira "Lolo 3"); um "1" sobrando é tolerado
  - empate: a capa da mesma região da ROM (senão EUA > Mundo > Europa > Japão) e sem Beta/Proto/Pirata
Notas: 1.0 = mesmo título; >= LIMIAR = aproximada; abaixo disso a ROM fica sem capa.

uso:  python associar_roms.py <pasta das capas> <pasta de ROMs> [...]    (lista o que associou)
"""
import difflib, os, re, sys, unicodedata

LIMIAR = 0.84
EXT_ROM = ('.nes',)
EXT_CAPA = ('.png', '.json')
ROMANOS = {'ii': '2', 'iii': '3', 'iv': '4', 'vi': '6', 'vii': '7', 'viii': '8'}
IGNORAR = {'the', 'a', 'an'}
REGIOES = [('us', ('u', 'usa', 'us', 'america')), ('w', ('w', 'world')), ('eu', ('e', 'europe', 'eur', 'uk')),
           ('jp', ('j', 'japan', 'jpn')), ('br', ('b', 'brazil')), ('as', ('asia', 'as', 'korea', 'k', 'china', 'ch'))]
PREFERENCIA = {'us': 0, 'w': 1, 'eu': 2, 'jp': 3}
RUINS = ('beta', 'proto', 'sample', 'demo', 'pirate', 'hack', 'bad', 'alt', 'unl', 'aftermarket', 'program')


def sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


class Titulo:
    """Um nome de arquivo decomposto: título limpo (chave, palavras, compacto, números) + região e marcas."""
    __slots__ = ('chave', 'palavras', 'compacto', 'numeros', 'regioes', 'ruim', 'principal')

    def __init__(self, nome, tirar_indice=False):
        s = sem_acento(os.path.splitext(nome)[0]).lower()
        tags = ' '.join(re.findall(r'[(\[]([^)\]]*)[)\]]', s))
        s = re.sub(r'[(\[][^)\]]*[)\]]?', ' ', s)                      # (U) (Japan, USA) [T+Eng] [!] ...
        if tirar_indice:
            s = re.sub(r'^\s*\d{1,4}\s*[-._)]?\s+', '', s)
        s = s.replace('&', ' and ').replace("'", '').replace('`', '')
        limpa = lambda x: [w for w in (ROMANOS.get(w, w) for w in re.findall(r'[a-z]+|\d+', x)) if w not in IGNORAR]
        p = limpa(s)
        self.principal = ' '.join(limpa(s.split(' - ')[0])) if ' - ' in s else ''   # título sem o subtítulo
        self.palavras = p
        self.chave = ' '.join(p)
        self.compacto = ''.join(p)
        self.numeros = frozenset(w.lstrip('0') or '0' for w in p if w.isdigit()) - {'1'}
        t = set(re.findall(r'[a-z0-9]+', tags))
        self.regioes = {r for r, nomes in REGIOES if t & set(nomes)}
        for c in re.findall(r'\b([ujew]{2,3})\b', tags):              # GoodNES junta: (JU) (UE)
            self.regioes |= {{'u': 'us', 'j': 'jp', 'e': 'eu', 'w': 'w'}[x] for x in c}
        self.ruim = any(r in tags for r in RUINS) or bool(re.search(r'\bt[+-]|\b(h|p|b|a|o)\d*\b', tags))


def nota(r, c):
    """Quanto o título da ROM r parece com o da capa c (0..1)."""
    if not r.compacto or not c.compacto: return 0.0
    if r.chave == c.chave: return 1.0
    if r.compacto == c.compacto: return 0.98
    if r.numeros != c.numeros: return 0.0
    m = difflib.SequenceMatcher(None, r.compacto, c.compacto)
    s = m.ratio() if m.real_quick_ratio() >= LIMIAR and m.quick_ratio() >= LIMIAR else 0.0
    a, b = set(r.palavras), set(c.palavras)
    j = len(a & b) / len(a | b)
    # um título contém o outro (palavras ou letras grudadas: "Battle Tank" em "Garry Kitchen's Battletank").
    # A capa com subtítulo a mais é segura ("Bases Loaded II" -> "... - Second Season"); a ROM com palavras a mais
    # costuma ser hack/outro jogo ("Bomberman - Luigi's Fall"), então vale menos.
    curto, longo = sorted((r.compacto, c.compacto), key=len)
    pal_curto = a if curto == r.compacto else b
    if (pal_curto <= (a & b) or curto in longo) and (len(pal_curto) >= 2 or len(curto) >= 6 or curto.isdigit() and len(curto) >= 3):
        f = len(curto) / len(longo)
        j = max(j, 0.80 + 0.15 * f if curto == r.compacto else 0.78 + 0.10 * f)
    if r.principal and r.principal == c.chave:                          # "Conan - The Mysteries of Time" -> "Conan"
        j = max(j, 0.88)
    if c.principal and c.principal == r.chave:
        j = max(j, 0.90)
    return max(s, j)


def desempate(r, c):
    """Pequeno bônus (< 0.01) entre capas do mesmo jogo: mesma região, região preferida, sem Beta/Proto."""
    b = 0.004 if r.regioes & c.regioes else 0.0
    b += 0.001 * (4 - min((PREFERENCIA.get(x, 4) for x in c.regioes), default=4))
    b -= 0.003 if c.ruim and not r.ruim else 0.0
    return b


def listar_roms(pastas):
    """Nomes de arquivo das ROMs (subpastas incluídas), sem repetir nome."""
    vistos, roms = set(), []
    for pasta in pastas:
        if not os.path.isdir(pasta): continue
        for raiz, _, arquivos in os.walk(pasta):
            for f in sorted(arquivos, key=str.lower):
                if f.lower().endswith(EXT_ROM) and f.lower() not in vistos:
                    vistos.add(f.lower()); roms.append(f)
    return roms


def listar_capas(pasta, ignorar=()):
    if not os.path.isdir(pasta): return []
    return sorted((f for f in os.listdir(pasta) if f.lower().endswith(EXT_CAPA) and f not in ignorar), key=str.lower)


class Indice:
    """Capas indexadas por chave, compacto e palavra (para não comparar cada ROM com todas as capas)."""

    def __init__(self, capas):
        por_stem = {}
        for f in capas:                                                # .json (projeto do Palette Lab) vence o .png
            k = os.path.splitext(f)[0].lower()
            if k not in por_stem or f.lower().endswith('.json'): por_stem[k] = f
        self.capas = [(f, Titulo(f)) for _, f in sorted(por_stem.items())]
        self.stem = {k: i for i, (k, _) in enumerate(sorted(por_stem.items()))}
        self.chave, self.compacto, self.palavra = {}, {}, {}
        for i, (f, t) in enumerate(self.capas):
            self.chave.setdefault(t.chave, []).append(i)
            self.compacto.setdefault(t.compacto, []).append(i)
            for w in set(t.palavras):
                self.palavra.setdefault(w, []).append(i)

    def candidatos(self, t):
        ids = set(self.chave.get(t.chave, ())) | set(self.compacto.get(t.compacto, ()))
        if ids: return ids
        raras = sorted((w for w in set(t.palavras) if len(w) >= 3 or w.isdigit()), key=lambda w: len(self.palavra.get(w, ())))
        for w in raras[:3]:
            ids |= set(self.palavra.get(w, ()))
        if len(t.compacto) >= 6:                                       # palavras grudadas: "Battle Tank" / "Battletank"
            ids |= {i for i, (_, c) in enumerate(self.capas) if t.compacto in c.compacto}
        if not ids:
            ids = {i for i, (_, c) in enumerate(self.capas) if c.compacto[:4] == t.compacto[:4]}
        return ids

    def melhor(self, rom):
        """(capa, nota) para a ROM, ou (None, melhor nota) se nenhuma passar do LIMIAR."""
        k = os.path.splitext(rom)[0].lower()
        if k in self.stem: return self.capas[self.stem[k]][0], 1.0          # mesmo nome de arquivo
        best, best_n = None, 0.0
        variantes = [Titulo(rom)]
        sem_ind = Titulo(rom, tirar_indice=True)
        if sem_ind.chave != variantes[0].chave and sem_ind.compacto: variantes.append(sem_ind)
        for t in variantes:
            for i in self.candidatos(t):
                f, c = self.capas[i]
                n = nota(t, c)
                if n <= 0: continue
                n += desempate(t, c)
                if n > best_n: best, best_n = f, n
        if best_n < LIMIAR: return None, best_n
        return best, min(1.0, best_n)


def associar(roms, capas):
    """{rom: (capa ou None, nota)} para cada nome de ROM."""
    ind = Indice(capas)
    return {r: ind.melhor(r) for r in roms}


def exata(rom, capa, n):
    return capa is not None and (n >= 0.995 or os.path.splitext(rom)[0].lower() == os.path.splitext(capa)[0].lower())


if __name__ == '__main__':
    if len(sys.argv) < 3: sys.exit(__doc__)
    import time
    t0 = time.time()
    capas = listar_capas(sys.argv[1], ('capas_config.json',))
    roms = listar_roms(sys.argv[2:])
    res = associar(roms, capas)
    for r in roms:
        c, n = res[r]
        print('%s %.2f  %-55s -> %s' % ('=' if exata(r, c, n) else '~' if c else '-', n, r[:55], c or ''))
    com = sum(1 for c, _ in res.values() if c)
    print('\n%d de %d ROMs com capa (%d capas na pasta) em %.1f s' % (com, len(roms), len(capas), time.time() - t0))
