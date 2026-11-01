-- "Fråga Claude" per föremål: samtalet sparas med föremålet ([{roll: "jag"|"claude", text, t}]).
alter table public.samling_foremal add column if not exists chatt jsonb;
