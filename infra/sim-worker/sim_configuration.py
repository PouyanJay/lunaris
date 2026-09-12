from dataclasses import dataclass


@dataclass(frozen=True)
class SimConfiguration:
    worker_image: str
    verifier_image: str
    vault_uri: str
    identity: str
    tenant: str
    supabase_url: str
    with_byok: bool = False
