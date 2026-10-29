create table if not exists public.fyndjakt_bilder (
  nyckel text primary key,
  mini text not null,
  bredd int,
  hojd int,
  skapad timestamptz not null default now()
);
comment on table public.fyndjakt_bilder is 'Miniatyr (data-URL, ~200 px JPEG) av första annonsbilden per fynd. Skrivs av nattkörningen, läses av Loppiskollen.';
alter table public.fyndjakt_bilder enable row level security;
drop policy if exists "medlemmar laser bilder" on public.fyndjakt_bilder;
create policy "medlemmar laser bilder" on public.fyndjakt_bilder
  for select to authenticated using ((select fyndjakt_ar_medlem()));
grant select on public.fyndjakt_bilder to authenticated;
grant all on public.fyndjakt_bilder to service_role;
