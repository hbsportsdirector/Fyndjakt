-- Samlingen delas mellan administratörerna (Per och Jill): en admin ser och ändrar alla föremål, all prishistorik
-- och alla bilder i bucketen samling. Övriga medlemmar ser fortfarande bara sina egna rader.
drop policy if exists "egna foremal" on public.samling_foremal;
create policy "egna foremal eller admin" on public.samling_foremal
  for all to authenticated
  using ((select public.fyndjakt_ar_medlem()) and (user_id = (select auth.uid()) or (select public.fyndjakt_ar_admin())))
  with check ((select public.fyndjakt_ar_medlem()) and (user_id = (select auth.uid()) or (select public.fyndjakt_ar_admin())));

drop policy if exists "egen prishistorik" on public.samling_prishistorik;
create policy "egen prishistorik eller admin" on public.samling_prishistorik
  for all to authenticated
  using (exists (select 1 from public.samling_foremal f where f.id = samling_prishistorik.foremal_id
                 and (f.user_id = (select auth.uid()) or (select public.fyndjakt_ar_admin()))))
  with check (exists (select 1 from public.samling_foremal f where f.id = samling_prishistorik.foremal_id
                      and (f.user_id = (select auth.uid()) or (select public.fyndjakt_ar_admin()))));

drop policy if exists "samling bilder egna" on storage.objects;
create policy "samling bilder egna eller admin" on storage.objects
  for all to authenticated
  using (bucket_id = 'samling' and ((storage.foldername(name))[1] = (select auth.uid())::text or (select public.fyndjakt_ar_admin())))
  with check (bucket_id = 'samling' and ((storage.foldername(name))[1] = (select auth.uid())::text or (select public.fyndjakt_ar_admin())));

-- Jill blir administratör, precis som Per (gjort direkt i databasen 2026-10-30):
-- update public.fyndjakt_anvandare set admin = true, namn = 'Jill' where lower(epost) = 'jilljonsson77@gmail.com';
