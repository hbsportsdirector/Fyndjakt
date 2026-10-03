"""Fyndjakt – letar begagnade fynd som passar din stil och skickar dem till Telegram.

Kör:  python main.py            (vanlig körning)
      python main.py --torr     (hämtar annonser och skriver ut, utan AI och utan notiser)
"""
import argparse
import sys
import time
from pathlib import Path

import yaml

from databas import Databas
from sources import Annons, auctionet, tradera

ROT = Path(__file__).parent


def las_config() -> dict:
    with open(ROT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["stilprofil"] = bygg_stilprofil(cfg)
    return cfg


def bygg_stilprofil(cfg: dict) -> str:
    """Stilen hämtas från stilfilen (t.ex. stil.md) plus eventuella tillägg i config."""
    delar = []
    stilfil = cfg.get("stilfil")
    if stilfil:
        sokvag = ROT / stilfil
        if not sokvag.exists():
            raise SystemExit(f"Hittar inte stilfilen {stilfil} – lägg den bredvid config.yaml.")
        delar.append(sokvag.read_text(encoding="utf-8").strip())
    if cfg.get("stilprofil"):
        delar.append(str(cfg["stilprofil"]).strip())
    if cfg.get("tillagg"):
        delar.append("Viktigt vid bedömningen:\n" + str(cfg["tillagg"]).strip())
    if not delar:
        raise SystemExit("Ingen stil angiven – sätt 'stilfil' i config.yaml.")
    return "\n\n".join(delar)


def hamta_alla(cfg: dict) -> list[Annons]:
    kallor = cfg.get("kallor", {})
    aktiva = []
    if kallor.get("auctionet", True):
        aktiva.append(("Auctionet", auctionet.sok))
    if kallor.get("tradera", True):
        if tradera.aktiverad():
            aktiva.append(("Tradera", tradera.sok))
        else:
            print("Tradera: ingen nyckel satt (TRADERA_APP_ID/TRADERA_APP_KEY) – hoppar över.")

    alla: dict[str, Annons] = {}
    for namn, sok in aktiva:
        for kategori, fragor in cfg["sokningar"].items():
            for fraga in fragor:
                try:
                    traffar = sok(fraga, kategori)
                except Exception as e:  # en trasig sökning ska inte stoppa resten
                    print(f"  {namn} '{fraga}': fel – {e}")
                    continue
                for a in traffar:
                    alla.setdefault(a.nyckel, a)
                print(f"  {namn:9} {fraga:28} {len(traffar):3} träffar")
    return list(alla.values())


def forfiltrera(a: Annons, cfg: dict) -> str | None:
    """Returnerar en anledning om annonsen ska sorteras bort utan AI."""
    text = f"{a.titel} {a.beskrivning}".lower()
    for ord_ in cfg.get("uteslut_ord", []):
        if ord_.lower() in text:
            return f"innehåller '{ord_}'"
    max_pris = cfg.get("max_pris") or 0
    if max_pris and a.pris and a.pris > max_pris:
        return f"pris {a.pris} > {max_pris}"
    return None


def blanda_kategorier(annonser: list[Annons]) -> list[Annons]:
    """Varvar kategorierna så att taket per körning inte bara går åt till möbler."""
    grupper: dict[str, list[Annons]] = {}
    for a in annonser:
        grupper.setdefault(a.kategori, []).append(a)
    ut = []
    while any(grupper.values()):
        for lista in grupper.values():
            if lista:
                ut.append(lista.pop(0))
    return ut


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
            print(f"- [{a.kalla}] {a.titel[:70]} | {a.pris_text} | {a.url}")
        return 0

    # Importeras här så att torrkörning fungerar utan nycklar.
    import bedomning
    import notis
    import sajt

    kandidater = []
    for a in nya:
        skal = forfiltrera(a, cfg)
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
            try:
                betyg, motivering = bedomning.bedom(a, cfg["stilprofil"], cfg["modell"], klient)
            except Exception as e:
                print(f"  [{i}] fel vid bedömning av {a.titel[:50]}: {e}")
                continue  # sparas inte – försöker igen nästa gång
            bra = betyg >= cfg.get("min_betyg", 7)
            db.spara(a, betyg, motivering, bra)
            print(f"  [{i:3}] {betyg:2}/10 {a.titel[:60]}")
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
        if not traffar and kandidater:
            try:
                notis.skicka_text(f"🔎 Fyndjakt: {len(kandidater)} nya annonser granskade idag – inget som passade riktigt.")
            except Exception:
                pass
    else:
        print("Telegram är inte inställt – hoppar över notiser.")

    print(f"\nKlart: {len(kandidater)} bedömda, {len(traffar)} nya träffar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
