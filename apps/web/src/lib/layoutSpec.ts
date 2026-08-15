/** How a turn is laid out for this learner — Tier 2's composition, over an allow-list catalog.
 *
 *  Mirrors `lunaris_live.session.schema.LayoutSpec`, discriminated by `component` exactly as the
 *  Python union is. It arrives two ways and they are the same object: on the session row
 *  (`SessionTurn.layout`, which `GET /{id}` returns) and as the arguments of the `lunaris.layout`
 *  AG-UI tool call.
 *
 *  **The catalog is the boundary (R6).** A composition may only name components in this union, so a
 *  layout carrying free-form markup, an iframe, or an unknown widget is not something this type can
 *  describe. The server enforces the same list by parsing into the same union — the allow-list is a
 *  type on both sides rather than a check either side could forget to run.
 *
 *  **Two of the blocks are slots.** `Prose` and `Surface` carry nothing: the tutor's words are
 *  `SessionTurn.tutor` and the Tier 1 card is `SessionTurn.surface`, and the layout says only where
 *  they go. A block that carried its own copy of either could disagree with the thing the learner is
 *  actually marked on.
 */

/** Which component. A closed set, mirroring `LayoutComponent`. */
export type LayoutComponentName =
  | "Stack"
  | "Prose"
  | "Surface"
  | "WorkedExample"
  | "Hint"
  | "Practice";

/** Children in reading order, referenced by id. A2UI v0.9's flat shape: the tree is a list. */
export interface StackBlockSpec {
  component: "Stack";
  id: string;
  children: string[];
}

/** Where the tutor's words go. */
export interface ProseBlockSpec {
  component: "Prose";
  id: string;
}

/** Where the director's Tier 1 card goes. */
export interface SurfaceBlockSpec {
  component: "Surface";
  id: string;
}

/** A worked example, open or closed. `expanded` is the server's decision, read off what the learner
 *  has shown about this concept — not a client preference and not a remembered toggle. */
export interface ExampleBlockSpec {
  component: "WorkedExample";
  id: string;
  title: string;
  steps: string[];
  expanded: boolean;
}

/** One hint, behind a disclosure. Its presence is the decision; it is always closed to begin with,
 *  because a hint that opens itself is the answer moved up the page. */
export interface HintBlockSpec {
  component: "Hint";
  id: string;
  hint: string;
}

/** Prompts to think through before answering. Nothing here is graded — the evidence still comes
 *  from the staged criterion answered in the card. */
export interface PracticeBlockSpec {
  component: "Practice";
  id: string;
  prompts: string[];
}

export type LayoutBlockSpec =
  | StackBlockSpec
  | ProseBlockSpec
  | SurfaceBlockSpec
  | ExampleBlockSpec
  | HintBlockSpec
  | PracticeBlockSpec;

export interface LayoutSpec {
  /** Which catalog these names belong to. Versioned, because the API and this SPA are deployed
   *  separately: a build that has never heard of the catalog in front of it must be able to say so
   *  rather than render half a lesson. */
  catalogId: string;
  blocks: LayoutBlockSpec[];
}

/** The catalog this build knows how to draw. */
export const LAYOUT_CATALOG = "lunaris.live.layout/v1";
