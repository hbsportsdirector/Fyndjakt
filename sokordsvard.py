"""Sökord som aldrig ger något pausas – så slipper appen leta, sålla och bedöma i onödan.

Ett sökord pausas när minst MIN_BEDOMDA annonser från det har bedömts utan ett enda fynd (8/10 eller mer).
Kunden ser de pausade sökorden under Mina bevakningar och kan slå på dem igen; det valet gäller då för alltid.
"""
MIN_BEDOMDA = 40


def statistik(db) -> dict[tuple, tuple[int, int]]:
    """{(spår, sökord): (bedömda, fynd)} – bedömda räknar även bortsållade, inte förfiltrerade (-1)."""
    ut = {}
    for spar, sokord, bedomda, fynd in db.con.execute(
            "SELECT spar, sokord, COUNT(*), SUM(betyg >= 8) FROM sedda WHERE betyg >= 0 GROUP BY spar, sokord"):
        if spar and sokord:
            ut[(spar, sokord)] = (bedomda, fynd or 0)
    return ut


def _val(export: dict | None, cfg: dict) -> dict[tuple, bool]:
    """Kundens egna val: {(spår, sökord): aktiv}. Gäller bara ägarens egna spår."""
    import smak
    ut = {}
    for v in (export or {}).get("sokord_val", []):
        spar = cfg["spar"].get(v.get("spar"))
        if spar is None:
            continue
        agare = smak._agare(spar, export)
        if v.get("user_id") in agare:
            ut[(v["spar"], v["sokord"])] = bool(v.get("aktiv"))
    return ut


def pausa(cfg: dict, db, export: dict | None) -> set[tuple]:
    """Markerar pausade sökord i varje spår (spar["pausade"]) och returnerar dem som {(spår, sökord)}."""
    stat = statistik(db)
    val = _val(export, cfg)
    pausade = set()
    for sid, spar in cfg["spar"].items():
        lista = []
        for fragor in spar.get("sokningar", {}).values():
            for q in fragor:
                bedomda, fynd = stat.get((sid, q), (0, 0))
                eget = val.get((sid, q))
                if eget is False or (eget is None and bedomda >= MIN_BEDOMDA and fynd == 0):
                    pausade.add((sid, q))
                    lista.append({"sokord": q, "bedomda": bedomda})
        spar["pausade"] = lista
    if pausade:
        print(f"Sökord: {len(pausade)} pausade (gav inget på {MIN_BEDOMDA}+ bedömda annonser).")
    return pausade
