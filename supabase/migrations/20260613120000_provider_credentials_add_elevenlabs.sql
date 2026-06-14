-- V3 (Voice): admit ElevenLabs as a BYOK provider.
--
-- The voice toggle narrates a video in one pass with the tenant's own ElevenLabs TTS key, stored in
-- the same encrypted-at-rest vault as the LLM/search keys. The provider CHECK on
-- provider_credentials is kept in lockstep with BYOK_PROVIDERS (credential_store_protocol.py); this
-- widens it to admit 'elevenlabs'. No data change — the table's access posture (RLS enabled, no
-- policies, grants revoked, AEAD ciphertext) is untouched and continues to apply to the new rows.
--
-- The inline column CHECK from the create-table migration is auto-named
-- provider_credentials_provider_check by Postgres; replace it with the widened set. `if exists`
-- keeps this safe to re-run.
--
-- To reverse: restore the four-provider CHECK (a tenant must remove any elevenlabs key first, or the
-- restore fails the constraint).

alter table public.provider_credentials
    drop constraint if exists provider_credentials_provider_check;

alter table public.provider_credentials
    add constraint provider_credentials_provider_check
    check (provider in ('anthropic', 'voyage', 'search', 'youtube', 'elevenlabs'));
