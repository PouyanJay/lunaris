from lunaris_runtime.credentials import has_scoped_secret
from lunaris_runtime.schema import CostPocket


def credential_pocket(env_var: str) -> CostPocket:
    """Which pocket a paid call on ``env_var`` bills to — ``user_key`` if the run scope carries a
    tenant key for it (a BYOK build on their own key), else ``platform`` (the process env / infra).

    This is the metering half of the credential-scope contract: ``resolve_secret`` returns the
    scoped key exactly when ``has_scoped_secret`` is true, so the same condition that decides
    *whose* key made the call decides *whose* pocket it comes out of."""
    return CostPocket.USER_KEY if has_scoped_secret(env_var) else CostPocket.PLATFORM
