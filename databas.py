"""Håller koll på vilka annonser som redan bedömts, och sparar träffarna till hemsidan."""
import json
import sqlite3
import time
from pathlib import Path

SOKVAG = Path(__file__).parent / "data" / "sedda.db"

KOLUMNER = {
    "nyckel": "TEXT PRIMARY KEY",
    "titel": "TEXT",
    "url": "TEXT",
    "betyg": "INTEGER",
    "motivering": "TEXT",
    "notifierad": "INTEGER DEFAULT 0",
    "sedd": "TEXT DEFAULT CURRENT_TIMESTAMP",
    "kalla": "TEXT",
    "kategori": "TEXT",
    "pris": "INTEGER",
    "pris_text": "TEXT",
    "plats": "TEXT",
    "slutar": "TEXT",
    "slutar_ts": "INTEGER",
    "bilder": "TEXT",
    "sokord": "TEXT",
    "spar": "TEXT",
    "jamforsok": "TEXT",
    "jmf_median": "INTEGER",
    "jmf_lag": "INTEGER",
    "jmf_hog": "INTEGER",
    "jmf_antal": "INTEGER",
    "jmf_tid": "INTEGER",
    "titelnorm": "TEXT",
}


def normalisera(titel: str) -> str:
    """Titel utan skiljetecken och versaler – samma föremål som läggs upp igen får samma nyckel."""
    import re
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (titel or "").lower())).strip()


class Databas:
    def __init__(self, sokvag: Path = SOKVAG):
        sokvag.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(sokvag)
        self.con.row_factory = sqlite3.Row
        kol = ", ".join(f"{k} {t}" for k, t in KOLUMNER.items())
        self.con.execute(f"CREATE TABLE IF NOT EXISTS sedda ({kol})")
        # Lägg till kolumner som saknas i en äldre databas.
        finns = {r["name"] for r in self.con.execute("PRAGMA table_info(sedda)")}
        for k, t in KOLUMNER.items():
            if k not in finns:
                self.con.execute(f"ALTER TABLE sedda ADD COLUMN {k} {t.replace('PRIMARY KEY', '')}")
        # Fyll i normaliserade titlar för äldre rader (en gång) och indexera dem.
        saknar = self.con.execute("SELECT nyckel, titel FROM sedda WHERE titelnorm IS NULL").fetchall()
        if saknar:
            self.con.executemany("UPDATE sedda SET titelnorm=? WHERE nyckel=?",
                                 [(normalisera(r["titel"]), r["nyckel"]) for r in saknar])
        self.con.execute("CREATE INDEX IF NOT EXISTS sedda_titelnorm ON sedda(spar, titelnorm)")
        self.con.commit()

    def tidigare_bedomning(self, a, min_langd: int = 25, dagar: int = 60, efter: str = "") -> dict | None:
        """En tidigare Claude-bedömning av samma föremål (samma spår, nästan identisk titel), annars None.
        Korta, allmänna titlar ("Vas, Orrefors") räknas inte – där kan det vara helt olika föremål."""
        norm = normalisera(a.titel)
        if len(norm) < min_langd:
            return None
        rad = self.con.execute(
            """SELECT betyg, motivering, jamforsok FROM sedda
               WHERE spar = ? AND titelnorm = ? AND betyg >= 0 AND nyckel != ?
                 AND motivering NOT LIKE 'Sållad%' AND motivering NOT LIKE 'Ej bildgranskad%'
                 AND sedd > datetime('now', ?) AND sedd >= ?
               ORDER BY sedd DESC LIMIT 1""",
            (a.spar, norm, a.nyckel, f"-{dagar} days", efter or "")).fetchone()
        return dict(rad) if rad else None

    def finns(self, nyckel: str) -> bool:
        return self.con.execute("SELECT 1 FROM sedda WHERE nyckel = ?", (nyckel,)).fetchone() is not None

    def vantande(self, nystart: dict | None = None) -> dict[str, int | None]:
        """Annonser som klarade titelsållningen men inte hann bildgranskas – de ska få en ny chans.
        {nyckel: titelbetyg}, så att de inte behöver sållas om. None = sållades med en äldre smak – sålla om."""
        nystart = nystart or {}
        ut = {}
        for nyckel, betyg, spar, sedd in self.con.execute(
                "SELECT nyckel, betyg, spar, sedd FROM sedda WHERE motivering LIKE 'Ej bildgranskad%' "
                "AND (slutar_ts IS NULL OR slutar_ts > ?)", (int(time.time()),)):
            ut[nyckel] = None if nystart.get(spar) and str(sedd or "") < nystart[spar] else betyg
        return ut

    def att_omvardera(self, nystart: dict, min_betyg: int = 8, max_antal: int = 1500) -> list[dict]:
        """Aktiva fynd som bedömdes med en äldre smak än spårets nystart – bäst först."""
        ut = []
        for spar, tid in nystart.items():
            ut += [dict(r) for r in self.con.execute(
                """SELECT * FROM sedda WHERE spar = ? AND betyg >= ? AND sedd < ?
                     AND (slutar_ts IS NULL OR slutar_ts > ?)""",
                (spar, min_betyg, tid, int(time.time()) + 3600))]
        ut.sort(key=lambda r: -r["betyg"])
        return ut[:max_antal]

    def spara(self, a, betyg: int, motivering: str, notifierad: bool = False):
        self.con.execute(
            """INSERT OR REPLACE INTO sedda
               (nyckel, titel, url, betyg, motivering, notifierad, kalla, kategori,
                pris, pris_text, plats, slutar, slutar_ts, bilder, sokord, spar, jamforsok, titelnorm)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (a.nyckel, a.titel, a.url, betyg, motivering, int(notifierad), a.kalla, a.kategori,
             a.pris, a.pris_text, a.plats, a.slutar, a.slutar_ts, json.dumps(a.bilder[:4]),
             a.sokord, a.spar, getattr(a, "jamforsok", ""), normalisera(a.titel)),
        )
        self.con.commit()

    def traffar(self, min_betyg: int) -> list[dict]:
        """Bedömda annonser som inte har gått ut, bäst först."""
        rader = self.con.execute(
            """SELECT * FROM sedda
               WHERE betyg >= ? AND (slutar_ts IS NULL OR slutar_ts > ?)
               ORDER BY betyg DESC, sedd DESC""",
            (min_betyg, int(time.time())),
        ).fetchall()
        ut = []
        for r in rader:
            d = dict(r)
            d["bilder"] = json.loads(d["bilder"] or "[]")
            ut.append(d)
        return ut

    def behover_jamforelse(self, min_betyg: int, max_alder_dagar: int = 14) -> list[dict]:
        """Aktuella fynd som saknar prisjämförelse, eller där den är gammal."""
        nu = int(time.time())
        return [dict(r) for r in self.con.execute(
            """SELECT nyckel, titel, jamforsok FROM sedda
               WHERE betyg >= ? AND (slutar_ts IS NULL OR slutar_ts > ?)
                 AND (jmf_tid IS NULL OR jmf_tid < ?)
               ORDER BY betyg DESC""",
            (min_betyg, nu, nu - max_alder_dagar * 86400),
        )]

    def spara_jamforelse(self, nyckel: str, fras: str, res: dict | None):
        res = res or {}
        self.con.execute(
            """UPDATE sedda SET jamforsok=?, jmf_median=?, jmf_lag=?, jmf_hog=?, jmf_antal=?, jmf_tid=?
               WHERE nyckel=?""",
            (fras, res.get("median"), res.get("lag"), res.get("hog"), res.get("antal", 0), int(time.time()), nyckel),
        )
        self.con.commit()

    def rensa_gamla(self, dagar: int = 120):
        self.con.execute("DELETE FROM sedda WHERE sedd < datetime('now', ?)", (f"-{dagar} days",))
        self.con.commit()
