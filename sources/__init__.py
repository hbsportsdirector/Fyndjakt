"""Källor för annonser. Varje källa returnerar en lista av Annons."""
from dataclasses import dataclass, field


@dataclass
class Annons:
    kalla: str            # "auctionet", "tradera" …
    id: str               # unikt id inom källan
    titel: str
    url: str
    beskrivning: str = ""
    pris: int | None = None        # kr – utrop, aktuellt bud eller köp nu
    pris_text: str = ""
    bilder: list[str] = field(default_factory=list)
    plats: str = ""
    slutar: str = ""               # läsbar tid
    slutar_ts: int | None = None   # unix-tid när annonsen slutar
    kategori: str = ""             # vilken av dina kategorier sökningen kom från
    sokord: str = ""               # vilken sökning som hittade annonsen
    valuta: str = "SEK"

    @property
    def nyckel(self) -> str:
        return f"{self.kalla}:{self.id}"
