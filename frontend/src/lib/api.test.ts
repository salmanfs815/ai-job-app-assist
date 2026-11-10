import { afterEach, describe, expect, it, vi } from "vitest";

import { api, configureApiAuth } from "@/lib/api";
import { ApiError, NetworkError } from "@/lib/errors";
import { jsonResponse, mockApi, userQuota } from "@/test/utils";

let restore: (() => void) | null = null;

afterEach(() => {
  restore?.();
  restore = null;
});

describe("api client", () => {
  it("attaches the headers supplied by the active auth provider", async () => {
    const mock = mockApi({ "GET /quota": userQuota });
    restore = configureApiAuth({
      getAuthHeaders: () => Promise.resolve({ Authorization: "Bearer token-123" }),
      onUnauthorized: () => undefined,
    });

    await api.getQuota();

    expect(mock.headersFor("GET /quota")?.get("Authorization")).toBe("Bearer token-123");
  });

  it("reports a rejected token to the auth provider", async () => {
    mockApi({ "GET /me": () => jsonResponse({ code: "invalid_token", status: 401 }, 401) });
    const onUnauthorized = vi.fn();
    restore = configureApiAuth({
      getAuthHeaders: () => Promise.resolve({ Authorization: "Bearer expired" }),
      onUnauthorized,
    });

    await expect(api.getMe()).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("does not report 401s for requests that carried no credentials", async () => {
    mockApi({ "GET /me": () => jsonResponse({ code: "authentication_required", status: 401 }, 401) });
    const onUnauthorized = vi.fn();
    restore = configureApiAuth({ getAuthHeaders: () => Promise.resolve({}), onUnauthorized });

    await expect(api.getMe()).rejects.toThrow("Please sign in to continue.");
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("turns network failures into a friendly error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(api.getQuota()).rejects.toBeInstanceOf(NetworkError);
  });

  it("passes aborts through untouched", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));

    await expect(api.getQuota()).rejects.toMatchObject({ name: "AbortError" });
  });

  it("sends JSON bodies and encodes resume IDs in paths", async () => {
    const mock = mockApi({
      "PATCH /resumes/a%2Fb": ({ body }: { body: unknown }) => jsonResponse({ id: "a/b", ...(body as object) }),
    });

    const result = await api.updateResume("a/b", { name: "Renamed" });

    expect(result).toMatchObject({ id: "a/b", name: "Renamed" });
    expect(mock.headersFor("PATCH /resumes/a%2Fb")?.get("Content-Type")).toBe("application/json");
  });

  it("uploads documents as multipart form data", async () => {
    const mock = mockApi({
      "POST /job-description/extract": { job_description_text: "Extracted job description.", ocr_status: "not_used" },
    });
    const file = new File(["bytes"], "job.docx");

    const result = await api.extractDocument("job-description", file);

    expect(result).toEqual({ text: "Extracted job description.", ocrStatus: "not_used" });
    const init = mock.fetch.mock.calls[0]?.[1] as RequestInit;
    expect((init.body as FormData).get("job_description_file")).toBeInstanceOf(File);
  });
});
