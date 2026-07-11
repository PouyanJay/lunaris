-- Course-cover tunability: widen the per-user runtime config to carry `coverGenerationEnabled` and
-- `coverStylePreset` (course-cover-images T10).
--
-- `user_runtime_config` (T8) constrains `config_key` to the per-user surface — model selection plus
-- the video settings. This adds the two cover keys: a master toggle (auto-generate a cover at build,
-- default on) and the art-direction preset ('nocturne' | 'blueprint' | 'aurora'). Both are NON-secret
-- (the owner reads + edits them) and stay `text` within the existing 1..200 bound (the toggle stores
-- 'true'/'false'; the preset stores its lowercase enum value). The existing owner-scoped RLS + grants
-- already cover the new keys (they constrain WHICH rows, not which `config_key`), so this migration
-- only relaxes the key whitelist.
--
-- Kept in lockstep with `PER_USER_CONFIG` (user_config/store_protocol.py) and `KNOWN_CONFIG`/`_KINDS`
-- (config_store/store.py): a new per-user key is a change in all of them.
--
-- Additive + deploy-safe: no existing row uses these keys, so widening the allowed set rejects
-- nothing already stored. To reverse, delete any `coverGenerationEnabled` / `coverStylePreset` rows,
-- then narrow the CHECK back to the video-era set.

alter table public.user_runtime_config
    drop constraint if exists user_runtime_config_config_key_check;

alter table public.user_runtime_config
    add constraint user_runtime_config_config_key_check
    check (
        config_key in (
            'modelStrong',
            'modelWorker',
            'videoEnabled',
            'videoLessonsEnabled',
            'videoVoice',
            'videoSummarySeconds',
            'videoOverviewSeconds',
            'videoLessonSeconds',
            'coverGenerationEnabled',
            'coverStylePreset'
        )
    );
