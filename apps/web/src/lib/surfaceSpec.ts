/** What a turn puts on screen — the Tier 1 card the director chose, and its props.
 *
 *  Mirrors `lunaris_live.session.schema.SurfaceSpec`, discriminated by `kind` exactly as the Python
 *  union is. It arrives two ways and they are the same object: on the session row (`SessionTurn.
 *  surface`, which `GET /{id}` returns) and as the arguments of the `lunaris.surface` AG-UI tool
 *  call. One type for both, because a surface that read the two differently would be two surfaces.
 *
 *  **Nothing here is generated.** Every field is a function of the director's move, the compiled
 *  map and the learner model (plan §8: "deterministic rendering is mandatory here because these
 *  components feed the learner model"). A renderer must therefore never invent, reorder or filter
 *  what it is given — the option order in particular is chosen server-side so the true answer is
 *  not always in the same place, and a client that sorted them would undo that.
 */

/** Which card. A closed set, mirroring `SurfaceKind` — a sixth means a deliberate change on both
 *  sides, which is why `SurfaceCard` renders nothing for a kind it does not know rather than
 *  guessing. */
export type SurfaceKind =
  | "criterion_card"
  | "quiz_card"
  | "explain_back"
  | "mastery_meter"
  | "concept_map";

/** What shape of evidence a criterion asks for. Mirrors `MasteryCriterionKind`. */
export type CriterionAsks = "predict" | "manipulate" | "explain";

/** The staged do-statement, shown as the thing the learner will be marked on (U1). */
export interface CriterionCardSpec {
  kind: "criterion_card";
  nodeId: string;
  concept: string;
  statement: string;
  asks: CriterionAsks;
}

/** The concept's authored misconceptions with its definition among them.
 *
 *  There is deliberately no "correct option" field: the learner's choice is sent as their answer
 *  and graded server-side by the separate grader, against the same criterion every other answer is
 *  marked against. A client that marked it locally would be a second assessment path. */
export interface QuizCardSpec {
  kind: "quiz_card";
  nodeId: string;
  concept: string;
  question: string;
  options: string[];
}

/** A place to say it back, with nothing to recognise — what a retrieval move asks for. */
export interface ExplainBackSpec {
  kind: "explain_back";
  nodeId: string;
  concept: string;
  prompt: string;
}

/** One concept's standing. `recall` is the decayed belief — what they are believed to hold now,
 *  not the estimate at its last evidence. */
export interface MeterEntrySpec {
  nodeId: string;
  concept: string;
  recall: number;
  evidenceCount: number;
}

/** What the learner demonstrated, shown when the session ends. */
export interface MasteryMeterSpec {
  kind: "mastery_meter";
  entries: MeterEntrySpec[];
}

/** Where a concept sits, for a turn this session cannot check. Prerequisites are names, in the
 *  order the map teaches them. */
export interface ConceptMapSpec {
  kind: "concept_map";
  focusNodeId: string;
  concept: string;
  prerequisites: string[];
}

export type SurfaceSpec =
  | CriterionCardSpec
  | QuizCardSpec
  | ExplainBackSpec
  | MasteryMeterSpec
  | ConceptMapSpec;
