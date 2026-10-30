-- Samlingen delas mellan administratörerna (Per och Jill): en admin ser och ändrar alla föremål, all prishistorik
-- och alla bilder i bucketen samling. Reglerna läggs till bredvid de befintliga "egna"-reglerna (RLS slår ihop
-- tillåtande regler med ELLER), så övriga medlemmar ser fortfarande bara sina egna rader.
-- Applicerad i WORK 2026-10-30.
create policy "admin ser alla foremal" on public.samling_foremal
  for all to authenticated
  using ((select public.fyndjakt_ar_medlem()) and (select public.fyndjakt_ar_admin()))
  with check ((select public.fyndjakt_ar_medlem()) and (select public.fyndjakt_ar_admin()));

create policy "admin ser all prishistorik" on public.samling_prishistorik
  for all to authenticated
  using ((select public.fyndjakt_ar_admin()))
  with check ((select public.fyndjakt_ar_admin()));

create policy "admin ser alla samlingsbilder" on storage.objects
  for all to authenticated
  using (bucket_id = 'samling' and (select public.fyndjakt_ar_admin()))
  with check (bucket_id = 'samling' and (select public.fyndjakt_ar_admin()));

-- Jill blev administratör, precis som Per (gjort direkt i databasen 2026-10-30):
-- update public.fyndjakt_anvandare set admin = true, namn = 'Jill' where lower(epost) = 'jilljonsson77@gmail.com';
