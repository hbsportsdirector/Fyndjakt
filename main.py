"""Fyndjakt – letar begagnade fynd som passar dina profiler och samlar dem på en hemsida.

Varje "spår" i config.yaml (t.ex. inredningen och konstsamlingen) har egen profil,
egna sökningar och egna filter.

Kör:  python main.py            (vanlig körning)
      python main.py --torr     (hämtar annonser och skriver ut, utan AI och utan notiser)
"""
import argparse
import re
from dataclasses import replace
import sys
import time
from pathlib import Path

import yaml

from databas import Databas
import inspect

from sources import Annons, auctionet, bukowskis, myrorna, stadsmissionen, tradera

ROT = Path(__file__).parent
STATISTIK: dict = {}
KORTA: dict = {}      # korta profiler per (spår, kategori)
EXPORT: dict = {}     # användare, reaktioner m.m. från databasen


def las_config() -> dict:
    with open(ROT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg.get("spar"):
        raise SystemExit("config.yaml saknar 'spar'.")
    for sid, spar in cfg["spar"].items():
        spar.setdefault("namn", sid)
        spar["profil"] = bygg_profil(spar)
        spar["profil_bas"] = spar["profil"]  # före reaktioner och lärdomar – används för kategoriprofilerna
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
    if not delar and spar.get("flipp"):
        # Flipp-spår betygsätts på pris (flipp.py) – profilen används inte vid bedömningen.
        return f"Flipp-spåret «{spar.get('namn')}»: köp under typiskt slutpris och sälj vidare."
    if not delar:
        raise SystemExit(f"Spåret {spar.get('namn')} saknar profil.")
    return "\n\n".join(delar)


def agare_av(spar: dict) -> str:
    """Vem spåret tillhör: "" för spåren i config.yaml (administratören), annars användarens id."""
    return spar.get("agare") or ""


def hamta_alla(cfg: dict, pausade: set | None = None) -> list[Annons]:
    kallor = cfg.get("kallor", {})
    std_sidor = cfg.get("sidor_per_sokning", 3)
    aktiva = []
    for namn, modul in [("Auctionet", auctionet), ("Bukowskis", bukowskis), ("Myrorna", myrorna),
                        ("Stadsmissionen", stadsmissionen)]:
        if kallor.get(namn.lower(), True):
            aktiva.append((namn, modul.sok, "sidor" in inspect.signature(modul.sok).parameters))
    if kallor.get("tradera", True):
        if tradera.aktiverad():
            aktiva.append(("Tradera", tradera.sok, True))
        else:
            print("Tradera: ingen nyckel satt (TRADERA_APP_ID/TRADERA_APP_KEY) – hoppar över.")

    alla: dict[str, Annons] = {}
    cache: dict[tuple, list[Annons]] = {}  # samma sökning i flera användares spår görs bara en gång
    # Spåret med mest specifika sökord (namngivna formgivare) söks först och "äger" föremål som
    # båda spåren hittar – annars hamnar t.ex. en Skultuna-ljusstake under inredningen.
    # Varje användare har sin egen uppsättning; samma annons kan alltså finnas hos flera användare.
    ordning = sorted(cfg["spar"].items(), key=lambda kv: kv[1].get("prioritet", 0), reverse=True)
    for sid, spar in ordning:
        agare = agare_av(spar)
        prefix = f"{agare[:8]}|" if agare else ""
        if spar.get("flipp"):
            prefix += f"{sid}|"  # eget exemplar – flipp-spåret tar aldrig annonser från smakspåren (eller tvärtom)
        sidor = min(spar.get("sidor", std_sidor), std_sidor)
        print(f"\n— {spar['namn']} —")
        for namn, sok, tar_sidor in aktiva:
            for kategori, fragor in spar["sokningar"].items():
                for fraga in fragor:
                    if pausade and (sid, fraga) in pausade:
                        continue  # gav aldrig något – pausat (kan slås på igen i appen)
                    st = STATISTIK.setdefault(namn, {"sokningar": 0, "traffar": 0, "fel": 0, "felexempel": []})
                    nyckel = (namn, fraga.lower(), sidor)
                    if nyckel not in cache:
                        st["sokningar"] += 1
                        try:
                            cache[nyckel] = sok(fraga, kategori, sidor=sidor) if tar_sidor else sok(fraga, kategori)
                        except Exception as e:  # en trasig sökning ska inte stoppa resten
                            print(f"  {namn} '{fraga}': fel – {e}")
                            st["fel"] += 1
                            if len(st["felexempel"]) < 5:
                                st["felexempel"].append(f"{fraga}: {type(e).__name__}: {str(e)[:200]}")
                            cache[nyckel] = []
                            continue
                        st["traffar"] += len(cache[nyckel])
                    traffar = cache[nyckel]
                    for a in traffar:
                        b = replace(a, sokord=a.sokord or fraga, spar=sid, kategori=kategori, prefix=prefix)
                        alla.setdefault(b.nyckel, b)  # första spåret (per användare) som hittar den äger den
                    if traffar or namn != "Stadsmissionen":
                        print(f"  {namn:14} {fraga:32} {len(traffar):3} träffar")
    return list(alla.values())


def forfiltrera(a: Annons, cfg: dict, spar: dict | None = None) -> str | None:
    """Returnerar en anledning om annonsen ska sorteras bort utan AI."""
    spar = spar or {}
    text = f"{a.titel} {a.beskrivning}".lower()
    titel = a.titel.lower()
    if spar.get("uteslut_bara_titel"):
        # Spårets ord gäller bara titeln och ord från början ("nytt" ska inte fälla "som nytt skick" i
        # beskrivningen, men "Nytt i kartong" i titeln). Korta ord (under 5 tecken) måste vara hela ord –
        # "nytt" fäller inte "nyttig"; längre ord får böjas ("oanvänd" fäller "oanvända").
        for ord_ in spar.get("uteslut_ord", []):
            slut = r"(?![\wåäö])" if len(ord_) < 5 else ""
            if re.search(rf"(?<![\wåäö]){re.escape(ord_.lower())}{slut}", titel):
                return f"titeln innehåller '{ord_}'"
        spar = {**spar, "uteslut_ord": []}
    for ord_ in cfg.get("uteslut_ord", []) + spar.get("uteslut_ord", []):
        if ord_.lower() in text:
            return f"innehåller '{ord_}'"
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
    """Varvar källor, spår och kategorier så att taket per körning inte går åt till en enda sorts sak."""
    grupper: dict[tuple, list[Annons]] = {}
    for a in annonser:
        grupper.setdefault((a.kalla, a.spar, a.kategori), []).append(a)
    ut = []
    while any(grupper.values()):
        for lista in grupper.values():
            if lista:
                ut.append(lista.pop(0))
    return ut


def begransa(kandidater: list[Annons], cfg: dict) -> list[Annons]:
    """Taket för antal bedömningar gäller per användare, så att ingen tar slut på de andras."""
    grupper: dict[str, list[Annons]] = {}
    for a in kandidater:
        grupper.setdefault(agare_av(cfg["spar"][a.spar]), []).append(a)
    ut = []
    for agare, lista in grupper.items():
        tak = (cfg.get("max_bedomningar_per_anvandare", 150) if agare
               else cfg.get("max_bedomningar_per_korning", 150))
        if len(lista) > tak:
            print(f"Bedömer {tak} av {len(lista)} för {agare[:8] or 'huvudspåren'} – resten tas nästa körning.")
        ut += blanda_kategorier(lista)[:tak]
    return ut


def tradera_orter(db: Databas, max_antal: int = 600) -> int:
    """Fyller i säljarens ort för aktiva Tradera-fynd som sparades innan orten hämtades."""
    if not tradera.aktiverad():
        return 0
    rader = db.con.execute(
        "SELECT nyckel FROM sedda WHERE kalla = 'tradera' AND plats = 'Tradera' AND betyg >= 8 "
        "AND (slutar_ts IS NULL OR slutar_ts > ?) LIMIT ?", (int(time.time()), max_antal)).fetchall()

    def en(rad):
        try:
            return rad[0], tradera.ort_ur(tradera.detaljer(rad[0].rsplit(":", 1)[-1]))
        except Exception:
            return rad[0], ""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as pool:
        klara = [(f"Tradera, {ort}", n) for n, ort in pool.map(en, rader) if ort]
    db.con.executemany("UPDATE sedda SET plats = ? WHERE nyckel = ?", klara)
    db.con.commit()
    return len(klara)


def prisjamfor(db: Databas, cfg: dict) -> None:
    """Hämtar vad liknande föremål sålts för på Auctionet, för fynden som visas på sidan."""
    import bedomning
    import prisjamforelse
    # Flipp-fynd prisjämförs redan när de betygsätts (betyget bygger på jämförelsen).
    rader = [r for r in db.behover_jamforelse(cfg.get("sajt_min_betyg", 8))
             if not cfg["spar"].get(r.get("spar") or "", {}).get("flipp")][: cfg.get("max_prisjamforelser_per_korning", 120)]
    if not rader:
        return
    print(f"\nPrisjämförelse för {len(rader)} fynd …")
    klient = None
    cache: dict[str, dict | None] = {}
    for r in rader:
        fras = r.get("jamforsok") or ""
        try:
            if not fras:
                klient = klient or bedomning._klient()
                fras = bedomning.foresla_jamforsok(r["titel"], cfg["modell"], klient)
            if fras.lower() not in cache:
                cache[fras.lower()] = prisjamforelse.jamfor(fras)
            res = cache[fras.lower()]
            db.spara_jamforelse(r["nyckel"], fras, res)
            if res:
                print(f"  {fras:28} median {res['median']} kr ({res['antal']} sålda)")
        except Exception as e:
            print(f"  Prisjämförelse misslyckades för {r['titel'][:40]}: {e}")
    STATISTIK["Prisjämförelse"] = {"fynd": len(rader), "med_data": sum(1 for v in cache.values() if v)}


def spara_rapport(totalt: int, nya: int, bedomda: int, traffar: int) -> None:
    """Liten rapport i repot så att man ser hur varje källa gick, utan att läsa loggar."""
    import json
    from datetime import datetime
    rapport = {
        "tid": datetime.now().isoformat(timespec="seconds"),
        "annonser_totalt": totalt, "nya": nya, "bedomda": bedomda, "nya_traffar": traffar,
        "kallor": STATISTIK,
        "kostnad": __import__("bedomning").kostnadsrapport(),
        "stadsmissionen_katalog": len(stadsmissionen._katalog or []),
    }
    (ROT / "data" / "senaste_korning.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")


def fran_rad(r: dict) -> Annons:
    """En sparad rad i databasen som annons igen (för att kunna bedömas om)."""
    import json
    nyckel = r["nyckel"]
    prefix = nyckel[:nyckel.rindex("|") + 1] if "|" in nyckel else ""
    kalla, _, id_ = nyckel[len(prefix):].partition(":")
    try:
        bilder = json.loads(r.get("bilder") or "[]")
    except ValueError:
        bilder = []
    return Annons(kalla=kalla, id=id_, titel=r["titel"], url=r["url"], pris=r.get("pris"),
                  pris_text=r.get("pris_text") or "", bilder=bilder, plats=r.get("plats") or "",
                  slutar=r.get("slutar") or "", slutar_ts=r.get("slutar_ts"), kategori=r.get("kategori") or "",
                  sokord=r.get("sokord") or "", spar=r["spar"], prefix=prefix)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--torr", action="store_true", help="Ingen AI, inga notiser, inget sparas")
    args = p.parse_args()

    cfg = las_config()
    export = None
    try:
        import smak
        export = smak.hamta(cfg)
        EXPORT.update(export or {})
        smak.tillampa(cfg, export)
        import smakanalys
        try:
            import bedomning as _b
            klient_analys = None if args.torr else _b._klient()
        except Exception:
            klient_analys = None
        STATISTIK["Smakanalys"] = smakanalys.analysera(cfg, export, klient_analys)
        import kategoriprofil
        KORTA.update(kategoriprofil.bygg(cfg, klient_analys))
    except Exception as e:  # lärandet får aldrig stoppa körningen
        print(f"Min smak: kunde inte läsa reaktioner – {e}")
        STATISTIK["Min smak"] = {"fel": str(e)[:200]}
    db = Databas()
    db.rensa_gamla()

    print("Hämtar annonser …")
    import sokordsvard
    pausade = sokordsvard.pausa(cfg, db, export)
    STATISTIK["Pausade sökord"] = len(pausade)
    annonser = hamta_alla(cfg, pausade)
    nystart = {k: str(v) for k, v in (cfg.get("smak_nystart") or {}).items() if k in cfg["spar"]}
    vantar = db.vantande(nystart)
    nya = [a for a in annonser if a.nyckel in vantar or not db.finns(a.nyckel)]
    # Flipp-spår med omidentifiera_fore: fynd identifierade före tidpunkten (t.ex. med en äldre instruktion)
    # identifieras om en gång.
    om_id = set()
    for sid, sp in cfg["spar"].items():
        if sp.get("flipp") and sp.get("omidentifiera_fore"):
            om_id |= db.bedomda_fore(sid, str(sp["omidentifiera_fore"]))
    if om_id:
        redan = {a.nyckel for a in nya}
        nya += [a for a in annonser if a.nyckel in om_id and a.nyckel not in redan]
    STATISTIK["Väntande från tidigare"] = sum(1 for a in nya if a.nyckel in vantar)
    sokord_stat = sokordsvard.statistik(db)
    print(f"\n{len(annonser)} annonser totalt, {len(nya)} nya (varav {STATISTIK['Väntande från tidigare']} väntande).")

    if args.torr:
        for a in nya[:25]:
            print(f"- [{a.spar}/{a.kalla}] {a.titel[:70]} | {a.pris_text} | {a.url}")
        return 0

    # Importeras här så att torrkörning fungerar utan nycklar.
    import bedomning
    import kategoriprofil

    def profil_for(a):
        """Kort profil för annonsens kategori (+ lärdomar och reaktioner i kategorin), annars hela profilen."""
        return kategoriprofil.profil_for(a, cfg, EXPORT or None, KORTA)
    import notis
    import sajt

    kandidater, flipp_kand = [], []
    for a in nya:
        skal = forfiltrera(a, cfg, cfg["spar"][a.spar])
        if skal:
            db.spara(a, -1, skal)
        elif cfg["spar"][a.spar].get("flipp"):
            flipp_kand.append(a)  # betygsätts på pris (flipp.py), inte mot en smakprofil
        else:
            kandidater.append(a)

    # Samma föremål som redan bedömts (t.ex. återpublicerat på Tradera) får sitt tidigare betyg – inget nytt anrop.
    ateranvanda, traffar = 0, []
    kvar_efter = []
    for a in kandidater:
        tidigare = db.tidigare_bedomning(a, efter=nystart.get(a.spar, ""))
        if tidigare:
            a.jamforsok = tidigare.get("jamforsok") or ""
            bra = tidigare["betyg"] >= cfg.get("min_betyg", 8)
            db.spara(a, tidigare["betyg"], tidigare["motivering"], bra)
            if bra:
                traffar.append((tidigare["betyg"], a, tidigare["motivering"]))
            ateranvanda += 1
        else:
            kvar_efter.append(a)
    kandidater = kvar_efter
    STATISTIK["Återanvända betyg"] = ateranvanda

    # Den egna, gratis modellen (tränad på Claudes tidigare bedömningar) sorterar bort det mycket osannolika.
    if cfg.get("egen_modell", True) and kandidater:
        import egen_modell
        modeller = egen_modell.trana_per_spar(db, nystart=nystart)
        kandidater, bort = egen_modell.sall(modeller, kandidater)
        for a in bort:
            db.spara(a, 2, "Sållad bort av egna modellen")
        STATISTIK["Egen modell"] = {"bortsorterade": len(bort), "spår med modell": len(modeller)}
        print(f"Egen modell: {len(bort)} sorterade bort utan Claude.")

    # Fler kandidater än vad som hinner granskas med bilder? Sålla först på titel och pris (billigt),
    # så att de dyra granskningarna går till det som har chans. Uppenbart fel sparas som kollat.
    tak_totalt = cfg.get("max_bedomningar_per_korning", 150) + cfg.get("max_bedomningar_per_anvandare", 150) * \
        len({cfg["spar"][a.spar].get("agare") for a in kandidater if cfg["spar"][a.spar].get("agare")})
    if cfg.get("sallning", True) and len(kandidater) > tak_totalt:
        try:
            grupper: dict = {}
            for a in kandidater:
                sp = cfg["spar"][a.spar]
                regler = sp.get("bedomningsregler") or (cfg.get("bedomningsregler_anvandare") if sp.get("agare") else None)
                if vantar.get(a.nyckel) is not None:  # redan sållad en tidigare natt (med nuvarande smak)
                    continue
                grupper.setdefault((a.spar, a.kategori), (profil_for(a), [], regler))[1].append(a)
            snabb = bedomning.salla(grupper, cfg["modell"], bedomning._klient()) if grupper else {}
            snabb.update({a.nyckel: vantar[a.nyckel] for a in kandidater if vantar.get(a.nyckel) is not None})
            grans = cfg.get("sallning_min_betyg", 6)
            kvar = []
            for a in kandidater:
                s = snabb.get(a.nyckel)
                if s is not None and s < grans:
                    db.spara(a, s, "Sållad bort på titeln")
                else:
                    kvar.append(a)
            # Mest lovande först (osållade sist), så att taket används på det bästa.
            import sajt as _sajt
            kvar.sort(key=lambda a: (-(snabb.get(a.nyckel) if a.nyckel in snabb else grans - 0.5),
                                     0 if _sajt.region_for(a.kalla, a.plats)[1] == "Stockholm" else 1))
            # Bildgranska bara de mest lovande per sökord – men sökord som ofta ger fynd får fler.
            # Det som inte hinns med väntar och tas med igen nästa körning.
            max_per = cfg.get("granska_max_per_sokord", 10)

            def tak_for(nyckel):
                bedomda, fynd = sokord_stat.get(nyckel, (0, 0))
                andel = fynd / bedomda if bedomda >= 20 else 0
                return int(max_per * (2 if andel >= 0.3 else 1.5 if andel >= 0.15 else 1))
            per_sokord: dict[tuple, int] = {}
            gallrad = []
            for a in kvar:
                nyckel = (a.spar, a.sokord)
                per_sokord[nyckel] = per_sokord.get(nyckel, 0) + 1
                if max_per and a.nyckel in snabb and per_sokord[nyckel] > tak_for(nyckel):
                    db.spara(a, min(snabb[a.nyckel], 7), "Ej bildgranskad – fler lovande på samma sökord")
                else:
                    gallrad.append(a)
            STATISTIK["Sållning"] = {"sållade": len(snabb), "bortsållade": len(kandidater) - len(kvar),
                                     "över gränsen per sökord": len(kvar) - len(gallrad), "kvar": len(gallrad)}
            kvar = gallrad
            kandidater = kvar
        except Exception as e:
            print(f"  Sållningen misslyckades ({e}) – går vidare utan den.")
    kandidater = begransa(kandidater, cfg)

    # Kön: annonser som klarat titelsållningen tidigare men aldrig hann bildgranskas. De behöver inte hittas
    # i nattens sökningar igen – de bedöms direkt från databasen, bäst först, så länge budgeten räcker.
    plats_kvar = cfg.get("max_bedomningar_per_korning", 800) - len(kandidater)
    fran_kon = min(cfg.get("max_fran_kon_per_korning", 300), max(0, plats_kvar))
    if fran_kon:
        redan = {a.nyckel for a in kandidater}
        rader = db.con.execute(
            "SELECT * FROM sedda WHERE motivering LIKE 'Ej bildgranskad%' AND (slutar_ts IS NULL OR slutar_ts > ?) "
            "ORDER BY betyg DESC, sedd DESC", (int(time.time()) + 3600,)).fetchall()
        ko = [fran_rad(dict(r)) for r in rader if r["nyckel"] not in redan and r["spar"] in cfg["spar"]][:fran_kon]
        kandidater += ko
        STATISTIK["Från kön"] = len(ko)
        print(f"Kön: {len(ko)} väntande annonser bedöms (av {len(rader)}).")

    # Ny smak i ett spår: aktiva fynd som bedömdes med den gamla smaken betygsätts om en gång.
    # omvardera_fore {spår: tid}: betygsätt om aktiva fynd från före tidpunkten (t.ex. efter skärpta regler),
    # utan att nollställa det appen lärt sig som smak_nystart gör.
    omv = {**nystart, **{k: str(v) for k, v in (cfg.get("omvardera_fore") or {}).items() if k in cfg["spar"]}}
    if omv:
        redan = {a.nyckel for a in kandidater}
        om = [r for r in db.att_omvardera(omv, cfg.get("min_betyg", 8),
                                          cfg.get("max_omvarderingar_per_korning", 1500)) if r["nyckel"] not in redan]
        for r in om:
            kandidater.append(fran_rad(r))
        if om:
            STATISTIK["Omvärdering med ny smak"] = len(om)
            print(f"Ny smak: {len(om)} aktiva fynd betygsätts om.")

    # Vissa källor visar ort och beskrivning bara på annonssidan – hämta dem för de som ska bedömas.
    moduler = {"bukowskis": bukowskis, "tradera": tradera}
    def berika(a):
        modul = moduler.get(a.kalla)
        if modul and hasattr(modul, "berika"):
            try:
                modul.berika(a)
            except Exception as e:
                print(f"  Kunde inte läsa annonssidan för {a.titel[:40]}: {e}")
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(berika, kandidater))

    if kandidater:
        klient = bedomning._klient()

        def regler_for(a):
            spar = cfg["spar"][a.spar]
            return spar.get("bedomningsregler") or (cfg.get("bedomningsregler_anvandare") if spar.get("agare") else None)

        # Först allt i en batch (halva priset), fem annonser per anrop så att profilen bara skickas en gång
        # per fem annonser; det som inte blir klart där bedöms direkt, åtta åt gången.
        fardiga: dict[str, tuple] = {}
        slut = False
        if cfg.get("batch", True):
            try:
                gjort = bedomning.bedom_grupper(kandidater, profil_for, regler_for,
                                                cfg["modell"], klient, cfg.get("gruppstorlek", bedomning.GRUPPSTORLEK))
                fardiga = {f"a{i}": r for i, r in gjort.items()}
            except bedomning.SlutPaKrediter:
                slut = True
            except Exception as e:
                print(f"  Batch misslyckades ({e}) – bedömer med vanliga anrop.")
        saknas = [] if slut else [(f"a{i}", a, profil_for(a), regler_for(a))
                                  for i, a in enumerate(kandidater) if f"a{i}" not in fardiga]
        STATISTIK["Bedömning"] = {"batch": len(fardiga), "direkt": len(saknas)}
        if saknas:
            try:
                fardiga.update(bedomning.bedom_parallellt(saknas, cfg["modell"], klient))
            except bedomning.SlutPaKrediter:
                slut = True
        if slut:
            print("  ⚠ Anthropic-kontot har slut på krediter – inga bedömningar kunde göras.")
            STATISTIK["Varning"] = "Slut på krediter hos Anthropic – fyll på under Plans & Billing."
        for i, a in enumerate(kandidater, 1):
            resultat = fardiga.get(f"a{i - 1}")
            if not resultat:
                continue  # sparas inte – försöker igen nästa gång
            betyg, motivering, a.jamforsok = resultat
            bra = betyg >= cfg.get("min_betyg", 8)
            db.spara(a, betyg, motivering, bra)
            print(f"  [{i:3}] {betyg:2}/10 [{a.spar}] {a.titel[:60]}")
            if bra:
                traffar.append((betyg, a, motivering))

    # Flipp-spåret: Claude identifierar, Auctionet ger typiskt slutpris, koden sätter betyget.
    import flipp
    flipp_tio = []
    try:
        STATISTIK["Flipp"] = {"priser uppdaterade": flipp.uppdatera_priser(annonser, db, cfg)}
        if flipp_kand and not STATISTIK.get("Varning"):
            flipp_tio = flipp.bedom(flipp_kand, db, cfg, bedomning._klient(), berika, STATISTIK["Flipp"])
            STATISTIK["Flipp"].update({"kandidater": len(flipp_kand), "betyg 10": len(flipp_tio)})
    except bedomning.SlutPaKrediter:
        STATISTIK["Varning"] = "Slut på krediter hos Anthropic – fyll på under Plans & Billing."
    except Exception as e:  # flipp-spåret får aldrig stoppa de andra spåren
        print(f"Flipp-spåret misslyckades: {e}")
        STATISTIK["Flipp"] = {"fel": str(e)[:200]}

    try:
        STATISTIK["Tradera-orter ifyllda"] = tradera_orter(db)
    except Exception as e:
        print(f"  Kunde inte fylla i Tradera-orter: {e}")
    prisjamfor(db, cfg)

    # Hemsidan byggs om varje gång, även om inget nytt hittades (utgångna annonser försvinner).
    sajt.bygg(db, cfg)
    try:
        import smak
        egna_fynd = sajt.anvandarfynd(db, cfg)
        smak.publicera(cfg, egna_fynd)
        STATISTIK["Notiser"] = smak.notifiera(cfg, export, egna_fynd)
        if STATISTIK.get("Varning"):
            smak.varna_admin(cfg, export, STATISTIK["Varning"])
    except Exception as e:
        print(f"Kunde inte lägga upp användarnas fynd: {e}")
        STATISTIK["Egna fynd"] = {"fel": str(e)[:200]}
    else:
        # Miniatyrer för de upplagda fynden (bilderna från bedömningen återanvänds), och städning.
        try:
            import bilder
            STATISTIK["Miniatyrer"] = bilder.synka(cfg, paus=0.3)
            STATISTIK["Miniatyrer"]["borttagna"] = bilder.stada(cfg)
        except Exception as e:
            print(f"Kunde inte spara miniatyrer: {e}")
            STATISTIK["Miniatyrer"] = {"fel": str(e)[:200]}

    traffar.sort(key=lambda t: t[0], reverse=True)
    if notis.aktiverad():
        for betyg, a, motivering in traffar:
            if agare_av(cfg["spar"][a.spar]):
                continue  # Telegram-notiserna går bara till administratören
            try:
                notis.skicka(a, betyg, motivering)
                time.sleep(1)
            except Exception as e:
                print(f"  Kunde inte skicka notis: {e}")
        for _, a, median in flipp_tio:
            if agare_av(cfg["spar"][a.spar]):
                continue
            try:
                notis.skicka_text(flipp.notistext(a, median))
                time.sleep(1)
            except Exception as e:
                print(f"  Kunde inte skicka flipp-notis: {e}")
    else:
        print("Telegram är inte inställt – hoppar över notiser.")

    print(f"\nKlart: {len(kandidater)} bedömda, {len(traffar)} nya träffar.")
    spara_rapport(len(annonser), len(nya), len(kandidater), len(traffar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
