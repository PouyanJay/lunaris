import ipaddress
from collections.abc import Set
from urllib.parse import urlparse

from lunaris_runtime.schema import TrustTier

# URL shorteners are redirect stubs, never authoritative content — blocked by default. P6 replaces
# this with the editable ``source_authorities`` config table (denylist + per-field allowlists).
_DEFAULT_BLOCKED: frozenset[str] = frozenset({"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly"})
# Domain labels that mark a government/standards body or an academic institution. Label-based (not
# suffix-based) so ``usa.gov`` and ``www.gov.uk`` both read as official, ``ox.ac.uk`` as academic.
# Imprecise by design (``edu.attacker.com`` would read REPUTABLE); P6's registry tightens it — this
# tier only orders preference, it is not an access-control boundary.
_OFFICIAL_LABELS: frozenset[str] = frozenset({"gov", "mil", "int"})
_ACADEMIC_LABELS: frozenset[str] = frozenset({"edu", "ac"})


def host(url: str) -> str:
    """The lowercased host of a URL, sans port/credentials/brackets and a leading ``www.``.

    Shared by the trust classifier and the resource curator (which shows it as a source domain).
    """
    # urlparse only finds a host when a scheme (or a leading //) is present; prefix // for bare
    # inputs. .hostname (not netloc) strips creds, port, and IPv6 brackets correctly.
    parsed = urlparse(url if "://" in url else f"//{url}")
    return (parsed.hostname or "").removeprefix("www.")


def _is_internal_ip(host: str) -> bool:
    """True when the host is a private/loopback/link-local/reserved IP — SSRF guard (SECURITY §A10).

    Blocks fetching internal addresses (e.g. ``169.254.169.254`` cloud metadata, ``10.0.0.0/8``)
    that a crafted search result or authority hint could otherwise point the extractor at. A
    non-IP host is not internal here — its trust is decided by the label rules below.
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified
    )


def _normalize_hint(hint: str) -> str:
    return hint.strip().lower().split("://")[-1].split("/")[0].removeprefix("www.")


def classify_domain(
    url: str, authority_hint: str = "", *, blocked: Set[str] = _DEFAULT_BLOCKED
) -> TrustTier:
    """Classify a URL's authority tier from its domain alone — deterministic, no network or model.

    The standard's own body (``authority_hint`` + its subdomains) is OFFICIAL; government and
    standards domains are OFFICIAL, academic ones REPUTABLE, a denylist + internal IPs BLOCKED, the
    rest OPEN. A malformed URL with no host is OPEN (never crashes the research stage).
    """
    domain = host(url)
    if not domain:
        return TrustTier.OPEN
    if domain in blocked or _is_internal_ip(domain):
        return TrustTier.BLOCKED
    hint = _normalize_hint(authority_hint)
    # Require a dot so a bare TLD (e.g. "ca") can't promote every domain under it to OFFICIAL.
    if hint and "." in hint and (domain == hint or domain.endswith(f".{hint}")):
        return TrustTier.OFFICIAL
    labels = set(domain.split("."))
    if labels & _OFFICIAL_LABELS:
        return TrustTier.OFFICIAL
    if labels & _ACADEMIC_LABELS:
        return TrustTier.REPUTABLE
    return TrustTier.OPEN
