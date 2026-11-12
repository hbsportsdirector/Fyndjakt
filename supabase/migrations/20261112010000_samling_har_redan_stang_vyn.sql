-- Vyn samling_har_redan gick runt radskyddet (security definer) och var läs- och skrivbar för oinloggade:
-- vem som helst med sajtens publika nyckel kunde läsa hela samlingen. Nu följer vyn anroparens rättigheter,
-- och bara nattkörningen når den (via samling_har_redan_export med bot-nyckeln, eller med servicenyckeln).
-- Applicerad i WORK 2026-11-12. Kontrollerat: anon och authenticated nekas, exporten ser alla rader.
alter view public.samling_har_redan set (security_invoker = true);
revoke all on public.samling_har_redan from anon, authenticated, public;
