import os
from dataclasses import dataclass

_ENV_PREFIX = "LUNARIS_VERIFIER_"


@dataclass(frozen=True)
class VerificationThresholds:
    """The verifier's tunable gates, as one injected value object.

    The defaults are the values the moat was calibrated with (P6.2): support thresholds gate how
    strongly evidence must back a claim per risk tier; ``high_credibility_floor`` sits just under
    the REPUTABLE scorer prior (0.75) so a curated source clears it while a nudged-up open-web
    source (max 0.65) does not; ``min_corroborating_domains`` (two distinct registrable domains) is
    the minimum that precludes a source corroborating itself. Recalibrate against the poisoning
    eval's FPR via :meth:`from_env` (``LUNARIS_VERIFIER_*``) or constructor injection — never by
    editing call sites.
    """

    high_support: float = 0.85
    low_support: float = 0.65
    high_credibility_floor: float = 0.70
    min_corroborating_domains: int = 2

    @classmethod
    def from_env(cls) -> "VerificationThresholds":
        """The thresholds with any ``LUNARIS_VERIFIER_<FIELD>`` env overrides applied.

        An unset (or empty) variable keeps the field's calibrated default; a set one must parse as
        the field's type — a malformed value raises rather than silently mis-tuning the moat.
        """
        defaults = cls()
        return cls(
            high_support=_float_env("HIGH_SUPPORT", defaults.high_support),
            low_support=_float_env("LOW_SUPPORT", defaults.low_support),
            high_credibility_floor=_float_env(
                "HIGH_CREDIBILITY_FLOOR", defaults.high_credibility_floor
            ),
            min_corroborating_domains=_int_env(
                "MIN_CORROBORATING_DOMAINS", defaults.min_corroborating_domains
            ),
        )


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(_ENV_PREFIX + name)
    # Explicit unset/empty check — "0" is a legitimate override, not "use the default".
    return default if raw is None or raw == "" else float(raw)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(_ENV_PREFIX + name)
    return default if raw is None or raw == "" else int(raw)
