import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Monitor, Moon, Sun, Trash2 } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { useTheme, type Theme } from "@/app/theme";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Alert, Skeleton, Spinner } from "@/components/ui/feedback";
import { FieldError, Input, Label } from "@/components/ui/form";
import { useAuth } from "@/features/auth/auth-context";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { formatDate, formatTime } from "@/lib/format";
import { useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";

const THEMES: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

const CONFIRM_WORD = "DELETE";

function DeleteAccountDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const inputId = useId();
  const { signOut } = useAuth();
  const queryClient = useQueryClient();
  const [confirmation, setConfirmation] = useState("");
  const remove = useMutation({
    mutationFn: api.deleteAccount,
    onSuccess: async () => {
      queryClient.clear();
      toast.success("Your account and saved data were deleted.");
      await signOut();
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (confirmation === CONFIRM_WORD) remove.mutate();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setConfirmation("");
          remove.reset();
        }
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Delete your account?</DialogTitle>
            <DialogDescription>
              This permanently deletes your saved resumes, generated results and usage history, then signs you out. It
              cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor={inputId}>Type {CONFIRM_WORD} to confirm</Label>
            <Input
              id={inputId}
              value={confirmation}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </div>
          {remove.isError ? <FieldError>{errorMessage(remove.error)}</FieldError> : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Keep my account
            </Button>
            <Button type="submit" variant="destructive" disabled={confirmation !== CONFIRM_WORD || remove.isPending}>
              {remove.isPending ? <Spinner /> : <Trash2 aria-hidden="true" />}
              Delete account
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-2 sm:flex-row sm:gap-4">
      <dt className="w-40 shrink-0 text-sm text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm break-words">{children}</dd>
    </div>
  );
}

export default function SettingsPage() {
  const { user, mode } = useAuth();
  const me = useMe();
  const { theme, setTheme } = useTheme();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const quota = me.data?.quota;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Settings</h1>
        <p className="text-muted-foreground">Your account, today&apos;s usage and how the app looks.</p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>
            {mode === "dev"
              ? "Local development sign-in. No real identity provider is involved."
              : "You sign in with Microsoft Entra External ID. Your password is never seen by this app."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {me.isPending ? (
            <div className="space-y-2" role="status" aria-label="Loading account">
              <Skeleton className="h-5 w-56" />
              <Skeleton className="h-5 w-72" />
            </div>
          ) : me.isError ? (
            <Alert
              variant="error"
              title="Your account could not be loaded"
              action={
                <Button size="sm" variant="outline" onClick={() => void me.refetch()}>
                  Try again
                </Button>
              }
            >
              {errorMessage(me.error)}
            </Alert>
          ) : (
            <dl className="divide-y">
              <Row label="Name">{me.data.displayName ?? user?.name ?? "Not provided"}</Row>
              <Row label="Email">{me.data.email ?? user?.email ?? "Not provided"}</Row>
              <Row label="Member since">{formatDate(me.data.createdAt)}</Row>
              {me.data.roles.length > 0 ? <Row label="Roles">{me.data.roles.join(", ")}</Row> : null}
            </dl>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Today&apos;s usage</CardTitle>
          <CardDescription>Generations are limited per day to keep this demo free to run.</CardDescription>
        </CardHeader>
        <CardContent>
          {quota ? (
            <div className="space-y-3">
              <p className="text-sm">
                <span className="text-2xl font-semibold">{quota.used}</span>
                <span className="text-muted-foreground"> of {quota.limit} generations used</span>
              </p>
              <div
                role="progressbar"
                aria-label="Generations used today"
                aria-valuemin={0}
                aria-valuemax={quota.limit}
                aria-valuenow={Math.min(quota.used, quota.limit)}
                className="h-2 overflow-hidden rounded-full bg-muted"
              >
                <div
                  className={cn("h-full rounded-full", quota.remaining > 0 ? "bg-primary" : "bg-warning")}
                  style={{ width: `${quota.limit > 0 ? Math.min(100, (quota.used / quota.limit) * 100) : 100}%` }}
                />
              </div>
              <p className="text-sm text-muted-foreground">
                Resets at {formatTime(quota.resetsAt)} (midnight UTC).
                {quota.llmAvailable ? "" : " Generation is paused: the demo has reached its AI budget for today."}
              </p>
            </div>
          ) : (
            <Skeleton className="h-16 w-full" />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>Choose a theme. &ldquo;System&rdquo; follows your device setting.</CardDescription>
        </CardHeader>
        <CardContent>
          <div role="radiogroup" aria-label="Theme" className="flex flex-wrap gap-2">
            {THEMES.map(({ value, label, icon: Icon }) => (
              <Button
                key={value}
                role="radio"
                aria-checked={theme === value}
                variant={theme === value ? "default" : "outline"}
                onClick={() => setTheme(value)}
              >
                <Icon aria-hidden="true" /> {label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle>Delete account</CardTitle>
          <CardDescription>
            Permanently removes your saved resumes, generated results and usage history from this app.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
            <Trash2 aria-hidden="true" /> Delete my account
          </Button>
        </CardContent>
      </Card>

      <DeleteAccountDialog open={deleteOpen} onOpenChange={setDeleteOpen} />
    </div>
  );
}
