import { Briefcase, LogIn, LogOut, Menu, Monitor, Moon, Settings, Sun, X } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet, ScrollRestoration, useNavigate } from "react-router";

import { useTheme, type Theme } from "@/app/theme";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/feedback";
import { useAuth } from "@/features/auth/auth-context";
import { config } from "@/lib/config";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  requiresAuth?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/analyze", label: "Analyze" },
  { to: "/resumes", label: "Resumes", requiresAuth: true },
];

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return cn(
    "rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground",
    isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground",
  );
}

function ThemeToggle() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const Icon = resolvedTheme === "dark" ? Moon : Sun;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Theme: ${theme}. Change theme`}>
          <Icon aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={(value) => setTheme(value as Theme)}>
          <DropdownMenuRadioItem value="light">
            <Sun aria-hidden="true" /> Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Moon aria-hidden="true" /> Dark
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Monitor aria-hidden="true" /> System
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UserMenu() {
  const { status, user, canSignIn, signIn, signOut } = useAuth();
  const navigate = useNavigate();

  if (!canSignIn) return null;
  if (status === "loading") return <Skeleton className="size-10 rounded-full" />;
  if (status === "signedOut" || !user) {
    return (
      <Button size="sm" onClick={() => void signIn()}>
        <LogIn aria-hidden="true" /> Sign in
      </Button>
    );
  }

  const label = user.name ?? user.email ?? "Account";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="secondary" size="icon" className="rounded-full" aria-label={`Account menu for ${label}`}>
          <span aria-hidden="true" className="text-xs font-semibold">
            {initials(user.name ?? user.email)}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="truncate">{label}</span>
          {user.email && user.email !== label ? (
            <span className="truncate text-xs font-normal text-muted-foreground">{user.email}</span>
          ) : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void navigate("/settings")}>
          <Settings aria-hidden="true" /> Settings
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void signOut()}>
          <LogOut aria-hidden="true" /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppShell() {
  const { status, canSignIn } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const items = NAV_ITEMS.filter((item) => !item.requiresAuth || (canSignIn && status === "signedIn"));

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-4">
          <Link to="/" className="mr-2 flex items-center gap-2 rounded-md font-semibold">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Briefcase aria-hidden="true" className="size-4" />
            </span>
            <span className="hidden min-[400px]:inline">Job Application Assistant</span>
          </Link>

          <nav aria-label="Main" className="hidden items-center gap-1 sm:flex">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} className={navLinkClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <UserMenu />
            <Button
              variant="ghost"
              size="icon"
              className="sm:hidden"
              aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={mobileOpen}
              aria-controls="mobile-nav"
              onClick={() => setMobileOpen((open) => !open)}
            >
              {mobileOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
            </Button>
          </div>
        </div>

        {mobileOpen ? (
          <nav id="mobile-nav" aria-label="Main" className="flex flex-col gap-1 border-t px-4 py-2 sm:hidden">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} className={navLinkClass} onClick={() => setMobileOpen(false)}>
                {item.label}
              </NavLink>
            ))}
          </nav>
        ) : null}
      </header>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 outline-none sm:py-10">
        <Outlet />
      </main>

      <footer className="border-t">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-4 text-sm text-muted-foreground">
          <p>A portfolio project. Generated content can be wrong: review it before you send it.</p>
          <a className="underline underline-offset-4 hover:text-foreground" href={config.repositoryUrl}>
            Source on GitHub
          </a>
        </div>
      </footer>
      <ScrollRestoration />
    </div>
  );
}
