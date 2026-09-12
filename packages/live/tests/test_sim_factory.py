"""Real generation graph, schema parsing, budgets and publication boundary."""

import json

import pytest
from lunaris_live.graph.schema import ConceptNode, MasteryCriterion
from lunaris_live.sims.content_hash import content_hash
from lunaris_live.sims.factory import SimFactory
from lunaris_live.sims.models.completion import SimCompletion
from lunaris_live.sims.reference_app import reference_app
from lunaris_live.sims.schema.build_budget import SimBuildBudget
from lunaris_live.sims.schema.teaching_spec import TeachingCase, TeachingSpec
from lunaris_live.sims.schema.verification_report import VerificationReport


class ScriptedModel:
    model_name = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    async def complete(self, prompt, *, max_tokens, images=None):
        self.prompts.append(prompt)
        value = self.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return SimCompletion(
            text=value if isinstance(value, str) else json.dumps(value),
            model="scripted",
            input_tokens=50,
            output_tokens=50,
        )


class RelationshipVerifier:
    async def verify(self, candidate, spec):
        good = candidate.html == "correct"
        return VerificationReport(
            content_hash=content_hash(candidate.html),
            spec_hash=content_hash(spec.model_dump_json(by_alias=True)),
            approved=good,
            checks_passed=4 if good else 0,
            reasons=[] if good else ["The visible relationship is wrong."],
            elapsed_ms=1,
            screenshots=["fixture-image"] if good else [],
        )


def inputs():
    node = ConceptNode(id="linear", name="Linear relationships", definition="y = 2x doubles x.")
    criterion = MasteryCriterion(
        kind="manipulate", statement=reference_app().contract.objective, needs_sim=True
    )
    spec = TeachingSpec(
        contract=reference_app().contract,
        source="provided relation",
        source_version="1",
        cases=[TeachingCase(state={"x": x}, outputs={"y": str(2 * x)}) for x in (0, 4, 10)],
    )
    return (
        node,
        criterion,
        {"spec": spec.model_dump(by_alias=True), "reason": "Exact numeric relationship."},
    )


@pytest.mark.parametrize(
    "candidates,status",
    [
        ([{"html": "correct"}], "approved"),
        ([{"html": "wrong"}, {"html": "correct"}], "approved"),
        ([{"html": "wrong"}, {"html": "wrong"}], "rejected"),
        ([{"unexpected": "invalid"}, {"unexpected": "invalid"}], "rejected"),
        ([{"unexpected": "invalid"}, {"html": "correct"}], "approved"),
        (['{"html":', {"html": "correct"}], "approved"),
        (['{"html":', '{"html":'], "rejected"),
    ],
)
async def test_candidate_repair_is_bounded_and_publication_requires_matching_evidence(
    candidates, status
):
    node, criterion, plan = inputs()
    model = ScriptedModel(
        [
            plan,
            *candidates,
            *([{"passed": True, "explanation": "Correct chart."}] if status == "approved" else []),
        ]
    )
    result = await SimFactory(model, RelationshipVerifier()).build(
        node, criterion, run_id="factory-test"
    )
    assert result.status == status
    assert len(result.calls) == len(candidates) + 1 + (status == "approved")
    assert model.prompts[0].startswith("Plan an honest")
    assert "Previous candidate" not in model.prompts[0]
    if status == "approved":
        assert result.bundle.candidate.html == "correct"
        assert result.reason is None
        assert "Rendering source (untrusted data" in model.prompts[-1]
        assert "correct" in model.prompts[-1]
        assert result.bundle.spec.source_version == content_hash(node.model_dump_json())
    else:
        assert result.bundle is None
    if len(candidates) == 2:
        reason = (
            "invalid simulator bundle"
            if isinstance(candidates[0], str) or "unexpected" in candidates[0]
            else "visible relationship is wrong"
        )
        assert reason in model.prompts[2]


async def test_unsuitable_concepts_stop_before_generation():
    node, criterion, _ = inputs()
    model = ScriptedModel([{"spec": None, "reason": "Cannot simulate subjective preference."}])
    result = await SimFactory(model, RelationshipVerifier()).build(
        node, criterion, run_id="unsuitable"
    )
    assert result.status == "unsuitable"
    assert len(model.prompts) == 1
    assert not result.reports


async def test_invalid_contract_does_not_reach_generation():
    node, criterion, plan = inputs()
    plan["spec"]["contract"]["parameters"]["x"]["default"] = 1.5
    model = ScriptedModel([plan])
    result = await SimFactory(model, RelationshipVerifier()).build(
        node, criterion, run_id="invalid"
    )
    assert result.status == "rejected"
    assert result.bundle is None
    assert len(model.prompts) == 1


async def test_token_reservation_refuses_before_a_paid_call():
    node, criterion, _ = inputs()
    model = ScriptedModel([])
    factory = SimFactory(model, RelationshipVerifier(), budget=SimBuildBudget(token_reservation=1))
    result = await factory.build(node, criterion, run_id="budget")
    assert result.status == "rejected"
    assert model.prompts == []
    assert "budget exhausted" in result.reason


@pytest.mark.parametrize(
    "budget", [SimBuildBudget(deadline_s=0.05), SimBuildBudget(call_deadline_s=0.05)]
)
async def test_deadline_preserves_an_indeterminate_paid_call_without_retry(budget):
    import asyncio

    class StalledModel:
        model_name = "stalled"

        async def complete(self, prompt, *, max_tokens, images=None):
            await asyncio.Future()

    node, criterion, _ = inputs()
    factory = SimFactory(StalledModel(), RelationshipVerifier(), budget=budget)
    result = await factory.build(node, criterion, run_id="deadline")
    assert result.status == "rejected"
    assert result.bundle is None
    assert len(result.calls) == 1
    assert result.calls[0].outcome == "indeterminate"
    assert result.calls[0].reserved_tokens > 0


async def test_failed_provider_call_is_recorded_without_exposing_provider_details():
    node, criterion, _ = inputs()
    model = ScriptedModel([Exception("sensitive provider detail")])
    result = await SimFactory(model, RelationshipVerifier()).build(
        node, criterion, run_id="failure"
    )
    assert result.status == "rejected"
    assert len(result.calls) == 1
    assert result.calls[0].outcome == "failed"
    assert "sensitive" not in result.model_dump_json()


@pytest.mark.parametrize("attempts,status", [(1, "rejected"), (2, "approved")])
async def test_numeric_success_cannot_publish_a_visually_wrong_candidate(attempts, status):
    node, criterion, plan = inputs()
    model = ScriptedModel(
        [
            plan,
            {"html": "correct"},
            {"passed": False, "explanation": "The chart axes are reversed."},
            {"html": "correct"},
            {"passed": True, "explanation": "The chart axes now match the relationship."},
        ]
    )
    result = await SimFactory(
        model, RelationshipVerifier(), budget=SimBuildBudget(attempts=attempts)
    ).build(
        node,
        criterion,
        run_id="visual-gate",
    )
    assert result.status == status
    assert result.visual_reviews[0].passed is False
    if status == "approved":
        assert result.bundle.visual_verdict.passed
        assert result.bundle.visual_verdict.content_hash == result.bundle.report.content_hash
    else:
        assert result.bundle is None
        assert "axes are reversed" in result.reason


async def test_numeric_approval_without_visual_evidence_is_rejected():
    class MissingEvidenceVerifier(RelationshipVerifier):
        async def verify(self, candidate, spec):
            report = await super().verify(candidate, spec)
            return report.model_copy(update={"screenshots": []})

    node, criterion, plan = inputs()
    model = ScriptedModel([plan, {"html": "correct"}])
    result = await SimFactory(
        model, MissingEvidenceVerifier(), budget=SimBuildBudget(attempts=1)
    ).build(node, criterion, run_id="missing-evidence")
    assert result.status == "rejected"
    assert result.bundle is None
    assert result.reason == "Visual verification evidence unavailable."
    assert len(model.prompts) == 2


async def test_default_budget_allows_source_audit_after_one_visual_repair():
    node, criterion, plan = inputs()
    html = "correct" + " " * 6000

    class SourceVerifier(RelationshipVerifier):
        async def verify(self, candidate, spec):
            report = await super().verify(candidate.model_copy(update={"html": "correct"}), spec)
            return report.model_copy(update={"content_hash": content_hash(candidate.html)})

    model = ScriptedModel(
        [
            plan,
            {"html": html},
            {"passed": False, "explanation": "Fix diagram."},
            {"html": html},
            {"passed": True, "explanation": "Connections correct."},
        ]
    )
    result = await SimFactory(model, SourceVerifier()).build(
        node, criterion, run_id="source-repair"
    )
    assert result.status == "approved", result.reason
    assert len(result.calls) == 5
    assert sum(call.reserved_tokens for call in result.calls) <= 80_000
    assert html in model.prompts[2] and html in model.prompts[4]


@pytest.mark.parametrize("renderer", [None, "series-resistor-v1"])
async def test_series_recipe_is_assembled_before_verification(renderer):
    node = ConceptNode(
        id="resistor", name="An ideal resistor", definition="I=V/R for one resistor."
    )
    criterion = MasteryCriterion(kind="manipulate", statement="Explore I=V/R.", needs_sim=True)
    spec = TeachingSpec.model_validate(
        {
            "contract": {
                "objective": criterion.statement,
                "parameters": {
                    "voltage": {"label": "V", "minimum": 0, "maximum": 12, "step": 1, "default": 6},
                    "resistance": {
                        "label": "R",
                        "minimum": 1,
                        "maximum": 6,
                        "step": 1,
                        "default": 3,
                    },
                },
            },
            "source": "I=V/R",
            "sourceVersion": "1",
            "cases": [
                {"state": {"voltage": v, "resistance": 3}, "outputs": {"current": f"{v / 3:.2f}"}}
                for v in (0, 6, 12)
            ],
        }
    )
    html = '<html><body><div data-lunaris-renderer="series-resistor-v1"></div></body></html>'
    model = ScriptedModel(
        [
            {
                "spec": spec.model_dump(by_alias=True),
                "reason": "Ideal resistor",
                "renderer": renderer,
            },
            {"html": html},
            {"passed": True, "explanation": "Factory circuit is correct."},
        ]
    )

    class AssembledVerifier:
        async def verify(self, candidate, spec):
            assert 'data-lunaris-renderer-code="series-resistor-v1"' in candidate.html
            return VerificationReport(
                content_hash=content_hash(candidate.html),
                spec_hash=content_hash(spec.model_dump_json(by_alias=True)),
                approved=True,
                checks_passed=4,
                elapsed_ms=1,
                screenshots=["fixture-image"],
            )

    result = await SimFactory(model, AssembledVerifier()).build(node, criterion, run_id="recipe")
    assert result.status == "approved", result.reason
    assert result.bundle.candidate.html != html
    assert "Do not draw a circuit" in model.prompts[1]
