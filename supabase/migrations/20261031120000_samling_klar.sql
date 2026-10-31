-- Till salu-flödet: Att fixa → Klar att lägga ut (klar) → Upplagd (upplagd) → Sålt.
alter table public.samling_foremal add column if not exists klar timestamptz;
