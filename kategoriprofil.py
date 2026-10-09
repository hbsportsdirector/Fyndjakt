"""Korta profiler per kategori.

Hela stilprofilen beskriver allt kunden letar efter – bokhyllor, kartor, keramik, glas … När Claude bedömer en
keramikskål behöver den bara det som gäller keramik. Därför skriver Claude EN gång en koncentrerad profil per
kategori (t.ex. "Keramik och design"), som sedan används för alla annonser i den kategorin.

Kategoriprofilerna sparas i data/kategoriprofiler.json och görs bara om när grundprofilen eller kategorins sökord
ändras. Lärdomar och reaktioner (som ändras oftare) läggs till efteråt, filtrerade på kategorin.
"""
import hashlib
import json
from pathlib import Path

FIL = Path(__file__).parent / "data" / "kategoriprofiler.json"
MODELL = "claude-sonnet-5-5"

INSTRUKTION = """Du förbereder bedömningen av begagnade annonser åt en kund. Nedan finns kundens fullständiga profil för
bevakningen «{namn}». Skriv en KONCENTRERAD bedömningsprofil för kategorin «{kategori}»
(kategorins sökord: {sokord}).

Ta med allt i profilen som är relevant för just den kategorin: stil, färger, material, epoker, form,
namngivna formgivare/konstnärer/fabriker/serier, prisnivåer, vad kunden redan har och vad kunden inte vill ha.
Behåll konkreta namn, siffror och undantag ordagrant. Utelämna allt som bara gäller andra kategorier.
Högst 250 ord, gärna i punktform. Svara bara med profilen."""


def _las() -> dict:
    try:
        return json.loads(FIL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _nyckel(bas: str, kategori: str, sokord: list[str]) -> str:
    return hashlib.sha256(f"{bas}\n§{kategori}\n§{'|'.join(sokord)}".encode()).hexdigest()[:16]


def _skriv(klient, spar: dict, kategori: str, sokord: list[str]) -> str:
    svar = klient.messages.create(
        model=MODELL, max_tokens=700,
        system=INSTRUKTION.format(namn=spar.get("namn", ""), kategori=kategori, sokord=", ".join(sokord[:40])),
        messages=[{"role": "user", "content": spar["profil_bas"]}])
    return "".join(b.text for b in svar.content if getattr(b, "type", "text") == "text").strip()


def bygg(cfg: dict, klient=None) -> dict[tuple, str]:
    """{(spår, kategori): kort profil}. Utan klient används bara sparade profiler."""
    cache = _las()
    ut, nya = {}, 0
    for sid, spar in cfg["spar"].items():
        bas = spar.get("profil_bas")
        if not bas:
            continue
        for kategori, sokord in spar.get("sokningar", {}).items():
            nyckel = _nyckel(bas, kategori, list(sokord))
            post = cache.get(f"{sid}|{kategori}")
            if (not post or post.get("nyckel") != nyckel) and klient is not None:
                try:
                    text = _skriv(klient, spar, kategori, list(sokord))
                    if len(text) > 50:
                        post = cache[f"{sid}|{kategori}"] = {"nyckel": nyckel, "profil": text}
                        nya += 1
                except Exception as e:  # då används hela profilen – körningen ska aldrig stoppa här
                    print(f"  Kategoriprofil för {spar.get('namn')}/{kategori} misslyckades: {e}")
            if post and post.get("nyckel") == nyckel:
                ut[(sid, kategori)] = post["profil"]
    if nya:
        FIL.parent.mkdir(exist_ok=True)
        FIL.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Kategoriprofiler: {len(ut)} i bruk, {nya} nyskrivna.")
    return ut


def profil_for(a, cfg: dict, export: dict | None, korta: dict[tuple, str]) -> str:
    """Kort kategoriprofil + lärdomar + kundens reaktioner i samma kategori. Hela profilen om ingen kort finns."""
    spar = cfg["spar"][a.spar]
    kort = korta.get((a.spar, a.kategori))
    if not kort:
        return spar["profil"]
    delar = [f"Bevakning: «{spar.get('namn', '')}» – kategori: {a.kategori}", kort]
    if spar.get("lardomar"):
        delar.append("LÄRDOMAR FRÅN KUNDENS REAKTIONER – följ dem:\n" + spar["lardomar"])
    if export:
        import smak
        tillagg = smak.profiltillagg(export, a.spar, smak._agare(spar, export), kategori=a.kategori)
        if tillagg:
            delar.append(tillagg)
    return "\n\n".join(delar)
