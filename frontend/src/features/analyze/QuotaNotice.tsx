import { Button } from "@/components/ui/button";
import { Alert, Skeleton } from "@/components/ui/feedback";
import type { Quota } from "@/lib/api";
import { formatDuration, formatTime } from "@/lib/format";

function resetText(resetsAt: string): string {
  const seconds = (new Date(resetsAt).getTime() - Date.now()) / 1000;
  const at = formatTime(resetsAt);
  return seconds > 0 && at ? `It resets in ${formatDuration(seconds)} (at ${at}).` : "It resets soon.";
}

interface QuotaNoticeProps {
  quota: Quota | undefined;
  loading: boolean;
  canSignIn: boolean;
  onSignIn: () => Promise<void>;
}

/** Tells the visitor how many generations are left today and what to do when there are none. */
export function QuotaNotice({ quota, loading, canSignIn, onSignIn }: QuotaNoticeProps) {
  if (loading) return <Skeleton className="h-5 w-64" />;
  if (!quota) return null;

  const signInAction = canSignIn ? (
    <Button size="sm" variant="outline" onClick={() => void onSignIn()}>
      Sign in for a larger allowance
    </Button>
  ) : undefined;

  if (!quota.llmAvailable) {
    return (
      <Alert variant="warning" title="Generation is paused for today">
        This demo has reached its AI budget for today. {resetText(quota.resetsAt)} Uploading and editing documents still
        works.
      </Alert>
    );
  }

  if (quota.remaining <= 0) {
    return (
      <Alert
        variant="warning"
        title={`You've used all ${quota.limit} of today's ${quota.scope === "guest" ? "free " : ""}generations`}
        action={quota.scope === "guest" ? signInAction : undefined}
      >
        {resetText(quota.resetsAt)}
      </Alert>
    );
  }

  return (
    <p className="text-sm text-muted-foreground" data-testid="quota-summary">
      <span className="font-medium text-foreground">
        {quota.remaining} of {quota.limit}
      </span>{" "}
      {quota.scope === "guest" ? "free " : ""}generations left today
      {quota.demo ? " · demo mode: sample output, no AI cost" : ""}
      {quota.scope === "guest" && canSignIn ? (
        <>
          {" · "}
          <button
            type="button"
            className="font-medium text-primary underline underline-offset-4"
            onClick={() => void onSignIn()}
          >
            Sign in for more
          </button>
        </>
      ) : null}
    </p>
  );
}
