-- Nattkörningen (Fyndjakt) hämtar samlingen som "har redan"-rader. Skyddad med bot-nyckeln, som fyndjakt_export.
-- Returnerar [{user_id, id, namn, tillverkare, serie, lada}] för allt som inte är sålt (vyn samling_har_redan).
create or replace function public.samling_har_redan_export(token text)
returns jsonb
language plpgsql stable security definer
set search_path to ''
as $$
begin
  perform public.fyndjakt_kolla_nyckel(token);
  return coalesce((
    select jsonb_agg(jsonb_build_object('user_id', h.user_id, 'id', h.id, 'namn', h.namn,
                                        'tillverkare', h.tillverkare, 'serie', h.serie, 'lada', h.lada)
                     order by h.user_id, h.namn)
    from public.samling_har_redan h), '[]'::jsonb);
end; $$;

revoke all on function public.samling_har_redan_export(text) from public;
grant execute on function public.samling_har_redan_export(text) to anon, authenticated, service_role;
