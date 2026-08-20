import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionList } from "./SessionList";

/** Two sessions as the API returns them, newest first (the server does the ordering). */
const LISTED = [
  {
    sessionId: "s2",
    graphId: "g2",
    topic: "How neural networks learn",
    status: "active" as const,
    turnCount: 6,
    startedAt: "2026-08-19T09:00:00Z",
    updatedAt: "2026-08-19T09:40:00Z",
  },
  {
    sessionId: "s1",
    graphId: "g1",
    topic: "How vaccines train the immune system",
    status: "closed" as const,
    turnCount: 1,
    startedAt: "2026-08-18T09:00:00Z",
    updatedAt: "2026-08-18T09:05:00Z",
  },
];

function answering(body: unknown, status = 200) {
  return vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
}

function shown() {
  return render(
    <MemoryRouter>
      <SessionList apiBaseUrl="" />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SessionList", () => {
  it("lists the learner's sessions in the order the server sent them", async () => {
    vi.stubGlobal("fetch", answering(LISTED));

    shown();

    const rows = await screen.findAllByRole("listitem");
    expect(rows).toHaveLength(2);
    // The server orders by when a session last moved; the surface must not re-sort it into
    // something else, or "newest first" would mean two different things in two places.
    expect(rows[0]).toHaveTextContent("How neural networks learn");
    expect(rows[1]).toHaveTextContent("How vaccines train the immune system");
  });

  it("names each session's state in words a learner can act on", async () => {
    vi.stubGlobal("fetch", answering(LISTED));

    shown();

    expect(await screen.findByText("In progress")).toBeInTheDocument();
    expect(screen.getByText("Finished")).toBeInTheDocument();
    // The wire's own vocabulary must not reach the screen: "active" tells nobody whether they can
    // carry on with it.
    expect(screen.queryByText("active")).not.toBeInTheDocument();
  });

  it("counts turns in the learner's own units", async () => {
    vi.stubGlobal("fetch", answering(LISTED));

    shown();

    expect(await screen.findByText("6 turns")).toBeInTheDocument();
    expect(screen.getByText("1 turn")).toBeInTheDocument();
  });

  it("offers a way to start one when the learner has never had a session", async () => {
    vi.stubGlobal("fetch", answering([]));

    shown();

    // An empty state with no action is a dead end, which is the one thing an empty state must
    // never be.
    expect(await screen.findByRole("link", { name: /start one/i })).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("offers a way back from a failed read", async () => {
    vi.stubGlobal("fetch", answering({ detail: "Storage is having trouble." }, 503));

    shown();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Storage is having trouble.");
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("re-reads the list when the learner retries", async () => {
    const failing = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ detail: "Down." }), { status: 503 })),
    );
    vi.stubGlobal("fetch", failing);

    shown();
    const retry = await screen.findByRole("button", { name: /try again/i });
    vi.stubGlobal("fetch", answering(LISTED));
    retry.click();

    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
  });

  it("says it is reading before it has anything to show", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );

    shown();

    // A list that renders empty while it is still loading tells a learner they have no sessions,
    // which is a different and wrong answer.
    expect(screen.getByRole("status")).toHaveTextContent(/reading your sessions/i);
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });
});
