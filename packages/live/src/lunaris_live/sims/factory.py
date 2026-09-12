import asyncio
from time import monotonic

import structlog
from langgraph.graph import END, START, StateGraph
from lunaris_runtime.logging import bind_run_id
from pydantic import ValidationError

from ..graph.schema import ConceptNode, MasteryCriterion
from ..model_json import parse_json_object
from .content_hash import content_hash
from .factory_prompts import factory_prompt
from .factory_state import FactoryState
from .protocols.model import ISimModel
from .protocols.verifier import ISimVerifier
from .schema.build_budget import SimBuildBudget
from .schema.build_result import SimBuildCall, SimBuildResult
from .schema.candidate import SimCandidate
from .schema.plan_proposal import SimPlanProposal
from .schema.verified_bundle import VerifiedBundle
from .schema.visual_verdict import SimVisualVerdict


class SimFactory:
    """Plan independently, generate, verify, and repair within explicit paid-work budgets."""

    def __init__(
        self, model: ISimModel, verifier: ISimVerifier, *, budget: SimBuildBudget | None = None
    ) -> None:
        self._model = model
        self._verifier = verifier
        self._budget = budget or SimBuildBudget()
        graph = StateGraph(FactoryState)
        graph.add_node("reserve_review", self._reserve_review)
        graph.add_node("review", self._review)
        graph.add_node("reserve_plan", self._reserve_plan)
        graph.add_node("reserve_generate", self._reserve_generate)
        graph.add_node("plan", self._plan)
        graph.add_node("generate", self._generate)
        graph.add_node("verify", self._verify)
        graph.add_edge(START, "reserve_plan")
        graph.add_conditional_edges("reserve_review", self._after_reserve)
        graph.add_conditional_edges("review", self._after_review)
        graph.add_conditional_edges("reserve_plan", self._after_reserve)
        graph.add_conditional_edges("reserve_generate", self._after_reserve)
        graph.add_conditional_edges("plan", self._after_plan)
        graph.add_conditional_edges("generate", self._after_generate)
        graph.add_conditional_edges("verify", self._after_verify)
        self._graph = graph.compile()

    async def build(
        self, node: ConceptNode, criterion: MasteryCriterion, *, run_id: str
    ) -> SimBuildResult:
        bind_run_id(run_id)
        started = monotonic()
        state = self._initial(node, criterion)
        try:
            async with asyncio.timeout(self._budget.deadline_s):
                async for update in self._graph.astream(state, stream_mode="values"):
                    state = update
        except TimeoutError:
            state = {**state, "status": "rejected", "reason": "Factory time budget exhausted."}
            state["calls"] = [
                call.model_copy(update={"outcome": "indeterminate"})
                if call.outcome == "started"
                else call
                for call in state["calls"]
            ]
        return self._finish(state, started=started)

    def _finish(self, state: FactoryState, *, started: float) -> SimBuildResult:
        result = SimBuildResult(
            status=state["status"],
            bundle=state["bundle"],
            spec=state["spec"],
            calls=state["calls"],
            reports=state["reports"],
            visual_reviews=state["visual_reviews"],
            candidates=state["candidates"],
            reason=state["reason"],
            elapsed_ms=int((monotonic() - started) * 1000),
        )
        structlog.get_logger().info(
            "live.sim.built",
            status=result.status,
            attempts=state["attempts"],
            elapsed_ms=result.elapsed_ms,
            reserved_tokens=state["reserved"],
        )
        return result

    def _initial(self, node: ConceptNode, criterion: MasteryCriterion) -> FactoryState:
        return FactoryState(
            node=node,
            criterion=criterion,
            spec=None,
            candidate=None,
            candidates=[],
            bundle=None,
            calls=[],
            reports=[],
            visual_reviews=[],
            reserved=0,
            attempts=0,
            status="rejected",
            reason=None,
        )

    def _reserve(self, state: FactoryState, *, stage: str) -> dict:
        prompt = factory_prompt(state, stage=stage)
        cap = self._output_cap(stage)
        reservation = len(prompt.encode("utf-8")) + cap + (6000 if stage == "review" else 0)
        if state["reserved"] + reservation > self._budget.token_reservation:
            return {"status": "rejected", "reason": "Factory token budget exhausted."}
        call = SimBuildCall(
            stage=stage,
            model=self._model.model_name,
            input_tokens=0,
            output_tokens=0,
            reserved_tokens=reservation,
            outcome="started",
        )
        return {
            "calls": [*state["calls"], call],
            "reserved": state["reserved"] + reservation,
            "status": "running",
            "attempts": state["attempts"] + (stage == "generate"),
        }

    def _reserve_plan(self, state: FactoryState) -> dict:
        return self._reserve(state, stage="plan")

    def _reserve_generate(self, state: FactoryState) -> dict:
        return self._reserve(state, stage="generate")

    async def _call(self, state: FactoryState, *, stage: str) -> tuple[str | None, dict]:
        prompt = factory_prompt(state, stage=stage)
        cap = self._output_cap(stage)
        call = state["calls"][-1]
        try:
            async with asyncio.timeout(self._budget.call_deadline_s):
                reply = await self._model.complete(
                    prompt,
                    max_tokens=cap,
                    images=state["reports"][-1].screenshots if stage == "review" else None,
                )
        except TimeoutError:
            return None, self._call_failed(state, outcome="indeterminate")
        except Exception:
            return None, self._call_failed(state, outcome="failed")
        completed = call.model_copy(
            update={
                "model": reply.model,
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "cost_usd": reply.cost_usd,
                "outcome": "succeeded",
            }
        )
        return reply.text, {"calls": [*state["calls"][:-1], completed]}

    def _call_failed(self, state: FactoryState, *, outcome: str) -> dict:
        call = state["calls"][-1].model_copy(update={"outcome": outcome})
        return {
            "status": "rejected",
            "reason": "Simulator model call failed.",
            "calls": [*state["calls"][:-1], call],
        }

    async def _plan(self, state: FactoryState) -> dict:
        text, update = await self._call(state, stage="plan")
        if text is None:
            return update
        try:
            proposal = SimPlanProposal.model_validate(parse_json_object(text))
            if proposal.spec is None:
                return {**update, "status": "unsuitable", "reason": proposal.reason}
            if proposal.spec.contract.objective != state["criterion"].statement:
                raise ValueError("Planner changed the learning objective.")
            spec = proposal.spec.model_copy(
                update={
                    "source": f"concept:{state['node'].id}",
                    "source_version": content_hash(state["node"].model_dump_json()),
                }
            )
            return {**update, "spec": spec}
        except (ValueError, ValidationError):
            return {
                **update,
                "status": "rejected",
                "reason": "Invalid independent teaching specification.",
            }

    async def _generate(self, state: FactoryState) -> dict:
        text, update = await self._call(state, stage="generate")
        update = {**update, "candidate": None}
        if text is None:
            return update
        try:
            candidate = SimCandidate.model_validate(parse_json_object(text))
            return {
                **update,
                "candidate": candidate,
                "candidates": [*state["candidates"], candidate],
            }
        except (ValueError, ValidationError):
            return {
                **update,
                "status": "rejected",
                "reason": "Model returned an invalid simulator bundle.",
            }

    async def _verify(self, state: FactoryState) -> dict:
        try:
            report = await self._verifier.verify(state["candidate"], state["spec"])
            return {
                "reports": [*state["reports"], report],
                "status": "rejected",
                "reason": (
                    None if report.screenshots else "Visual verification evidence unavailable."
                )
                if report.approved
                else "Independent verification rejected the candidate.",
            }
        except (ValueError, RuntimeError, OSError):
            return {"status": "rejected", "reason": "Independent verification unavailable."}

    def _after_plan(self, state: FactoryState) -> str:
        return "reserve_generate" if state["spec"] is not None else END

    def _after_generate(self, state: FactoryState) -> str:
        return "verify" if state["candidate"] is not None else END

    def _after_verify(self, state: FactoryState) -> str:
        if (
            state["reports"]
            and state["reports"][-1].approved
            and state["reports"][-1].content_hash == content_hash(state["candidate"].html)
            and state["reason"] is None
        ):
            return "reserve_review" if state["reports"][-1].screenshots else END
        return self._after_review(state)

    def _after_review(self, state: FactoryState) -> str:
        if state["bundle"] is not None or state["attempts"] >= self._budget.attempts:
            return END
        if state["calls"][-1].outcome != "succeeded":
            return END
        return "reserve_generate"

    def _reserve_review(self, state: FactoryState) -> dict:
        return self._reserve(state, stage="review")

    def _output_cap(self, stage: str) -> int:
        return min(self._budget.output_tokens, {"plan": 2500, "review": 1500}.get(stage, 8000))

    async def _review(self, state: FactoryState) -> dict:
        text, update = await self._call(state, stage="review")
        if text is None:
            return update
        try:
            verdict = SimVisualVerdict.model_validate(parse_json_object(text)).model_copy(
                update={"content_hash": content_hash(state["candidate"].html)}
            )
            update = {
                **update,
                "visual_reviews": [*state["visual_reviews"], verdict],
                "status": "rejected",
                "reason": verdict.explanation,
            }
            if not verdict.passed:
                return update
            bundle = VerifiedBundle(
                candidate=state["candidate"],
                spec=state["spec"],
                report=state["reports"][-1],
                visual_verdict=verdict,
            )
            return {**update, "bundle": bundle, "status": "approved", "reason": None}
        except ValueError:
            return {**update, "status": "rejected", "reason": "Invalid independent visual review."}

    def _after_reserve(self, state: FactoryState) -> str:
        return state["calls"][-1].stage if state["status"] == "running" else END
