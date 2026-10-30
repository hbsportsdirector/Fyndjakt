-- Värderingsförslag att granska: omvärderingen (tools/vardera_samlingen.py) lägger här de värden den inte vågar
-- ändra själv (stor ändring, osäker attribution, allmänt sökord, få sålda, konst). På sajten väljer man
-- "Använd förslaget" eller "Behåll mitt". Partier och låsta värden föreslås aldrig.
create table if not exists public.samling_forslag (
  foremal_id text primary key references public.samling_foremal(id) on delete cascade,
  datum date not null default current_date,
  median integer, lag integer, hog integer, antal integer,
  fras text, skal text, text text, url text,
  skapad timestamptz not null default now()
);
alter table public.samling_forslag enable row level security;
drop policy if exists "forslag egna eller admin" on public.samling_forslag;
create policy "forslag egna eller admin" on public.samling_forslag
  for select to authenticated
  using ((select public.fyndjakt_ar_medlem()) and exists (
    select 1 from public.samling_foremal f where f.id = samling_forslag.foremal_id
      and (f.user_id = (select auth.uid()) or (select public.fyndjakt_ar_admin()))));
grant select on public.samling_forslag to authenticated;
grant all on public.samling_forslag to service_role;

-- Skriver ett nytt värde: gamla värdet till prishistoriken (första gången), dagens rad, föremålet, och flyttar en
-- tidigare jämförelsetext till anteckningen. Används av samling_varde_spara och samling_forslag_svara.
create or replace function public.samling_varde_skriv(p_id text, p_median integer, p_lag integer, p_hog integer,
                                                       p_antal integer, p_text text, p_url text)
returns void
language plpgsql security definer
set search_path to ''
as $$
declare f public.samling_foremal; idag date := current_date;
begin
  select * into f from public.samling_foremal where id = p_id;
  if not found then return; end if;
  if f.auk_median is not null and not exists (select 1 from public.samling_prishistorik h where h.foremal_id = f.id) then
    insert into public.samling_prishistorik(foremal_id, datum, median, lag, hog, antal, kalla)
    values (f.id, least(coalesce(f.pris_uppdaterad, f.skapad::date), idag - 1), f.auk_median, f.marknad_min, f.marknad_max, null, 'tidigare')
    on conflict (foremal_id, datum) do nothing;
  end if;
  insert into public.samling_prishistorik(foremal_id, datum, median, lag, hog, antal, kalla)
  values (f.id, idag, p_median, p_lag, p_hog, p_antal, 'auctionet')
  on conflict (foremal_id, datum) do update set median = excluded.median, lag = excluded.lag, hog = excluded.hog,
    antal = excluded.antal, kalla = excluded.kalla;
  update public.samling_foremal set
    auk_median = p_median, pris_uppdaterad = idag, jfr = p_text, jfr_url = p_url,
    anteckning = case when coalesce(f.jfr, '') <> '' and f.jfr not like 'Auctionet %' and position(f.jfr in coalesce(f.anteckning, '')) = 0
                      then concat_ws(E'\n', nullif(f.anteckning, ''), 'Tidigare jämförelse: ' || f.jfr) else f.anteckning end
  where id = f.id;
end; $$;
revoke all on function public.samling_varde_skriv(text, integer, integer, integer, integer, text, text) from public, anon, authenticated;

-- Omvärderingens sparning: [{id, fras, uppdatera, forslag, skal, median, lag, hog, antal, text, url}].
create or replace function public.samling_varde_spara(token text, poster jsonb)
returns integer
language plpgsql security definer
set search_path to ''
as $$
declare p jsonb; f public.samling_foremal; n integer := 0;
begin
  perform public.fyndjakt_kolla_nyckel(token);
  for p in select * from jsonb_array_elements(poster) loop
    select * into f from public.samling_foremal where id = p->>'id';
    if not found then continue; end if;
    if coalesce(f.sokord, '') = '' and coalesce(p->>'fras', '') <> '' then
      update public.samling_foremal set sokord = p->>'fras' where id = f.id;
    end if;
    if coalesce((p->>'uppdatera')::boolean, false) then
      perform public.samling_varde_skriv(f.id, (p->>'median')::int, (p->>'lag')::int, (p->>'hog')::int,
                                         (p->>'antal')::int, p->>'text', p->>'url');
      delete from public.samling_forslag where foremal_id = f.id;
      n := n + 1;
    elsif coalesce((p->>'forslag')::boolean, false) then
      insert into public.samling_forslag(foremal_id, datum, median, lag, hog, antal, fras, skal, text, url)
      values (f.id, current_date, (p->>'median')::int, (p->>'lag')::int, (p->>'hog')::int, (p->>'antal')::int,
              p->>'fras', p->>'skal', p->>'text', p->>'url')
      on conflict (foremal_id) do update set datum = excluded.datum, median = excluded.median, lag = excluded.lag,
        hog = excluded.hog, antal = excluded.antal, fras = excluded.fras, skal = excluded.skal, text = excluded.text,
        url = excluded.url, skapad = now();
    else
      delete from public.samling_forslag where foremal_id = f.id;
    end if;
  end loop;
  return n;
end; $$;

-- Svar från sajten: använd förslaget (nytt värde) eller behåll det nuvarande. Returnerar föremålet.
create or replace function public.samling_forslag_svara(p_id text, p_anvand boolean)
returns jsonb
language plpgsql security definer
set search_path to ''
as $$
declare fs public.samling_forslag;
begin
  if not public.fyndjakt_ar_medlem() or not exists (select 1 from public.samling_foremal f where f.id = p_id
       and (f.user_id = auth.uid() or public.fyndjakt_ar_admin())) then
    raise exception 'ingen åtkomst';
  end if;
  select * into fs from public.samling_forslag where foremal_id = p_id;
  if found and p_anvand then
    perform public.samling_varde_skriv(p_id, fs.median, fs.lag, fs.hog, fs.antal, fs.text, fs.url);
  end if;
  delete from public.samling_forslag where foremal_id = p_id;
  return (select to_jsonb(f) from public.samling_foremal f where f.id = p_id);
end; $$;
revoke all on function public.samling_forslag_svara(text, boolean) from public, anon;
grant execute on function public.samling_forslag_svara(text, boolean) to authenticated;
