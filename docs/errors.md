# API errors

Every error response is [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) `application/problem+json`:

```json
{
  "type": "https://github.com/salmanfs815/ai-job-app-assist/blob/master/docs/errors.md#quota_exceeded",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "You have used all 3 free generations for today.",
  "code": "quota_exceeded",
  "retryAfterSeconds": 41520,
  "resetsAt": "2026-11-10T00:00:00Z"
}
```

`code` is the stable, machine-readable identifier. `429` and `503` responses always carry a
`Retry-After` header (seconds) and the same value as `retryAfterSeconds`.

| Code | Status | Meaning | Extra members |
| --- | --- | --- | --- |
| <a id="rate_limited"></a>`rate_limited` | 429 | Too many requests from one IP address. | `retryAfterSeconds` |
| <a id="quota_exceeded"></a>`quota_exceeded` | 429 | The caller's daily generation quota is used up. | `retryAfterSeconds`, `resetsAt`, `scope` (`guest`/`user`), `limit` |
| <a id="llm_budget_exhausted"></a>`llm_budget_exhausted` | 503 | The global daily LLM budget is spent. Non-LLM features keep working. | `retryAfterSeconds`, `resetsAt` |
| <a id="usage_unavailable"></a>`usage_unavailable` | 503 | Limits could not be checked, so the generation was refused. | `retryAfterSeconds` |
| <a id="validation_error"></a>`validation_error` | 422 | The request body is invalid. | `errors[]` with `field` and `message` |
| <a id="internal_error"></a>`internal_error` | 500 | Unexpected failure. No internal detail is exposed. | |
| `http_<status>` | 4xx | Any other HTTP error (`http_400`, `http_404`, `http_413`, ...). | |

Errors that happen after a generation stream has started are delivered in-band as an SSE
`error` event (`message`, `retryable`, `partial`).
