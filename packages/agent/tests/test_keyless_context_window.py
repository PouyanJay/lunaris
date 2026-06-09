"""The keyless model must bound the deep-agent planner to its small local context window.

A full keyless build accumulates planner context (todo list + tool results) that overflowed the
local model's window mid-build (llama.cpp `400 exceed_context_size_error`). The durable fix: the
keyless model advertises its window via `profile.max_input_tokens`, so the deepagents harness sizes
summarization to a *fraction* of it (summarize before the limit) instead of its fixed 170k-token
trigger for unknown models, which never fires inside a 16k window. This pins that integration in the
agent layer (where deepagents is a real dependency), proving the wiring rather than a mock.
"""

from deepagents.middleware.summarization import compute_summarization_defaults
from lunaris_runtime.resilience.llm_client import build_keyless_chat_model


def test_keyless_model_drives_fraction_based_summarization() -> None:
    # Arrange — the keyless fallback model (no key needed to construct).
    model = build_keyless_chat_model()

    # Act — let deepagents derive its summarization settings from the model.
    defaults = compute_summarization_defaults(model)

    # Assert — the model advertises a finite input window …
    assert model.profile is not None
    assert isinstance(model.profile.get("max_input_tokens"), int)
    # … so deepagents summarizes at a fraction of that window, not the ("tokens", 170000) fixed
    # fallback it uses for models whose context size it can't infer (which never fires inside 16k).
    assert defaults["trigger"] == ("fraction", 0.85)
    assert defaults["truncate_args_settings"]["trigger"] == ("fraction", 0.85)
