import { LogIn } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { useAuth } from "@/features/auth/auth-context";

/** Shows its children to signed-in users and a sign-in prompt to everyone else. */
export function RequireAuth({ children, feature }: { children: ReactNode; feature: string }) {
  const { status, canSignIn, sessionExpired, signIn } = useAuth();

  if (status === "loading") {
    return (
      <div className="space-y-4" role="status" aria-label="Loading">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (status === "signedIn") return <>{children}</>;

  if (!canSignIn) {
    return (
      <EmptyState
        title="Accounts are not enabled here"
        action={
          <Button asChild variant="outline">
            <Link to="/analyze">Use the analyzer as a guest</Link>
          </Button>
        }
      >
        This deployment runs in guest-only mode, so {feature} are unavailable.
      </EmptyState>
    );
  }

  return (
    <EmptyState
      icon={<LogIn aria-hidden="true" />}
      title={sessionExpired ? "Your session has expired" : `Sign in to use ${feature}`}
      action={
        <Button onClick={() => void signIn()}>
          <LogIn aria-hidden="true" /> Sign in
        </Button>
      }
    >
      {sessionExpired
        ? "Sign in again to pick up where you left off."
        : `An account keeps your ${feature} private to you and gives you a larger daily allowance.`}
    </EmptyState>
  );
}
