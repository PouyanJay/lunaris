from collections.abc import Sequence

import structlog

from ..graph import ConceptGraph
from ..model_json import parse_json_object
from .ask_model import ModelCallFailedError, ModelCallTimedOutError, ask_model
from .prior_mapper_unavailable_error import PriorMapperUnavailableError
from .schema import InterviewExchange, NodePrior, PlacementResult

logger = structlog.get_logger()

#: One classification-shaped call the first lesson is waiting on; tighter than a lesson's 30 s.
_DEFAULT_DEADLINE_S = 20.0

#: The most a claim may say. The prompt says so too; the code holds it because the model is not
#: guaranteed to listen, and a claim is a claim.
_MAX_PRIOR = 0.9

_PROMPT = """A learner is about to be taught "{topic}" one concept at a time. Before the teaching
began, they were asked a few questions about themselves. Read what they said and place them.

What they said, oldest first:
{exchanges}

The map's concepts (id: name, definition):
{concepts}

Answer with JSON only, one object:
  {{"profile": "<one short paragraph: who this learner is, what they have met, what they want to be
               able to do; written for their tutor to read; empty string if nothing usable>",
    "priors": [{{"nodeId": "<an id from the list above>", "prior": <0.0 to 1.0>}}, ...]}}

Rules for priors:
- Only concepts the learner gave you real grounds to think they already hold. Name only ids from
  the list. Leave out anything they did not touch on: an absent prior means "no claim".
- 0.6 or above means "they can probably do this already; check it, then skip it". Use it only
  when they said or clearly implied they know the concept. Below 0.6 means "some exposure";
  the tutor will still teach it, gently.
- Never above 0.9. A claim is a claim.
"""


class ClaudePriorMapper:
    """Places a learner from their interview with Claude (P2c T3).

    Runs on the worker tier (A3): reading a short exchange against a list of concepts is a
    classification, not a quality surface. Every way it fails is ``PriorMapperUnavailableError``,
    which the loop degrades to a placement with no priors. Priors naming a concept not on the map
    are dropped, not kept: the mapper reasons, the map is the record.
    """

    def __init__(
        self,
        model_name: str,
        *,
        client: object | None = None,
        deadline_s: float = _DEFAULT_DEADLINE_S,
    ) -> None:
        self._model_name = model_name
        self._client = client
        self._deadline_s = deadline_s

    async def map(
        self,
        topic: str,
        exchanges: Sequence[InterviewExchange],
        graph: ConceptGraph,
        *,
        run_id: str,
    ) -> PlacementResult:
        prompt = _PROMPT.format(
            topic=topic,
            exchanges="\n".join(f"Q: {e.question}\nA: {e.answer}" for e in exchanges)
            or "(nothing)",
            concepts="\n".join(f"- {n.id}: {n.name}, {n.definition}" for n in graph.nodes),
        )
        payload = parse_json_object(await self._say(prompt, run_id=run_id))
        if payload is None or not isinstance(payload.get("priors"), list):
            logger.warning("live.prior_mapper.answer_unusable", run_id=run_id)
            raise PriorMapperUnavailableError("prior mapper answered with no usable JSON")

        on_map = {node.id for node in graph.nodes}
        priors = [
            claim for entry in payload["priors"] if (claim := _claim(entry, on_map)) is not None
        ]
        profile = payload.get("profile")
        result = PlacementResult(
            profile=profile.strip()[:2000] if isinstance(profile, str) else "",
            priors=priors,
        )
        logger.info(
            "live.prior_mapper.placed",
            run_id=run_id,
            priors=len(result.priors),
            dropped=len(payload["priors"]) - len(result.priors),
        )
        return result

    async def _say(self, prompt: str, *, run_id: str) -> str:
        try:
            return await ask_model(
                self._client,
                model_name=self._model_name,
                prompt=prompt,
                deadline_s=self._deadline_s,
                on_client=self._keep,
            )
        except ModelCallTimedOutError as exc:
            logger.warning(
                "live.prior_mapper.timed_out", run_id=run_id, deadline_s=self._deadline_s
            )
            raise PriorMapperUnavailableError("prior mapper timed out") from exc
        except ModelCallFailedError as exc:
            logger.warning("live.prior_mapper.call_failed", run_id=run_id, exc_info=True)
            raise PriorMapperUnavailableError("prior mapper could not place") from exc

    def _keep(self, client: object) -> None:
        self._client = client


def _claim(entry: object, on_map: set[str]) -> NodePrior | None:
    """One prior the model wrote, if it names a concept on the map with a number; clamped."""
    if not isinstance(entry, dict):
        return None
    node_id = entry.get("nodeId", entry.get("node_id"))
    prior = entry.get("prior")
    if not isinstance(node_id, str) or node_id not in on_map:
        return None
    if isinstance(prior, bool) or not isinstance(prior, int | float):
        return None
    return NodePrior(node_id=node_id, prior=min(_MAX_PRIOR, max(0.0, float(prior))))
