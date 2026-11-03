"""Skapar en ny bot-nyckel för Fyndjakt (den som nattkörningen och hemmaskripten använder mot Supabase).

Själva nyckeln skrivs bara ut här, på din dator – spara den som miljövariabeln FYNDJAKT_BOT_TOKEN.
Databasen lagrar bara en hash av nyckeln, och hashen är ofarlig att dela: klistra in SQL-raden i Supabase
(SQL Editor), eller skicka hashen till Claude så lägger den in den. Flera nycklar kan finnas samtidigt.

Kör:  python tools/ny_bot_nyckel.py
"""
import hashlib
import secrets

nyckel = "fj_" + secrets.token_urlsafe(36)
hash_ = hashlib.sha256(nyckel.encode()).hexdigest()
print("Din nya bot-nyckel (spara den – den visas bara nu):\n")
print("  " + nyckel + "\n")
print("Lägg in hashen i databasen (ofarlig att dela):\n")
print(f"  insert into public.fyndjakt_bot_nyckel (id, hash) values ((select coalesce(max(id), 0) + 1 from public.fyndjakt_bot_nyckel), '{hash_}');\n")
print("Windows (PowerShell), sätt nyckeln för alltid:   [Environment]::SetEnvironmentVariable('FYNDJAKT_BOT_TOKEN', '" + nyckel + "', 'User')")
print("Linux/macOS:   echo 'export FYNDJAKT_BOT_TOKEN=" + nyckel + "' >> ~/.bashrc")
