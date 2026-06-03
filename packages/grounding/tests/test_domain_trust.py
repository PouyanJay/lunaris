"""P7.2-T2 — the deterministic domain trust classifier (the minimal, real trust model P6 extends).

Classifies a URL's authority tier from its domain alone — no network, no model — so the research
(and later resource) stages can prefer official/reputable sources and skip junk. The authority hint
from the brief's target standard makes its own body OFFICIAL; government/academic suffixes and a
small denylist (URL shorteners — redirect stubs, never authoritative) cover the rest.
"""

from lunaris_grounding import classify_domain
from lunaris_runtime.schema import TrustTier


def test_the_authority_hint_host_and_its_subdomains_are_official() -> None:
    assert (
        classify_domain("https://ircc.canada.ca/clb/10", authority_hint="ircc.canada.ca")
        is TrustTier.OFFICIAL
    )
    # A subdomain of the authority body is still official; www is normalised away.
    assert (
        classify_domain("https://www.ircc.canada.ca/x", authority_hint="ircc.canada.ca")
        is TrustTier.OFFICIAL
    )


def test_the_authority_hint_does_not_promote_unrelated_hosts() -> None:
    # The hint must not leak to other hosts — an unrelated domain stays OPEN.
    assert (
        classify_domain("https://random.com/clb", authority_hint="ircc.canada.ca") is TrustTier.OPEN
    )
    # A bare TLD hint must not promote every domain under it (no dot → ignored).
    assert classify_domain("https://anything.ca/x", authority_hint="ca") is TrustTier.OPEN


def test_government_and_standards_domains_are_official_without_a_hint() -> None:
    assert classify_domain("https://www.usa.gov/benefits") is TrustTier.OFFICIAL
    assert classify_domain("https://www.gov.uk/guidance") is TrustTier.OFFICIAL
    assert classify_domain("https://www.army.mil/x") is TrustTier.OFFICIAL


def test_academic_domains_are_reputable() -> None:
    assert classify_domain("https://www.mit.edu/research") is TrustTier.REPUTABLE
    assert classify_domain("https://www.ox.ac.uk/about") is TrustTier.REPUTABLE


def test_the_general_web_is_open() -> None:
    assert classify_domain("https://some-blog.com/post") is TrustTier.OPEN


def test_url_shorteners_are_blocked_by_default() -> None:
    # Shorteners are redirect stubs, never authoritative content — never fetched or shown.
    assert classify_domain("https://bit.ly/abc123") is TrustTier.BLOCKED


def test_internal_and_loopback_addresses_are_blocked() -> None:
    # SSRF guard: a crafted result/hint must not point the fetcher at internal addresses.
    assert (
        classify_domain("http://169.254.169.254/latest/meta-data/") is TrustTier.BLOCKED
    )  # cloud metadata
    assert classify_domain("http://192.168.1.1/admin") is TrustTier.BLOCKED
    assert classify_domain("http://127.0.0.1:8000/secret") is TrustTier.BLOCKED
    assert classify_domain("http://[::1]/x") is TrustTier.BLOCKED


def test_a_custom_denylist_replaces_the_default() -> None:
    # The blocked set replaces (not extends) the default — fully caller-controlled: spam is now
    # blocked, and the default shortener is no longer.
    assert (
        classify_domain("https://spam.example/x", blocked=frozenset({"spam.example"}))
        is TrustTier.BLOCKED
    )
    assert (
        classify_domain("https://bit.ly/x", blocked=frozenset({"spam.example"})) is TrustTier.OPEN
    )


def test_a_malformed_or_empty_url_is_open_rather_than_crashing() -> None:
    assert classify_domain("") is TrustTier.OPEN
    assert classify_domain("not a url") is TrustTier.OPEN
