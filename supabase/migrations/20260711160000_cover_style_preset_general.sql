-- cover-general-preset: the new GENERAL art-direction preset (premium enterprise infographic —
-- dark graphite + amber; light twin white + azure) becomes the house default.
--
-- `cover_jobs.style_preset` has no CHECK (the app validates against the runtime enum), so the only
-- schema surface is the column DEFAULT — flipped from 'nocturne' to 'general' so a row inserted
-- without an explicit preset (none exists today; the app always supplies one) matches the product
-- default. Existing rows keep their stored preset untouched.
--
-- Additive + deploy-safe: changes no stored data and rejects nothing. To reverse, set the default
-- back to 'nocturne'.

alter table public.cover_jobs
    alter column style_preset set default 'general';
