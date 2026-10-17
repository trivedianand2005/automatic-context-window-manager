import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getSessionId, request, SESSION_HEADER, toApiError } from "./api";
import { budgetSegments, fmtPct, fmtScore, lineRangeLabel } from "./format";

describe("getSessionId", () => {
  it("creates a valid id once and reuses it", () => {
    localStorage.clear();
    const a = getSessionId();
    expect(a).toMatch(/^[A-Za-z0-9-]{8,64}$/);
    expect(getSessionId()).toBe(a);
  });

  it("replaces a malformed stored id", () => {
    localStorage.setItem("acwm-session-id", "bad id!");
    expect(getSessionId()).toMatch(/^[A-Za-z0-9-]{8,64}$/);
  });
});

describe("toApiError", () => {
  it("reads the backend's structured error body", async () => {
    const res = new Response(
      JSON.stringify({ error: { code: "path_not_allowed", message: "Outside allowed roots." } }),
      { status: 403 },
    );
    const err = await toApiError(res);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.code).toBe("path_not_allowed");
    expect(err.message).toBe("Outside allowed roots.");
  });

  it("appends validation details", async () => {
    const res = new Response(
      JSON.stringify({
        error: { code: "validation_error", message: "Request validation failed.",
          details: [{ loc: ["body", "token_budget"], msg: "too small" }] },
      }),
      { status: 422 },
    );
    expect((await toApiError(res)).message).toContain("token_budget too small");
  });

  it("handles non-JSON error pages", async () => {
    const err = await toApiError(new Response("<html>bad gateway</html>", { status: 502 }));
    expect(err.code).toBe("http_error");
    expect(err.message).toContain("502");
  });
});

describe("request", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends the session header and JSON body", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    await request("/context/build", { method: "POST", body: { task: "x" } });
    const [, init] = fetchMock.mock.calls[0];
    const headers = init!.headers as Record<string, string>;
    expect(headers[SESSION_HEADER]).toMatch(/^[A-Za-z0-9-]{8,64}$/);
    expect(headers["Content-Type"]).toBe("application/json");
    expect(init!.body).toBe(JSON.stringify({ task: "x" }));
  });

  it("turns network failures into a friendly ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(request("/health")).rejects.toMatchObject({ code: "network_error", status: 0 });
  });
});

describe("format helpers", () => {
  it("budget segments always add up to the total budget", () => {
    const segs = budgetSegments({
      total_budget: 4000, reserved_system_tokens: 400, reserved_task_tokens: 31,
      reserved_response_tokens: 1500, safety_margin_tokens: 200,
      rendered_context_tokens: 1850, usable_tokens: 1869,
    });
    expect(segs.reduce((a, s) => a + s.tokens, 0)).toBe(4000);
    expect(segs.reduce((a, s) => a + s.share, 0)).toBeCloseTo(1, 5);
    expect(segs.find((s) => s.key === "free")!.tokens).toBe(19);
  });

  it("formats missing metrics as N/A, never 0", () => {
    expect(fmtPct(null)).toBe("N/A");
    expect(fmtScore(undefined)).toBe("N/A");
    expect(fmtScore(0)).toBe("0.00");
  });

  it("labels line ranges", () => {
    expect(lineRangeLabel([[3, 12], [33, 36]], 36)).toBe("lines 3-12, 33-36 of 36");
    expect(lineRangeLabel([], 10)).toBe("0 of 10 lines");
  });
});
