import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ToolCallCard } from "./ToolCallCard";

/** Serialise a tool result the way the harness does (json.dumps → the tap's result string). */
function resultOf(payload: unknown): string {
  return JSON.stringify(payload);
}

describe("ToolCallCard per-tool renderers", () => {
  it("extract_concepts: lists the concept labels and count, never the raw JSON", () => {
    render(
      <ToolCallCard
        tool="extract_concepts"
        args={{ topic: "HTTPS" }}
        result={resultOf({
          goalId: "tls",
          count: 3,
          concepts: [
            { id: "tcp", label: "TCP", definition: "…", difficulty: 0.1 },
            { id: "cert", label: "Certificates", definition: "…", difficulty: 0.4 },
            { id: "tls", label: "TLS Handshake", definition: "…", difficulty: 0.7 },
          ],
        })}
      />,
    );

    expect(screen.getByText("HTTPS")).toBeInTheDocument();
    expect(screen.getByText("TCP")).toBeInTheDocument();
    expect(screen.getByText("TLS Handshake")).toBeInTheDocument();
    expect(screen.getByText(/3 concepts/i)).toBeInTheDocument();
    // The raw JSON dump must not leak into the transcript.
    expect(screen.queryByText(/"goalId"/)).not.toBeInTheDocument();
  });

  it("interpret_request: renders the interpreted brief as a card, never the raw JSON", () => {
    render(
      <ToolCallCard
        tool="interpret_request"
        args={{ request: "Improve my English to achieve CLB 10" }}
        result={resultOf({
          subject: "English language proficiency",
          goal: "reach CLB 10 across all four skills",
          targetStandard: { name: "CLB 10", kind: "external_standard", authorityHint: "ircc.ca" },
          targetLevel: "advanced",
          assumedPrior: "strong everyday English (CLB 8-9)",
          audience: "an adult learner",
          deliverableShape: { lessons: 6 },
          needsResearch: true,
          domainField: "language-learning",
          preferences: { detailDepth: "in_depth", languageStyle: "sophisticated" },
        })}
      />,
    );

    expect(screen.getByText("English language proficiency")).toBeInTheDocument();
    expect(screen.getByText("reach CLB 10 across all four skills")).toBeInTheDocument();
    // Target combines the humanised level + the named standard.
    expect(screen.getByText("advanced · CLB 10")).toBeInTheDocument();
    expect(screen.getByText("strong everyday English (CLB 8-9)")).toBeInTheDocument();
    // The deliverable + preferences summary, with enum tokens humanised.
    expect(
      screen.getByText(/6 lessons · in depth · sophisticated · needs research/i),
    ).toBeInTheDocument();
    // No raw JSON dump leaks into the transcript.
    expect(screen.queryByText(/"subject"/)).not.toBeInTheDocument();
  });

  it("interpret_request: omits the Target field when the level is n/a and no standard is named", () => {
    render(
      <ToolCallCard
        tool="interpret_request"
        args={{ request: "teach me knitting" }}
        result={resultOf({
          subject: "Knitting",
          goal: "knit a scarf",
          targetStandard: null,
          targetLevel: "n/a",
          assumedPrior: "",
          deliverableShape: { lessons: null },
          needsResearch: false,
          preferences: { detailDepth: "balanced", languageStyle: "balanced" },
        })}
      />,
    );

    expect(screen.getByText("Knitting")).toBeInTheDocument();
    expect(screen.getByText("knit a scarf")).toBeInTheDocument();
    // No Target field — level is n/a and there is no named standard.
    expect(screen.queryByText("Target")).not.toBeInTheDocument();
    // The captured (default) preferences still summarise.
    expect(screen.getByText(/balanced · balanced/i)).toBeInTheDocument();
  });

  it("interpret_request: falls back to the request when the result is truncated (parsed=null)", () => {
    // The tap clips large results to ~600 chars → unparseable. The card leans on the call args
    // (the request) rather than rendering empty, and never leaks the half-written JSON.
    render(
      <ToolCallCard
        tool="interpret_request"
        args={{ request: "Improve my English to achieve CLB 10" }}
        result={'{"subject":"English language proficiency","goal":"reach CLB 10 across all f'}
      />,
    );

    expect(screen.getByText("Improve my English to achieve CLB 10")).toBeInTheDocument();
    expect(screen.queryByText(/"subject"/)).not.toBeInTheDocument();
  });

  it("model_learner: chips the known areas the course will skip", () => {
    render(
      <ToolCallCard
        tool="model_learner"
        args={{}}
        result={resultOf({ frontier: ["the alphabet", "basic vocabulary"], count: 2 })}
      />,
    );

    expect(screen.getByText("the alphabet")).toBeInTheDocument();
    expect(screen.getByText("basic vocabulary")).toBeInTheDocument();
    // The full outcome — "skipped" is the semantically load-bearing word, not just the count.
    expect(screen.getByText(/assumes 2 known areas — skipped/i)).toBeInTheDocument();
    expect(screen.queryByText(/"frontier"/)).not.toBeInTheDocument();
  });

  it("model_learner: singularises the count for a single known area", () => {
    render(
      <ToolCallCard
        tool="model_learner"
        args={{}}
        result={resultOf({ frontier: ["arithmetic"], count: 1 })}
      />,
    );

    expect(screen.getByText(/assumes 1 known area — skipped/i)).toBeInTheDocument();
  });

  it("model_learner: shows the novice note when the frontier is empty", () => {
    render(
      <ToolCallCard tool="model_learner" args={{}} result={resultOf({ frontier: [], count: 0 })} />,
    );

    expect(screen.getByText(/novice — teaching from the foundations/i)).toBeInTheDocument();
  });

  it("model_learner: shows a running indicator while in flight", () => {
    render(<ToolCallCard tool="model_learner" args={{}} result={null} />);

    expect(screen.getByText(/running…/i)).toBeInTheDocument();
  });

  it("build_prerequisite_graph: chips the concepts from ARGS even when the result is truncated", () => {
    // The real graph result is ~3.7KB and the tap clips it → unparseable. The concept chips must
    // come from the (full, untruncated) call args, marking the goal.
    const truncated = '{"nodes": [{"id": "tcp", "label": "TCP", "definition": "a long def';
    const { container } = render(
      <ToolCallCard
        tool="build_prerequisite_graph"
        args={{
          concepts: [
            { id: "tcp", label: "TCP" },
            { id: "cert", label: "Certificates" },
            { id: "tls", label: "TLS Handshake" },
          ],
          goal: "tls",
        }}
        result={truncated}
      />,
    );

    expect(screen.getByText("TCP")).toBeInTheDocument();
    expect(screen.getByText("TLS Handshake")).toBeInTheDocument();
    expect(screen.getByText(/3 concepts/i)).toBeInTheDocument();
    // The goal concept is marked.
    const goalChip = container.querySelector('[data-tone="goal"]');
    expect(goalChip).toHaveTextContent("TLS Handshake");
    // No raw JSON array of concepts dumped.
    expect(screen.queryByText(/\[\{"id"/)).not.toBeInTheDocument();
  });

  it("build_prerequisite_graph: shows edge count + acyclic when the result is small enough to parse", () => {
    render(
      <ToolCallCard
        tool="build_prerequisite_graph"
        args={{
          concepts: [
            { id: "a", label: "A" },
            { id: "b", label: "B" },
            { id: "c", label: "C" },
          ],
          goal: "c",
        }}
        result={resultOf({
          nodes: [{ id: "a" }, { id: "b" }, { id: "c" }],
          edges: [
            { from: "a", to: "c" },
            { from: "b", to: "c" },
          ],
          isAcyclic: true,
          topoOrder: ["a", "b", "c"],
          frontier: [],
        })}
      />,
    );

    expect(screen.getByText(/3 concepts/i)).toBeInTheDocument();
    expect(screen.getByText(/2 edges/i)).toBeInTheDocument();
    expect(screen.getByText(/acyclic/i)).toBeInTheDocument();
  });

  it("design_curriculum: lists each module by title", () => {
    render(
      <ToolCallCard
        tool="design_curriculum"
        args={{}}
        result={resultOf({
          moduleCount: 2,
          modules: [
            { id: "m0", title: "Foundations", kcs: ["a", "b"], objectiveCount: 2 },
            { id: "m1", title: "Advanced Routing", kcs: ["c"], objectiveCount: 1 },
          ],
        })}
      />,
    );

    expect(screen.getByText("Foundations")).toBeInTheDocument();
    expect(screen.getByText("Advanced Routing")).toBeInTheDocument();
    expect(screen.queryByText(/"objectiveCount"/)).not.toBeInTheDocument();
  });

  it("finalize_course: shows a published status and module count", () => {
    render(
      <ToolCallCard
        tool="finalize_course"
        args={{}}
        result={resultOf({ courseId: "c1", status: "published", moduleCount: 4, issues: [] })}
      />,
    );

    expect(screen.getByText(/published/i)).toBeInTheDocument();
    expect(screen.getByText(/4 modules/i)).toBeInTheDocument();
  });

  it("finalize_course: surfaces the blocking issues when held for review", () => {
    render(
      <ToolCallCard
        tool="finalize_course"
        args={{}}
        result={resultOf({
          courseId: "c1",
          status: "review",
          moduleCount: 3,
          issues: ["objective binary_search is not assessed"],
        })}
      />,
    );

    expect(screen.getByText(/review/i)).toBeInTheDocument();
    expect(screen.getByText(/objective binary_search is not assessed/i)).toBeInTheDocument();
  });

  it("verify_claims: tallies supported vs cut claims", () => {
    render(
      <ToolCallCard
        tool="verify_claims"
        args={{ claims: ["c1", "c2", "c3"], risk_tier: "low" }}
        result={resultOf({
          results: [
            { text: "c1", status: "supported", supportedBy: "s1" },
            { text: "c2", status: "cut", supportedBy: null },
            { text: "c3", status: "supported", supportedBy: "s2" },
          ],
          citations: [],
        })}
      />,
    );

    expect(screen.getByText(/2 supported/i)).toBeInTheDocument();
    expect(screen.getByText(/1 cut/i)).toBeInTheDocument();
  });

  it("task: names the delegated subagent and shows the task description", () => {
    render(
      <ToolCallCard
        tool="task"
        args={{ subagent_type: "module-author", description: "Author the Foundations module" }}
        result="Authored Foundations; 2 claims supported, 0 cut."
      />,
    );

    expect(screen.getByText("module-author")).toBeInTheDocument();
    expect(screen.getByText(/Author the Foundations module/i)).toBeInTheDocument();
    // Once the subagent returns, its summary shows in place of the running indicator.
    expect(screen.getByText(/2 claims supported, 0 cut/i)).toBeInTheDocument();
  });

  it("verify_claims: shows the submitted count + a running indicator while in flight", () => {
    render(
      <ToolCallCard
        tool="verify_claims"
        args={{ claims: ["c1", "c2"], risk_tier: "low" }}
        result={null}
      />,
    );

    expect(screen.getByText(/verifying 2 claims/i)).toBeInTheDocument();
    expect(screen.getByText(/running…/i)).toBeInTheDocument();
  });

  it("verify_claims: falls back to the submitted count when the result is truncated", () => {
    // A large verify result is clipped by the tap → unparseable; degrade to the args count, no JSON.
    render(
      <ToolCallCard
        tool="verify_claims"
        args={{ claims: ["c1", "c2", "c3"], risk_tier: "high" }}
        result={'{"results": [{"text": "c1", "status": "supported", "supportedBy'}
      />,
    );

    expect(screen.getByText(/3 claims verified/i)).toBeInTheDocument();
    expect(screen.queryByText(/"results"/)).not.toBeInTheDocument();
  });

  it("design_curriculum: shows a running indicator while in flight", () => {
    render(<ToolCallCard tool="design_curriculum" args={{}} result={null} />);

    expect(screen.getByText(/running…/i)).toBeInTheDocument();
  });

  it("unknown tool with no args and an empty result reads as done", () => {
    render(<ToolCallCard tool="noop_tool" args={{}} result="" />);

    expect(screen.getByText(/^done$/i)).toBeInTheDocument();
  });

  it("unknown tool: hides the raw arguments behind a collapsed disclosure (no JSON dumped open)", () => {
    const { container } = render(
      <ToolCallCard tool="mystery_tool" args={{ foo: { bar: 1 } }} result={resultOf({ x: 1 })} />,
    );

    // The tool name still shows.
    expect(screen.getByText("mystery_tool")).toBeInTheDocument();
    // The raw view is a disclosure, closed by default — not dumped inline.
    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
  });

  it("renders a running indicator while a call is still in flight, with args content shown", () => {
    render(
      <ToolCallCard
        tool="build_prerequisite_graph"
        args={{ concepts: [{ id: "a", label: "A" }], goal: "a" }}
        result={null}
      />,
    );

    expect(screen.getByText(/running…/i)).toBeInTheDocument();
    // Args-derived content is available immediately, before the result.
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  // Variant coverage of request #2: every branded tool, given a representative payload, shows branded
  // content and never dumps its raw JSON — the single contract the renderer registry exists to keep.
  it.each([
    {
      tool: "interpret_request",
      args: { request: "Improve my English to CLB 10" },
      result: resultOf({ subject: "English", goal: "reach CLB 10", targetLevel: "advanced" }),
      present: "English",
      absent: /"subject"/,
    },
    {
      tool: "model_learner",
      args: {},
      result: resultOf({ frontier: ["the alphabet"], count: 1 }),
      present: "the alphabet",
      absent: /"frontier"/,
    },
    {
      tool: "extract_concepts",
      args: { topic: "X" },
      result: resultOf({
        goalId: "a",
        count: 2,
        concepts: [
          { id: "a", label: "Alpha" },
          { id: "b", label: "Beta" },
        ],
      }),
      present: "Alpha",
      absent: /"goalId"/,
    },
    {
      tool: "build_prerequisite_graph",
      args: { concepts: [{ id: "a", label: "Alpha" }], goal: "a" },
      result: '{"nodes": [{"id": "a", "label": "Alpha", "definition": "a long', // truncated
      present: "Alpha",
      absent: /"label":/,
    },
    {
      tool: "design_curriculum",
      args: {},
      result: resultOf({
        moduleCount: 1,
        modules: [{ id: "m", title: "Mod A", kcs: ["a"], objectiveCount: 1 }],
      }),
      present: "Mod A",
      absent: /"objectiveCount"/,
    },
    {
      tool: "finalize_course",
      args: {},
      result: resultOf({ courseId: "c", status: "published", moduleCount: 2, issues: [] }),
      present: /published/i,
      absent: /"courseId"/,
    },
    {
      tool: "verify_claims",
      args: { claims: ["c1", "c2"] },
      result: resultOf({
        results: [
          { text: "c1", status: "supported", supportedBy: "s" },
          { text: "c2", status: "cut", supportedBy: null },
        ],
        citations: [],
      }),
      present: /supported/i,
      absent: /"citations"/,
    },
    {
      tool: "task",
      args: { subagent_type: "module-author", description: "Do the thing" },
      result: "All done.",
      present: "module-author",
      absent: /"subagent_type"/,
    },
  ])(
    "$tool renders branded content and never dumps raw JSON",
    ({ tool, args, result, present, absent }) => {
      render(<ToolCallCard tool={tool} args={args} result={result} />);

      expect(screen.getByText(present)).toBeInTheDocument();
      expect(screen.queryByText(absent)).not.toBeInTheDocument();
    },
  );

  it("renders every chip for a large concept set (long content)", () => {
    const concepts = Array.from({ length: 24 }, (_, i) => ({
      id: `kc${i}`,
      label: `Concept ${i}`,
    }));
    render(
      <ToolCallCard
        tool="build_prerequisite_graph"
        args={{ concepts, goal: "kc23" }}
        result={null}
      />,
    );

    // First, last, and the count all render — large arrays are chipped in full, not truncated.
    expect(screen.getByText("Concept 0")).toBeInTheDocument();
    expect(screen.getByText("Concept 23")).toBeInTheDocument();
    expect(screen.getByText(/24 concepts/i)).toBeInTheDocument();
  });

  // Every tool — branded or not — keeps the same chrome: a "Tool call" eyebrow + the mono tool name.
  it.each([
    "extract_concepts",
    "build_prerequisite_graph",
    "design_curriculum",
    "finalize_course",
    "verify_claims",
    "task",
    "an_unregistered_tool",
    "interpret_request",
    "model_learner",
  ])("keeps the 'Tool call' eyebrow and mono tool name for %s", (tool) => {
    const { unmount } = render(<ToolCallCard tool={tool} args={{}} result="ok" />);

    const eyebrow = screen.getByText(/tool call/i);
    expect(within(eyebrow.parentElement as HTMLElement).getByText(tool)).toBeInTheDocument();
    unmount();
  });
});
