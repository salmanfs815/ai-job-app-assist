import { lazy, Suspense, type ReactNode } from "react";

import { Spinner } from "@/components/ui/feedback";
import { AuthContext, guestOnlyAuth } from "@/features/auth/auth-context";
import { DevAuthProvider } from "@/features/auth/DevAuthProvider";
import { config, type AuthMode } from "@/lib/config";

const EntraAuthProvider = lazy(() => import("@/features/auth/EntraAuthProvider"));

function AuthLoading() {
  return (
    <div className="flex min-h-dvh items-center justify-center gap-2 text-muted-foreground" role="status">
      <Spinner />
      <span>Loading…</span>
    </div>
  );
}

/** Chooses the sign-in implementation for this deployment (see `VITE_AUTH_MODE`). */
export function AuthProvider({ children, mode = config.authMode }: { children: ReactNode; mode?: AuthMode }) {
  if (mode === "dev") return <DevAuthProvider>{children}</DevAuthProvider>;
  if (mode === "entra") {
    return (
      <Suspense fallback={<AuthLoading />}>
        <EntraAuthProvider>{children}</EntraAuthProvider>
      </Suspense>
    );
  }
  return <AuthContext value={guestOnlyAuth}>{children}</AuthContext>;
}
