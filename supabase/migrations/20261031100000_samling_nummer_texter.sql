-- Köpt-flödet: löpnummer FJ-0001 … för varje föremål (gemensamt för den delade samlingen) och tre texter:
-- beskrivning (katalogtext), säljannons (rubrik + text) och proveniens (var/när/för hur mycket det köptes).
create sequence if not exists public.samling_nummer_seq;

alter table public.samling_foremal
  add column if not exists nummer integer,
  add column if not exists beskrivning text,
  add column if not exists annons_rubrik text,
  add column if not exists annons_text text,
  add column if not exists proveniens text;

-- Befintliga föremål numreras i den ordning de köptes/lades in (utan att röra "uppdaterad").
alter table public.samling_foremal disable trigger samling_foremal_touch;
with ordning as (
  select id, row_number() over (order by coalesce(inkopt, skapad::date), skapad, id) as n
  from public.samling_foremal where nummer is null
)
update public.samling_foremal f set nummer = o.n + coalesce((select max(nummer) from public.samling_foremal), 0)
from ordning o where f.id = o.id;
alter table public.samling_foremal enable trigger samling_foremal_touch;

select setval('public.samling_nummer_seq', greatest(1, (select coalesce(max(nummer), 0) from public.samling_foremal)),
              (select count(*) > 0 from public.samling_foremal where nummer is not null));
alter sequence public.samling_nummer_seq owned by public.samling_foremal.nummer;
alter table public.samling_foremal alter column nummer set default nextval('public.samling_nummer_seq');
create unique index if not exists samling_foremal_nummer_idx on public.samling_foremal (nummer);
grant usage, select on sequence public.samling_nummer_seq to authenticated;
