from enum import StrEnum


class ComputeChoice(StrEnum):
    """Where a keyless (Draft) build's LLM completions run — the web compute dropdown's value.

    ``SERVER`` is the keyless Lunaris endpoint (today's Draft tier); ``DEVICE`` serves completions
    from the learner's browser over the device bridge. A keyed build ignores the choice entirely
    (it always runs hosted), mirroring the explain tiers.
    """

    SERVER = "server"
    DEVICE = "device"
