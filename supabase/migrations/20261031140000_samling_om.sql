-- "Läs mer om pjäsen": Claudes faktaruta + Wikipedia-källor, sparad så att den inte hämtas om varje gång.
-- {text, kallor: [{titel, url, utdrag}], sokord: [...], datum}
alter table public.samling_foremal add column if not exists om jsonb;
