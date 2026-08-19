#: The tool a Tier 1 card arrives as, and the name the browser registers with `useCopilotAction`.
#:
#: CopilotKit renders a controlled component by calling a tool the frontend provides, which is the
#: mechanism plan §8's Tier 1 asks for — with the one difference that matters here: the caller is
#: `select_surface`, a pure function of the move, the map and the belief, so the arguments are
#: auditable from the frame alone rather than being a model's choice.
#:
#: **One tool, not five.** The payload is already a discriminated `SurfaceSpec`, so a renderer
#: switches on `kind` either way — while five tools would mean five registrations on the browser
#: side, each free to drift from the Python enum that decides which of them is ever called. A card
#: that silently never renders is the worst failure this seam has, because the run looks perfect
#: from the server.
#:
#: Duplicated deliberately in `apps/web`, like the runtime's mount path (T1's `contract.ts`): the
#: two are separately deployed, so a shared import would only prove agreement at commit time and
#: says nothing about which build is running where. Both sides pin it as a literal instead.
SURFACE_TOOL = "lunaris.surface"
