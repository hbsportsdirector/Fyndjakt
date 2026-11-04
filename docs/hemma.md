# Köra Fyndjakt hemma (EVO-X1)

Nattjakten kan köras på din egen dator i stället för på GitHub. Vinsten är två saker: **den går när du vill** (GitHub
försenar schemalagda körningar flera timmar och hoppar ibland över dem), och den kan **leta varje timme** på Tradera
och Myrorna, där billiga saker försvinner inom några timmar. GitHub-jobbet finns kvar som reserv: det ser i
`data/senaste_korning.json` om kvällens körning redan är gjord hemma och hoppar då över.

Fynden hamnar i Supabase direkt, så appen i telefonen märker ingen skillnad utom att de kommer oftare.

## 1. Python 3.14 (en gång)

Fyndjakt behöver paket som ännu inte finns färdigbyggda för Python 3.15 (lxml, pillow, cryptography). Installera därför
**Python 3.14** vid sidan om (3.12 får inga installationspaket längre): <https://www.python.org/downloads/windows/> →
"Python 3.14.x" → Windows installer (64-bit). Kryssa i "Add python.exe to PATH". Sedan, i PowerShell i `C:\Users\Per\Fyndjakt`:

```powershell
git pull
py -3.14 -m pip install -r requirements.txt
```

`py -3.14` väljer rätt version även om 3.15 är standard. Skriptet hittar den automatiskt (3.14, 3.13 eller 3.12).

## 2. Nycklarna (en gång)

Samma hemligheter som GitHub-jobbet har (GitHub → Settings → Secrets → Actions). Sätt dem som miljövariabler för din
användare, en rad per nyckel i PowerShell, och öppna sedan ett nytt fönster:

```powershell
[Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', 'sk-ant-…', 'User')
[Environment]::SetEnvironmentVariable('FYNDJAKT_BOT_TOKEN', '…', 'User')     # har du redan från referensbiblioteket
[Environment]::SetEnvironmentVariable('TRADERA_APP_ID', '…', 'User')
[Environment]::SetEnvironmentVariable('TRADERA_APP_KEY', '…', 'User')
[Environment]::SetEnvironmentVariable('TELEGRAM_BOT_TOKEN', '…', 'User')     # valfritt
[Environment]::SetEnvironmentVariable('TELEGRAM_CHAT_ID', '…', 'User')       # valfritt
```

Var de finns: Anthropic-nyckeln på <https://console.anthropic.com> (skapa en ny om du inte har den sparad – GitHub
visar aldrig sina). Tradera-nycklarna på <https://api.tradera.com> under din applikation.

## 3. Provkör

```powershell
py -3.14 main.py --torr
```

Torrkörningen hämtar annonser och skriver ut dem, utan Claude och utan att spara. Går den igenom är allt installerat.
Sedan en riktig snabbkörning:

```powershell
powershell -ExecutionPolicy Bypass -File tools\kor_hemma.ps1 -Snabb
```

Första gången skriptet pushar till GitHub öppnas ett inloggningsfönster (Git Credential Manager); logga in en gång, så
minns datorn det. Loggen hamnar i `data\hemma.log`.

## 4. Schemalägg (en gång)

```powershell
powershell -ExecutionPolicy Bypass -File tools\installera_schema.ps1
```

Det lägger in två uppgifter i Windows schemaläggare:

- **Fyndjakt kväll**, 21:00 varje dag: hela körningen, som nattjobbet på GitHub. Klar vid 22-tiden, innan GitHubs
  första försök, som då hoppar över. Är datorn av tar GitHub över som förut.
- **Fyndjakt timme**, varje hel timme 07–23: snabbkörning – bara Tradera och Myrorna, högst 60 bedömningar och
  30 prisjämförelser per gång (ändra med `snabb_max_bedomningar` och `snabb_max_prisjamforelser` i `config.yaml`).
  Räknas inte som kvällens körning.

Datorn måste vara igång: Inställningar → System → Ström → "Försätt enheten i viloläge" på **Aldrig** när den är nätansluten.

Prova direkt: `Start-ScheduledTask -TaskName 'Fyndjakt timme'`, och läs `data\hemma.log`.

## Att veta

- Två körningar går aldrig samtidigt (lås i `data\hemma.lock`). Kör något redan hoppar timkörningen över, medan
  kvällskörningen väntar upp till 45 minuter – timkörningen startar också 21:00.
- Resultatet (`data/sedda.db` med mera) committas och pushas till main efter varje körning, så att GitHub-reserven ser
  samma läge. Skriptet ställer sig alltid på grenen `main` och hämtar senaste koden före varje körning. Krockar
  datafilerna med något som pushats under tiden tar det GitHubs kod och lägger sina egna datafiler ovanpå – inget
  rebase som kan lämna repot "utanför en gren".
- Stäng av: `Unregister-ScheduledTask -TaskName "Fyndjakt kväll","Fyndjakt timme" -Confirm:$false`. GitHub tar då
  över nästa natt utan att något behöver ändras.
- `data/sedda.db` städas i början av varje körning: utgångna annonser töms på bilder och länkar efter två veckor,
  rader äldre än 60 dagar tas bort, och filen krymps. Den bör hålla sig kring 40–60 MB (GitHub varnar över 50 MB,
  men stoppar först vid 100).
- Kostnad: snabbkörningarna är små (högst 60 bedömningar à ca 2,5 öre), men de är 17 om dagen. Räkna med ungefär
  samma Claude-kostnad per dag som en nattkörning till.
