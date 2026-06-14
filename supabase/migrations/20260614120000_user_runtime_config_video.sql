-- Explainer-video V6 (T0): widen the per-user runtime config to carry the video settings.
--
-- The per-user `user_runtime_config` table (T8) constrained `config_key` to model selection only
-- (`modelStrong` / `modelWorker`). V6 lets a tenant control their own video generation — a master
-- toggle, a voice toggle, and the three per-kind target lengths — through the same per-user config
-- surface (`/api/config`), so the build path reads them from the run-config scope just like the
-- chosen models. These are NON-secret (the owner reads + edits them); the existing owner-scoped RLS
-- and grants already cover the new keys (they constrain WHICH rows, not which `config_key`), so this
-- migration only relaxes the key whitelist. Values stay `text` within the existing 1..200 bound
-- (booleans as 'true'/'false'; lengths as a whole number of seconds the app re-validates in range).
--
-- Kept in lockstep with `PER_USER_CONFIG` (user_config/store_protocol.py): a new per-user key is a
-- change in both places.
--
-- Additive + deploy-safe: no existing row uses a video key, so widening the allowed set rejects
-- nothing already stored. To reverse, narrow the CHECK back to ('modelStrong', 'modelWorker') after
-- deleting any video rows.

alter table public.user_runtime_config
    drop constraint if exists user_runtime_config_config_key_check;

alter table public.user_runtime_config
    add constraint user_runtime_config_config_key_check
    check (
        config_key in (
            'modelStrong',
            'modelWorker',
            'videoEnabled',
            'videoVoice',
            'videoSummarySeconds',
            'videoOverviewSeconds',
            'videoLessonSeconds'
        )
    );
