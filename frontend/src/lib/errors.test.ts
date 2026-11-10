import { describe, expect, it } from "vitest";

import { ApiError, errorFromResponse } from "@/lib/errors";
import { formatDuration } from "@/lib/format";

function problem(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/problem+json", ...headers },
  });
}

describe("formatDuration", () => {
  it.each([
    [1, "1 second"],
    [45, "45 seconds"],
    [60, "1 minute"],
    [600, "10 minutes"],
    [3600, "1 hour"],
    [5 * 3600 + 20 * 60, "5 hours 20 min"],
  ])("formats %i seconds as %s", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });
});

describe("errorFromResponse", () => {
  it("explains an exhausted guest quota, when it resets, and suggests signing in", async () => {
    const error = await errorFromResponse(
      problem(429, {
        code: "quota_exceeded",
        scope: "guest",
        limit: 3,
        retryAfterSeconds: 7200,
        resetsAt: "2026-11-10T00:00:00Z",
      }),
      "Generation failed",
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error.isLimit).toBe(true);
    expect(error.retryAfterSeconds).toBe(7200);
    expect(error.message).toMatch(/^You've used all 3 of today's free generations\. It resets in 2 hours \(at .+\)\./);
    expect(error.message).toContain("Sign in for a larger daily allowance.");
  });

  it("does not suggest signing in to a signed-in user", async () => {
    const error = await errorFromResponse(
      problem(429, { code: "quota_exceeded", scope: "user", limit: 20, retryAfterSeconds: 60 }),
      "x",
    );

    expect(error.message).toBe("You've used all 20 of today's generations. Try again in 1 minute.");
  });

  it("explains the global budget pause", async () => {
    const error = await errorFromResponse(
      problem(503, { code: "llm_budget_exhausted", retryAfterSeconds: 1800, resetsAt: "2026-11-10T00:00:00Z" }),
      "Generation failed",
    );

    expect(error.isLimit).toBe(true);
    expect(error.message).toContain("reached its AI budget for today");
    expect(error.message).toContain("resets in 30 minutes");
  });

  it("uses the Retry-After header for plain rate limiting", async () => {
    const error = await errorFromResponse(problem(429, { code: "rate_limited" }, { "Retry-After": "12" }), "x");

    expect(error.message).toBe("You're sending requests too quickly. Try again in 12 seconds.");
  });

  it.each([
    ["authentication_required", 401, "Please sign in to continue."],
    ["invalid_token", 401, "Your session has expired. Please sign in again."],
    ["auth_not_configured", 401, "Sign-in is not available on this server yet."],
  ])("maps %s to a friendly message", async (code, status, expected) => {
    const error = await errorFromResponse(problem(status, { code }), "x");

    expect(error.message).toBe(expected);
    expect(error.isUnauthorized).toBe(true);
  });

  it("keeps the server's detail for other errors", async () => {
    const error = await errorFromResponse(
      problem(413, { code: "http_413", detail: "Resume file is too large." }),
      "Upload failed",
    );

    expect(error.message).toBe("Resume file is too large.");
    expect(error.code).toBe("http_413");
    expect(error.isLimit).toBe(false);
  });

  it("falls back when the body is not JSON", async () => {
    const error = await errorFromResponse(new Response("<html>Bad gateway</html>", { status: 502 }), "Request failed");

    expect(error.message).toBe("Request failed");
    expect(error.code).toBe("http_502");
  });

  it("reports a generic 503 with its retry time", async () => {
    const error = await errorFromResponse(problem(503, { code: "storage_unavailable" }, { "Retry-After": "5" }), "x");

    expect(error.message).toBe("The service is temporarily unavailable. Try again in 5 seconds.");
  });
});
