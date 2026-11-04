-- referens_antal() läste hela tabellen (200 000 rader, 18 s) och slog i tidsgränsen för anrop.
-- Indexet bär nu även "salt", så räkningen klarar sig med indexet ensamt (under 1 s). Uppslagen på
-- fabrik + modell i stämpelsökningen använder samma index.
create index if not exists referens_fabrik_modell_salt on public.referens (fabrik, modell) include (salt);
drop index if exists public.referens_fabrik_modell;
