# Bygga referensbiblioteket på hemmadatorn

Referensbiblioteket är tabellen `referens` i Supabase: sålda föremål från Auctionet med fabrik, formgivare,
modellnummer, vad som står på botten och ett foto på stämpeln. Butik slår upp i den när en stämpel har lästs,
så att Claude får riktiga referensfoton att jämföra med i stället för att gissa ur minnet.

Hämtningen går långsamt med flit (en sekund mellan anropen) och tar några timmar för hela fraslistan. Den kan
avbrytas när som helst och startas om – den fortsätter där den var.

## 1. Installera (en gång)

**Windows 11 (EVO-X1):**

1. Python: hämta från <https://www.python.org/downloads/windows/> (3.12 eller senare). Kryssa i **"Add python.exe to PATH"** i installationens första ruta.
2. Git: hämta från <https://git-scm.com/download/win>, standardval rakt igenom.
3. Öppna **PowerShell** och hämta koden:

```powershell
cd $HOME
git clone https://github.com/hbsportsdirector/Fyndjakt.git
cd Fyndjakt
pip install -r requirements.txt
```

**Linux:** `sudo apt install python3 python3-pip git`, sedan samma tre rader.

## 2. Bot-nyckeln (en gång)

Skripten skriver till Supabase med Fyndjakts bot-nyckel, samma sorts nyckel som nattkörningen på GitHub har.
Har du den sparad (GitHub → Settings → Secrets → `FYNDJAKT_BOT_TOKEN`) använder du den. Annars skapar du en ny:

```powershell
python tools/ny_bot_nyckel.py
```

Skriptet skriver ut nyckeln (spara den) och en SQL-rad med nyckelns hash. Hashen är ofarlig: klistra in raden i
Supabase → SQL Editor och kör, eller skicka den till Claude. Sätt sedan nyckeln som miljövariabel (raden står i
skriptets utskrift) och **öppna ett nytt PowerShell-fönster** så att den gäller.

Kontrollera: `python tools/referens_hamta.py --status` ska svara med en (tom) lista, inte med "ogiltig nyckel".

## 3. Hämta

Ett första varv med högst 20 sidor per fras (ca 1 000 poster per fras, tar en halvtimme) så att biblioteket får
bredd direkt:

```powershell
python tools/referens_hamta.py --max-sidor 20
```

Sedan hela vägen (upp till 250 sidor per fras där det finns så mycket – flera timmar, låt den stå):

```powershell
python tools/referens_hamta.py --om
```

`--om` betyder "börja om från sida 1" – redan sparade rader uppdateras, inget dubbleras. Utan `--om` hoppar
skriptet över fraser som redan är klara.

Bara en fras: `python tools/referens_hamta.py "Mari Simmulson"`. Se hur det växer: `python tools/referens_hamta.py --status`.

## 4. Fylla på senare

Fraserna står i `tools/referens_fraser.txt`. Lägg till en rad för en ny formgivare eller fabrik och kör skriptet
igen – bara den nya frasen hämtas. Pusha gärna filen till GitHub så att listan följer med (`git add tools/referens_fraser.txt`,
`git commit -m "Fler referensfraser"`, `git push`).

Innan du kör igen efter ett tag: `git pull` i mappen, så att du har senaste versionen av skripten.

## Vad som sparas

Per post: Auctionets id, titel, fabrik, formgivare, modellnummer, stämpelfrasen ur katalogtexten ("märkt Upsala-Ekeby
nr 342, signerad VL"), ett utdrag ur beskrivningen, länk, slutpris, datum, och bildlänkar (sista bilden är nästan
alltid botten). Poster med flera föremål markeras `parti`, eftersom bottenfotot då inte säkert hör till det
namngivna föremålet. Bilderna ligger kvar hos Auctionet och hämtas när de behövs.
