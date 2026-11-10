import { QueryClient } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { vi, type Mock } from "vitest";

import { AppProviders } from "@/app/App";
import { routes } from "@/app/router";
import type { AuthMode } from "@/lib/config";

export function jsonResponse(data: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": status >= 400 ? "application/problem+json" : "application/json", ...headers },
  });
}

export function streamResponse(events: [string, Record<string, unknown>][]): Response {
  const encoder = new TextEncoder();
  const body = events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  return new Response(
    new ReadableStream({
      start(controller) {
        // Split mid-event to exercise reassembly across transport chunks.
        controller.enqueue(encoder.encode(body.slice(0, 19)));
        controller.enqueue(encoder.encode(body.slice(19)));
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

export const guestQuota = {
  scope: "guest",
  limit: 3,
  used: 0,
  remaining: 3,
  resetsAt: new Date(Date.now() + 5 * 3600 * 1000).toISOString(),
  llmAvailable: true,
  demo: false,
};

export const userQuota = { ...guestQuota, scope: "user", limit: 20, remaining: 20 };

type Handler = (request: { url: URL; method: string; headers: Headers; body: unknown }) => Response | Promise<Response>;

export interface MockApi {
  fetch: Mock;
  /** Requests seen so far as "METHOD /path". */
  calls: string[];
  headersFor: (call: string) => Headers | undefined;
}

/**
 * Replaces `fetch` with a router over "METHOD /path" keys. Unknown routes fail the test
 * loudly instead of hanging.
 */
export function mockApi(handlers: Record<string, unknown>): MockApi {
  const calls: string[] = [];
  const seenHeaders = new Map<string, Headers>();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" || input instanceof URL ? input.toString() : input.url);
    const method = (init?.method ?? "GET").toUpperCase();
    const key = `${method} ${url.pathname}`;
    const headers = new Headers(init?.headers);
    calls.push(key);
    seenHeaders.set(key, headers);
    const handler = handlers[key];
    if (handler === undefined) return jsonResponse({ code: "http_404", detail: `No mock for ${key}` }, 404);
    if (typeof handler !== "function") return jsonResponse(handler);
    let body: unknown = init?.body;
    if (typeof body === "string") {
      try {
        body = JSON.parse(body);
      } catch {
        // Leave non-JSON bodies as they are.
      }
    }
    return (handler as Handler)({ url, method, headers, body });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetch: fetchMock, calls, headersFor: (call) => seenHeaders.get(call) };
}

export function signInAsDevUser(): void {
  localStorage.setItem("jobassist.dev-user", "demo");
}

/** Renders the real route tree at `path` with fresh providers. */
export function renderApp(path = "/", options: { authMode?: AuthMode } = {}): RenderResult {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
  });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <AppProviders queryClient={queryClient} authMode={options.authMode ?? "dev"}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
}
