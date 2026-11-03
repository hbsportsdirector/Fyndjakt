-- Egna referenser: varje föremål i samlingen med känd tillverkare och minst två bilder (bild 2 = stämpeln) speglas
-- automatiskt till referensbiblioteket som kalla = 'egen'. Då är din egen stämpelbild facit nästa gång samma
-- stämpel dyker upp i Butik. Rättar du ett föremål uppdateras referensen; tas föremålet bort försvinner den.
-- bild_url för egna referenser är 'samling:<path i bucketen samling>' – sajten och edge-funktionen hämtar den signerat.

create or replace function public.referens_modell_ur(serie text)
returns text language sql immutable as $$
  select nullif(substring(coalesce(serie, '') from '\d{3,5}(?:/\d{1,4})?'), '');
$$;

create or replace function public.referens_fabrik_norm(t text)
returns text language sql immutable as $$
  select case
    when t ~* 'up+sala[ -]*ekeby|\mekeby\M|\mUE\M' then 'Upsala-Ekeby'
    when t ~* 'gusta[fv]sberg' then 'Gustavsberg'
    when t ~* 'r[öo]rstrand' then 'Rörstrand'
    when t ~* '\marabia\M' then 'Arabia'
    when t ~* 'royal copenhagen|kongelig' then 'Royal Copenhagen'
    when t ~* '\msaxbo\M' then 'Saxbo'
    when t ~* 'palshus' then 'Palshus'
    when t ~* 'bo ?fajans' then 'Bo Fajans'
    when t ~* '\mgefle\M' then 'Gefle'
    when t ~* 'h[öo]gan[äa]s' then 'Höganäs'
    when t ~* '\mboda\M' then 'Boda'
    when t ~* '\mkosta\M' then 'Kosta'
    when t ~* 'orrefors' then 'Orrefors'
    else nullif(btrim(t), '') end;
$$;

create or replace function public.referens_spegla_foremal()
returns trigger language plpgsql security definer set search_path = '' as $$
declare f record; bilder jsonb; stampel text; alla jsonb;
begin
  if tg_op = 'DELETE' then
    delete from public.referens where kalla = 'egen' and kalla_id = old.id;
    return old;
  end if;
  f := new;
  bilder := coalesce(f.bilder, '[]'::jsonb);
  if f.tillverkare is null or f.tillverkare in ('', 'Okänd') or jsonb_array_length(bilder) < 2 then
    delete from public.referens where kalla = 'egen' and kalla_id = f.id;
    return new;
  end if;
  stampel := 'samling:' || (bilder->1->>'path');
  select jsonb_agg('samling:' || (b->>'path')) into alla from jsonb_array_elements(bilder) b;
  insert into public.referens (kalla, kalla_id, titel, fabrik, formgivare, modell, stampeltext, text, bild_url, bilder, url, pris, salt, slutade, sokfras, hus, parti)
  values ('egen', f.id,
          case when f.nummer is not null then 'FJ-' || lpad(f.nummer::text, 4, '0') || ' ' else '' end || coalesce(f.namn, ''),
          public.referens_fabrik_norm(f.tillverkare), nullif(btrim(coalesce(f.formgivare, '')), ''),
          public.referens_modell_ur(f.serie), nullif(left(coalesce(f.stampel, ''), 240), ''),
          left(concat_ws(' ', f.serie, f.period, f.skick, f.anteckning), 600),
          stampel, coalesce(alla, '[]'::jsonb), null, f.salt_for, f.salt_for is not null, f.salt_datum, 'egen', 'Egen samling',
          coalesce(f.antal, 1) > 1)
  on conflict (kalla, kalla_id) do update set
    titel = excluded.titel, fabrik = excluded.fabrik, formgivare = excluded.formgivare, modell = excluded.modell,
    stampeltext = excluded.stampeltext, text = excluded.text, bild_url = excluded.bild_url, bilder = excluded.bilder,
    pris = excluded.pris, salt = excluded.salt, slutade = excluded.slutade, parti = excluded.parti;
  return new;
end $$;

drop trigger if exists referens_spegla on public.samling_foremal;
create trigger referens_spegla
  after insert or update or delete on public.samling_foremal
  for each row execute function public.referens_spegla_foremal();

-- Spegla det som redan finns.
update public.samling_foremal set uppdaterad = uppdaterad where true;
