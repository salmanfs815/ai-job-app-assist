import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as streaming from "@/lib/streaming";
import { guestQuota, jsonResponse, mockApi, renderApp, signInAsDevUser, streamResponse, userQuota } from "@/test/utils";

const RESUME = "Backend engineer with substantial Python and API delivery experience.";
const JOB = "Seeking a backend engineer with Python and API delivery experience.";

async function fillDocuments() {
  fireEvent.change(await screen.findByLabelText("Resume text"), { target: { value: RESUME } });
  fireEvent.change(screen.getByLabelText("Job description"), { target: { value: JOB } });
}

describe("Analyze page", () => {
  it("shows the guest allowance and streams Markdown resume suggestions", async () => {
    const mock = mockApi({
      "GET /quota": guestQuota,
      "POST /generate/resume-suggestions": () =>
        streamResponse([
          ["status", { message: "Comparing…", demo: true }],
          ["delta", { text: "# Match overview\n\n" }],
          ["delta", { text: "Strong Python alignment." }],
          ["done", { demo: true }],
        ]),
    });
    renderApp("/analyze");

    expect(await screen.findByTestId("quota-summary")).toHaveTextContent("3 of 3 free generations left today");
    await fillDocuments();
    await userEvent.click(screen.getByRole("button", { name: "Get Resume Suggestions" }));

    expect(await screen.findByRole("heading", { name: "Match overview" })).toBeInTheDocument();
    expect(screen.getByText("Strong Python alignment.")).toBeInTheDocument();
    expect(screen.getByText("Resume suggestions ready.")).toBeInTheDocument();
    expect(screen.getByText("Demo output")).toBeInTheDocument();
    // The allowance is refreshed after a generation.
    await waitFor(() => expect(mock.calls.filter((call) => call === "GET /quota")).toHaveLength(2));
  });

  it("sends the optional company and role with a cover letter", async () => {
    const mock = mockApi({
      "GET /quota": guestQuota,
      "POST /generate/cover-letter": ({ body }: { body: Record<string, string> }) => {
        expect(body).toMatchObject({ company_name: "Acme", role_title: "Backend Engineer", tone: "concise" });
        return streamResponse([
          ["delta", { text: "Dear Hiring Manager,\n\nA tailored letter." }],
          ["done", { demo: false }],
        ]);
      },
    });
    renderApp("/analyze");
    await fillDocuments();
    await userEvent.type(screen.getByLabelText("Company (for the cover letter)"), "Acme");
    await userEvent.type(screen.getByLabelText("Role (for the cover letter)"), "Backend Engineer");
    await userEvent.selectOptions(screen.getByLabelText("Tone"), "concise");

    await userEvent.click(screen.getByRole("button", { name: "Generate Cover Letter" }));

    expect(await screen.findByText("A tailored letter.")).toBeInTheDocument();
    expect(screen.getByText("Cover letter ready.")).toBeInTheDocument();
    expect(mock.calls).toContain("POST /generate/cover-letter");
  });

  it("explains a quota error with its reset time", async () => {
    mockApi({
      "GET /quota": guestQuota,
      "POST /generate/resume-suggestions": () =>
        jsonResponse(
          {
            status: 429,
            code: "quota_exceeded",
            scope: "guest",
            limit: 3,
            retryAfterSeconds: 3600,
            resetsAt: "2026-11-10T00:00:00Z",
          },
          429,
          { "Retry-After": "3600" },
        ),
    });
    renderApp("/analyze");
    await fillDocuments();

    await userEvent.click(screen.getByRole("button", { name: "Get Resume Suggestions" }));

    expect(
      await screen.findByText(/You've used all 3 of today's free generations\. It resets in 1 hour/),
    ).toBeVisible();
    expect(screen.getByText("Limit reached")).toBeInTheDocument();
  });

  it("disables generation and says why once the daily allowance is used up", async () => {
    mockApi({ "GET /quota": { ...guestQuota, used: 3, remaining: 0 } });
    renderApp("/analyze");
    await fillDocuments();

    expect(await screen.findByText("You've used all 3 of today's free generations")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Get Resume Suggestions" })).toBeDisabled();
  });

  it("tells everyone when the daily AI budget is spent", async () => {
    mockApi({ "GET /quota": { ...guestQuota, llmAvailable: false } });
    renderApp("/analyze");

    expect(await screen.findByText("Generation is paused for today")).toBeInTheDocument();
  });

  it("extracts an upload once per file and keeps the text editable", async () => {
    vi.spyOn(streaming, "sha256File").mockResolvedValue("same-file-hash");
    const mock = mockApi({
      "GET /quota": guestQuota,
      "POST /resume/extract": { resume_text: "Extracted resume text that is long enough.", ocr_status: "used" },
    });
    renderApp("/analyze");
    const input = await waitFor(() => {
      const element = document.querySelector<HTMLInputElement>("#resume-file-input");
      if (!element) throw new Error("file input not rendered");
      return element;
    });
    const file = new File(["resume bytes"], "resume.pdf", { type: "application/pdf" });

    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() =>
      expect(screen.getByLabelText("Resume text")).toHaveValue("Extracted resume text that is long enough."),
    );
    expect(screen.getByText(/OCR was used to read your scanned resume/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Resume text"), { target: { value: RESUME } });

    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByText(/reused from this page session/)).toBeInTheDocument();
    expect(mock.calls.filter((call) => call === "POST /resume/extract")).toHaveLength(1);
  });

  it("rejects files above the upload limit before sending them", async () => {
    const mock = mockApi({ "GET /quota": guestQuota });
    renderApp("/analyze");
    const input = await waitFor(() => document.querySelector<HTMLInputElement>("#job-description-file-input")!);
    const big = new File(["x"], "job.pdf");
    Object.defineProperty(big, "size", { value: 6 * 1024 * 1024 });

    fireEvent.change(input, { target: { files: [big] } });

    expect(await screen.findByText(/File is too large \(6\.0 MB\)/)).toBeInTheDocument();
    expect(mock.calls).not.toContain("POST /job-description/extract");
  });

  it("fills in a signed-in user's default resume and offers the others", async () => {
    signInAsDevUser();
    const mock = mockApi({
      "GET /quota": userQuota,
      "GET /resumes": {
        items: [
          { id: "r1", name: "General", isDefault: true, charCount: 70, sourceFilename: null, ocrStatus: "not_used" },
          { id: "r2", name: "Backend", isDefault: false, charCount: 70, sourceFilename: null, ocrStatus: "not_used" },
        ],
        nextCursor: null,
      },
      "GET /resumes/r1": { id: "r1", name: "General", isDefault: true, text: RESUME, ocrStatus: "not_used" },
    });
    renderApp("/analyze");

    await waitFor(() => expect(screen.getByLabelText("Resume text")).toHaveValue(RESUME));
    const picker = screen.getByLabelText("Saved resume");
    expect(within(picker).getByRole("option", { name: "General (default)" })).toBeInTheDocument();
    expect(picker).toHaveValue("r1");
    expect(mock.headersFor("GET /resumes")?.get("X-Dev-User")).toBe("demo");
    expect(await screen.findByTestId("quota-summary")).toHaveTextContent("20 of 20 generations left today");
  });

  it("saves pasted resume text to a signed-in user's resumes", async () => {
    signInAsDevUser();
    mockApi({
      "GET /quota": userQuota,
      "GET /resumes": { items: [], nextCursor: null },
      "POST /resumes": ({ body }: { body: Record<string, unknown> }) =>
        jsonResponse({ id: "r9", ...body, isDefault: true }, 201),
    });
    renderApp("/analyze");
    fireEvent.change(await screen.findByLabelText("Resume text"), { target: { value: RESUME } });

    await userEvent.click(await screen.findByRole("button", { name: "Save to my resumes" }));
    const dialog = await screen.findByRole("dialog", { name: "Save resume" });
    await userEvent.type(within(dialog).getByLabelText("Name"), "Pasted CV");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save resume" }));

    expect(await screen.findByText('Saved "Pasted CV" to your resumes.')).toBeInTheDocument();
  });

  it("does not offer saving to guests", async () => {
    mockApi({ "GET /quota": guestQuota });
    renderApp("/analyze");
    fireEvent.change(await screen.findByLabelText("Resume text"), { target: { value: RESUME } });

    expect(screen.queryByRole("button", { name: "Save to my resumes" })).not.toBeInTheDocument();
  });
});
