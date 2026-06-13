from lunaris_video.style.tokens import VideoStyleTokens

# The enterprise-ui DARK theme semantic tokens (apps/web/src/index.css [data-theme="dark"]) —
# videos use the dark ramp because the skill's visual language is a deep-ink instrument canvas.
# Mapping: BG←--surface, INK←--text, MUTED←--text-muted, ACCENT←--accent-500, DANGER←--danger,
# GREEN←--success, PANEL←--surface-raised, ALT←--tier-1. The font stays the skill's validated
# default: render environments guarantee DejaVu Sans (Linux worker image), not the web font.
# tests/video/test_style_token_drift.py pins these hexes to index.css.
ENTERPRISE_DARK_TOKENS = VideoStyleTokens(
    background="#0F1115",
    ink="#E9EBEE",
    muted="#565C66",
    accent="#E0A23C",
    danger="#D2726A",
    success="#56A585",
    panel="#13161B",
    alt="#6B8FC4",
    font="DejaVu Sans",
)
