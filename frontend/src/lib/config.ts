/** Build-time configuration (Vite `VITE_*` variables). See `.env.example`. */

export type AuthMode = "entra" | "dev" | "none";

const env = import.meta.env;

function parseAuthMode(value: string | undefined): AuthMode {
  return value === "entra" || value === "dev" ? value : "none";
}

const requestedAuthMode = parseAuthMode(env.VITE_AUTH_MODE);
const entra = {
  tenantSubdomain: env.VITE_ENTRA_TENANT_SUBDOMAIN ?? "",
  spaClientId: env.VITE_ENTRA_SPA_CLIENT_ID ?? "",
  apiScope: env.VITE_ENTRA_API_SCOPE ?? "",
};
const entraConfigured = Boolean(entra.tenantSubdomain && entra.spaClientId && entra.apiScope);

export const config = {
  apiBaseUrl: (env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, ""),
  maxUploadBytes: Number(env.VITE_MAX_UPLOAD_BYTES ?? "5242880"),
  /**
   * `none` hides sign-in entirely: the app runs as the original guest-only tool. That is
   * also what happens when `entra` is requested but not fully configured, so a deployment
   * missing its variables degrades to the working demo instead of a broken sign-in button.
   */
  authMode: requestedAuthMode === "entra" && !entraConfigured ? "none" : requestedAuthMode,
  entra,
  repositoryUrl: "https://github.com/salmanfs815/ai-job-app-assist",
} as const;
