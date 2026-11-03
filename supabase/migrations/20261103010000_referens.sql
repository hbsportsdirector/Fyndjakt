-- Referensbiblioteket för stämplar: sålda poster från Auctionet (och egna rättelser) med fabrik, formgivare,
-- modellnummer, stämpelfras och bottenfoto. Fylls på av tools/referens_hamta.py med bot-nyckeln; medlemmar läser.

create table if not exists public.referens (
  id bigserial primary key,
  kalla text not null default 'auctionet',       -- auctionet | egen
  kalla_id text not null,                        -- Auctionets id, eller samlingens föremåls-id
  titel text,
  fabrik text,
  formgivare text,
  modell text,
  stampeltext text,
  text text,
  bild_url text,                                 -- botten/stämpeln (sista bilden)
  bilder jsonb not null default '[]'::jsonb,
  url text,
  pris integer,
  salt boolean not null default false,
  slutade date,
  sokfras text,
  hus text,
  parti boolean not null default false,          -- flera föremål i posten: sista bilden är inte säkert rätt stämpel
  skapad timestamptz not null default now(),
  unique (kalla, kalla_id)
);
create index if not exists referens_fabrik_modell on public.referens (fabrik, modell);
create index if not exists referens_formgivare on public.referens (formgivare);
create index if not exists referens_stampeltext on public.referens (lower(stampeltext));

alter table public.referens enable row level security;
drop policy if exists "medlemmar laser referenser" on public.referens;
create policy "medlemmar laser referenser" on public.referens for select using ((select public.fyndjakt_ar_medlem()));

-- Upsert av en lista poster med bot-nyckeln (samma som nattkörningen). Returnerar antalet sparade.
create or replace function public.referens_spara(token text, poster jsonb)
returns integer language plpgsql security definer set search_path = '' as $$
declare n integer := 0; p jsonb;
begin
  perform public.fyndjakt_kolla_nyckel(token);
  for p in select * from jsonb_array_elements(poster) loop
    if p->>'kalla_id' is null then continue; end if;
    insert into public.referens (kalla, kalla_id, titel, fabrik, formgivare, modell, stampeltext, text, bild_url, bilder, url, pris, salt, slutade, sokfras, hus, parti)
    values (coalesce(p->>'kalla', 'auctionet'), p->>'kalla_id', p->>'titel', p->>'fabrik', p->>'formgivare', p->>'modell', p->>'stampeltext',
            p->>'text', p->>'bild_url', coalesce(p->'bilder', '[]'::jsonb), p->>'url', (p->>'pris')::integer, coalesce((p->>'salt')::boolean, false),
            (p->>'slutade')::date, p->>'sokfras', p->>'hus', coalesce((p->>'parti')::boolean, false))
    on conflict (kalla, kalla_id) do update set
      titel = excluded.titel, fabrik = excluded.fabrik, formgivare = excluded.formgivare, modell = excluded.modell,
      stampeltext = excluded.stampeltext, text = excluded.text, bild_url = excluded.bild_url, bilder = excluded.bilder,
      url = excluded.url, pris = excluded.pris, salt = excluded.salt, slutade = excluded.slutade, hus = excluded.hus, parti = excluded.parti;
    n := n + 1;
  end loop;
  return n;
end $$;
revoke all on function public.referens_spara(text, jsonb) from public;
grant execute on function public.referens_spara(text, jsonb) to anon, authenticated;

-- Antal per fabrik – för guiden och för att se hur biblioteket växer.
create or replace function public.referens_antal()
returns table (fabrik text, antal bigint, salda bigint, med_modell bigint)
language sql stable security definer set search_path = '' as $$
  select fabrik, count(*), count(*) filter (where salt), count(*) filter (where modell is not null)
  from public.referens group by fabrik order by 2 desc;
$$;
