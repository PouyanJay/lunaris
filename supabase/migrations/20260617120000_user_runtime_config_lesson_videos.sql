-- Lesson-video sub-toggle: widen the per-user runtime config to carry `videoLessonsEnabled`.
--
-- `user_runtime_config` (T8) constrains `config_key` to the per-user surface — model selection plus
-- the V6 video settings (master toggle, voice toggle, the three per-kind lengths). This adds one
-- more per-user key: a sub-toggle under the master that lets a tenant keep the two course-level
-- videos (summary + overview) while skipping the per-lesson ones. It is NON-secret (the owner reads
-- + edits it) and stays `text` within the existing 1..200 bound (boolean as 'true'/'false'); the
-- existing owner-scoped RLS and grants already cover the new key (they constrain WHICH rows, not
-- which `config_key`), so this migration only relaxes the key whitelist.
--
-- Kept in lockstep with `PER_USER_CONFIG` (user_config/store_protocol.py): a new per-user key is a
-- change in both places.
--
-- Additive + deploy-safe: no existing row uses this key, so widening the allowed set rejects nothing
-- already stored. To reverse, delete any `videoLessonsEnabled` rows, then narrow the CHECK back to
-- ('modelStrong', 'modelWorker', 'videoEnabled', 'videoVoice', 'videoSummarySeconds',
-- 'videoOverviewSeconds', 'videoLessonSeconds').

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
            'videoLessonSeconds'
        )
    );
