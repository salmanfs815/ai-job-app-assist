import { formatDuration, formatTime } from "@/lib/format";

/** RFC 9457 problem details as returned by the API (see docs/errors.md). */
export interface Problem {
  type?: string;
  title?: string;
  status?: number;
  detail?: unknown;
  code?: string;
  retryAfterSeconds?: number;
  resetsAt?: string;
  scope?: "guest" | "user";
  limit?: number;
  errors?: { field: string; message: string }[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: Problem | null;
  readonly retryAfterSeconds: number | null;

  constructor(message: string, status: number, problem: Problem | null, retryAfterSeconds: number | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = problem?.code ?? `http_${status}`;
    this.problem = problem;
    this.retryAfterSeconds = retryAfterSeconds;
  }

  /** The caller must sign in (or sign in again). */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** A limit was hit; retrying before `retryAfterSeconds` will not help. */
  get isLimit(): boolean {
    return this.status === 429 || this.code === "llm_budget_exhausted";
  }
}

export class NetworkError extends Error {
  constructor() {
    super("Could not reach the server. Check your connection and try again.");
    this.name = "NetworkError";
  }
}

function retryAfter(response: Response, problem: Problem | null): number | null {
  if (typeof problem?.retryAfterSeconds === "number" && Number.isFinite(problem.retryAfterSeconds)) {
    return problem.retryAfterSeconds;
  }
  const header = Number(response.headers.get("Retry-After"));
  return Number.isFinite(header) && header > 0 ? header : null;
}

function resetSuffix(seconds: number | null, resetsAt: string | undefined): string {
  if (seconds === null) return "";
  const at = resetsAt ? formatTime(resetsAt) : "";
  return at ? ` It resets in ${formatDuration(seconds)} (at ${at}).` : ` Try again in ${formatDuration(seconds)}.`;
}

/** A message a person can act on. Limit errors say when the limit resets. */
export function describeProblem(
  status: number,
  problem: Problem | null,
  seconds: number | null,
  fallback: string,
): string {
  switch (problem?.code) {
    case "quota_exceeded": {
      const count = typeof problem.limit === "number" ? `all ${problem.limit}` : "all";
      const what = problem.scope === "guest" ? "free generations" : "generations";
      const hint = problem.scope === "guest" ? " Sign in for a larger daily allowance." : "";
      return `You've used ${count} of today's ${what}.${resetSuffix(seconds, problem.resetsAt)}${hint}`;
    }
    case "llm_budget_exhausted":
      return `This demo has reached its AI budget for today, so generation is paused.${resetSuffix(seconds, problem.resetsAt)}`;
    case "authentication_required":
      return "Please sign in to continue.";
    case "invalid_token":
      return "Your session has expired. Please sign in again.";
    case "auth_not_configured":
      return "Sign-in is not available on this server yet.";
    default:
      break;
  }
  if (status === 429) return `You're sending requests too quickly.${resetSuffix(seconds, undefined)}`;
  if (status === 503) return `The service is temporarily unavailable.${resetSuffix(seconds, undefined)}`;
  if (typeof problem?.detail === "string" && problem.detail.trim()) return problem.detail;
  return fallback;
}

export async function errorFromResponse(response: Response, fallback: string): Promise<ApiError> {
  let problem: Problem | null = null;
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object") problem = body;
  } catch {
    // Not JSON (for example a proxy error page): use the generic messages.
  }
  const seconds = retryAfter(response, problem);
  return new ApiError(describeProblem(response.status, problem, seconds, fallback), response.status, problem, seconds);
}

export function errorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException ? error.name === "AbortError" : (error as Error | null)?.name === "AbortError";
}
