#: The tool a Tier 2 layout arrives as, and the name the browser registers a renderer for.
#:
#: A sibling of `SURFACE_TOOL` rather than a field on it, because the two tiers are decided by
#: different things and fail differently. Tier 1's card is chosen by a rule set that feeds the
#: learner model; Tier 2's arrangement is composed around it and moves no belief. Sent as one call
#: each, a build that renders the card and not the layout still assesses the learner correctly —
#: whereas one payload would make a change to the arrangement a change to the assessment's envelope.
#:
#: Frame order puts it **after** `SURFACE_TOOL`: the layout holds a slot for the card, so a client
#: that draws the layout as it arrives already has the thing the slot points at.
#:
#: Duplicated deliberately in `apps/web`, like `SURFACE_TOOL` and the runtime's mount path: the two
#: are separately deployed, so a shared import would only prove agreement at commit time and says
#: nothing about which build is running where. Both sides pin it as a literal instead.
LAYOUT_TOOL = "lunaris.layout"
