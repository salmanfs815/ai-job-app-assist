import { useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/feedback";
import { FieldError, FieldHint, Input, Label } from "@/components/ui/form";
import type { OcrStatus, ResumeDetail } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { formatCount } from "@/lib/format";
import { useCreateResume } from "@/lib/queries";

interface SaveResumeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  text: string;
  sourceFilename: string | null;
  ocrStatus: OcrStatus;
  suggestedName: string;
  onSaved: (resume: ResumeDetail) => void;
}

/** Mounted only while the dialog is open, so every opening starts from a clean form. */
function SaveResumeForm(props: SaveResumeDialogProps) {
  const nameId = useId();
  const defaultId = useId();
  const [name, setName] = useState(props.suggestedName);
  const [makeDefault, setMakeDefault] = useState(false);
  const create = useCreateResume();

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      { name, text: props.text, sourceFilename: props.sourceFilename, ocrStatus: props.ocrStatus, makeDefault },
      {
        onSuccess: (resume) => {
          props.onOpenChange(false);
          props.onSaved(resume);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>Save resume</DialogTitle>
        <DialogDescription>
          Saves the extracted text ({formatCount(props.text.trim().length, "character")}) so you can reuse it. The
          uploaded file itself is not stored.
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-2">
        <Label htmlFor={nameId}>Name</Label>
        <Input
          id={nameId}
          value={name}
          maxLength={120}
          required
          autoComplete="off"
          placeholder="For example: Backend engineer"
          aria-invalid={create.isError}
          onChange={(event) => setName(event.target.value)}
        />
        <FieldHint>A label only you see, to tell your resumes apart.</FieldHint>
      </div>
      <div className="flex items-center gap-2">
        <input
          id={defaultId}
          type="checkbox"
          className="size-4 accent-primary"
          checked={makeDefault}
          onChange={(event) => setMakeDefault(event.target.checked)}
        />
        <Label htmlFor={defaultId}>Use as my default resume</Label>
      </div>
      {create.isError ? <FieldError>{errorMessage(create.error)}</FieldError> : null}
      <DialogFooter>
        <Button variant="outline" onClick={() => props.onOpenChange(false)}>
          Cancel
        </Button>
        <Button type="submit" disabled={create.isPending || !name.trim()}>
          {create.isPending ? <Spinner /> : null}
          Save resume
        </Button>
      </DialogFooter>
    </form>
  );
}

/** Names and saves already-extracted resume text. The original file is never uploaded for storage. */
export function SaveResumeDialog(props: SaveResumeDialogProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent>
        <SaveResumeForm {...props} />
      </DialogContent>
    </Dialog>
  );
}
