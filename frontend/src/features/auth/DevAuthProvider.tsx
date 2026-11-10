import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useLayoutEffect, useMemo, useState, type ReactNode } from "react";

import { AuthContext, type AuthContextValue, type AuthUser } from "@/features/auth/auth-context";
import { configureApiAuth } from "@/lib/api";

const STORAGE_KEY = "jobassist.dev-user";
export const DEV_USER_NAME = "demo";

function readStoredUser(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function toUser(name: string): AuthUser {
  return {
    id: `dev-${name}`,
    name: `${name.charAt(0).toUpperCase()}${name.slice(1)} User`,
    email: `${name}@example.test`,
  };
}

/**
 * Local development sign-in: no identity provider, just an `X-Dev-User` header that the
 * API honours only when it runs with AUTH_MODE=dev and ENVIRONMENT=local.
 */
export function DevAuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState<string | null>(readStoredUser);

  // A layout effect, not a plain effect: React runs child effects before parent effects, so
  // with useEffect the pages' first queries would go out before the headers are registered.
  useLayoutEffect(
    () =>
      configureApiAuth({
        getAuthHeaders: () => Promise.resolve<Record<string, string>>(name ? { "X-Dev-User": name } : {}),
        onUnauthorized: () => undefined,
      }),
    [name],
  );

  const signIn = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, DEV_USER_NAME);
    setName(DEV_USER_NAME);
    return Promise.resolve();
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setName(null);
    queryClient.clear();
    return Promise.resolve();
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      mode: "dev",
      status: name ? "signedIn" : "signedOut",
      user: name ? toUser(name) : null,
      canSignIn: true,
      sessionExpired: false,
      signIn,
      signOut,
    }),
    [name, signIn, signOut],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}
