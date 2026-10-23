# Fyndjakt – så fungerar appen och hur fynden väljs ut

*Senast uppdaterad 23 oktober 2026. Repo: `hbsportsdirector/Fyndjakt`. Ägare/admin: Per Lundgren.*

Det här dokumentet är skrivet så att en annan Claude-session (eller en människa) ska kunna förstå
**exakt varför en annons hamnar – eller inte hamnar – i listan**, och utifrån det skriva en ny
"Min smak" som fungerar bra i appen. Avsnitt 5 är själva instruktionen för att skriva en Min smak.

---

## 1. Vad appen är

Fyndjakt söker varje natt igenom svenska auktioner och second hand, låter Claude betygsätta varje
intressant annons 0–10 mot en smakprofil, och visar de bästa på en privat webbsida.

- **Källor:** Auctionet (500+ auktionshus), Bukowskis, Tradera (inkl. Myrorna, Erikshjälpen m.fl. som säljer där),
  Myrornas webbshop och Stockholms Stadsmissions webbshop (kategorin Hem).
- **Bevakningar ("spår"):** varje bevakning har en egen profil, egna sökord och en egen flik.
  - `samlingen` – **Samlingen** (konst, glas, keramik). Profil: `samlingsprofil.md`.
  - `hemmet` – **The Reading Room** (möbler och detaljer till ett engelskt bibliotek). Profil: `stil.md`.
  - Inbjudna användare kan skapa egna bevakningar på sidan (max 3, max 30 sökord). De lagras i Supabase.
- **Sidan:** GitHub Pages + inloggning (Google/e-post) via Supabase. Inget är publikt – fynden laddas först efter inloggning.
- **Körning:** GitHub Actions (`.github/workflows/fyndjakt.yml`), en gång per natt.
- **Data:** `data/sedda.db` (SQLite) – varje annons som någonsin setts, med betyg, motivering, sökord, spår m.m.

---

## 2. Filerna som styr smaken

| Fil / fält | Vad det är | Påverkar |
|---|---|---|
| `samlingsprofil.md`, `stil.md` | Själva smakprofilen i fri text (markdown) | Både titelsållning och bildbedömning |
| `config.yaml → spar.<id>.tillagg` | Extra bedömningsregler som läggs efter profilen ("Viktigt vid bedömningen:") | Både sållning och bedömning |
| `config.yaml → spar.<id>.lardomar_bas` | Fasta "lärdomar" – konkreta regler om vad kunden gillar/inte gillar | Bedömningen + visas under Min smak |
| `config.yaml → spar.<id>.bedomningsregler` | Betygsskalan (vad 10/9/8/… betyder) för spåret | Både sållning och bedömning |
| `config.yaml → spar.<id>.sokningar` | Sökorden, grupperade i kategorier (kategorin = flik/filter på sidan) | Vad som över huvud taget hittas |
| `config.yaml → spar.<id>.uteslut_ord` | Ord som sorterar bort en annons direkt (titel + beskrivning, delsträng) | Förfiltret |
| `config.yaml → spar.<id>.har_redan` / `har_redan_ord` | Saker kunden äger. `har_redan_ord` sorterar bort annonser med ordet i titeln! | Förfiltret / bedömning |
| `config.yaml → spar.<id>.max_pris` | Prisgräns (kr) | Förfiltret |
| `config.yaml → smak_nystart` | Tidpunkt per spår: reaktioner/betyg före den räknas inte längre | Allt som lär sig av reaktioner |
| `config.yaml → omvardera_fore` | Tidpunkt per spår: aktiva fynd (8+) från före den betygsätts om en gång | Engångsomräkning |
| Supabase `fyndjakt_reaktioner` | Kundens 👍 / 👎 / 🛒 (+ ev. kommentar) | Lärdomar, exempel i profilen, dolda kort |
| Supabase `fyndjakt_anteckningar` | Fria anteckningar under Min smak (gillar / gillar inte / har) | Profilen |
| Supabase `fyndjakt_sokord_val` | Sökord kunden pausat ("Sluta visa") eller slagit på igen | Sökningar + nej-lista i profilen |

---

## 3. Urvalskedjan – från 10 000 annonser till ca 50 fynd

Ordningen nedan är exakt den i `main.py`. Varje steg kan förklara varför något saknas eller dyker upp.

### 3.1 Sökning
- Varje sökord körs mot alla källor, upp till `sidor_per_sokning` (4) sidor. Tradera sorteras på relevans.
- **Pausade sökord hoppas över:** ett sökord pausas automatiskt när ≥ 40 annonser bedömts utan ett enda fynd (8+),
  eller när kunden tryckt "Sluta visa". (`sokordsvard.py`)
- **Följd:** det appen aldrig söker på kan den aldrig hitta. Smala sökord ger få men träffsäkra annonser,
  breda sökord ger många och mer skräp (se 5.4).

### 3.2 Redan sedda
- Annonser som redan finns i `sedda.db` hoppas över – en annons bedöms i princip en gång.
- Undantag: annonser i **kön** (se 3.6) och omvärderingar (3.8).

### 3.3 Förfilter (gratis, utan AI)
En annons sorteras bort om något av detta gäller:
- titel/beskrivning innehåller ett `uteslut_ord` (delsträng – akta korta ord som "sked" som också finns i "skedde"),
- titeln innehåller ett `har_redan_ord`,
- valutan inte är SEK (`bara_sverige`),
- priset är över `max_pris`.

### 3.4 Återanvända betyg och egen modell (gratis)
- **Samma titel igen** (≥ 25 tecken, samma spår, senaste 60 dagarna, efter nystart) → samma betyg som förra gången.
- **Egen modell** (`egen_modell.py`): en enkel naiv Bayes-modell tränad på Claudes tidigare betyg (bara efter nystart)
  sorterar bort annonser som är *mycket* osannolika fynd. Gränsen är satt så att 98 % av riktiga fynd släpps igenom.

### 3.5 Titelsållning (billig AI, bara titel + pris)
- Körs bara när det finns fler kandidater än budgeten. Claude (Haiku) ger varje titel ett snabbt betyg 0–10
  mot spårets **kategoriprofil** (en koncentrerad version av profilen per kategori, skriven en gång av Sonnet och cachad
  i `data/kategoriprofiler.json`) + lärdomar + reaktioner.
- Under `sallning_min_betyg` (5) → bort ("Sållad bort på titeln").
- **Namngivna formgivare/fabriker/serier i profilen eller reglerna får alltid minst 6** – så att bilderna får avgöra.
- Följd: står ett namn i profilen tas det nästan alltid vidare. Står det INTE där bedöms det bara på hur titeln låter.

### 3.6 Tak per sökord och kön
- Högst `granska_max_per_sokord` (25) annonser per sökord och natt går till bildgranskning. Sökord som ofta ger fynd
  får lite fler (×1,5 vid ≥ 15 % träffar, ×2 vid ≥ 30 %).
- Det som inte hinns med sparas som **"Ej bildgranskad"** = kön. Varje natt tas upp till `max_fran_kon_per_korning` (300)
  ur kön direkt från databasen, bäst först.
- Stockholm går först vid lika titelbetyg.

### 3.7 Budget och berikning
- Totalt högst `max_bedomningar_per_korning` (800) bildgranskningar per natt (+ omvärderingar).
- För Tradera hämtas säljarens **ort** och längre beskrivning; för Bukowskis ort och beskrivning.

### 3.8 Bildbedömning (själva betyget)
- Claude (Haiku, via Batch-API) bedömer annonserna **5 i taget** (samma spår och kategori), med **en bild** per annons
  (nedskalad till 400 px), titel, pris, plats och beskrivning.
- Det som skickas till Claude är, i ordning (se avsnitt 4): kategoriprofil → lärdomar → nej-lista → reaktioner → bedömningsregler.
- Svar: betyg 0–10, en motivering (en mening) och en sökfras för prisjämförelse.
- **Omvärdering:** aktiva fynd 8+ som bedömdes före `smak_nystart`/`omvardera_fore` bedöms om en gång.

### 3.9 Vad som visas på sidan
- Sidan får alla aktiva bildgranskade annonser med betyg ≥ `sajt_min_betyg` (7). Reglaget "Minst" börjar på
  `min_betyg` (8); dra ner till 7 för "nästan-fynd". 7:or från före nystart visas inte.
- **Dolt:** allt kunden redan reagerat på (👍 visas under fliken *Gillade*), samma titel som något redan reagerat på
  (≥ 20 tecken, samma spår – fångar omlistade annonser), och sökord kunden sagt nej till.
- **Sortering "Bäst matchning":** betyg, men varje ytterligare fynd från samma sökord räknas 0,25 lägre (variation),
  Stockholm före övriga vid lika värde.
- **Högst 5 fynd per sökord åt gången**; fler dyker upp när kunden reagerat på de första ("· N väntar").
- 50 fynd per sida, "Visa 50 till" för fler. Område/källa/kategori/sök filtrerar ytterligare.

### 3.10 Typiska siffror (oktober 2026, steady state)
En vanlig natt: ~400 nya annonser hittas → ~260 + 300 ur kön bildgranskas → **15–40 nya fynd per bevakning**.
Kostnad 6–9 kr/natt (14 kr nätter med omvärdering).

---

## 4. Vad Claude faktiskt ser när ett betyg sätts

För varje spår byggs en profiltext i den här ordningen (`main.bygg_profil`, `smak.tillampa`, `smakanalys.analysera`,
`kategoriprofil.profil_for`):

1. **Profilfilen** (`samlingsprofil.md` / `stil.md`) + `tillagg` – i både sållning och bildbedömning ersatt av
   **kategoriprofilen** för annonsens kategori (en koncentrerad sammanfattning, ≤ 250 ord, skriven av Sonnet ur profilen +
   kategorins sökord). Finns ingen kategoriprofil (t.ex. borttagen kategori) används hela profilen.
2. **"Viktigt vid bedömningen:"** + `tillagg` (ingår i underlaget för kategoriprofilen).
3. **"Kunden HAR REDAN följande – ge 0–3 åt samma typ av föremål"** + `har_redan` (om satt).
4. **"LÄRDOMAR OM KUNDENS SMAK – följ dem:"** = `lardomar_bas` + automatiska lärdomar från smakanalysen.
   Smakanalysen (Sonnet) jämför de senaste ≤ 40 gillade och ≤ 40 ogillade (titlar, gamla motiveringar, 8 bilder per sida)
   och skriver 4–15 nya punkter. Görs om när reaktionerna ändrats, bara med reaktioner efter `smak_nystart`.
5. **"KUNDEN HAR SAGT NEJ TILL DESSA … högst 2"** – sökord kunden tryckt "Sluta visa" på.
6. **"KUNDENS EGNA REAKTIONER"** – upp till 30 exempel per sort (gillat / inte passat / köpt / anteckningar),
   filtrerade på kategori i titelsållningen. Bara efter nystart.
7. **Betygsskalan** – `bedomningsregler` för spåret (annars en sträng standard: ca 1 av 10 får 8+).

**Plats:** reglerna i `tillagg` säger att Stockholm ger +1 och att stora/ömtåliga föremål långt bort utan frakt ger −2.

**Viktig konsekvens för den som skriver en Min smak:** profilen, `tillagg` och `lardomar_bas` är det enda som gäller direkt
efter en nystart. Eftersom kategoriprofilen är en *sammanfattning* per kategori: skriv profilen så att varje regel hör tydligt
till en serie/formgivare/typ – allmänna resonemang kan falla bort i sammanfattningen, medan `lardomar_bas` alltid skickas ordagrant. Det som inte står där får Claude gissa – och Claude gissar generöst för allt som ser "designat" ut.

---

## 5. Så skriver du en ny Min smak (instruktion till en annan session)

### 5.1 Vad du ska leverera
1. **En profilfil per bevakning** (`samlingsprofil.md` och/eller `stil.md`) – se mall 5.6.
2. **Ett config-block per bevakning** för `config.yaml`: `tillagg`, `lardomar_bas`, `bedomningsregler`,
   `sokningar` (grupperade), `uteslut_ord`, ev. `max_pris`.
3. **Beslut om nystart:** ska gamla reaktioner sluta gälla? Då sätts `smak_nystart.<spår>` till nu (UTC, `"ÅÅÅÅ-MM-DD HH:MM:SS"`),
   och aktiva fynd betygsätts om automatiskt. Vill man bara skärpa reglerna men behålla det appen lärt sig: sätt
   `omvardera_fore.<spår>` i stället.

### 5.2 Principer som fungerar i den här appen
- **Namnge allt som ska ge högt betyg** – formgivare, fabrik, serie, modellnamn. Namn i profilen får alltid passera
  titelsållningen och känns igen på bilden.
- **Säg uttryckligen vad som INTE ska med, per serie/formgivare.** Exempel som visat sig avgörande:
  "Deco Hälsingborg: burkar ja – vaser, krus, kannor och fat nej". Utan sådana rader ger Claude 8–9 åt allt från rätt fabrik.
- **Skilj på föremålstyper inom en serie** (burk/fat/assiett/kanna/karott). Kunden reagerar ofta på typen, inte serien.
- **Ange vad kunden redan äger med nummer/variant** ("Janssons frestelse – har nr 111, 112, 114").
- **Ange prisnivåer** per typ (konst, glas, keramik, möbler). Dyra studioföremål har ofta fått nej.
- **Var sparsam med 9–10 i betygsskalan.** Säg vad som är *ovanligt* (Röd Eld, röd Höglund, en saknad karaff) –
  annars får allt från rätt serie 9 och det verkliga fyndet drunknar.
- **Volym:** ett sökord med enorm tillgång (t.ex. Kosta Boda Line, mässingsljusstakar) tar över listan om alla träffar får 8+.
  Begränsa med regler ("bara champagne- och martiniglas kan få 8+") eller ta bort sökordet.
- **Möbler:** skriv träslag som ja/nej (mahogny, valnöt, mörk ek ja – björk, furu, ljus bok nej), stil (engelsk, Chippendale,
  Chesterfield) och vad som *inte* är rätt (moderna danska designfåtöljer, soffgrupper).
- **Undvik `har_redan_ord` för saker kunden vill ha fler av** – ordet sorterar bort annonsen helt.

### 5.3 Sökord – tumregler
- Kombinera namn + föremålstyp när namnet ensamt drar skräp: "Deco Hälsingborg burk", "chippendale byrå"
  (bara "chippendale" gav silverbestick och filmer).
- Ta med **felstavningar** och **varianter**: Bengtson/Bengtsson, Jäntofta, Copland, "bankers lamp".
- Ta med **engelska** sökningar för engelskt porslin ("Spode tea pot", "serving dish").
- Breda sökord ("Blå Eld", "Eld Rörstrand") fångar blandade "servisdelar"-poster där den saknade biten gömmer sig.
- Max ca 50 sökord per bevakning – fler ger mer kö och kostnad utan fler fynd.
- Sökord som gett **0 fynd på 40+ bedömda** pausas automatiskt; sökord där kunden gett nästan bara 👎 bör tas bort.

### 5.4 Sökord som visat sig dåliga (okt 2026)
| Sökord | Problem |
|---|---|
| `chippendale` (ensamt) | Bestick, silver, filmer |
| `fåtölj läder` | Moderna danska/skandinaviska designfåtöljer (1 👍 / 17 👎) |
| `skrivbord antikt` | Beslag, förstoringsglas, skrivbordsset |
| `lampett mässing`, `vägglampa mässing`, `läslampa mässing` | Väggmonterat får nej |
| `Rörstrand 1960/1970` | Allmänt 60-talsporslin (Elisabeth, Sippa) – 0 👍 / 9 👎 |
| `Anna Ehrner` | Dubblerar Kosta Boda Line |
| `Boda röd glas` | 0 👍 / 4 👎 |

### 5.5 Kundens reaktioner 14–19 okt (underlag för nästa Min smak)
| Bevakning | Sökord | 👍 | 👎 | Mönster |
|---|---|---|---|---|
| Samlingen | Blå Eld | 29 | 2 | Nästan alltid rätt |
| Samlingen | Jie / Anita Nylund | 28 | 5 | Burkar, kryddställ – enstaka dyra Vår lilla stad-burkar nej |
| Samlingen | Spode Italian | 11 | 1 | Nästan alltid rätt |
| Samlingen | Kosta Boda Line | 51 | 36 | Gillar serien men för stor volym; stora satser/dyra nej |
| Samlingen | Deco Hälsingborg | 15 | 12 | Burkar ja – vaser, krus, kannor, fat nej |
| Samlingen | Rörstrand Picknick | 4 | 11 | Burkar ja – karotter, skålar, fat nej |
| Samlingen | Rörstrand Valentine | 5 | 7 | Fat, kannor, koppar ja – assietter nej |
| Samlingen | Stig Lindberg | 2 | 7 | Reptil ja – dyra studioföremål nej |
| Samlingen | Nils Landberg | 2 | 5 | Sommerso, karaffer ja – Illusion, tulpanglas nej |
| Samlingen | Vicke Lindstrand | 4 | 4 | Tjockt underfång med bubblor/ränder ja |
| Reading Room | ljusstakar mässing | 25 | 25 | Höga par/kandelabrar ja – nattljusstakar, enstaka omärkta nej |
| Reading Room | sekretär | 11 | 6 | Rejäla med lådor/jalusi, 1 000–2 000 kr |
| Reading Room | byrå mahogny | 10 | 2 | Oftast rätt |
| Reading Room | läderband böcker | 8 | 4 | Enhetliga serier, låga priser |
| Reading Room | skrivbord mahogny | 5 | 4 | Engelsk stil, läderskiva, 1 500–2 500 kr |
| Reading Room | fåtölj läder | 1 | 17 | Moderna designfåtöljer – nej |
| Reading Room | lampett/vägglampa | 9 | 14 | Väggmonterat nej |

**Tvärgående mönster:** burkar med lock (Deco, Jie, Picknick) gillas genomgående. Varm mässingston ja, silver/krom nej.
Stockholm är ett plus (kunden hämtar gärna själv).

Färska siffror kan tas fram med SQL mot Supabase (`fyndjakt_reaktioner`, filtrera på `skapad`) och `data/sedda.db`
(kolumnen `sokord` per `nyckel`) – se avsnitt 7.

### 5.6 Mall – profilfil

```markdown
# Min smak – <Bevakningens namn>
*Ägare: … | Ny profil från <datum> – ersätter all tidigare*

<En–två meningar: vad bevakningen är till för. "Bedöm ENBART efter den här profilen.">

## <Kategori 1, t.ex. Glas>
- **<Formgivare/serie>** – vad som söks (typer, färger, storlekar). Vad som INTE söks.
- **<Formgivare/serie>** – … "Saknas: <konkret sak>" – högsta prioritet.

**INTE intresserad av:** <namn, serier, typer>.

## <Kategori 2 …>

## Skick och äkthet
<Vad som drar ner: nagg, krackelering, nyproduktion, osignerat …>

## Prisnivåer
- <Typ>: <spann> kr. Lågt pris är ett plus. Långt över drar ner.

## Redan i samlingen (ge lågt åt exakt samma sak)
- <Föremål med nummer/variant>
```

### 5.7 Mall – config-block

```yaml
  samlingen:
    namn: Samlingen
    profilfil: samlingsprofil.md
    tillagg: |
      Bedöm ENBART efter profilen ovan. Det kunden inte nämner där är inte intressant.
      <Hårda regler: "X högst 2", "bara Y kan få 8+">
      PLATS: Kunden bor i Stockholm … +1 / −2 (behåll)
    uteslut_ord: [<ord som alltid betyder fel>]
    lardomar_bas: |
      - <En konkret regel per rad: serie/typ ja – serie/typ nej, prisnivå>
    bedomningsregler: |
      <Vad kunden samlar>. Var sparsam med 9 och 10:
      - 10: <ovanlig variant / uttryckligen saknad sak / långt under marknadspris>
      - 9: <eftersökt serie, form som inte är vardaglig, bra pris>
      - 8: <rätt serie, vanlig form, gott skick>
      - 6–7: <rätt fabrik men fel serie, dåligt skick>
      - 4–5: <osäkert, nyproduktion>
      - 0–3: <fel kategori, nej-listan, exakt det kunden har>
    max_pris: 40000
    sokningar:
      <Kategori som visas som filter>:
        - <sökord>
```

### 5.8 Kontrollista innan du lämnar över
- [ ] Varje serie/formgivare har en rad om vilka **typer** som är ja och nej.
- [ ] Nej-listan är explicit (namn + "högst 2").
- [ ] Det som redan ägs står med nummer/variant.
- [ ] 9–10 är reserverat för ovanliga/saknade saker.
- [ ] Sökord: namn + typ där namnet ensamt drar skräp; felstavningar; engelska vid behov; inga från listan i 5.4.
- [ ] Inga `har_redan_ord` för sådant kunden vill ha fler av.
- [ ] Beslut: `smak_nystart` (börja om) eller `omvardera_fore` (behåll lärdomar).

---

## 6. Så läggs en ny Min smak in

1. Ersätt profilfilen och config-blocket i repot.
2. Sätt `smak_nystart` och/eller `omvardera_fore` för spåret till nu (UTC).
3. Kör `python -m pytest -q` (testerna kontrollerar bl.a. att config laddas).
4. Commit + push till `main`. **En push som ändrar `stil.md`, `samlingsprofil.md` eller `kor_nu.txt` startar en körning direkt**
   (~30–60 min, 8–15 kr med omvärdering). Annars sker det nästa natt (från 23:07 svensk tid).
5. Kontrollera efteråt: `data/senaste_korning.json` (kostnad, "Omvärdering med ny smak", fel) och fynd per sökord i `data/sedda.db`.

---

## 7. Användbara frågor

```sql
-- Supabase: kundens reaktioner sedan nystart
select typ, spar, titel, kommentar, skapad from fyndjakt_reaktioner
where user_id = (select user_id from fyndjakt_anvandare where epost = 'lundgrenper.pl@gmail.com')
  and skapad > '2026-10-13 23:30' order by skapad;
```

```sql
-- data/sedda.db: aktiva fynd per sökord
select spar, sokord, count(*) from sedda
where betyg >= 8 and (slutar_ts is null or slutar_ts > strftime('%s','now'))
group by spar, sokord order by 3 desc;
```

Koppla reaktioner till sökord via `nyckel` (samma i båda).

---

## 8. Drift i korthet

- **Schema:** GitHub försenar schemalagda körningar flera timmar, därför finns flera cron-tider från 23:07. En körning per
  "natt" (fönster 20:00–20:00 svensk tid); senare försök avbryts direkt.
- **Kostnad:** Haiku via Batch-API (50 % rabatt), 5 annonser per anrop, 1 bild. Kostnadsmätaren skriver till
  `data/senaste_korning.json → kostnad`. Slut på Anthropic-krediter → push-notis till admin.
- **Publicering utan körning:** ändra `sajt_version.txt` (eller `publicera.py`) → sidan och allas fynd publiceras om från
  befintlig databas på ~1 min.
- **Nycklar:** `ANTHROPIC_API_KEY`, `TRADERA_APP_ID`, `TRADERA_APP_KEY`, `FYNDJAKT_BOT_TOKEN` finns som GitHub-secrets –
  skriv aldrig ut eller committa dem.
