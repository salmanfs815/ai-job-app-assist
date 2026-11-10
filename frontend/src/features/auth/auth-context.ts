import { createContext, useContext } from "react";

import type { AuthMode } from "@/lib/config";

export interface AuthUser {
  id: string;
  name: string | null;
  email: string | null;
}

/** `loading` while the sign-in state is still being restored (for example after a redirect). */
export type AuthStatus = "loading" | "signedOut" | "signedIn";

export interface AuthContextValue {
  mode: AuthMode;
  status: AuthStatus;
  user: AuthUser | null;
  /** False when this deployment has no sign-in configured (guest-only demo). */
  canSignIn: boolean;
  /** True after the API or identity provider rejected a previously valid session. */
  sessionExpired: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

export const guestOnlyAuth: AuthContextValue = {
  mode: "none",
  status: "signedOut",
  user: null,
  canSignIn: false,
  sessionExpired: false,
  signIn: () => Promise.resolve(),
  signOut: () => Promise.resolve(),
};

export const AuthContext = createContext<AuthContextValue>(guestOnlyAuth);

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

/** Cache-key segment that changes whenever the identity behind API calls changes. */
export function useIdentityKey(): string {
  const { status, user } = useAuth();
  return status === "signedIn" && user ? user.id : "guest";
}
