# Fyndjakt hemma: kör nattjakten (eller en snabbkörning) på den egna datorn och sparar resultatet i repot.
#
#   powershell -ExecutionPolicy Bypass -File tools\kor_hemma.ps1          # hela körningen (som nattjobbet på GitHub)
#   powershell -ExecutionPolicy Bypass -File tools\kor_hemma.ps1 -Snabb   # bara Tradera och Myrorna, liten budget
#
# Nycklarna läses ur miljövariabler (se docs/hemma.md). Loggen hamnar i data\hemma.log. Ett lås i data\hemma.lock
# hindrar två körningar samtidigt. Fynden läggs upp i Supabase direkt av main.py – sajten behöver ingen ny publicering.
param([switch]$Snabb)
$ErrorActionPreference = "Continue"
$rot = Split-Path -Parent $PSScriptRoot
Set-Location $rot
$logg = Join-Path $rot "data\hemma.log"
$las = Join-Path $rot "data\hemma.lock"
function Logga($t) { $rad = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $t"; Write-Host $rad; Add-Content -Path $logg -Value $rad }

# Lås: en körning i taget. Ett lås äldre än fyra timmar räknas som kvarglömt.
if (Test-Path $las) {
  if ((Get-Date) - (Get-Item $las).LastWriteTime -lt (New-TimeSpan -Hours 4)) { Logga "Hoppar över – en körning pågår redan."; exit 0 }
  Remove-Item $las -Force
}
New-Item -ItemType File -Path $las -Force | Out-Null
try {
  foreach ($n in "ANTHROPIC_API_KEY", "FYNDJAKT_BOT_TOKEN") {
    if (-not [Environment]::GetEnvironmentVariable($n)) { Logga "Saknar miljövariabeln $n – se docs/hemma.md."; exit 1 }
  }
  if (-not $env:SAJT_URL) { $env:SAJT_URL = "https://hbsportsdirector.github.io/Fyndjakt/" }

  # Python 3.14, 3.13 eller 3.12 om någon finns (den allra nyaste versionen saknar färdiga paket för lxml, pillow och cryptography).
  $py = "python"; $pyArgs = @()
  if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($ver in "-3.14", "-3.13", "-3.12") { $v = & py $ver -c "print(1)" 2>$null; if ($v -eq "1") { $py = "py"; $pyArgs = @($ver); break } }
  }

  Logga ("Startar " + $(if ($Snabb) { "snabbkörning" } else { "hel körning" }) + " med $py $pyArgs")
  git pull -q --rebase origin main 2>&1 | ForEach-Object { Logga "git: $_" }

  $flaggor = @()
  if ($Snabb) { $flaggor += "--snabb" }
  & $py @pyArgs main.py @flaggor 2>&1 | Tee-Object -FilePath $logg -Append | Out-Null
  $kod = $LASTEXITCODE
  Logga "main.py avslutades med kod $kod"

  # Spara sedda annonser och rapporten, precis som nattjobbet på GitHub gör.
  git add data/sedda.db data/senaste_korning.json 2>$null
  git add data/smakanalys.json data/kategoriprofiler.json 2>$null
  git diff --cached --quiet
  if ($LASTEXITCODE -ne 0) {
    git -c user.name="fyndjakt-hemma" -c user.email="fyndjakt-hemma@users.noreply.github.com" commit -q -m $(if ($Snabb) { "Uppdatera sedda annonser (hemma, snabb)" } else { "Uppdatera sedda annonser (hemma)" })
    $ok = $false
    for ($i = 0; $i -lt 3 -and -not $ok; $i++) {
      git push -q origin HEAD:main 2>&1 | ForEach-Object { Logga "git: $_" }
      if ($LASTEXITCODE -eq 0) { $ok = $true; break }
      git fetch -q origin main
      git rebase -X theirs origin/main 2>&1 | ForEach-Object { Logga "git: $_" }
      Start-Sleep -Seconds 5
    }
    Logga $(if ($ok) { "Resultatet är sparat i repot." } else { "Kunde inte pusha – försöker nästa gång." })
  } else { Logga "Inget nytt att spara." }
  exit $kod
} finally {
  Remove-Item $las -Force -ErrorAction SilentlyContinue
}
