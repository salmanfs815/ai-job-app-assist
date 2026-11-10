import { cva, type VariantProps } from "class-variance-authority";
import { CircleAlert, Info, LoaderCircle, TriangleAlert } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      default: "border-transparent bg-primary text-primary-foreground",
      secondary: "border-transparent bg-secondary text-secondary-foreground",
      outline: "text-foreground",
      success: "border-success/40 bg-success/10 text-success",
      warning: "border-warning/40 bg-warning/10 text-warning",
    },
  },
  defaultVariants: { variant: "secondary" },
});

function Badge({ className, variant, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}

const alertVariants = cva("flex gap-3 rounded-lg border p-4 text-sm [&>svg]:mt-0.5 [&>svg]:size-4 [&>svg]:shrink-0", {
  variants: {
    variant: {
      info: "border-primary/30 bg-accent text-accent-foreground",
      warning: "border-warning/40 bg-warning/10 text-foreground [&>svg]:text-warning",
      error: "border-destructive/40 bg-destructive/10 text-foreground [&>svg]:text-destructive",
    },
  },
  defaultVariants: { variant: "info" },
});

const alertIcons = { info: Info, warning: TriangleAlert, error: CircleAlert } as const;

type AlertProps = Omit<ComponentProps<"div">, "title"> &
  VariantProps<typeof alertVariants> & { title?: ReactNode; action?: ReactNode };

/** Errors use role="alert" (announced immediately); other messages use role="status". */
function Alert({ className, variant = "info", title, action, children, ...props }: AlertProps) {
  const Icon = alertIcons[variant ?? "info"];
  return (
    <div
      data-slot="alert"
      role={variant === "error" ? "alert" : "status"}
      className={cn(alertVariants({ variant }), className)}
      {...props}
    >
      <Icon aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-1">
        {title ? <p className="leading-tight font-medium">{title}</p> : null}
        <div className="text-pretty">{children}</div>
        {action ? <div className="pt-2">{action}</div> : null}
      </div>
    </div>
  );
}

function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden="true"
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <>
      <LoaderCircle aria-hidden="true" className={cn("size-4 animate-spin", className)} />
      {label ? <span className="sr-only">{label}</span> : null}
    </>
  );
}

function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center">
      {icon ? (
        <div className="flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground [&_svg]:size-6">
          {icon}
        </div>
      ) : null}
      <h2 className="text-lg font-semibold">{title}</h2>
      {children ? <p className="max-w-md text-sm text-pretty text-muted-foreground">{children}</p> : null}
      {action ? <div className="pt-2">{action}</div> : null}
    </div>
  );
}

export { Alert, Badge, EmptyState, Skeleton, Spinner };
