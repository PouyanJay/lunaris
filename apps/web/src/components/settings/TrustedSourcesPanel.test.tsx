import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SourceAuthority } from "../../types/course";
import { TrustedSourcesPanel } from "./TrustedSourcesPanel";

const API = "http://test";

function authority(over: Partial<SourceAuthority> = {}): SourceAuthority {
  return {
    domain: "en.wikipedia.org",
    kind: "spine",
    tier: "reputable",
    field: null,
    sourceType: "reference",
    note: null,
    ...over,
  };
}

/** A stateful fake API over a mutable `rows` list: GET lists, PUT adds/replaces by (domain, field),
 *  DELETE removes by the query key — so a reload after a write reflects the change. Records calls. */
function fakeServer(rows: SourceAuthority[]) {
  const calls: { method: string; url: string; body?: unknown }[] = [];
  const fetchMock = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const href = url.toString();
    const body = init?.body ? (JSON.parse(init.body as string) as SourceAuthority) : undefined;
    calls.push({ method, url: href, body });
    if (method === "PUT" && body) {
      const i = rows.findIndex((r) => r.domain === body.domain && r.field === body.field);
      if (i >= 0) rows[i] = body;
      else rows.push(body);
      return new Response(init?.body as string, { status: 200 });
    }
    if (method === "DELETE") {
      const params = new URL(href).searchParams;
      const domain = params.get("domain");
      const field = params.get("field");
      const i = rows.findIndex((r) => r.domain === domain && (r.field ?? null) === field);
      if (i >= 0) rows.splice(i, 1);
      return new Response(null, { status: 204 });
    }
    return new Response(JSON.stringify(rows), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

afterEach(() => vi.unstubAllGlobals());

describe("TrustedSourcesPanel", () => {
  it("lists authorities grouped by kind with their tier", async () => {
    fakeServer([
      authority(),
      authority({
        domain: "pubmed.ncbi.nlm.nih.gov",
        kind: "pack",
        field: "medicine",
        tier: "official",
      }),
      authority({ domain: "bit.ly", kind: "denylist", tier: "blocked", sourceType: null }),
    ]);
    render(<TrustedSourcesPanel apiBaseUrl={API} />);

    await waitFor(() => expect(screen.getByText("en.wikipedia.org")).toBeInTheDocument());
    expect(screen.getByText("Universal spine")).toBeInTheDocument();
    expect(screen.getByText("Field packs")).toBeInTheDocument();
    expect(screen.getByText("Denylist")).toBeInTheDocument();
    // The pack row shows its field label + its tier (scoped to the row, since "official" also
    // appears as a <select> option in the form).
    const packRow = screen.getByText("pubmed.ncbi.nlm.nih.gov").closest("li") as HTMLElement;
    expect(within(packRow).getByText("Medicine")).toBeInTheDocument();
    expect(within(packRow).getByText("official")).toBeInTheDocument();
  });

  it("shows the empty state when no authorities are configured", async () => {
    fakeServer([]);
    render(<TrustedSourcesPanel apiBaseUrl={API} />);
    await waitFor(() =>
      expect(screen.getByText(/No trusted sources configured/i)).toBeInTheDocument(),
    );
  });

  it("submits a new authority and reloads", async () => {
    const { calls } = fakeServer([]);
    render(<TrustedSourcesPanel apiBaseUrl={API} />);
    await waitFor(() =>
      expect(screen.getByText(/No trusted sources configured/i)).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByLabelText(/Domain/i), { target: { value: "w3.org" } });
    fireEvent.click(screen.getByRole("button", { name: /save entry/i }));

    await waitFor(() => expect(screen.getByText(/Saved w3\.org/i)).toBeInTheDocument());
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.body).toMatchObject({ domain: "w3.org", kind: "spine" });
  });

  it("surfaces a validation error from the API without crashing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string | URL, init?: RequestInit) => {
        if ((init?.method ?? "GET") === "GET")
          return new Response(JSON.stringify([]), { status: 200 });
        return new Response(null, { status: 422 });
      }),
    );
    render(<TrustedSourcesPanel apiBaseUrl={API} />);
    await waitFor(() =>
      expect(screen.getByText(/No trusted sources configured/i)).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByLabelText(/Domain/i), { target: { value: "example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /save entry/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/isn't valid/i));
  });

  it("removes an authority via its labelled action", async () => {
    const { calls } = fakeServer([
      authority({ domain: "bit.ly", kind: "denylist", tier: "blocked" }),
    ]);
    render(<TrustedSourcesPanel apiBaseUrl={API} />);
    await waitFor(() => expect(screen.getByText("bit.ly")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Remove bit\.ly/i }));

    // The row disappears from the list after the delete + reload (not just: the request fired).
    await waitFor(() => expect(screen.queryByText("bit.ly")).not.toBeInTheDocument());
    const del = calls.find((c) => c.method === "DELETE");
    expect(del?.url).toContain("domain=bit.ly");
  });

  it("shows a loading state while the list is in flight", () => {
    // A fetch that never resolves keeps the panel in its loading state.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    render(<TrustedSourcesPanel apiBaseUrl={API} />);
    expect(screen.getByText(/Loading trusted sources/i)).toBeInTheDocument();
  });

  it("surfaces a load error and recovers on Try again", async () => {
    let attempt = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        attempt += 1;
        if (attempt === 1) throw new TypeError("network down"); // first GET fails
        return new Response(JSON.stringify([authority({ domain: "w3.org" })]), { status: 200 });
      }),
    );
    render(<TrustedSourcesPanel apiBaseUrl={API} />);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => expect(screen.getByText("w3.org")).toBeInTheDocument());
  });

  it("reveals the field selector only for a pack", async () => {
    fakeServer([]);
    render(<TrustedSourcesPanel apiBaseUrl={API} />);
    await waitFor(() => expect(screen.getByLabelText(/Domain/i)).toBeInTheDocument());

    expect(screen.queryByLabelText(/^Field$/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Kind/i), { target: { value: "pack" } });
    expect(within(screen.getByRole("form")).getByLabelText(/^Field$/i)).toBeInTheDocument();
  });
});
