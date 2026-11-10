/**
 * Turns an error response from the API (RFC 9457 problem+json) into a message a person can act on.
 * Limit errors (429 / 503) say when the limit resets.
 */

export function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.round(totalSeconds));
  if (seconds < 60) return `${seconds} second${seconds === 1 ? "" : "s"}`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const hourText = `${hours} hour${hours === 1 ? "" : "s"}`;
  return rest ? `${hourText} ${rest} min` : hourText;
}

export function formatResetTime(resetsAt, locale) {
  const date = new Date(resetsAt);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
}

function retryAfterSeconds(response, problem) {
  if (Number.isFinite(problem?.retryAfterSeconds)) return problem.retryAfterSeconds;
  const header = Number(response.headers.get("Retry-After"));
  return Number.isFinite(header) && header > 0 ? header : null;
}

function resetSuffix(seconds, resetsAt) {
  if (seconds === null) return "";
  const at = resetsAt ? formatResetTime(resetsAt) : "";
  return at ? ` It resets in ${formatDuration(seconds)} (at ${at}).` : ` Try again in ${formatDuration(seconds)}.`;
}

export async function describeApiError(response, fallback) {
  let problem = null;
  try {
    problem = await response.json();
  } catch (_error) {
    // Non-JSON error body: fall through to the generic messages below.
  }

  const seconds = retryAfterSeconds(response, problem);

  if (problem?.code === "quota_exceeded") {
    const count = Number.isFinite(problem.limit) ? `all ${problem.limit}` : "all";
    const who = problem.scope === "guest" ? "free generations" : "generations";
    return `You've used ${count} of today's ${who}.${resetSuffix(seconds, problem.resetsAt)}`;
  }
  if (problem?.code === "llm_budget_exhausted") {
    return `This demo has reached its AI budget for today, so generation is paused.${resetSuffix(seconds, problem.resetsAt)}`;
  }
  if (response.status === 429) {
    return `You're sending requests too quickly.${resetSuffix(seconds, null)}`;
  }
  if (response.status === 503) {
    return `The service is temporarily unavailable.${resetSuffix(seconds, null)}`;
  }

  if (typeof problem?.detail === "string" && problem.detail.trim()) return problem.detail;
  if (Array.isArray(problem?.detail) && problem.detail.length > 0) {
    return problem.detail.map((detail) => detail?.msg || JSON.stringify(detail)).join("; ");
  }
  return fallback;
}
