# Lägger in Fyndjakt i Windows schemaläggare: hel körning varje kväll 21:00 och snabbkörning varje timme 07–23.
# Kör en gång, som vanlig användare:
#   powershell -ExecutionPolicy Bypass -File tools\installera_schema.ps1
# Ta bort igen:
#   Unregister-ScheduledTask -TaskName "Fyndjakt kväll","Fyndjakt timme" -Confirm:$false
$rot = Split-Path -Parent $PSScriptRoot
$skript = Join-Path $rot "tools\kor_hemma.ps1"
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$inst = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4) -StartWhenAvailable -DontStopOnIdleEnd

$kvall = New-ScheduledTaskAction -Execute $ps -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$skript`"" -WorkingDirectory $rot
Register-ScheduledTask -TaskName "Fyndjakt kväll" -Action $kvall -Trigger (New-ScheduledTaskTrigger -Daily -At 21:00) -Settings $inst -Description "Fyndjakt: hela nattjakten, körs hemma" -Force | Out-Null

$timme = New-ScheduledTaskAction -Execute $ps -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$skript`" -Snabb" -WorkingDirectory $rot
# Varje dag 07:00, och sedan en gång i timmen i 16 timmar (till 23:00). Daily-utlösaren får upprepningen från en Once-utlösare.
$utl = New-ScheduledTaskTrigger -Daily -At 07:00
$utl.Repetition = (New-ScheduledTaskTrigger -Once -At 07:00 -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 16)).Repetition
Register-ScheduledTask -TaskName "Fyndjakt timme" -Action $timme -Trigger $utl -Settings $inst -Description "Fyndjakt: Tradera och Myrorna varje timme 07–23" -Force | Out-Null

Write-Host "Klart. Två uppgifter finns nu i Schemaläggaren: 'Fyndjakt kväll' (21:00) och 'Fyndjakt timme' (07–23, varje timme)."
Write-Host "Prova direkt:  Start-ScheduledTask -TaskName 'Fyndjakt timme'   – och läs data\hemma.log."
