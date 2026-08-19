import os


def supabase_client(*, url_env: str, service_key_env: str, purpose: str) -> object:
    """A service-role Supabase client from the environment, or a clear refusal.

    The one thing every durable store used to spell out for itself: read the two env vars, refuse
    by name when either is missing (a store that failed with a bare ``None`` URL was a store nobody
    could tell was misconfigured), build the client. Callers still own the *laziness* — they hold
    the client and call this on first use — because that is what lets a composition root build a
    store with no credentials and no network. Extracted at the fourth Live copy (P2c T4).
    """
    from supabase import create_client

    url = os.environ.get(url_env)
    key = os.environ.get(service_key_env)
    if not url or not key:
        raise RuntimeError(f"{url_env} / {service_key_env} not set; cannot {purpose}")
    return create_client(url, key)
