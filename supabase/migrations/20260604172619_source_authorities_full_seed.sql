-- P6.2 (T1): seed the full day-one source-authority config (plan §4a).
--
-- The universal spine (authoritative across every topic), the per-field packs (CS-ML / Medicine /
-- Physics / Chemistry) and the shared multidisciplinary venues (field = 'shared', loaded for every
-- run), plus the social-broadcast denylist. Tier is the authority *prior*; source_type records what
-- the source IS (peer-reviewed vs preprint vs official vs database/reference/docs). A pack hit sets
-- the tier prior only — it never inflates the credibility score (§4a). Everything here is editable at
-- runtime via the Trusted-sources UI (T4); this is just the seed, not a code-level source of truth.
--
-- Idempotent: ON CONFLICT DO NOTHING on (domain, field), so re-running (or the T0 representative rows
-- already present) is a no-op. Preprint servers (arxiv/medrxiv/chemrxiv) are tiered 'reputable' with
-- source_type = 'preprint' — a notch below peer-reviewed, captured by the type, not the tier.
--
-- To reverse this seed without dropping the T0 rows, delete the domains listed below; or, since the
-- two P6.2 migrations apply as a unit, `supabase db reset` reverts both. (A blanket
-- `delete ... where created_at < now()` would also wipe the T0 spine/denylist — don't use it.)

insert into public.source_authorities (domain, kind, field, tier, source_type) values
    -- Universal spine: standards bodies + encyclopedic references, authoritative across topics.
    ('en.wikipedia.org', 'spine', null, 'reputable', 'reference'),
    ('w3.org', 'spine', null, 'official', 'official'),
    ('ietf.org', 'spine', null, 'official', 'official'),
    ('rfc-editor.org', 'spine', null, 'official', 'official'),
    ('iso.org', 'spine', null, 'official', 'official'),
    ('developer.mozilla.org', 'spine', null, 'reputable', 'docs'),

    -- Shared multidisciplinary venues — loaded for every field (the field-loader treats 'shared' as
    -- always-applicable), so top-tier general-science venues are not duplicated per pack.
    ('nature.com', 'pack', 'shared', 'reputable', 'peer_reviewed'),
    ('science.org', 'pack', 'shared', 'reputable', 'peer_reviewed'),
    ('pnas.org', 'pack', 'shared', 'reputable', 'peer_reviewed'),

    -- CS / ML / AI: conferences outrank journals; arXiv is the field's preprint server.
    ('proceedings.neurips.cc', 'pack', 'cs_ml', 'reputable', 'peer_reviewed'),
    ('openreview.net', 'pack', 'cs_ml', 'reputable', 'peer_reviewed'),
    ('aclanthology.org', 'pack', 'cs_ml', 'reputable', 'peer_reviewed'),
    ('proceedings.mlr.press', 'pack', 'cs_ml', 'reputable', 'peer_reviewed'),
    ('jmlr.org', 'pack', 'cs_ml', 'reputable', 'peer_reviewed'),
    ('dl.acm.org', 'pack', 'cs_ml', 'reputable', 'peer_reviewed'),
    ('ieeexplore.ieee.org', 'pack', 'cs_ml', 'reputable', 'peer_reviewed'),
    ('usenix.org', 'pack', 'cs_ml', 'reputable', 'peer_reviewed'),
    ('openaccess.thecvf.com', 'pack', 'cs_ml', 'reputable', 'peer_reviewed'),
    ('dblp.org', 'pack', 'cs_ml', 'reputable', 'database'),
    ('arxiv.org', 'pack', 'cs_ml', 'reputable', 'preprint'),

    -- Medicine: default-HIGH-risk field. Cochrane = evidence-synthesis gold standard; medRxiv preprint.
    ('pubmed.ncbi.nlm.nih.gov', 'pack', 'medicine', 'official', 'database'),
    ('pmc.ncbi.nlm.nih.gov', 'pack', 'medicine', 'official', 'database'),
    ('cochranelibrary.com', 'pack', 'medicine', 'reputable', 'database'),
    ('who.int', 'pack', 'medicine', 'official', 'official'),
    ('nih.gov', 'pack', 'medicine', 'official', 'official'),
    ('cdc.gov', 'pack', 'medicine', 'official', 'official'),
    ('nice.org.uk', 'pack', 'medicine', 'official', 'official'),
    ('nejm.org', 'pack', 'medicine', 'reputable', 'peer_reviewed'),
    ('thelancet.com', 'pack', 'medicine', 'reputable', 'peer_reviewed'),
    ('jamanetwork.com', 'pack', 'medicine', 'reputable', 'peer_reviewed'),
    ('bmj.com', 'pack', 'medicine', 'reputable', 'peer_reviewed'),
    ('medlineplus.gov', 'pack', 'medicine', 'official', 'reference'),
    ('medrxiv.org', 'pack', 'medicine', 'reputable', 'preprint'),

    -- Physics: arXiv is primary; NIST = reference data; ADS = astrophysics index.
    ('journals.aps.org', 'pack', 'physics', 'reputable', 'peer_reviewed'),
    ('iopscience.iop.org', 'pack', 'physics', 'reputable', 'peer_reviewed'),
    ('pubs.aip.org', 'pack', 'physics', 'reputable', 'peer_reviewed'),
    ('nist.gov', 'pack', 'physics', 'official', 'database'),
    ('ui.adsabs.harvard.edu', 'pack', 'physics', 'reputable', 'database'),
    ('home.cern', 'pack', 'physics', 'official', 'official'),
    ('arxiv.org', 'pack', 'physics', 'reputable', 'preprint'),

    -- Chemistry: PubChem / NIST WebBook = authoritative factual data; chemRxiv preprint.
    ('pubs.acs.org', 'pack', 'chemistry', 'reputable', 'peer_reviewed'),
    ('pubs.rsc.org', 'pack', 'chemistry', 'reputable', 'peer_reviewed'),
    ('onlinelibrary.wiley.com', 'pack', 'chemistry', 'reputable', 'peer_reviewed'),
    ('pubchem.ncbi.nlm.nih.gov', 'pack', 'chemistry', 'official', 'database'),
    ('webbook.nist.gov', 'pack', 'chemistry', 'official', 'database'),
    ('iupac.org', 'pack', 'chemistry', 'official', 'official'),
    ('chemrxiv.org', 'pack', 'chemistry', 'reputable', 'preprint'),

    -- Denylist (never ingested): social broadcast is not a grounding source, and URL shorteners hide
    -- their destination. These mirror classify_domain's in-code baseline so the table is the editable
    -- source of truth; that in-code set + cross-source agreement (T2/T5) remain the real defenses —
    -- an exhaustive denylist is impossible, this is hygiene for the obvious ones.
    ('x.com', 'denylist', null, 'blocked', null),
    ('twitter.com', 'denylist', null, 'blocked', null),
    ('facebook.com', 'denylist', null, 'blocked', null),
    ('instagram.com', 'denylist', null, 'blocked', null),
    ('tiktok.com', 'denylist', null, 'blocked', null),
    ('threads.net', 'denylist', null, 'blocked', null),
    ('t.me', 'denylist', null, 'blocked', null),
    ('bit.ly', 'denylist', null, 'blocked', null),
    ('tinyurl.com', 'denylist', null, 'blocked', null),
    ('t.co', 'denylist', null, 'blocked', null),
    ('goo.gl', 'denylist', null, 'blocked', null),
    ('ow.ly', 'denylist', null, 'blocked', null)
on conflict on constraint source_authorities_domain_field_key do nothing;
