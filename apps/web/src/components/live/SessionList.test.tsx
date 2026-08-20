import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LiveSessionStatus } from "../../lib/liveSessions";
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

  describe("the verbs", () => {
    it("offers ending and leaving only while a session is still going", async () => {
      vi.stubGlobal("fetch", answering(LISTED));

      shown();

      const rows = await screen.findAllByRole("listitem");
      // The live one.
      expect(within(rows[0]!).getByRole("button", { name: /finish/i })).toBeInTheDocument();
      expect(within(rows[0]!).getByRole("button", { name: /leave/i })).toBeInTheDocument();
      // The finished one: there is nothing left to finish or leave.
      expect(within(rows[1]!).queryByRole("button", { name: /finish/i })).not.toBeInTheDocument();
      expect(within(rows[1]!).queryByRole("button", { name: /leave/i })).not.toBeInTheDocument();
    });

    it("offers forgetting a topic only once its session has ended", async () => {
      vi.stubGlobal("fetch", answering(LISTED));

      shown();

      const rows = await screen.findAllByRole("listitem");
      // The API refuses a reset while a session on that map is going, because the session would
      // write its beliefs back over it. The surface teaches the rule rather than hiding a 409.
      expect(within(rows[1]!).getByRole("button", { name: /forget/i })).toBeInTheDocument();
      expect(within(rows[0]!).queryByRole("button", { name: /forget/i })).not.toBeInTheDocument();
    });

    it("can always delete a session, going or not", async () => {
      vi.stubGlobal("fetch", answering(LISTED));

      shown();

      const rows = await screen.findAllByRole("listitem");
      for (const row of rows) {
        expect(within(row).getByRole("button", { name: /delete/i })).toBeInTheDocument();
      }
    });

    it("asks before deleting, and does nothing if the learner backs out", async () => {
      const methods: string[] = [];
      const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        methods.push(init?.method ?? "GET");
        return Promise.resolve(
          new Response(JSON.stringify(LISTED), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      });
      vi.stubGlobal("fetch", fetchMock);

      shown();
      const rows = await screen.findAllByRole("listitem");
      fireEvent.click(within(rows[1]!).getByRole("button", { name: /delete/i }));
      fireEvent.click(await screen.findByRole("button", { name: /cancel/i }));

      // Confirm-before, never optimistic: an irreversible action must not have already happened by
      // the time the learner is asked about it.
      expect(methods).not.toContain("DELETE");
    });

    it("deletes the session the learner confirmed", async () => {
      const calls: { url: string; method: string }[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
          const url = String(input);
          calls.push({ url, method: init?.method ?? "GET" });
          if (init?.method === "DELETE")
            return Promise.resolve(new Response(null, { status: 204 }));
          return Promise.resolve(
            new Response(JSON.stringify(LISTED), {
              status: 200,
              headers: { "content-type": "application/json" },
            }),
          );
        }),
      );

      shown();
      const rows = await screen.findAllByRole("listitem");
      fireEvent.click(within(rows[1]!).getByRole("button", { name: /delete/i }));
      fireEvent.click(await screen.findByRole("button", { name: /^delete session$/i }));

      await waitFor(() =>
        expect(
          calls.some((call) => call.method === "DELETE" && call.url.endsWith("/sessions/s1")),
        ).toBe(true),
      );
    });

    it("names the topic in the confirmation, so nobody deletes the wrong one", async () => {
      vi.stubGlobal("fetch", answering(LISTED));

      shown();
      const rows = await screen.findAllByRole("listitem");
      fireEvent.click(within(rows[1]!).getByRole("button", { name: /delete/i }));

      const dialog = await screen.findByRole("dialog");
      expect(dialog).toHaveTextContent("How vaccines train the immune system");
    });

    it("says what forgetting a topic costs, which is not the same as deleting it", async () => {
      vi.stubGlobal("fetch", answering(LISTED));

      shown();
      const rows = await screen.findAllByRole("listitem");
      fireEvent.click(within(rows[1]!).getByRole("button", { name: /forget/i }));

      const dialog = await screen.findByRole("dialog");
      // The two verbs remove different things, and a learner has to be able to tell which one they
      // are about to press.
      expect(dialog).toHaveTextContent(/progress|demonstrated|knows about you/i);
    });

    it("finishing a session needs no confirmation, because nothing is lost", async () => {
      const calls: string[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
          const url = String(input);
          if (init?.method === "POST") {
            calls.push(url);
            return Promise.resolve(
              new Response(JSON.stringify({}), {
                status: 200,
                headers: { "content-type": "application/json" },
              }),
            );
          }
          return Promise.resolve(
            new Response(JSON.stringify(LISTED), {
              status: 200,
              headers: { "content-type": "application/json" },
            }),
          );
        }),
      );

      shown();
      const rows = await screen.findAllByRole("listitem");
      fireEvent.click(within(rows[0]!).getByRole("button", { name: /finish/i }));

      await waitFor(() => expect(calls.some((url) => url.endsWith("/s2/end"))).toBe(true));
    });

    it("shows why a verb failed and keeps the row", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
          if (init?.method === "DELETE") {
            return Promise.resolve(
              new Response(JSON.stringify({ detail: "Storage is having trouble." }), {
                status: 503,
                headers: { "content-type": "application/json" },
              }),
            );
          }
          return Promise.resolve(
            new Response(JSON.stringify(LISTED), {
              status: 200,
              headers: { "content-type": "application/json" },
            }),
          );
        }),
      );

      shown();
      const rows = await screen.findAllByRole("listitem");
      fireEvent.click(within(rows[1]!).getByRole("button", { name: /delete/i }));
      fireEvent.click(await screen.findByRole("button", { name: /^delete session$/i }));

      // A destructive action that failed silently is the worst of both: the learner believes it
      // happened and it did not.
      expect(await screen.findByText(/storage is having trouble/i)).toBeInTheDocument();
      expect(screen.getAllByRole("listitem")).toHaveLength(2);
    });
  });

  describe("every state a row can be in", () => {
    /** Which verbs a row offers, per status. The mirror of the API's own table (T10): the surface
     *  and the service have to agree about what is possible, and two tables that can drift are how
     *  a learner meets a button that answers 409. */
    const OFFERS: Record<
      LiveSessionStatus,
      { finish: boolean; leave: boolean; forget: boolean; remove: boolean }
    > = {
      placing: { finish: true, leave: true, forget: false, remove: true },
      warming: { finish: true, leave: true, forget: false, remove: true },
      active: { finish: true, leave: true, forget: false, remove: true },
      closed: { finish: false, leave: false, forget: true, remove: true },
      abandoned: { finish: false, leave: false, forget: true, remove: true },
    };

    it.each(Object.keys(OFFERS) as LiveSessionStatus[])(
      "offers the right verbs on a %s session",
      async (status) => {
        vi.stubGlobal("fetch", answering([{ ...LISTED[0], status }]));

        shown();

        const row = await screen.findByRole("listitem");
        const offered = OFFERS[status];
        expect(!!within(row).queryByRole("button", { name: /finish/i })).toBe(offered.finish);
        expect(!!within(row).queryByRole("button", { name: /leave/i })).toBe(offered.leave);
        expect(!!within(row).queryByRole("button", { name: /forget/i })).toBe(offered.forget);
        expect(!!within(row).queryByRole("button", { name: /delete/i })).toBe(offered.remove);
      },
    );

    it.each(Object.keys(OFFERS) as LiveSessionStatus[])(
      "names the %s state in words rather than in the wire's",
      async (status) => {
        vi.stubGlobal("fetch", answering([{ ...LISTED[0], status }]));

        shown();

        const row = await screen.findByRole("listitem");
        // The status label table is exhaustive by type, so this asserts the other half: none of
        // those labels is the raw wire value handed straight through.
        expect(row).not.toHaveTextContent(new RegExp(`\\b${status}\\b`));
      },
    );
  });
});
