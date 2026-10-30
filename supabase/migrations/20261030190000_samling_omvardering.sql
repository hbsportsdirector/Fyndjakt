-- Omvärderingen av samlingen (tools/vardera_samlingen.py, GitHub Actions). Skyddad med bot-nyckeln som
-- fyndjakt_export – Actions har inte servicenyckeln.

-- Underlaget: alla föremål som inte är sålda.
create or replace function public.samling_varde_underlag(token text)
returns jsonb
language plpgsql stable security definer
set search_path to ''
as $$
begin
  perform public.fyndjakt_kolla_nyckel(token);
  return coalesce((
    select jsonb_agg(jsonb_build_object('id', f.id, 'namn', f.namn, 'kategori', f.kategori, 'tillverkare', f.tillverkare,
                                        'serie', f.serie, 'sokord', f.sokord, 'antal', f.antal, 'anteckning', f.anteckning,
                                        'auk_median', f.auk_median) order by f.id)
    from public.samling_foremal f where f.lada <> 'salt'), '[]'::jsonb);
end; $$;

-- Sparar värderingarna: [{id, fras, median, lag, hog, antal, text, url, uppdatera}]. Returnerar antal uppdaterade.
-- Inget går förlorat: första gången sparas det gamla värdet som en rad i prishistoriken (kalla 'tidigare'),
-- och en tidigare jämförelsetext flyttas till anteckningen innan den ersätts.
create or replace function public.samling_varde_spara(token text, poster jsonb)
returns integer
language plpgsql security definer
set search_path to ''
as $$
declare p jsonb; f public.samling_foremal; n integer := 0; idag date := current_date;
begin
  perform public.fyndjakt_kolla_nyckel(token);
  for p in select * from jsonb_array_elements(poster) loop
    select * into f from public.samling_foremal where id = p->>'id';
    if not found then continue; end if;
    -- Sökordet sparas om föremålet saknade ett (nästa körning blir billigare och Fyndjakt får bättre "har redan").
    if coalesce(f.sokord, '') = '' and coalesce(p->>'fras', '') <> '' then
      update public.samling_foremal set sokord = p->>'fras' where id = f.id;
    end if;
    if coalesce((p->>'uppdatera')::boolean, false) is false then continue; end if;
    if f.auk_median is not null and not exists (select 1 from public.samling_prishistorik h where h.foremal_id = f.id) then
      insert into public.samling_prishistorik(foremal_id, datum, median, lag, hog, antal, kalla)
      values (f.id, least(coalesce(f.pris_uppdaterad, f.skapad::date), idag - 1), f.auk_median, f.marknad_min, f.marknad_max, null, 'tidigare')
      on conflict (foremal_id, datum) do nothing;
    end if;
    insert into public.samling_prishistorik(foremal_id, datum, median, lag, hog, antal, kalla)
    values (f.id, idag, (p->>'median')::int, (p->>'lag')::int, (p->>'hog')::int, (p->>'antal')::int, 'auctionet')
    on conflict (foremal_id, datum) do update set median = excluded.median, lag = excluded.lag, hog = excluded.hog,
      antal = excluded.antal, kalla = excluded.kalla;
    update public.samling_foremal set
      auk_median = (p->>'median')::int,
      pris_uppdaterad = idag,
      jfr = p->>'text',
      jfr_url = p->>'url',
      anteckning = case when coalesce(f.jfr, '') <> '' and f.jfr not like 'Auctionet %' and position(f.jfr in coalesce(f.anteckning, '')) = 0
                        then concat_ws(E'\n', nullif(f.anteckning, ''), 'Tidigare jämförelse: ' || f.jfr) else f.anteckning end,
      uppdaterad = now()
    where id = f.id;
    n := n + 1;
  end loop;
  return n;
end; $$;

revoke all on function public.samling_varde_underlag(text) from public;
revoke all on function public.samling_varde_spara(text, jsonb) from public;
grant execute on function public.samling_varde_underlag(text) to anon, authenticated, service_role;
grant execute on function public.samling_varde_spara(text, jsonb) to anon, authenticated, service_role;
