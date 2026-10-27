-- Flipp-spår: profiler som betygsätts på pris (aktuellt pris / typiskt slutpris) i stället för smak.
alter table public.fyndjakt_profiler add column if not exists flipp boolean default false;
