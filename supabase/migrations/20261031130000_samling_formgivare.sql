-- Formgivare som eget fält (tidigare inbakad i serie/anteckning). Fylls av den guidade identifieringen.
alter table public.samling_foremal add column if not exists formgivare text;
