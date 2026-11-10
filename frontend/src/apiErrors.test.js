import { describe, expect, it } from "vitest";

import { describeApiError, formatDuration } from "./apiErrors";

function problem(status, body, headers = {}) {
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

describe("describeApiError", () => {
  it("explains an exhausted guest quota and when it resets", async () => {
    const message = await describeApiError(
      problem(429, {
        code: "quota_exceeded",
        scope: "guest",
        limit: 3,
        retryAfterSeconds: 7200,
        resetsAt: "2026-11-10T00:00:00Z",
        detail: "You have used all 3 free generations for today.",
      }),
      "Generation failed"
    );

    expect(message).toMatch(/^You've used all 3 of today's free generations\. It resets in 2 hours \(at .+\)\.$/);
  });

  it("explains the global budget pause", async () => {
    const message = await describeApiError(
      problem(503, { code: "llm_budget_exhausted", retryAfterSeconds: 1800, resetsAt: "2026-11-10T00:00:00Z" }),
      "Generation failed"
    );

    expect(message).toContain("reached its AI budget for today");
    expect(message).toContain("resets in 30 minutes");
  });

  it("uses the Retry-After header for plain rate limiting", async () => {
    const message = await describeApiError(
      problem(429, { code: "rate_limited" }, { "Retry-After": "12" }),
      "Request failed"
    );

    expect(message).toBe("You're sending requests too quickly. Try again in 12 seconds.");
  });

  it("keeps showing the server's detail for other errors", async () => {
    const message = await describeApiError(
      problem(413, { code: "http_413", detail: "Resume file is too large." }),
      "Upload failed"
    );

    expect(message).toBe("Resume file is too large.");
  });

  it("falls back when the body is not JSON", async () => {
    const response = new Response("<html>Bad gateway</html>", { status: 502 });

    expect(await describeApiError(response, "Request failed")).toBe("Request failed");
  });
});
