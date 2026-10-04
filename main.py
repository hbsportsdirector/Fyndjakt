"""Fyndjakt – letar begagnade fynd som passar dina profiler och samlar dem på en hemsida.

Varje "spår" i config.yaml (t.ex. inredningen och konstsamlingen) har egen profil,
egna sökningar och egna filter.

Kör:  python main.py            (vanlig körning)
      python main.py --torr     (hämtar annonser och skriver ut, utan AI och utan notiser)
"""
import argparse
import sys
import time
from pathlib import Path

import yaml

from databas import Databas
import inspect

from sources import Annons, auctionet, bukowskis, myrorna, stadsmissionen, tradera

ROT = Path(__file__).parent
STATISTIK: dict = {}


def las_config() -> dict:
    with open(ROT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg.get("spar"):
        raise SystemExit("config.yaml saknar 'spar'.")
    for sid, spar in cfg["spar"].items():
        spar.setdefault("namn", sid)
        spar["profil"] = bygg_profil(spar)
    return cfg


def bygg_profil(spar: dict) -> str:
    """Profilen = profilfilen (t.ex. stil.md) + tillägg + det kunden redan har."""
    delar = []
    fil = spar.get("profilfil")
    if fil:
        sokvag = ROT / fil
        if not sokvag.exists():
            raise SystemExit(f"Hittar inte profilfilen {fil} – lägg den bredvid config.yaml.")
        delar.append(sokvag.read_text(encoding="utf-8").strip())
    if spar.get("tillagg"):
        delar.append("Viktigt vid bedömningen:\n" + str(spar["tillagg"]).strip())
    if spar.get("har_redan"):
        delar.append("Kunden HAR REDAN följande – ge 0–3 åt samma typ av föremål:\n- "
                     + "\n- ".join(spar["har_redan"]))
    if not delar:
        raise SystemExit(f"Spåret {spar.get('namn')} saknar profil.")
    return "\n\n".join(delar)


def hamta_alla(cfg: dict) -> list[Annons]:
    kallor = cfg.get("kallor", {})
    sidor = cfg.get("sidor_per_sokning", 3)
    aktiva = []
    for namn, modul in [("Auctionet", auctionet), ("Bukowskis", bukowskis), ("Myrorna", myrorna),
                        ("Stadsmissionen", stadsmissionen)]:
        if kallor.get(namn.lower(), True):
            sok = modul.sok
            if "sidor" in inspect.signature(sok).parameters:
                sok = (lambda f: lambda q, k: f(q, k, sidor=sidor))(sok)
            aktiva.append((namn, sok))
    if kallor.get("tradera", True):
        if tradera.aktiverad():
            aktiva.append(("Tradera", tradera.sok))
        else:
            print("Tradera: ingen nyckel satt (TRADERA_APP_ID/TRADERA_APP_KEY) – hoppar över.")

    alla: dict[str, Annons] = {}
    for sid, spar in cfg["spar"].items():
        print(f"\n— {spar['namn']} —")
        for namn, sok in aktiva:
            for kategori, fragor in spar["sokningar"].items():
                for fraga in fragor:
                    st = STATISTIK.setdefault(namn, {"sokningar": 0, "traffar": 0, "fel": 0, "felexempel": []})
                    st["sokningar"] += 1
                    try:
                        traffar = sok(fraga, kategori)
                    except Exception as e:  # en trasig sökning ska inte stoppa resten
                        print(f"  {namn} '{fraga}': fel – {e}")
                        st["fel"] += 1
                        if len(st["felexempel"]) < 5:
                            st["felexempel"].append(f"{fraga}: {type(e).__name__}: {str(e)[:200]}")
                        continue
                    st["traffar"] += len(traffar)
                    for a in traffar:
                        a.sokord = a.sokord or fraga
                        a.spar = sid
                        alla.setdefault(a.nyckel, a)  # första spåret som hittar den äger den
                    if traffar or namn != "Stadsmissionen":
                        print(f"  {namn:14} {fraga:32} {len(traffar):3} träffar")
    return list(alla.values())


def forfiltrera(a: Annons, cfg: dict, spar: dict | None = None) -> str | None:
    """Returnerar en anledning om annonsen ska sorteras bort utan AI."""
    spar = spar or {}
    text = f"{a.titel} {a.beskrivning}".lower()
    for ord_ in cfg.get("uteslut_ord", []) + spar.get("uteslut_ord", []):
        if ord_.lower() in text:
            return f"innehåller '{ord_}'"
    titel = a.titel.lower()
    for ord_ in spar.get("har_redan_ord", []):
        if ord_.lower() in titel:
            return f"har redan ('{ord_}')"
    if cfg.get("bara_sverige") and a.valuta != "SEK":
        return f"utanför Sverige ({a.valuta})"
    max_pris = spar.get("max_pris", cfg.get("max_pris")) or 0
    if max_pris and a.pris and a.pris > max_pris:
        return f"pris {a.pris} > {max_pris}"
    return None


def blanda_kategorier(annonser: list[Annons]) -> list[Annons]:
    """Varvar spår och kategorier så att taket per körning inte går åt till en enda sorts sak."""
    grupper: dict[tuple, list[Annons]] = {}
    for a in annonser:
        grupper.setdefault((a.spar, a.kategori), []).append(a)
    ut = []
    while any(grupper.values()):
        for lista in grupper.values():
            if lista:
                ut.append(lista.pop(0))
    return ut


def spara_rapport(totalt: int, nya: int, bedomda: int, traffar: int) -> None:
    """Liten rapport i repot så att man ser hur varje källa gick, utan att läsa loggar."""
    import json
    from datetime import datetime
    rapport = {
        "tid": datetime.now().isoformat(timespec="seconds"),
        "annonser_totalt": totalt, "nya": nya, "bedomda": bedomda, "nya_traffar": traffar,
        "kallor": STATISTIK,
        "stadsmissionen_katalog": len(stadsmissionen._katalog or []),
    }
    (ROT / "data" / "senaste_korning.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--torr", action="store_true", help="Ingen AI, inga notiser, inget sparas")
    args = p.parse_args()

    cfg = las_config()
    db = Databas()
    db.rensa_gamla()

    print("Hämtar annonser …")
    annonser = hamta_alla(cfg)
    nya = [a for a in annonser if not db.finns(a.nyckel)]
    print(f"\n{len(annonser)} annonser totalt, {len(nya)} nya.")

    if args.torr:
        for a in nya[:25]:
            print(f"- [{a.spar}/{a.kalla}] {a.titel[:70]} | {a.pris_text} | {a.url}")
        return 0

    # Importeras här så att torrkörning fungerar utan nycklar.
    import bedomning
    import notis
    import sajt

    kandidater = []
    for a in nya:
        skal = forfiltrera(a, cfg, cfg["spar"][a.spar])
        if skal:
            db.spara(a, -1, skal)
        else:
            kandidater.append(a)

    tak = cfg.get("max_bedomningar_per_korning", 150)
    if len(kandidater) > tak:
        print(f"Bedömer {tak} av {len(kandidater)} – resten tas nästa körning.")
    kandidater = blanda_kategorier(kandidater)[:tak]

    traffar = []
    if kandidater:
        klient = bedomning._klient()
        for i, a in enumerate(kandidater, 1):
            spar = cfg["spar"][a.spar]
            try:
                betyg, motivering = bedomning.bedom(a, spar["profil"], cfg["modell"], klient)
            except Exception as e:
                print(f"  [{i}] fel vid bedömning av {a.titel[:50]}: {e}")
                continue  # sparas inte – försöker igen nästa gång
            bra = betyg >= cfg.get("min_betyg", 8)
            db.spara(a, betyg, motivering, bra)
            print(f"  [{i:3}] {betyg:2}/10 [{a.spar}] {a.titel[:60]}")
            if bra:
                traffar.append((betyg, a, motivering))
            time.sleep(0.3)

    # Hemsidan byggs om varje gång, även om inget nytt hittades (utgångna annonser försvinner).
    sajt.bygg(db, cfg)

    traffar.sort(key=lambda t: t[0], reverse=True)
    if notis.aktiverad():
        for betyg, a, motivering in traffar:
            try:
                notis.skicka(a, betyg, motivering)
                time.sleep(1)
            except Exception as e:
                print(f"  Kunde inte skicka notis: {e}")
    else:
        print("Telegram är inte inställt – hoppar över notiser.")

    print(f"\nKlart: {len(kandidater)} bedömda, {len(traffar)} nya träffar.")
    spara_rapport(len(annonser), len(nya), len(kandidater), len(traffar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
