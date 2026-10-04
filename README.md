# Fyndjakt 🔎

Letar varje morgon igenom Auctionet och Tradera efter möbler, belysning, mattor, konst och dekor.
Claude tittar på bilderna och betygsätter hur väl varje föremål passar din stil (0–10).
Alla bra fynd samlas på **din egen hemsida** som uppdateras varje morgon, och de bästa (7 eller mer)
skickas dessutom till Telegram med bild, pris, motivering och länk.

## Så fungerar det

1. GitHub Actions startar `main.py` kl. 07:37 varje dag.
2. Alla sökningar i `config.yaml` körs mot Auctionet (och Tradera om du har nyckel).
3. Annonser du redan sett hoppas över (`data/sedda.db`).
4. Nya annonser grovfiltreras på pris och "uteslut-ord", sedan bedöms resten av Claude mot din stilprofil.
5. Hemsidan byggs om med alla aktuella fynd (utgångna auktioner försvinner automatiskt).
6. Nya bra träffar skickas till Telegram, bäst först.

## Kom igång (ca 15 minuter)

### 1. Telegram-bot (valfritt – hoppa över om hemsidan räcker)
1. Öppna Telegram, sök efter **@BotFather** och skriv `/newbot`. Följ instruktionerna.
2. Du får en **token**, t.ex. `123456:ABC-DEF…`. Spara den.
3. Skicka ett valfritt meddelande till din nya bot.
4. Öppna `https://api.telegram.org/bot<DIN_TOKEN>/getUpdates` i webbläsaren och leta upp `"chat":{"id": …}`. Det numret är ditt **chat-id**.

### 2. Claude API-nyckel
Skapa ett konto på [console.anthropic.com](https://console.anthropic.com), fyll på lite kredit och skapa en API-nyckel.

### 3. Tradera (valfritt men rekommenderat)
Registrera ett gratis utvecklarkonto på [api.tradera.com/register](https://api.tradera.com/register) och skapa en applikation. Du får ett **AppId** och en **AppKey**.
Utan nyckel körs bara Auctionet.

### 4. Lägg upp på GitHub
1. Skapa ett nytt repo på GitHub och ladda upp alla filer i den här mappen
   (dra och släpp går bra via "Add file → Upload files"; mappen `.github` måste med).
2. Gå till **Settings → Secrets and variables → Actions → New repository secret** och lägg till:

   | Namn | Värde |
   |---|---|
   | `ANTHROPIC_API_KEY` | din Claude-nyckel |
   | `TELEGRAM_BOT_TOKEN` | (valfritt) token från BotFather |
   | `TELEGRAM_CHAT_ID` | (valfritt) ditt chat-id |
   | `TRADERA_APP_ID` | (valfritt) |
   | `TRADERA_APP_KEY` | (valfritt) |

3. Slå på hemsidan: **Settings → Pages → Source: GitHub Actions**.
4. Gå till fliken **Actions**, välj **Fyndjakt** och tryck **Run workflow** för att testa direkt.
5. När körningen är klar finns sidan på `https://<ditt-användarnamn>.github.io/<repots-namn>/`.
   Lägg den gärna på hemskärmen i mobilen (Dela → Lägg till på hemskärmen).

**Publikt eller privat repo?** GitHub Pages från ett *privat* repo kräver GitHub Pro (ca 4 USD/mån).
Med ett *publikt* repo är det gratis. Dina nycklar ligger då fortfarande hemligt (Secrets syns aldrig),
men koden, `stil.md` och själva sidan går att se för den som har adressen. Sidan är markerad så att
sökmotorer inte listar den.

Första körningen hittar många annonser och bedömer max 150 åt gången – resten tas de närmaste dagarna.

## Anpassa

Det finns två spår, med var sin flik på sidan: **The Reading Room** (profil i `stil.md`) och **Samlingen** (profil i `samlingsprofil.md`). Sökningar och filter per spår finns under `spar:` i `config.yaml`.

Din stil ligger i **`stil.md`**. Redigera den direkt i GitHub (pennikonen) eller ladda upp en ny version med samma namn – nästa körning använder den.

Resten styrs från `config.yaml`:

- **tillagg** – korta extra instruktioner till AI:n, t.ex. vad du letar efter just nu.
- **min_betyg** – gräns för Telegram-notiser (och standardfiltret på sidan).
- **sajt_min_betyg** – lägsta betyg som alls visas på hemsidan (standard 6).
- **max_pris** – högsta pris i kronor.
- **sokningar** – lägg till eller ta bort sökord under respektive kategori.
- **uteslut_ord** – ord som sorterar bort annonser direkt.
- **modell** – byt till `claude-sonnet-5-5` för skarpare (men dyrare) omdömen.

Ändra tid i `.github/workflows/fyndjakt.yml` (raden `cron`, tiden är i UTC).

## Kostnad

Auctionet, Tradera, Telegram, GitHub Actions och GitHub Pages (publikt repo) är gratis för det här.
Claude-bedömningen kostar några öre per annons med Haiku. De första dagarna blir det mest,
sedan kommer bara nya annonser. Räkna grovt med några tior i månaden; `max_bedomningar_per_korning` sätter taket.

## Blocket och Facebook Marketplace

De har inga öppna API:er och förbjuder automatisk skrapning, så de ingår inte här.
Använd deras egna sparade sökningar med notiser – gärna med samma sökord som i `config.yaml`.

## Testa lokalt

```bash
pip install -r requirements.txt pytest
python -m pytest tests          # offline-tester
python main.py --torr           # hämtar riktiga annonser, utan AI och notiser
python main.py                  # full körning; sidan hamnar i site/index.html
```
