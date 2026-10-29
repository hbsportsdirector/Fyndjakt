-- Miniatyrbilder per fynd (max 200 px, JPEG som data-URL), så att andra appar (t.ex. Loppiskollen)
-- kan visa en bild per fynd utan att hämta från Tradera/Auctionet.
create table if not exists public.fyndjakt_bilder (
  nyckel text primary key,          -- samma som poster[].nyckel, t.ex. "tradera:757886219"
  mini text not null,               -- data-URL: "data:image/jpeg;base64,..."
  bredd int, hojd int,
  skapad timestamptz default now()
);

-- Läs för inloggade. Inga skrivpolicyer: bara service-rollen och nattjobbets funktioner nedan skriver.
alter table public.fyndjakt_bilder enable row level security;
revoke all on public.fyndjakt_bilder from anon, authenticated;
grant select on public.fyndjakt_bilder to authenticated;
create policy "inloggade läser miniatyrer" on public.fyndjakt_bilder
  for select to authenticated using (true);

-- Fynd i någon användares data.poster som saknar miniatyr: [{"nyckel": ..., "bild": bilder[0]}].
create or replace function public.fyndjakt_bilder_saknas(token text)
returns jsonb
language plpgsql stable security definer
set search_path to ''
as $$
begin
  perform public.fyndjakt_kolla_nyckel(token);
  return coalesce((
    select jsonb_agg(jsonb_build_object('nyckel', p.nyckel, 'bild', p.bild))
    from (select distinct on (e->>'nyckel') e->>'nyckel' as nyckel, e->'bilder'->>0 as bild
          from public.fyndjakt_fynd f, jsonb_array_elements(f.data->'poster') e
          where e->>'nyckel' is not null and e->'bilder'->>0 is not null) p
    where not exists (select 1 from public.fyndjakt_bilder b where b.nyckel = p.nyckel)), '[]'::jsonb);
end; $$;

-- Sparar miniatyrer: [{"nyckel", "mini", "bredd", "hojd"}]. Returnerar antal.
create or replace function public.fyndjakt_bilder_spara(token text, bilder jsonb)
returns integer
language plpgsql security definer
set search_path to ''
as $$
declare n integer;
begin
  perform public.fyndjakt_kolla_nyckel(token);
  insert into public.fyndjakt_bilder(nyckel, mini, bredd, hojd)
  select b->>'nyckel', b->>'mini', (b->>'bredd')::int, (b->>'hojd')::int
  from jsonb_array_elements(bilder) b
  where b->>'nyckel' is not null and b->>'mini' like 'data:image/%'
  on conflict (nyckel) do update set mini = excluded.mini, bredd = excluded.bredd,
    hojd = excluded.hojd, skapad = now();
  get diagnostics n = row_count;
  return n;
end; $$;

-- Tar bort miniatyrer vars nyckel inte längre finns i någon användares data.poster. Returnerar antal.
create or replace function public.fyndjakt_bilder_stada(token text)
returns integer
language plpgsql security definer
set search_path to ''
as $$
declare n integer;
begin
  perform public.fyndjakt_kolla_nyckel(token);
  delete from public.fyndjakt_bilder b
  where not exists (select 1 from public.fyndjakt_fynd f, jsonb_array_elements(f.data->'poster') e
                    where e->>'nyckel' = b.nyckel);
  get diagnostics n = row_count;
  return n;
end; $$;
