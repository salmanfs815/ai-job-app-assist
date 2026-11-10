import {
  InteractionRequiredAuthError,
  InteractionStatus,
  PublicClientApplication,
  type AccountInfo,
  type IPublicClientApplication,
} from "@azure/msal-browser";
import { MsalProvider, useMsal } from "@azure/msal-react";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { AuthContext, type AuthContextValue, type AuthUser } from "@/features/auth/auth-context";
import { configureApiAuth } from "@/lib/api";
import { config } from "@/lib/config";

/**
 * Microsoft Entra External ID sign-in (authorization code flow with PKCE).
 *
 * This module is loaded lazily so guests and dev-mode sessions never download MSAL.
 * The redirect URI is the MSAL v5 redirect bridge page (`/redirect.html`).
 */
function createClient(): PublicClientApplication {
  const authorityHost = `${config.entra.tenantSubdomain}.ciamlogin.com`;
  return new PublicClientApplication({
    auth: {
      clientId: config.entra.spaClientId,
      authority: `https://${authorityHost}/`,
      knownAuthorities: [authorityHost],
      redirectUri: `${window.location.origin}/redirect.html`,
      postLogoutRedirectUri: window.location.origin,
    },
    cache: { cacheLocation: "localStorage" },
  });
}

let sharedClient: PublicClientApplication | null = null;

function toUser(account: AccountInfo): AuthUser {
  const claims = account.idTokenClaims as { email?: string; oid?: string } | undefined;
  return {
    id: claims?.oid ?? account.localAccountId,
    name: account.name ?? null,
    email: claims?.email ?? account.username ?? null,
  };
}

function EntraSession({ children }: { children: ReactNode }) {
  const { instance, accounts, inProgress } = useMsal();
  const queryClient = useQueryClient();
  const [sessionExpired, setSessionExpired] = useState(false);
  const account = instance.getActiveAccount() ?? accounts[0] ?? null;
  const scopes = useMemo(() => [config.entra.apiScope], []);

  useEffect(() => {
    if (!instance.getActiveAccount() && accounts[0]) instance.setActiveAccount(accounts[0]);
  }, [instance, accounts]);

  const signIn = useCallback(async () => {
    setSessionExpired(false);
    await instance.loginRedirect({ scopes });
  }, [instance, scopes]);

  const signOut = useCallback(async () => {
    queryClient.clear();
    await instance.logoutRedirect({ account: instance.getActiveAccount() });
  }, [instance, queryClient]);

  const expireSession = useCallback(() => {
    setSessionExpired((alreadyExpired) => {
      if (!alreadyExpired) {
        toast.warning("Your session has expired", {
          id: "session-expired",
          description: "Sign in again to keep using your saved resumes.",
          action: { label: "Sign in", onClick: () => void signIn() },
          duration: 15_000,
        });
      }
      return true;
    });
  }, [signIn]);

  // A layout effect, not a plain effect: React runs child effects before parent effects, so
  // with useEffect the pages' first queries would go out before the headers are registered.
  useLayoutEffect(
    () =>
      configureApiAuth({
        getAuthHeaders: async (): Promise<Record<string, string>> => {
          const active = instance.getActiveAccount();
          if (!active || sessionExpired) return {};
          try {
            const result = await instance.acquireTokenSilent({ scopes, account: active });
            return { Authorization: `Bearer ${result.accessToken}` };
          } catch (error) {
            if (error instanceof InteractionRequiredAuthError) {
              // The refresh token is gone or was revoked: continue as a guest and ask to sign in.
              expireSession();
              return {};
            }
            throw error;
          }
        },
        onUnauthorized: expireSession,
      }),
    [instance, scopes, sessionExpired, expireSession],
  );

  const restoring = inProgress === InteractionStatus.Startup || inProgress === InteractionStatus.HandleRedirect;
  const value = useMemo<AuthContextValue>(() => {
    const signedIn = Boolean(account) && !sessionExpired;
    return {
      mode: "entra",
      status: restoring ? "loading" : signedIn ? "signedIn" : "signedOut",
      user: signedIn && account ? toUser(account) : null,
      canSignIn: true,
      sessionExpired,
      signIn,
      signOut,
    };
  }, [account, restoring, sessionExpired, signIn, signOut]);

  return <AuthContext value={value}>{children}</AuthContext>;
}

export default function EntraAuthProvider({
  children,
  client,
}: {
  children: ReactNode;
  /** Injected in tests; the real client is created once per page load. */
  client?: IPublicClientApplication;
}) {
  const instance = client ?? (sharedClient ??= createClient());
  return (
    <MsalProvider instance={instance}>
      <EntraSession>{children}</EntraSession>
    </MsalProvider>
  );
}
