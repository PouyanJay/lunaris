#: Where the placeholder simulator is served from (P2b T6).
#:
#: A path rather than an absolute URL, because the host differs per environment and the browser
#: already knows its own API origin — the same reasoning every other Live endpoint uses. The API's
#: route is mounted at exactly this, and `apps/copilot` pins the same literal from its side.
#:
#: Its own module rather than sitting beside ``StubSimRegistry``: this is a route constant consumed
#: by a different package (`lunaris_api`), while the registry is an implementation of a protocol.
#: One public export per file, and these are not one fact.
STUB_SIM_PATH = "/api/live/sims/stub"
