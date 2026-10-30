-- Aktuella bud för fynden, hämtade av databasen själv (pg_net + pg_cron) – tätare ju närmare slutet.
-- Auctionet via det publika API:et. Tradera via det officiella API:et, men bara om Tradera-nycklarna finns i
-- Vault (fyndjakt_tradera_app_id, fyndjakt_tradera_app_key) – annars hoppas Tradera över.
-- Sidor som Loppiskollen läser fyndjakt_bud.

create table if not exists public.fyndjakt_bud (
  nyckel text primary key,              -- "auctionet:5401470", "tradera:756847540" (utan användar-/spårprefix)
  kalla text not null,
  pris int,                             -- högsta bud, annars utrop/nästa bud
  pris_text text,
  bud_antal int,
  nasta_bud int,
  reservation_uppnadd boolean,
  slutar_ts bigint,                     -- kan flyttas fram (förlängning vid sena bud)
  status text,                          -- pagar | avslutad
  hamtad timestamptz,
  andrad timestamptz                    -- senast priset ändrades
);
comment on table public.fyndjakt_bud is 'Aktuella bud för fynden i fyndjakt_fynd. Uppdateras av fyndjakt_bud_tick() var 30:e sekund (tätare nära slutet).';
alter table public.fyndjakt_bud enable row level security;
drop policy if exists "medlemmar laser bud" on public.fyndjakt_bud;
create policy "medlemmar laser bud" on public.fyndjakt_bud
  for select to authenticated using ((select fyndjakt_ar_medlem()));
revoke all on public.fyndjakt_bud from anon, authenticated;
grant select on public.fyndjakt_bud to authenticated;
grant all on public.fyndjakt_bud to service_role;

-- Utestående hämtningar (pg_net är asynkront: skicka nu, läs svaret vid nästa tick).
create table if not exists public.fyndjakt_bud_ko (
  request_id bigint primary key,
  nyckel text not null,
  kalla text not null,
  skickad timestamptz not null default now()
);
alter table public.fyndjakt_bud_ko enable row level security;
revoke all on public.fyndjakt_bud_ko from anon, authenticated;

-- Hur ofta ett fynd ska kollas (sekunder), efter tid kvar. null = inte alls.
create or replace function public.fyndjakt_bud_intervall(kalla text, kvar bigint)
returns int
language sql immutable
as $$
  select case
    when kvar < -900 then null          -- slutade för mer än 15 min sedan
    when kvar < 1800 then 25            -- sista halvtimmen: varje tick (30 s)
    when kvar < 3 * 3600 then 300
    when kvar < 86400 then 1800
    when kalla = 'auctionet' then 10800 -- Tradera-API:et sparas till sista dygnet
    else null
  end
$$;

create or replace function public.fyndjakt_bud_tick(max_per_tick int default 40)
returns jsonb
language plpgsql security definer
set search_path to ''
as $$
declare
  r record; j jsonb; it jsonb; nu bigint := extract(epoch from now())::bigint;
  lasta int := 0; skickade int := 0; fel int := 0;
  pris_ int; antal_ int; slut_ bigint; text_ text; status_ text; nasta_ int; res_ boolean;
  tid text; tnyckel text; id_ text;
begin
  -- 1. Läs svar som kommit.
  for r in select k.request_id, k.nyckel, k.kalla, h.status_code, h.content
           from public.fyndjakt_bud_ko k join net._http_response h on h.id = k.request_id loop
    begin
      if r.status_code = 200 then
        j := btrim(r.content)::jsonb;
        pris_ := null; antal_ := null; slut_ := null; nasta_ := null; res_ := null; it := null;
        if r.kalla = 'auctionet' then
          select x into it from jsonb_array_elements(j->'items') x
            where x->>'id' = split_part(r.nyckel, ':', 2) limit 1;
          if it is not null then
            select max((b->>'amount')::int), count(*) into pris_, antal_ from jsonb_array_elements(coalesce(it->'bids', '[]')) b;
            slut_ := (it->>'ends_at')::bigint;
            nasta_ := nullif(it->>'next_bid_amount', '')::int;
            res_ := (it->>'reserve_met')::boolean;
            text_ := case when coalesce(antal_, 0) > 0 then 'Bud ' || pris_ || ' ' || coalesce(it->>'currency', 'SEK')
                          else 'Utrop ' || coalesce(it->>'estimate', '?') || ' ' || coalesce(it->>'currency', 'SEK') end;
            if coalesce(antal_, 0) = 0 then pris_ := nullif(it->>'estimate', '')::int; end if;
            status_ := case when it->>'state' = 'published' and coalesce(slut_, nu + 1) > nu then 'pagar' else 'avslutad' end;
          end if;
        else -- tradera (API:et svarar i camelCase eller PascalCase)
          it := j;
          antal_ := coalesce(nullif(it->>'bidCount', ''), nullif(it->>'BidCount', ''), '0')::int;
          pris_ := coalesce(nullif(it->>'maxBid', ''), nullif(it->>'MaxBid', ''))::numeric::int;
          nasta_ := coalesce(nullif(it->>'nextBid', ''), nullif(it->>'NextBid', ''))::numeric::int;
          tid := coalesce(it->>'endDate', it->>'EndDate');
          slut_ := case when tid is not null then extract(epoch from tid::timestamptz)::bigint end;
          text_ := case when antal_ > 0 then 'Bud ' || pris_ || ' kr' else 'Utrop ' || coalesce(nasta_::text, '?') || ' kr' end;
          if antal_ = 0 then pris_ := nasta_; end if;
          status_ := case when coalesce(slut_, nu + 1) > nu then 'pagar' else 'avslutad' end;
        end if;
        if it is not null then
          insert into public.fyndjakt_bud as b (nyckel, kalla, pris, pris_text, bud_antal, nasta_bud,
                                                reservation_uppnadd, slutar_ts, status, hamtad, andrad)
          values (r.nyckel, r.kalla, pris_, text_, antal_, nasta_, res_, slut_, status_, now(), now())
          on conflict (nyckel) do update set
            andrad = case when b.pris is distinct from excluded.pris then now() else b.andrad end,
            pris = excluded.pris, pris_text = excluded.pris_text, bud_antal = excluded.bud_antal,
            nasta_bud = excluded.nasta_bud, reservation_uppnadd = excluded.reservation_uppnadd,
            slutar_ts = excluded.slutar_ts, status = excluded.status, hamtad = now();
          lasta := lasta + 1;
        end if;
      else
        fel := fel + 1;
        update public.fyndjakt_bud set hamtad = now() where nyckel = r.nyckel; -- vänta ett intervall innan nästa försök
      end if;
    exception when others then
      fel := fel + 1;
    end;
    delete from public.fyndjakt_bud_ko where request_id = r.request_id;
  end loop;
  delete from public.fyndjakt_bud_ko where skickad < now() - interval '3 minutes'; -- svar som aldrig kom

  -- 2. Skicka nya hämtningar för fynd som är på tur – de som slutar först går först.
  select max(case when name = 'fyndjakt_tradera_app_id' then decrypted_secret end),
         max(case when name = 'fyndjakt_tradera_app_key' then decrypted_secret end)
    into id_, tnyckel from vault.decrypted_secrets where name like 'fyndjakt_tradera_app_%';
  for r in
    with poster as (
      select distinct on (k) k, split_part(k, ':', 1) kalla, split_part(k, ':', 2) id, ts
      from (select substring(e->>'nyckel' from '((?:auctionet|tradera):\d+)$') k, (e->>'slutar_ts')::bigint ts,
                   coalesce(e->>'pris_text', '') pt
            from public.fyndjakt_fynd f, jsonb_array_elements(f.data->'poster') e) x
      where k is not null and ts is not null
        and (k like 'auctionet:%' or pt ~* '^(bud|utrop)')   -- Tradera: bara auktioner, inte köp nu
      order by k, ts desc
    )
    select p.k, p.kalla, p.id, coalesce(b.slutar_ts, p.ts) - nu as kvar
    from poster p left join public.fyndjakt_bud b on b.nyckel = p.k
    where coalesce(b.status, 'pagar') = 'pagar' or coalesce(b.slutar_ts, p.ts) > nu - 900
    order by coalesce(b.slutar_ts, p.ts)
  loop
    exit when skickade >= max_per_tick;
    continue when public.fyndjakt_bud_intervall(r.kalla, r.kvar) is null;
    continue when exists (select 1 from public.fyndjakt_bud_ko k where k.nyckel = r.k);
    continue when exists (select 1 from public.fyndjakt_bud b where b.nyckel = r.k
                          and b.hamtad > now() - make_interval(secs => public.fyndjakt_bud_intervall(r.kalla, r.kvar)));
    if r.kalla = 'auctionet' then
      insert into public.fyndjakt_bud_ko (request_id, nyckel, kalla)
      values (net.http_get('https://auctionet.com/api/v2/items.json', jsonb_build_object('q', r.id),
                           '{"User-Agent": "Fyndjakt/1.0 (privat bevakning)"}'::jsonb, 10000), r.k, r.kalla);
    elsif id_ is not null and tnyckel is not null then
      insert into public.fyndjakt_bud_ko (request_id, nyckel, kalla)
      values (net.http_get('https://api.tradera.com/v4/items/' || r.id, '{}'::jsonb,
                           jsonb_build_object('X-App-Id', id_, 'X-App-Key', tnyckel, 'Accept', 'application/json'),
                           10000), r.k, r.kalla);
    else
      continue;
    end if;
    skickade := skickade + 1;
  end loop;

  -- Avslutade fynd som inte längre finns hos någon användare städas bort efter ett dygn.
  delete from public.fyndjakt_bud where hamtad < now() - interval '1 day' and status = 'avslutad';
  return jsonb_build_object('lasta', lasta, 'skickade', skickade, 'fel', fel);
end; $$;
revoke all on function public.fyndjakt_bud_tick(int) from public, anon, authenticated;

select cron.unschedule(jobid) from cron.job where jobname = 'fyndjakt-bud';
select cron.schedule('fyndjakt-bud', '30 seconds', $$select public.fyndjakt_bud_tick()$$);
