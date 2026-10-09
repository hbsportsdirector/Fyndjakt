"""En liten egen modell som lärt sig av Claudes tidigare bedömningar – kostar ingenting att köra.

Den läser bara titel, källa och pris och räknar ut hur troligt det är att annonsen blir ett fynd (8/10+).
Annonser som är MYCKET osannolika sorteras bort innan Claude ens tittar på titeln. Gränsen sätts så att
modellen på testdata behåller minst 98 % av de annonser som faktiskt blev fynd – hellre släppa igenom för
mycket än tappa något bra. Modellen tränas om varje körning (tar under en sekund) och används bara för spår
med tillräckligt mycket underlag.
"""
import math
import random
import re
from collections import Counter

MIN_RADER = 400
MIN_FYND = 30
BEHALL_ANDEL = 0.98  # andel av riktiga fynd som måste klara gränsen på testdata
MARGINAL = 1.5       # extra säkerhetsmarginal under gränsen (log-odds) – hellre släppa igenom än tappa fynd


def _drag(titel: str, kalla: str, pris) -> list[str]:
    ord_ = re.findall(r"[a-zåäöéü0-9]+", (titel or "").lower())
    ut = [o for o in ord_ if len(o) > 1]
    ut += [f"{a}_{b}" for a, b in zip(ord_, ord_[1:])]
    ut.append(f"källa:{kalla}")
    if pris:
        ut.append(f"pris:{min(int(math.log10(max(pris, 1)) * 2), 12)}")
    return ut


class Modell:
    """Multinomial naiv Bayes – enkel, snabb och förvånansvärt bra på korta titlar."""

    def __init__(self):
        self.ord = {0: Counter(), 1: Counter()}
        self.antal = Counter()
        self.grans = None

    def trana(self, rader: list[tuple[list[str], int]]):
        for drag, y in rader:
            self.ord[y].update(drag)
            self.antal[y] += 1
        self._sum = {y: sum(c.values()) for y, c in self.ord.items()}
        self._vokab = len(set(self.ord[0]) | set(self.ord[1])) or 1

    def poang(self, drag: list[str]) -> float:
        """log P(fynd) − log P(inte fynd)."""
        p = math.log((self.antal[1] + 1) / (self.antal[0] + 1))
        for d in drag:
            p += math.log((self.ord[1][d] + 1) / (self._sum[1] + self._vokab))
            p -= math.log((self.ord[0][d] + 1) / (self._sum[0] + self._vokab))
        return p


def trana_per_spar(db, seed: int = 1) -> dict[str, Modell]:
    """En modell per spår, med gräns vald på testdata. Spår med för lite underlag får ingen modell."""
    rader: dict[str, list] = {}
    for spar, titel, kalla, pris, betyg in db.con.execute(
            "SELECT spar, titel, kalla, pris, betyg FROM sedda WHERE betyg >= 0 AND spar IS NOT NULL "
            "AND motivering NOT LIKE 'Sållad bort av egna modellen%'"):  # lär bara av Claudes egna bedömningar
        rader.setdefault(spar, []).append((_drag(titel, kalla, pris), 1 if betyg >= 8 else 0))
    ut = {}
    rnd = random.Random(seed)
    for spar, lista in rader.items():
        if len(lista) < MIN_RADER or sum(y for _, y in lista) < MIN_FYND:
            continue
        rnd.shuffle(lista)
        skarning = int(len(lista) * 0.8)
        trana, test = lista[:skarning], lista[skarning:]
        m = Modell(); m.trana(trana)
        fynd = sorted(m.poang(d) for d, y in test if y == 1)
        if len(fynd) < 5:
            continue
        grans = fynd[int(len(fynd) * (1 - BEHALL_ANDEL))] - MARGINAL
        bort = sum(1 for d, y in test if y == 0 and m.poang(d) < grans) / max(1, sum(1 for _, y in test if y == 0))
        # Slutlig modell på allt underlag, med gränsen från testet.
        slut = Modell(); slut.trana(lista); slut.grans = grans
        slut.andel_bort = bort
        ut[spar] = slut
    return ut


def sall(modeller: dict[str, Modell], annonser: list) -> tuple[list, list]:
    """Delar upp i (behåll, sortera bort). Annonser i spår utan modell behålls."""
    behall, bort = [], []
    for a in annonser:
        m = modeller.get(a.spar)
        if m is not None and m.poang(_drag(a.titel, a.kalla, a.pris)) < m.grans:
            bort.append(a)
        else:
            behall.append(a)
    return behall, bort
