/**
 * Typed client for the backend API.
 *
 * Authentication is pluggable: the active auth provider registers a function that
 * returns the headers to attach (a bearer token, a dev header, or nothing for guests)
 * and a callback for when the API says the session is no longer valid.
 */
import { config } from "@/lib/config";
import { type ApiError, errorFromResponse, isAbortError, NetworkError } from "@/lib/errors";

export type OcrStatus = "used" | "failed" | "not_used";

export interface Quota {
  scope: "user" | "guest";
  limit: number;
  used: number;
  remaining: number;
  resetsAt: string;
  llmAvailable: boolean;
  demo: boolean;
}

export interface Me {
  id: string;
  email: string | null;
  displayName: string | null;
  roles: string[];
  createdAt: string;
  quota: Quota;
}

export interface ResumeSummary {
  id: string;
  name: string;
  isDefault: boolean;
  charCount: number;
  sourceFilename: string | null;
  ocrStatus: OcrStatus;
  version: number;
  createdAt: string;
  updatedAt: string;
}

export interface ResumeDetail extends ResumeSummary {
  text: string;
}

export interface ResumeList {
  items: ResumeSummary[];
  nextCursor: string | null;
}

export interface CreateResumeInput {
  name: string;
  text: string;
  sourceFilename?: string | null;
  ocrStatus?: OcrStatus;
  makeDefault?: boolean;
}

export interface ExtractedDocument {
  text: string;
  ocrStatus: OcrStatus;
}

export interface GenerationInput {
  resume_text: string;
  job_description_text: string;
  tone: string;
  company_name?: string;
  role_title?: string;
}

type AuthHeadersProvider = () => Promise<Record<string, string>>;
type UnauthorizedHandler = (error: ApiError) => void;

let authHeadersProvider: AuthHeadersProvider = () => Promise.resolve({});
let unauthorizedHandler: UnauthorizedHandler = () => undefined;

/** Called by the auth provider. Returns a function that restores the previous hooks. */
export function configureApiAuth(hooks: {
  getAuthHeaders: AuthHeadersProvider;
  onUnauthorized: UnauthorizedHandler;
}): () => void {
  const previous = { authHeadersProvider, unauthorizedHandler };
  authHeadersProvider = hooks.getAuthHeaders;
  unauthorizedHandler = hooks.onUnauthorized;
  return () => {
    authHeadersProvider = previous.authHeadersProvider;
    unauthorizedHandler = previous.unauthorizedHandler;
  };
}

interface RequestOptions {
  method?: string;
  json?: unknown;
  body?: BodyInit;
  signal?: AbortSignal;
  fallbackError?: string;
}

/** Performs a request and returns the raw response, throwing `ApiError` for non-2xx statuses. */
export async function apiRequest(path: string, options: RequestOptions = {}): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json", ...(await authHeadersProvider()) };
  let body = options.body;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }

  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method: options.method ?? "GET",
      headers,
      body,
      signal: options.signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new NetworkError();
  }

  if (!response.ok) {
    const error = await errorFromResponse(response, options.fallbackError ?? "The request failed.");
    if (error.isUnauthorized && "Authorization" in headers) unauthorizedHandler(error);
    throw error;
  }
  return response;
}

async function apiJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await apiRequest(path, options);
  return (await response.json()) as T;
}

export const api = {
  getQuota: (signal?: AbortSignal) => apiJson<Quota>("/quota", { signal }),

  getMe: (signal?: AbortSignal) => apiJson<Me>("/me", { signal }),

  deleteAccount: () =>
    apiJson<{ deleted: true; resumes: number; results: number; usageRecords: number }>("/me", {
      method: "DELETE",
      fallbackError: "Your account could not be deleted.",
    }),

  listResumes: (signal?: AbortSignal) => apiJson<ResumeList>("/resumes", { signal }),

  getResume: (id: string, signal?: AbortSignal) =>
    apiJson<ResumeDetail>(`/resumes/${encodeURIComponent(id)}`, { signal }),

  createResume: (input: CreateResumeInput) =>
    apiJson<ResumeDetail>("/resumes", { method: "POST", json: input, fallbackError: "The resume could not be saved." }),

  updateResume: (id: string, changes: { name?: string; isDefault?: boolean }) =>
    apiJson<ResumeSummary>(`/resumes/${encodeURIComponent(id)}`, {
      method: "PATCH",
      json: changes,
      fallbackError: "The resume could not be updated.",
    }),

  deleteResume: async (id: string): Promise<void> => {
    await apiRequest(`/resumes/${encodeURIComponent(id)}`, {
      method: "DELETE",
      fallbackError: "The resume could not be deleted.",
    });
  },

  async extractDocument(
    kind: "resume" | "job-description",
    file: File,
    signal?: AbortSignal,
  ): Promise<ExtractedDocument> {
    const isResume = kind === "resume";
    const form = new FormData();
    form.append(isResume ? "resume_file" : "job_description_file", file);
    const data = await apiJson<{ resume_text?: string; job_description_text?: string; ocr_status: OcrStatus }>(
      isResume ? "/resume/extract" : "/job-description/extract",
      {
        method: "POST",
        body: form,
        signal,
        fallbackError: `${isResume ? "Resume" : "Job description"} extraction failed.`,
      },
    );
    return { text: (isResume ? data.resume_text : data.job_description_text) ?? "", ocrStatus: data.ocr_status };
  },

  /** Starts a streamed generation. The caller consumes the SSE body with `consumeEventStream`. */
  startGeneration: (kind: "resume-suggestions" | "cover-letter", input: GenerationInput, signal?: AbortSignal) =>
    apiRequest(`/generate/${kind}`, { method: "POST", json: input, signal, fallbackError: "Generation failed." }),
};
