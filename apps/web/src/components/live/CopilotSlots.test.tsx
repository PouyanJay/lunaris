import type { AssistantMessageProps, UserMessageProps } from "@copilotkit/react-ui";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LearnerMessage, TurnComposer, TurnError, TutorMessage } from "./CopilotSlots";

/** The panel's slots, driven with the props CopilotKit's `RenderMessage` and `CopilotChat` hand
 *  them. These are ours (AD1: the kit's machinery, none of its skin), so what they must prove is
 *  not that they look right — jsdom cannot see that — but that they carry the loop's meaning:
 *  the tutor's words as written, the director's card, one answer path, and every state. */

/** The kit types `rawData` as `any` and the message content as its own union; the fixtures below
 *  are the shapes `RenderMessage` actually passes (see `@copilotkit/react-ui`'s own AssistantMessage
 *  and UserMessage), narrowed no further than the slot reads them. */
function tutorProps(overrides: Partial<AssistantMessageProps> = {}): AssistantMessageProps {
  return {
    message: message(""),
    isLoading: false,
    isGenerating: false,
    rawData: undefined,
    ...overrides,
  };
}

function learnerProps(content: unknown): UserMessageProps {
  return {
    message: { id: "u1", role: "user", content } as NonNullable<UserMessageProps["message"]>,
    ImageRenderer: () => null,
    rawData: undefined,
  };
}

describe("the tutor's message slot", () => {
  it("draws the tutor's words exactly as they were written", () => {
    // The tutor is told to write prose — no markdown — and the transcript surface prints its
    // words verbatim. A slot that ran them through a markdown renderer would be deciding about
    // the words (a stray `*` pair becomes emphasis and vanishes), so the fixture is one a
    // renderer would rewrite.
    const words = "Multiply 2*3 first, then 4*5, and only then compare.";
    const { container } = render(<TutorMessage {...tutorProps({ message: message(words) })} />);

    expect(container.querySelector('[data-speaker="tutor"]')).toHaveTextContent(words);
  });

  it("draws the card the turn's tool call handed it, under the words", () => {
    // `RenderMessage` passes the tool call's rendered UI as `subComponent`. This is where the
    // Tier 1 card and the Tier 2 layout arrive in the panel — a slot that drops it makes every
    // server-side assertion pass while nothing renders (AD14's exact failure).
    const { container } = render(
      <TutorMessage
        {...tutorProps({
          message: message("Which way is downhill?"),
          subComponent: <div data-testid="the-card">the card</div>,
        })}
      />,
    );

    const tutor = container.querySelector('[data-speaker="tutor"]')!;
    expect(within(tutor as HTMLElement).getByTestId("the-card")).toBeInTheDocument();
    // Order is meaning: the words frame the card, so the card comes after them.
    const text = tutor.textContent ?? "";
    expect(text.indexOf("Which way is downhill?")).toBeLessThan(text.indexOf("the card"));
  });

  it("honours a tool result that asks to be drawn before the words", () => {
    // The kit's own message shape carries `generativeUIPosition`; "before" is set by the kit for
    // tool results that frame what follows. The default is words-then-card, so the inversion is
    // pinned on its own — deleting the branch leaves every other test green.
    const { container } = render(
      <TutorMessage
        {...tutorProps({
          message: { ...message("Which way is downhill?"), generativeUIPosition: "before" },
          subComponent: <div data-testid="the-card">the card</div>,
        })}
      />,
    );

    const text = container.querySelector('[data-speaker="tutor"]')?.textContent ?? "";
    expect(text.indexOf("the card")).toBeLessThan(text.indexOf("Which way is downhill?"));
  });

  it("draws a card that arrived without words", () => {
    // A layout-only or card-only message has empty content; the kit's own slot renders content
    // and generative UI independently, and so must this one.
    render(
      <TutorMessage
        {...tutorProps({ subComponent: <div data-testid="the-card">the card</div> })}
      />,
    );

    expect(screen.getByTestId("the-card")).toBeInTheDocument();
  });

  it("offers no way to regenerate, rate or copy a turn", () => {
    // The kit's slot renders regenerate/copy/thumbs controls. Regenerating a *graded* turn would
    // take another turn against the same criterion; feedback has nowhere to go. So none of the
    // handlers, even when the kit passes them, gets a control.
    const { container } = render(
      <TutorMessage
        {...tutorProps({
          message: message("Anything at all."),
          onRegenerate: vi.fn(),
          onCopy: vi.fn(),
          onThumbsUp: vi.fn(),
          onThumbsDown: vi.fn(),
        })}
      />,
    );

    expect(within(container).queryByRole("button")).not.toBeInTheDocument();
  });

  it("says the tutor is writing while the turn has started and no words have arrived", () => {
    // `isLoading` is the kit's word for "current message, in progress, no content yet" — the
    // window between TEXT_MESSAGE_START and the first CONTENT frame. Announced, so a screen
    // reader hears that something is coming rather than silence.
    render(<TutorMessage {...tutorProps({ isLoading: true })} />);

    expect(screen.getByRole("status")).toHaveTextContent(/writing/i);
  });

  it("stops saying so once words are on screen", () => {
    render(
      <TutorMessage
        {...tutorProps({ message: message("The slope points downhill."), isGenerating: true })}
      />,
    );

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("draws nothing for a message with no words, no card and nothing pending", () => {
    // Otherwise every such message is an empty hairline-divided row in the list.
    const { container } = render(<TutorMessage {...tutorProps()} />);

    expect(container).toBeEmptyDOMElement();
  });
});

describe("the learner's message slot", () => {
  it("draws the learner's words under their own label", () => {
    const { container } = render(<LearnerMessage {...learnerProps("It falls faster.")} />);

    const learner = container.querySelector('[data-speaker="learner"]') as HTMLElement;
    expect(within(learner).getByText("You")).toBeInTheDocument();
    expect(within(learner).getByText("It falls faster.")).toBeInTheDocument();
  });

  it("joins a multi-part message the way the kit does", () => {
    // AG-UI user content may arrive as parts. Text parts joined with a space is the kit's own
    // rule (its UserMessage's `getTextContent`), kept so the record reads the same either way.
    const { container } = render(
      <LearnerMessage
        {...learnerProps([
          { type: "text", text: "It falls" },
          { type: "text", text: "faster." },
        ])}
      />,
    );

    expect(container.querySelector('[data-speaker="learner"]')).toHaveTextContent(
      "It falls faster.",
    );
  });
});

describe("the composer slot", () => {
  it("is our answer form: ⌘↵ sends, Enter stays a newline, and there is no vendor mark", () => {
    // The kit's composer sends on Enter and prints "Powered by CopilotKit" beneath itself. Ours
    // is the same form the transcript surface uses, so a learner meets one composer, not two.
    const onSend = vi.fn(async () => ({}) as never);
    render(<TurnComposer inProgress={false} chatReady onSend={onSend} />);

    const box = screen.getByRole("textbox", { name: /your answer/i });
    fireEvent.change(box, { target: { value: "  It falls faster.  " } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();

    fireEvent.keyDown(box, { key: "Enter", metaKey: true });
    expect(onSend).toHaveBeenCalledWith("It falls faster.");
    expect(screen.queryByText(/powered by/i)).not.toBeInTheDocument();
  });

  it("locks while a turn is in flight", () => {
    // One turn in flight per session (P2a): the box locks so one answer cannot be sent twice.
    render(<TurnComposer inProgress chatReady onSend={vi.fn(async () => ({}) as never)} />);

    expect(screen.getByRole("textbox", { name: /your answer/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled();
  });

  it("locks until the runtime has answered for the agent", () => {
    // `chatReady` is false until CopilotKit has discovered the agent at the runtime. A send
    // before that is dropped by the kit with nothing shown — so the form does not offer one.
    render(<TurnComposer inProgress={false} chatReady={false} onSend={vi.fn()} />);

    expect(screen.getByRole("textbox", { name: /your answer/i })).toBeDisabled();
  });

  it("offers no stop control", () => {
    // AD8: a dropped stream does not cancel the turn, so a "Stop" here would stop the words and
    // not the turn — the learner would be told something ended that had not.
    render(
      <TurnComposer
        inProgress
        chatReady
        onSend={vi.fn(async () => ({}) as never)}
        onStop={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: /stop/i })).not.toBeInTheDocument();
  });
});

describe("the failed-turn slot", () => {
  it("announces the failure with its cause and the way back", () => {
    // A `RUN_ERROR` mid-turn, or a refusal the runtime relayed. Without an `ErrorMessage` slot
    // the kit shows nothing at all (it logs to the console), so a failed turn looked like a
    // tutor still thinking. Announced, with the cause, and with what to do next.
    render(
      <TurnError error={{ message: "The tutor is unavailable.", timestamp: 1 }} isCurrentMessage />,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The tutor is unavailable.");
    expect(alert).toHaveTextContent(/still here/i);
  });
});

function message(content: string): NonNullable<AssistantMessageProps["message"]> {
  return { id: "m1", role: "assistant", content };
}
