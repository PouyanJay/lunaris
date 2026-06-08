import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CredentialError,
  deleteCredential,
  fetchCredentials,
  saveCredential,
  testCredential,
} from "./credentials";

// Auth not configured in tests → authedFetch delegates to the global fetch, which we stub.
function stubFetch(impl: (url: string, init?: RequestInit) => unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => impl(String(url), init)),
  );
}

describe("credentials lib", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("fetches the per-user credential statuses", async () => {
    stubFetch(() => ({
      ok: true,
      json: async () => [{ provider: "anthropic", isSet: true, last4: "9abc" }],
    }));

    const statuses = await fetchCredentials("http://test");

    expect(statuses).toEqual([{ provider: "anthropic", isSet: true, last4: "9abc" }]);
  });

  it("saves a key via PUT and returns the masked status", async () => {
    let captured: { url: string; init: RequestInit | undefined } | null = null;
    stubFetch((url, init) => {
      captured = { url, init };
      return {
        ok: true,
        json: async () => ({ provider: "anthropic", isSet: true, last4: "WXYZ" }),
      };
    });

    const status = await saveCredential("http://test", "anthropic", "sk-ant-WXYZ");

    expect(status.isSet).toBe(true);
    expect(status.last4).toBe("WXYZ");
    expect(captured!.url).toBe("http://test/api/credentials/anthropic");
    expect(captured!.init?.method).toBe("PUT");
    expect(JSON.parse(String(captured!.init?.body))).toEqual({ value: "sk-ant-WXYZ" });
  });

  it("deletes a key via DELETE", async () => {
    let method: string | undefined;
    stubFetch((_url, init) => {
      method = init?.method;
      return { ok: true, json: async () => ({ provider: "search", isSet: false, last4: null }) };
    });

    const status = await deleteCredential("http://test", "search");

    expect(method).toBe("DELETE");
    expect(status.isSet).toBe(false);
  });

  it("probes a key via the test endpoint and returns the result", async () => {
    stubFetch(() => ({
      ok: true,
      json: async () => ({ ok: false, detail: "provider rejected the key" }),
    }));

    const result = await testCredential("http://test", "anthropic", "bad");

    expect(result.ok).toBe(false);
    expect(result.detail).toBe("provider rejected the key");
  });

  it("surfaces the backend detail message on a 400", async () => {
    stubFetch(() => ({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Key value must be non-empty and free of control characters." }),
    }));

    await expect(saveCredential("http://test", "anthropic", "")).rejects.toThrow(CredentialError);
    await expect(saveCredential("http://test", "anthropic", "")).rejects.toThrow(/non-empty/);
  });

  it("wraps a transport failure in a CredentialError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );

    await expect(fetchCredentials("http://test")).rejects.toThrow(CredentialError);
  });
});
