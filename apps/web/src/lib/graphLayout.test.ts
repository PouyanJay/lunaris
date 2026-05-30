import { describe, expect, it } from "vitest";

import { makeCourse } from "../test/fixtures";
import { buildGraphLayout, difficultyTier } from "./graphLayout";

describe("difficultyTier", () => {
  it("maps 0..1 difficulty onto tiers 1..5", () => {
    expect(difficultyTier(0)).toBe(1);
    expect(difficultyTier(0.1)).toBe(1);
    expect(difficultyTier(0.45)).toBe(3);
    expect(difficultyTier(0.75)).toBe(4);
    expect(difficultyTier(1)).toBe(5);
  });

  it("clamps out-of-range values into 1..5", () => {
    expect(difficultyTier(-2)).toBe(1);
    expect(difficultyTier(99)).toBe(5);
  });
});

describe("buildGraphLayout", () => {
  it("produces one positioned node per KC with numeric coordinates", () => {
    const course = makeCourse();

    const { nodes } = buildGraphLayout(course.graph, course.goalConcept);

    expect(nodes).toHaveLength(3);
    for (const node of nodes) {
      expect(Number.isFinite(node.position.x)).toBe(true);
      expect(Number.isFinite(node.position.y)).toBe(true);
      expect(node.type).toBe("kc");
    }
  });

  it("ranks prerequisites above the concepts that depend on them", () => {
    const course = makeCourse();

    const { nodes } = buildGraphLayout(course.graph, course.goalConcept);
    const y = (id: string) => nodes.find((n) => n.id === id)!.position.y;

    expect(y("comparison")).toBeLessThan(y("sorted_order"));
    expect(y("sorted_order")).toBeLessThan(y("binary_search"));
  });

  it("flags the goal, order and tier in node data", () => {
    const course = makeCourse();

    const { nodes } = buildGraphLayout(course.graph, course.goalConcept);
    const goal = nodes.find((n) => n.id === "binary_search")!;
    const root = nodes.find((n) => n.id === "comparison")!;

    expect(goal.data.isGoal).toBe(true);
    expect(goal.data.order).toBe(3);
    expect(goal.data.tier).toBe(4);
    expect(root.data.isGoal).toBe(false);
    expect(root.data.order).toBe(1);
  });

  it("marks frontier concepts as known", () => {
    const course = makeCourse();
    course.graph.frontier = ["comparison"];

    const { nodes } = buildGraphLayout(course.graph, course.goalConcept);

    expect(nodes.find((n) => n.id === "comparison")!.data.isKnown).toBe(true);
    expect(nodes.find((n) => n.id === "binary_search")!.data.isKnown).toBe(false);
  });

  it("maps each prerequisite edge to a directed React Flow edge with an arrowhead", () => {
    const course = makeCourse();

    const { edges } = buildGraphLayout(course.graph, course.goalConcept);

    expect(edges).toHaveLength(2);
    const edge = edges.find((e) => e.id === "comparison->sorted_order")!;
    expect(edge.source).toBe("comparison");
    expect(edge.target).toBe("sorted_order");
    expect(edge.markerEnd).toBeDefined();
  });

  it("ignores edges that reference an unknown node", () => {
    const course = makeCourse();
    course.graph.edges.push({ from: "ghost", to: "binary_search", strength: 0.5 });

    // Layout must not throw on the dangling edge; it is dropped from both nodes and edges.
    const { nodes, edges } = buildGraphLayout(course.graph, course.goalConcept);

    expect(nodes).toHaveLength(3);
    expect(nodes.some((node) => node.id === "ghost")).toBe(false);
    expect(edges.some((edge) => edge.source === "ghost" || edge.target === "ghost")).toBe(false);
  });
});
