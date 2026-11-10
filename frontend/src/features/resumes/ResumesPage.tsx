import { FileText, FileUp, Pencil, Star, Trash2 } from "lucide-react";
import { useId, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Alert, Badge, EmptyState, Skeleton, Spinner } from "@/components/ui/feedback";
import { FieldError, Input, Label } from "@/components/ui/form";
import { SaveResumeDialog } from "@/features/resumes/SaveResumeDialog";
import { api, type ExtractedDocument, type ResumeSummary } from "@/lib/api";
import { config } from "@/lib/config";
import { errorMessage } from "@/lib/errors";
import { formatBytes, formatCount, formatDate } from "@/lib/format";
import { useDeleteResume, useResumes, useUpdateResume } from "@/lib/queries";

function RenameDialog({ resume, onClose }: { resume: ResumeSummary | null; onClose: () => void }) {
  const inputId = useId();
  const [name, setName] = useState("");
  const update = useUpdateResume();
  const [seenId, setSeenId] = useState<string | null>(null);

  // Reset the field whenever a different resume is opened.
  if (resume && resume.id !== seenId) {
    setSeenId(resume.id);
    setName(resume.name);
    update.reset();
  }
  if (!resume && seenId !== null) setSeenId(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!resume) return;
    update.mutate(
      { id: resume.id, name },
      {
        onSuccess: () => {
          toast.success("Resume renamed.");
          onClose();
        },
      },
    );
  }

  return (
    <Dialog open={Boolean(resume)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Rename resume</DialogTitle>
            <DialogDescription>Choose a name that tells this version apart from the others.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor={inputId}>Name</Label>
            <Input
              id={inputId}
              value={name}
              maxLength={120}
              required
              autoComplete="off"
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          {update.isError ? <FieldError>{errorMessage(update.error)}</FieldError> : null}
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending || !name.trim()}>
              {update.isPending ? <Spinner /> : null}
              Save name
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function DeleteDialog({ resume, onClose }: { resume: ResumeSummary | null; onClose: () => void }) {
  const remove = useDeleteResume();

  function confirm() {
    if (!resume) return;
    remove.mutate(resume.id, {
      onSuccess: () => {
        toast.success(`Deleted "${resume.name}".`);
        onClose();
      },
    });
  }

  return (
    <Dialog
      open={Boolean(resume)}
      onOpenChange={(open) => {
        if (!open) {
          remove.reset();
          onClose();
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete this resume?</DialogTitle>
          <DialogDescription>
            &ldquo;{resume?.name}&rdquo; will be permanently deleted. This cannot be undone.
            {resume?.isDefault ? " Your most recently updated resume will become the default." : ""}
          </DialogDescription>
        </DialogHeader>
        {remove.isError ? <FieldError>{errorMessage(remove.error)}</FieldError> : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Keep it
          </Button>
          <Button variant="destructive" onClick={confirm} disabled={remove.isPending}>
            {remove.isPending ? <Spinner /> : <Trash2 aria-hidden="true" />}
            Delete resume
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResumeCard({
  resume,
  onRename,
  onDelete,
}: {
  resume: ResumeSummary;
  onRename: () => void;
  onDelete: () => void;
}) {
  const update = useUpdateResume();
  return (
    <li className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-center sm:p-5">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="truncate font-semibold">{resume.name}</h2>
          {resume.isDefault ? (
            <Badge variant="success">
              <Star aria-hidden="true" className="size-3" /> Default
            </Badge>
          ) : null}
          {resume.ocrStatus === "used" ? <Badge variant="outline">Read with OCR</Badge> : null}
        </div>
        <p className="text-sm text-muted-foreground">
          {formatCount(resume.charCount, "character")} · updated {formatDate(resume.updatedAt)}
          {resume.sourceFilename ? ` · from ${resume.sourceFilename}` : ""}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {!resume.isDefault ? (
          <Button
            variant="outline"
            size="sm"
            disabled={update.isPending}
            aria-label={`Make ${resume.name} the default resume`}
            onClick={() =>
              update.mutate(
                { id: resume.id, isDefault: true },
                {
                  onSuccess: () => toast.success(`"${resume.name}" is now your default resume.`),
                  onError: (error) => toast.error(errorMessage(error)),
                },
              )
            }
          >
            <Star aria-hidden="true" /> Make default
          </Button>
        ) : null}
        <Button variant="outline" size="sm" onClick={onRename} aria-label={`Rename ${resume.name}`}>
          <Pencil aria-hidden="true" /> Rename
        </Button>
        <Button variant="outline" size="sm" onClick={onDelete} aria-label={`Delete ${resume.name}`}>
          <Trash2 aria-hidden="true" /> Delete
        </Button>
      </div>
    </li>
  );
}

export default function ResumesPage() {
  const resumes = useResumes();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [upload, setUpload] = useState<(ExtractedDocument & { filename: string }) | null>(null);
  const [renaming, setRenaming] = useState<ResumeSummary | null>(null);
  const [deleting, setDeleting] = useState<ResumeSummary | null>(null);

  async function handleFile(file: File | null) {
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (!file) return;
    setUploadError("");
    if (file.size > config.maxUploadBytes) {
      setUploadError(
        `File is too large (${formatBytes(file.size)}). The maximum is ${formatBytes(config.maxUploadBytes)}.`,
      );
      return;
    }
    setExtracting(true);
    try {
      const extracted = await api.extractDocument("resume", file);
      setUpload({ ...extracted, filename: file.name });
    } catch (error) {
      setUploadError(errorMessage(error, "The resume could not be read."));
    } finally {
      setExtracting(false);
    }
  }

  const items = resumes.data?.items ?? [];
  const uploadButton = (
    <Button asChild aria-disabled={extracting}>
      <label htmlFor="new-resume-file">
        {extracting ? <Spinner /> : <FileUp aria-hidden="true" />}
        {extracting ? "Reading resume…" : "Upload a resume (PDF/DOCX)"}
      </label>
    </Button>
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Saved resumes</h1>
          <p className="text-pretty text-muted-foreground">
            Keep the versions you reuse. Only extracted text is stored, never the uploaded file.
          </p>
        </div>
        {items.length > 0 ? uploadButton : null}
      </header>

      <input
        ref={fileInputRef}
        id="new-resume-file"
        type="file"
        accept=".pdf,.docx"
        className="sr-only"
        disabled={extracting}
        onChange={(event) => void handleFile(event.target.files?.[0] ?? null)}
      />

      {uploadError ? (
        <Alert variant="error" title="Upload failed">
          {uploadError}
        </Alert>
      ) : null}

      {resumes.isPending ? (
        <div className="space-y-3" role="status" aria-label="Loading resumes">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : resumes.isError ? (
        <Alert
          variant="error"
          title="Your resumes could not be loaded"
          action={
            <Button size="sm" variant="outline" onClick={() => void resumes.refetch()}>
              Try again
            </Button>
          }
        >
          {errorMessage(resumes.error)}
        </Alert>
      ) : items.length === 0 ? (
        <EmptyState icon={<FileText aria-hidden="true" />} title="No saved resumes yet" action={uploadButton}>
          Upload a PDF or DOCX to save its text here. The first resume you save becomes your default and is filled in
          automatically on the Analyze page.
        </EmptyState>
      ) : (
        <ul className="space-y-3" aria-label="Saved resumes">
          {items.map((resume) => (
            <ResumeCard
              key={resume.id}
              resume={resume}
              onRename={() => setRenaming(resume)}
              onDelete={() => setDeleting(resume)}
            />
          ))}
        </ul>
      )}

      <SaveResumeDialog
        open={Boolean(upload)}
        onOpenChange={(open) => !open && setUpload(null)}
        text={upload?.text ?? ""}
        sourceFilename={upload?.filename ?? null}
        ocrStatus={upload?.ocrStatus ?? "not_used"}
        suggestedName={upload?.filename.replace(/\.(pdf|docx)$/i, "") ?? ""}
        onSaved={(resume) => toast.success(`Saved "${resume.name}".`)}
      />
      <RenameDialog resume={renaming} onClose={() => setRenaming(null)} />
      <DeleteDialog resume={deleting} onClose={() => setDeleting(null)} />
    </div>
  );
}
