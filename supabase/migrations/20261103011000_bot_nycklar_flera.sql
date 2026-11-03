-- Flera bot-nycklar: nattkörningen på GitHub och hemmadatorn (referensbiblioteket) ska kunna ha var sin.
-- Tabellen var låst till exakt en rad (check id = 1). Nycklarna lagras fortfarande bara som sha256-hash;
-- fyndjakt_kolla_nyckel godtar vilken som helst av dem. Ny nyckel: tools/ny_bot_nyckel.py.
alter table public.fyndjakt_bot_nyckel drop constraint if exists fyndjakt_bot_nyckel_id_check;
alter table public.fyndjakt_bot_nyckel add column if not exists kommentar text;
