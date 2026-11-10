/* eslint-disable react-refresh/only-export-components -- route table, not a component module */
import { lazy, Suspense, type ReactNode } from "react";
import { Link, type RouteObject } from "react-router";

import { AppShell } from "@/app/layout/AppShell";
import { RequireAuth } from "@/app/layout/RequireAuth";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { LandingPage } from "@/features/landing/LandingPage";

// Route-level code splitting: each page is its own chunk.
const AnalyzePage = lazy(() => import("@/features/analyze/AnalyzePage"));
const ResumesPage = lazy(() => import("@/features/resumes/ResumesPage"));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));

function PageFallback() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading page">
      <Skeleton className="h-9 w-64" />
      <Skeleton className="h-5 w-96 max-w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function page(element: ReactNode): ReactNode {
  return <Suspense fallback={<PageFallback />}>{element}</Suspense>;
}

function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      action={
        <Button asChild>
          <Link to="/">Back to the start</Link>
        </Button>
      }
    >
      That address does not match anything here.
    </EmptyState>
  );
}

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: "analyze", element: page(<AnalyzePage />) },
      {
        path: "resumes",
        element: <RequireAuth feature="saved resumes">{page(<ResumesPage />)}</RequireAuth>,
      },
      {
        path: "settings",
        element: <RequireAuth feature="account settings">{page(<SettingsPage />)}</RequireAuth>,
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
