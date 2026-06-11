class PersistenceError(Exception):
    """A persistence backend failed: unreachable, misconfigured, or it rejected the operation.

    The contract every store implementation raises at its boundary (see ``guard``), so callers can
    be deliberately lenient about *backend* failures — the API's best-effort history writes catch
    exactly this — without also swallowing programming errors (a ``TypeError`` from a bad call, a
    schema drift ``KeyError``), which must surface. Domain not-found signals (the course stores'
    ``FileNotFoundError``) are part of each store's contract, not failures, and pass through.
    """
