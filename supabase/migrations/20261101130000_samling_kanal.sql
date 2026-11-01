-- Säljkanal per föremål till salu: "blocket" eller "tradera" (avhämtning), satt av Claude eller av ägaren.
alter table public.samling_foremal add column if not exists kanal text, add column if not exists kanal_varfor text;
