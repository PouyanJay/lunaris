"""Supabase Auth constants shared by the token verifiers (kept in one place to avoid drift)."""

# Supabase stamps end-user access tokens with this audience.
AUDIENCE = "authenticated"

# Where a Supabase project publishes its asymmetric signing keys, relative to the project URL.
JWKS_PATH = "/auth/v1/.well-known/jwks.json"
