-- Close the style_preset integrity gap (cover-general-preset review): mirror the CoverStylePreset
-- enum as a CHECK, exactly as `status` already mirrors its state machine. Writes to cover_jobs are
-- server-only (service-role), so this is defense-in-depth for app bugs / manual SQL, not an attack
-- surface fix. Kept in lockstep with CoverStylePreset in lunaris_runtime/schema/enums.py — a new
-- preset is a change in both places (a pytest lockstep guard parses this CHECK).
--
-- Safe: every existing row is one of the admitted values ('nocturne' from the launch presets).
-- To reverse, drop constraint cover_jobs_style_preset_check.

alter table public.cover_jobs
    add constraint cover_jobs_style_preset_check
    check (style_preset in ('general', 'nocturne', 'blueprint', 'aurora'));
