import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { Toaster } from "sonner";

import { routes } from "@/app/router";
import { ThemeProvider, useTheme } from "@/app/theme";
import { AuthProvider } from "@/features/auth/AuthProvider";
import type { AuthMode } from "@/lib/config";
import { ApiError } from "@/lib/errors";

// eslint-disable-next-line react-refresh/only-export-components
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        // Retrying a limit or auth error only wastes the visitor's allowance.
        retry: (failureCount, error) => !(error instanceof ApiError && error.status < 500) && failureCount < 2,
      },
    },
  });
}

function ThemedToaster() {
  const { resolvedTheme } = useTheme();
  return <Toaster theme={resolvedTheme} position="bottom-right" richColors closeButton />;
}

/** Everything a page needs around it. Tests reuse this with their own router and client. */
export function AppProviders({
  children,
  queryClient,
  authMode,
}: {
  children: ReactNode;
  queryClient?: QueryClient;
  authMode?: AuthMode;
}) {
  const [client] = useState(() => queryClient ?? createQueryClient());
  return (
    <ThemeProvider>
      <QueryClientProvider client={client}>
        <AuthProvider mode={authMode}>{children}</AuthProvider>
        <ThemedToaster />
      </QueryClientProvider>
    </ThemeProvider>
  );
}

const router = createBrowserRouter(routes);

export default function App() {
  return (
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
