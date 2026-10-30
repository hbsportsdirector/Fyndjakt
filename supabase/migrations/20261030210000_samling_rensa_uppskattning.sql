-- De gamla uppskattningarna från Loppiskollen (uppskattat_min/max och saker) saknade källa och låg ofta långt över
-- sålda jämförelser. De raderades 2026-10-30 efter en kopia till samling_backup_20261030 (bara servicenyckeln kommer
-- åt den). Föreslagna värden mer än 3 × eller under 1/3 av nuvarande värde togs bort – sökningen hade träffat fel
-- sorts föremål. Applicerat i WORK 2026-10-30.
create table if not exists public.samling_backup_20261030 as
  select id, uppskattat_min, uppskattat_max, saker, marknad_min, marknad_max, marknad_sakerhet, auk_median, jfr, jfr_url,
         pris_uppdaterad, now() as sparad
  from public.samling_foremal;
alter table public.samling_backup_20261030 enable row level security;

update public.samling_foremal set uppskattat_min = null, uppskattat_max = null, saker = null
where uppskattat_min is not null or uppskattat_max is not null or saker is not null;

delete from public.samling_forslag fs using public.samling_foremal f
where f.id = fs.foremal_id and f.auk_median is not null and fs.median is not null
  and (fs.median::numeric / f.auk_median > 3 or fs.median::numeric / f.auk_median < 1.0/3);
