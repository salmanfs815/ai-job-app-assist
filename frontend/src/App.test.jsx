import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";


vi.mock("./streaming", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, sha256File: vi.fn().mockResolvedValue("same-file-hash") };
});


function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}


function streamResponse(events) {
  const encoder = new TextEncoder();
  const body = events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(body.slice(0, 19)));
        controller.enqueue(encoder.encode(body.slice(19)));
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } }
  );
}


describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("uses the accurate resume suggestions action label", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "Get Resume Suggestions" })).toBeInTheDocument();
  });

  it("extracts once per file hash, reuses the session cache, and keeps text editable", async () => {
    fetch.mockResolvedValue(jsonResponse({
      resume_text: "Extracted resume text that is long enough to edit and reuse.",
      ocr_status: "not_used",
    }));
    render(<App />);
    const input = document.querySelector("#resume-file-input");
    const file = new File(["resume bytes"], "resume.pdf", { type: "application/pdf" });

    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.getByLabelText("Resume text").value).toContain("Extracted resume"));
    fireEvent.change(screen.getByLabelText("Resume text"), { target: { value: "Edited resume text with enough content for generation." } });
    expect(screen.getByLabelText("Resume text")).toHaveValue("Edited resume text with enough content for generation.");

    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText(/reused from this page session/i)).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("renders streamed Markdown resume suggestions", async () => {
    fetch.mockResolvedValue(streamResponse([
      ["status", { message: "Comparing…", demo: false }],
      ["delta", { text: "# Match overview\n\n" }],
      ["delta", { text: "Strong Python alignment." }],
      ["done", { demo: false }],
    ]));
    render(<App />);
    fireEvent.change(screen.getByLabelText("Resume text"), {
      target: { value: "Backend engineer with substantial Python and API delivery experience." },
    });
    fireEvent.change(screen.getByLabelText("Job description"), {
      target: { value: "Seeking a backend engineer with Python and API delivery experience." },
    });

    fireEvent.click(screen.getByRole("button", { name: "Get Resume Suggestions" }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "Match overview" })).toBeInTheDocument());
    expect(screen.getByText("Strong Python alignment.")).toBeInTheDocument();
    expect(screen.getByText("Resume suggestions ready.")).toBeInTheDocument();
  });

  it("streams the cover letter through its separate action", async () => {
    fetch.mockResolvedValue(streamResponse([
      ["status", { message: "Drafting…", demo: false }],
      ["delta", { text: "Dear Hiring Manager,\n\nA tailored letter." }],
      ["done", { demo: false }],
    ]));
    render(<App />);
    fireEvent.change(screen.getByLabelText("Resume text"), {
      target: { value: "Backend engineer with substantial Python and API delivery experience." },
    });
    fireEvent.change(screen.getByLabelText("Job description"), {
      target: { value: "Seeking a backend engineer with Python and API delivery experience." },
    });

    fireEvent.click(screen.getByRole("button", { name: "Generate Cover Letter" }));

    await waitFor(() => expect(screen.getByText("A tailored letter.")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/generate/cover-letter"),
      expect.objectContaining({ method: "POST" })
    );
    expect(screen.getByText("Cover letter ready.")).toBeInTheDocument();
  });
});
