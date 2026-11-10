import { Label as LabelPrimitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const fieldClasses =
  "w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs transition-colors placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-destructive";

function Label({ className, ...props }: ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root data-slot="label" className={cn("text-sm leading-none font-medium", className)} {...props} />
  );
}

function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return <input data-slot="input" type={type} className={cn(fieldClasses, "h-10", className)} {...props} />;
}

function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea data-slot="textarea" className={cn(fieldClasses, "min-h-40 resize-y py-2", className)} {...props} />;
}

/** A styled native select: fully keyboard and screen-reader accessible with no extra code. */
function NativeSelect({ className, ...props }: ComponentProps<"select">) {
  return <select data-slot="select" className={cn(fieldClasses, "h-10 pr-8", className)} {...props} />;
}

function FieldHint({ className, ...props }: ComponentProps<"p">) {
  return <p className={cn("text-xs text-muted-foreground", className)} {...props} />;
}

function FieldError({ className, ...props }: ComponentProps<"p">) {
  return <p role="alert" className={cn("text-sm text-destructive", className)} {...props} />;
}

export { FieldError, FieldHint, Input, Label, NativeSelect, Textarea };
