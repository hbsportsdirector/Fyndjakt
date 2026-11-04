"""Aktuellt bud för fynden som visas på sidan.

Sökningarna hämtar bara det som råkar komma med i resultatet, och timkörningen hämtar inte Auctionet alls – så ett bud
kunde vara ett dygn gammalt när du tryckte på kortet. Här hämtas varje visat fynd för sig, de som slutar snarast först:
- Auctionet har inget uppslag på en enskild annons, men en sökning på annonsens titel hittar den (matchas på id).
- Tradera slås upp direkt med annonsens id.
Flipp-annonserna räknas sedan om (köp max, vinst, betyg) av flipp.uppdatera_priser. Avslutade annonser tas bort från sidan.
"""
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from sources import Annons, auctionet, tradera

MAX_AUCTIONET = 300   # anrop per körning – sökningen är snabb och utan kvot
MAX_TRADERA = 150     # Tradera har en dagskvot; de som slutar snarast först


def att_uppdatera(db, min_betyg: int, redan: set[str], nu: float | None = None) -> list[dict]:
    """Visade fynd som inte hämtades i den här körningen, de som slutar snarast först."""
    nu = int(nu or time.time())
    rader = db.con.execute(
        """SELECT nyckel, titel, kalla, spar, pris, pris_text, slutar_ts FROM sedda
           WHERE betyg >= ? AND kalla IN ('auctionet', 'tradera') AND (slutar_ts IS NULL OR slutar_ts > ?)
           ORDER BY slutar_ts IS NULL, slutar_ts""", (min_betyg, nu)).fetchall()
    return [dict(r) for r in rader if r["nyckel"] not in redan]


def _prefix(nyckel: str, kalla: str) -> tuple[str, str]:
    """"flipp|auctionet:5496446" → ("flipp|", "5496446")."""
    fore, _, id_ = nyckel.rpartition(f"{kalla}:")
    return fore, id_


def hamta_auctionet(rad: dict) -> tuple[Annons | None, bool]:
    """(annonsen med aktuellt bud, avslutad?). Söker på titeln och plockar ut rätt id."""
    _, id_ = _prefix(rad["nyckel"], "auctionet")
    r = requests.get(auctionet.API, params={"q": rad["titel"][:120], "per_page": 48}, headers=auctionet.HEADERS, timeout=30)
    r.raise_for_status()
    for post in r.json().get("items") or []:
        if str(post.get("id")) == id_:
            a = auctionet.tolka(post)
            return a, a is None            # tolka ger None för sålda och avslutade
    return None, False                     # hittades inte – rör inte (titelsökningen kan missa)


def hamta_tradera(rad: dict) -> tuple[Annons | None, bool]:
    _, id_ = _prefix(rad["nyckel"], "tradera")
    d = tradera.detaljer(id_)
    if tradera._hamta(d, "isEnded", default=False):
        return None, True
    return tradera.tolka(d), False


def kor(db, cfg: dict, redan: set[str], nu: float | None = None) -> tuple[list[Annons], dict]:
    """Hämtar aktuella priser. Returnerar (annonser med nytt pris, statistik). Priset skrivs direkt i databasen;
    flipp-annonserna ska dessutom räknas om av flipp.uppdatera_priser."""
    rader = att_uppdatera(db, cfg.get("sajt_min_betyg", 6), redan, nu)
    jobb = [r for r in rader if r["kalla"] == "auctionet"][:MAX_AUCTIONET]
    if tradera.aktiverad():
        jobb += [r for r in rader if r["kalla"] == "tradera"][:MAX_TRADERA]

    def en(rad):
        try:
            return rad, *(hamta_auctionet(rad) if rad["kalla"] == "auctionet" else hamta_tradera(rad))
        except Exception:
            return rad, None, False

    ut, stat = [], {"kollade": len(jobb), "nytt pris": 0, "avslutade": 0, "missade": 0}
    with ThreadPoolExecutor(6) as pool:
        resultat = list(pool.map(en, jobb))
    for rad, a, slut in resultat:
        if slut:
            # Såld eller avslutad: tas bort från sidan nu i stället för när sluttiden passerar.
            db.con.execute("UPDATE sedda SET slutar_ts = ? WHERE nyckel = ?", (int(time.time()) - 1, rad["nyckel"]))
            stat["avslutade"] += 1
            continue
        if not a or not a.pris:
            stat["missade"] += 1
            continue
        a.prefix, _ = _prefix(rad["nyckel"], rad["kalla"])
        a.spar = rad["spar"] or ""
        if (a.pris, a.pris_text) != (rad["pris"], rad["pris_text"]):
            db.con.execute("UPDATE sedda SET pris = ?, pris_text = ?, slutar_ts = COALESCE(?, slutar_ts) WHERE nyckel = ?",
                           (a.pris, a.pris_text, a.slutar_ts, rad["nyckel"]))
            stat["nytt pris"] += 1
        ut.append(a)
    db.con.commit()
    print(f"Priser: {stat['kollade']} visade fynd kollade – {stat['nytt pris']} nya bud, {stat['avslutade']} avslutade.")
    return ut, stat
