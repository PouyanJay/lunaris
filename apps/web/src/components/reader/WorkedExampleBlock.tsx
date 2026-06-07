import { WorkedExample } from "./visuals/WorkedExample";

/** Attributes lowered onto the `<workedexample>` element by `remarkProseStructure` (lowercase to
 *  match the sanitiser allow-list + react-markdown's property casing). */
interface WorkedExampleBlockProps {
  literallabel?: string;
  literal?: string;
  improvedlabel?: string;
  improved?: string;
  note?: string;
}

/** The prose-pattern lift of a worked example: a `Worked Example N: Literal: '…' With X: '…' (why)`
 *  paragraph that the remark pipeline lowered to a `<workedexample>` element. This reads its
 *  attributes and forwards them to the shared WorkedExample view, so an already-built course renders
 *  the same panel as a freshly-authored typed `worked-example` visual — no rebuild needed. */
export function WorkedExampleBlock({
  literallabel,
  literal,
  improvedlabel,
  improved,
  note,
}: WorkedExampleBlockProps) {
  return (
    <WorkedExample
      literal={{ label: literallabel ?? "Literal", text: literal ?? "" }}
      improved={{ label: improvedlabel ?? "Improved", text: improved ?? "" }}
      note={note ? note : null}
    />
  );
}
