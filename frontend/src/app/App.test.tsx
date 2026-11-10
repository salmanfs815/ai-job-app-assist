import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { guestQuota, jsonResponse, mockApi, renderApp, signInAsDevUser, userQuota } from "@/test/utils";

const RESUME = {
  id: "r1",
  name: "General",
  isDefault: true,
  charCount: 1200,
  sourceFilename: "cv.pdf",
  ocrStatus: "not_used",
  version: 1,
  createdAt: "2026-11-01T10:00:00Z",
  updatedAt: "2026-11-02T10:00:00Z",
};

describe("app shell and navigation", () => {
  it("shows the landing page with a way into the tool", async () => {
    mockApi({});
    renderApp("/");

    expect(screen.getByRole("heading", { level: 1, name: /Tailor your resume to the job/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Analyze a resume/ })).toHaveAttribute("href", "/analyze");
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main");
  });

  it("offers sign-in to visitors and hides account pages until they sign in", async () => {
    mockApi({ "GET /quota": guestQuota });
    renderApp("/");

    const nav = screen.getAllByRole("navigation", { name: "Main" })[0]!;
    expect(within(nav).queryByRole("link", { name: "Resumes" })).not.toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: /Sign in/ })[0]!);

    expect(await screen.findByRole("link", { name: "Resumes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Account menu for Demo User/ })).toBeInTheDocument();
  });

  it("asks guests to sign in on account pages", async () => {
    mockApi({});
    renderApp("/resumes");

    expect(await screen.findByRole("heading", { name: "Sign in to use saved resumes" })).toBeInTheDocument();
  });

  it("runs as a guest-only tool when sign-in is not configured", async () => {
    mockApi({ "GET /quota": guestQuota });
    renderApp("/resumes", { authMode: "none" });

    expect(await screen.findByRole("heading", { name: "Accounts are not enabled here" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sign in/ })).not.toBeInTheDocument();
  });

  it("shows a helpful page for unknown addresses", async () => {
    mockApi({});
    renderApp("/nope");

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it("switches and remembers the colour theme", async () => {
    mockApi({});
    renderApp("/");

    await userEvent.click(screen.getByRole("button", { name: /Change theme/ }));
    await userEvent.click(await screen.findByRole("menuitemradio", { name: "Dark" }));

    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("signs out from the account menu", async () => {
    signInAsDevUser();
    mockApi({});
    renderApp("/");

    await userEvent.click(screen.getByRole("button", { name: /Account menu/ }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Sign out" }));

    expect(await screen.findAllByRole("button", { name: /Sign in/ })).not.toHaveLength(0);
    expect(localStorage.getItem("jobassist.dev-user")).toBeNull();
  });
});

describe("resumes page", () => {
  it("guides a new user to upload their first resume", async () => {
    signInAsDevUser();
    mockApi({ "GET /resumes": { items: [], nextCursor: null } });
    renderApp("/resumes");

    expect(await screen.findByRole("heading", { name: "No saved resumes yet" })).toBeInTheDocument();
  });

  it("uploads, names and saves a resume", async () => {
    signInAsDevUser();
    let saved: Record<string, unknown> | null = null;
    mockApi({
      "GET /resumes": () => jsonResponse({ items: saved ? [{ ...RESUME, ...saved }] : [], nextCursor: null }),
      "POST /resume/extract": { resume_text: "Extracted resume text, long enough to save.", ocr_status: "not_used" },
      "POST /resumes": ({ body }: { body: Record<string, unknown> }) => {
        saved = body;
        return jsonResponse({ ...RESUME, ...body }, 201);
      },
    });
    renderApp("/resumes");
    await screen.findByRole("heading", { name: "No saved resumes yet" });

    await userEvent.upload(
      document.querySelector<HTMLInputElement>("#new-resume-file")!,
      new File(["x"], "Backend CV.pdf"),
    );
    const dialog = await screen.findByRole("dialog", { name: "Save resume" });
    expect(within(dialog).getByLabelText("Name")).toHaveValue("Backend CV");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save resume" }));

    expect(await screen.findByRole("heading", { level: 2, name: "Backend CV" })).toBeInTheDocument();
    expect(saved).toMatchObject({ name: "Backend CV", sourceFilename: "Backend CV.pdf", makeDefault: false });
  });

  it("lists, renames, sets the default and deletes resumes", async () => {
    signInAsDevUser();
    const other = { ...RESUME, id: "r2", name: "Backend", isDefault: false };
    const mock = mockApi({
      "GET /resumes": { items: [RESUME, other], nextCursor: null },
      "PATCH /resumes/r2": ({ body }: { body: object }) => jsonResponse({ ...other, ...body }),
      "DELETE /resumes/r2": () => new Response(null, { status: 204 }),
    });
    renderApp("/resumes");

    const list = await screen.findByRole("list", { name: "Saved resumes" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("Default")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Make General the default resume" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Make Backend the default resume" }));
    expect(await screen.findByText('"Backend" is now your default resume.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Rename Backend" }));
    const rename = await screen.findByRole("dialog", { name: "Rename resume" });
    await userEvent.clear(within(rename).getByLabelText("Name"));
    await userEvent.type(within(rename).getByLabelText("Name"), "Backend (Python)");
    await userEvent.click(within(rename).getByRole("button", { name: "Save name" }));
    expect(await screen.findByText("Resume renamed.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete Backend" }));
    const confirm = await screen.findByRole("dialog", { name: "Delete this resume?" });
    await userEvent.click(within(confirm).getByRole("button", { name: "Delete resume" }));
    expect(await screen.findByText('Deleted "Backend".')).toBeInTheDocument();
    expect(mock.calls).toEqual(expect.arrayContaining(["PATCH /resumes/r2", "DELETE /resumes/r2"]));
  });

  it("explains when the resume limit is reached", async () => {
    signInAsDevUser();
    mockApi({
      "GET /resumes": { items: [RESUME], nextCursor: null },
      "POST /resume/extract": { resume_text: "Another resume, long enough to save it.", ocr_status: "not_used" },
      "POST /resumes": () =>
        jsonResponse(
          {
            status: 409,
            code: "resume_limit_reached",
            detail: "You can save up to 1 resumes. Delete one to add another.",
          },
          409,
        ),
    });
    renderApp("/resumes");
    await screen.findByRole("list", { name: "Saved resumes" });

    await userEvent.upload(document.querySelector<HTMLInputElement>("#new-resume-file")!, new File(["x"], "cv.docx"));
    const dialog = await screen.findByRole("dialog", { name: "Save resume" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save resume" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Delete one to add another.");
  });

  it("offers a retry when the list cannot be loaded", async () => {
    signInAsDevUser();
    mockApi({ "GET /resumes": () => jsonResponse({ status: 503, code: "storage_unavailable" }, 503) });
    renderApp("/resumes");

    expect(await screen.findByText("Your resumes could not be loaded")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("settings page", () => {
  it("shows the account and today's usage", async () => {
    signInAsDevUser();
    mockApi({
      "GET /me": {
        id: "dev-demo",
        email: "demo@example.test",
        displayName: "Demo User",
        roles: [],
        createdAt: "2026-11-01T10:00:00Z",
        quota: { ...userQuota, used: 5, remaining: 15 },
      },
    });
    renderApp("/settings");

    expect(await screen.findByText("demo@example.test")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Generations used today" })).toHaveAttribute("aria-valuenow", "5");
  });

  it("deletes the account only after typed confirmation, then signs out", async () => {
    signInAsDevUser();
    const mock = mockApi({
      "GET /me": {
        id: "dev-demo",
        email: null,
        displayName: null,
        roles: [],
        createdAt: "2026-11-01T10:00:00Z",
        quota: userQuota,
      },
      "DELETE /me": { deleted: true, resumes: 2, results: 1, usageRecords: 3 },
    });
    renderApp("/settings");

    await userEvent.click(await screen.findByRole("button", { name: "Delete my account" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete your account?" });
    const submit = within(dialog).getByRole("button", { name: "Delete account" });
    expect(submit).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELETE");
    await userEvent.click(submit);

    expect(await screen.findByText("Your account and saved data were deleted.")).toBeInTheDocument();
    expect(mock.calls).toContain("DELETE /me");
    await waitFor(() => expect(localStorage.getItem("jobassist.dev-user")).toBeNull());
  });
});
