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
}


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
        self.con.commit()

    def finns(self, nyckel: str) -> bool:
        return self.con.execute("SELECT 1 FROM sedda WHERE nyckel = ?", (nyckel,)).fetchone() is not None

    def spara(self, a, betyg: int, motivering: str, notifierad: bool = False):
        self.con.execute(
            """INSERT OR REPLACE INTO sedda
               (nyckel, titel, url, betyg, motivering, notifierad, kalla, kategori,
                pris, pris_text, plats, slutar, slutar_ts, bilder, sokord)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (a.nyckel, a.titel, a.url, betyg, motivering, int(notifierad), a.kalla, a.kategori,
             a.pris, a.pris_text, a.plats, a.slutar, a.slutar_ts, json.dumps(a.bilder[:4]),
             a.sokord),
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

    def rensa_gamla(self, dagar: int = 120):
        self.con.execute("DELETE FROM sedda WHERE sedd < datetime('now', ?)", (f"-{dagar} days",))
        self.con.commit()
