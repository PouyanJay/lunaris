import type { CopilotChat } from "@copilotkit/react-ui";
import { render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import { CopilotSession, PanelComposer } from "./CopilotSession";
import { LearnerMessage, TurnError, TutorMessage } from "./CopilotSlots";

/** What the panel hands `<CopilotChat/>`, captured at the kit's own prop contract.
 *
 *  Two of the slots (the tutor's message and the composer) are proven through the real kit in
 *  `CopilotSession.test.tsx`, because seeding an initial label makes it render them. The rest —
 *  the learner's message, the failed-turn slot, the activity mark, suggestions off — only render
 *  once a run is in flight, which jsdom cannot drive. So they are pinned here at the seam: a panel
 *  that forgot to pass `ErrorMessage` would show nothing for a failed turn, with every other test
 *  green. */

type CopilotChatProps = ComponentProps<typeof CopilotChat>;

const chatProps = vi.hoisted(() => ({ current: null as CopilotChatProps | null }));

vi.mock("@copilotkit/react-ui", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@copilotkit/react-ui")>()),
  CopilotChat: (props: CopilotChatProps) => {
    chatProps.current = props;
    return null;
  },
}));

// The provider fetches `${runtimeUrl}/info` on mount; stubbed so this test does no network I/O.
vi.stubGlobal(
  "fetch",
  vi.fn(async () => new Response(JSON.stringify({ agents: {} }), { status: 200 })),
);

function mountPanel(): CopilotChatProps {
  render(
    <CopilotSession
      runtimeUrl="http://runtime.test"
      sessionId="sess-1"
      topic="Neural networks"
      standingTurn="Which way would you step?"
      standingSeq={1}
    />,
  );
  expect(chatProps.current, "the panel did not mount <CopilotChat/>").not.toBeNull();
  return chatProps.current!;
}

describe("what the panel hands CopilotChat", () => {
  it("every slot that paints is one of ours", () => {
    const props = mountPanel();

    expect(props.AssistantMessage).toBe(TutorMessage);
    expect(props.UserMessage).toBe(LearnerMessage);
    // The panel's own composer wraps `TurnComposer` (T10): the same form, plus the send path the
    // cards answer through and the ending in the composer's place once the session has closed.
    expect(props.Input).toBe(PanelComposer);
    expect(props.ErrorMessage).toBe(TurnError);
  });

  it("replaces the kit's activity mark with the house one", () => {
    // Between the learner's send and the tutor's first word the kit shows `icons.activityIcon` —
    // three bouncing dots in its own colour if left alone.
    const props = mountPanel();

    // Drawn, not merely present: any node would satisfy "defined", the kit's own dots included.
    render(<>{props.icons?.activityIcon}</>);
    expect(screen.getByRole("status")).toHaveTextContent(/marking your answer/i);
  });

  it("never offers generated suggested replies", () => {
    // The kit's default is `auto`: it would generate "suggested replies" and put them under the
    // tutor's words, which is the surface answering for the learner.
    expect(mountPanel().suggestions).toBe("manual");
  });
});
