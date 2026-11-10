import { useQueryClient } from "@tanstack/react-query";
import { FileUp, Save, Square, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type RefObject } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Badge, Spinner } from "@/components/ui/feedback";
import { FieldHint, Input, Label, NativeSelect, Textarea } from "@/components/ui/form";
import { MarkdownResult } from "@/features/analyze/MarkdownResult";
import { QuotaNotice } from "@/features/analyze/QuotaNotice";
import { useAuth, useIdentityKey } from "@/features/auth/auth-context";
import { SaveResumeDialog } from "@/features/resumes/SaveResumeDialog";
import { api, type OcrStatus } from "@/lib/api";
import { config } from "@/lib/config";
import { ApiError, errorMessage, isAbortError } from "@/lib/errors";
import { formatBytes } from "@/lib/format";
import { queryKeys, useQuota, useResumes } from "@/lib/queries";
import { consumeEventStream, sha256File } from "@/lib/streaming";

type DocumentTarget = "resume" | "job-description";
type Action = "resume" | "cover";

const MIN_TEXT_LENGTH = 20;
const TONES = ["professional", "concise", "confident"] as const;

function ocrHint(status: OcrStatus, label: string): string {
  if (status === "used") return `OCR was used to read your scanned ${label}. Check the extracted text for mistakes.`;
  if (status === "failed") return `The uploaded ${label} looks like a scan and its text could not be read.`;
  return "";
}

/** Batches streamed text into one state update per animation frame. */
function createFrameAppender(setValue: (update: (current: string) => string) => void) {
  let pending = "";
  let frameId: number | null = null;
  const flush = () => {
    frameId = null;
    if (!pending) return;
    const text = pending;
    pending = "";
    setValue((current) => current + text);
  };
  return {
    append(text: string) {
      pending += text;
      frameId ??= requestAnimationFrame(flush);
    },
    flushNow() {
      if (frameId !== null) cancelAnimationFrame(frameId);
      flush();
    },
  };
}

interface DocumentFieldProps {
  target: DocumentTarget;
  title: string;
  textLabel: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  file: File | null;
  inputRef: RefObject<HTMLInputElement | null>;
  busy: boolean;
  disabled: boolean;
  onFile: (file: File | null) => void;
  onRemove: () => void;
}

function DocumentField({
  target,
  title,
  textLabel,
  placeholder,
  value,
  onChange,
  file,
  inputRef,
  busy,
  disabled,
  onFile,
  onRemove,
}: DocumentFieldProps) {
  const inputId = `${target}-file-input`;
  const textId = useId();
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label htmlFor={textId} className="text-base">
          {title}
        </Label>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline" size="sm" aria-disabled={disabled}>
            <label htmlFor={inputId}>
              <FileUp aria-hidden="true" />
              {file ? `Replace ${title.toLowerCase()} file` : `Upload ${title.toLowerCase()} (PDF/DOCX)`}
            </label>
          </Button>
          {file ? (
            <Button variant="ghost" size="sm" onClick={onRemove} disabled={disabled}>
              <X aria-hidden="true" /> Remove
            </Button>
          ) : null}
        </div>
      </div>
      <input
        ref={inputRef}
        id={inputId}
        className="sr-only"
        type="file"
        accept=".pdf,.docx"
        disabled={disabled}
        onChange={(event) => onFile(event.target.files?.[0] ?? null)}
      />
      {file ? <FieldHint>Using uploaded file: {file.name}</FieldHint> : null}
      <Textarea
        id={textId}
        aria-label={textLabel}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        disabled={busy}
        maxLength={60_000}
      />
    </div>
  );
}

export default function AnalyzePage() {
  const { status: authStatus, canSignIn, signIn } = useAuth();
  const signedIn = authStatus === "signedIn";
  const identity = useIdentityKey();
  const queryClient = useQueryClient();
  const quota = useQuota();
  const resumes = useResumes();

  const [resumeText, setResumeText] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [savedResumeId, setSavedResumeId] = useState("");
  const [jobDescriptionText, setJobDescriptionText] = useState("");
  const [jobDescriptionFile, setJobDescriptionFile] = useState<File | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [tone, setTone] = useState<string>("professional");
  const [resumeSuggestions, setResumeSuggestions] = useState("");
  const [coverLetter, setCoverLetter] = useState("");
  const [activeAction, setActiveAction] = useState<Action | null>(null);
  const [extractingTarget, setExtractingTarget] = useState<DocumentTarget | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState<{ message: string; limit: boolean } | null>(null);
  const [hint, setHint] = useState("");
  const [ocrStatus, setOcrStatus] = useState<OcrStatus | "">("");
  const [demoMode, setDemoMode] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);

  const documentCacheRef = useRef(new Map<string, { text: string; ocrStatus: OcrStatus }>());
  const resumeFileInputRef = useRef<HTMLInputElement | null>(null);
  const jobDescriptionFileInputRef = useRef<HTMLInputElement | null>(null);
  const extractionAbortRef = useRef<AbortController | null>(null);
  const generationAbortRef = useRef<AbortController | null>(null);
  const defaultAppliedRef = useRef(false);

  const busy = Boolean(extractingTarget) || Boolean(activeAction);
  const canSubmit = useMemo(
    () =>
      resumeText.trim().length >= MIN_TEXT_LENGTH &&
      jobDescriptionText.trim().length >= MIN_TEXT_LENGTH &&
      !extractingTarget,
    [resumeText, jobDescriptionText, extractingTarget],
  );
  const savedResumes = resumes.data?.items ?? [];
  const selectedSaved = savedResumes.find((resume) => resume.id === savedResumeId);

  useEffect(
    () => () => {
      extractionAbortRef.current?.abort();
      generationAbortRef.current?.abort();
    },
    [],
  );

  function showError(cause: unknown, fallback: string) {
    setStatusMessage("");
    setError({ message: errorMessage(cause, fallback), limit: cause instanceof ApiError && cause.isLimit });
  }

  async function loadSavedResume(id: string) {
    setSavedResumeId(id);
    if (!id) return;
    setError(null);
    setStatusMessage("Loading saved resume…");
    try {
      const resume = await queryClient.fetchQuery({
        queryKey: queryKeys.resume(identity, id),
        queryFn: ({ signal }) => api.getResume(id, signal),
        staleTime: 60_000,
      });
      setResumeText(resume.text);
      setResumeFile(null);
      setOcrStatus(resume.ocrStatus);
      setHint("");
      setStatusMessage(`Using saved resume "${resume.name}".`);
    } catch (cause) {
      setSavedResumeId("");
      showError(cause, "The saved resume could not be loaded.");
    }
  }

  // Signed-in users start with their default resume filled in.
  const defaultResumeId = savedResumes.find((resume) => resume.isDefault)?.id;
  useEffect(() => {
    if (!signedIn || defaultAppliedRef.current || !defaultResumeId || resumeText) return;
    defaultAppliedRef.current = true;
    void loadSavedResume(defaultResumeId);
    // Runs once when the default resume becomes known.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signedIn, defaultResumeId]);

  async function handleDocumentFile(file: File | null, target: DocumentTarget) {
    const isResume = target === "resume";
    const label = isResume ? "resume" : "job description";
    const Label = isResume ? "Resume" : "Job description";
    const setFile = isResume ? setResumeFile : setJobDescriptionFile;
    const setText = isResume ? setResumeText : setJobDescriptionText;
    const inputRef = isResume ? resumeFileInputRef : jobDescriptionFileInputRef;
    extractionAbortRef.current?.abort();
    setError(null);
    setHint("");
    if (isResume) setOcrStatus("");
    if (!file) return;

    if (file.size > config.maxUploadBytes) {
      clearDocumentFile(target, false);
      setError({
        message: `File is too large (${formatBytes(file.size)}). The maximum is ${formatBytes(config.maxUploadBytes)}.`,
        limit: false,
      });
      return;
    }

    const controller = new AbortController();
    extractionAbortRef.current = controller;
    setFile(file);
    setExtractingTarget(target);
    setStatusMessage(`Reading ${label}…`);

    try {
      const hash = await sha256File(file);
      let extracted = documentCacheRef.current.get(hash);
      const reused = Boolean(extracted);
      if (!extracted) {
        extracted = await api.extractDocument(target, file, controller.signal);
        documentCacheRef.current.set(hash, extracted);
      }
      setText(extracted.text);
      if (isResume) {
        setOcrStatus(extracted.ocrStatus);
        setSavedResumeId("");
      }
      setHint(ocrHint(extracted.ocrStatus, label));
      setStatusMessage(
        reused
          ? `${Label} ready (reused from this page session).`
          : `${Label} ready. Review or edit the extracted text below.`,
      );
    } catch (cause) {
      if (!isAbortError(cause)) {
        setFile(null);
        showError(cause, `${Label} extraction failed.`);
      }
    } finally {
      if (extractionAbortRef.current === controller) {
        extractionAbortRef.current = null;
        setExtractingTarget(null);
        if (inputRef.current) inputRef.current.value = "";
      }
    }
  }

  function clearDocumentFile(target: DocumentTarget, clearText = true) {
    const isResume = target === "resume";
    const inputRef = isResume ? resumeFileInputRef : jobDescriptionFileInputRef;
    extractionAbortRef.current?.abort();
    extractionAbortRef.current = null;
    if (isResume) {
      setResumeFile(null);
      if (clearText) setResumeText("");
      setOcrStatus("");
    } else {
      setJobDescriptionFile(null);
      if (clearText) setJobDescriptionText("");
    }
    setHint("");
    setStatusMessage("");
    setExtractingTarget(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function runGeneration(action: Action) {
    generationAbortRef.current?.abort();
    const controller = new AbortController();
    generationAbortRef.current = controller;
    const isResume = action === "resume";
    const setOutput = isResume ? setResumeSuggestions : setCoverLetter;
    const appender = createFrameAppender(setOutput);
    let streamedError: Error | null = null;

    setActiveAction(action);
    setOutput("");
    setError(null);
    setDemoMode(false);
    setStatusMessage(isResume ? "Preparing resume suggestions…" : "Preparing cover letter…");

    try {
      const response = await api.startGeneration(
        isResume ? "resume-suggestions" : "cover-letter",
        {
          resume_text: resumeText,
          job_description_text: jobDescriptionText,
          tone,
          ...(isResume
            ? {}
            : {
                company_name: companyName.trim() || "Target Company",
                role_title: roleTitle.trim() || "the advertised role",
              }),
        },
        controller.signal,
      );

      await consumeEventStream(response, (event, data) => {
        if (event === "status") {
          setStatusMessage(typeof data.message === "string" ? data.message : "Generating…");
          setDemoMode(Boolean(data.demo));
        } else if (event === "delta") {
          appender.append(typeof data.text === "string" ? data.text : "");
          setStatusMessage(isResume ? "Generating resume suggestions…" : "Drafting cover letter…");
        } else if (event === "done") {
          setDemoMode(Boolean(data.demo));
          setStatusMessage(isResume ? "Resume suggestions ready." : "Cover letter ready.");
        } else if (event === "error") {
          streamedError = new Error(typeof data.message === "string" ? data.message : "Generation failed.");
        }
      });
      if (streamedError) throw streamedError as Error;
    } catch (cause) {
      if (isAbortError(cause)) setStatusMessage("Generation stopped.");
      else showError(cause, "Generation failed.");
    } finally {
      appender.flushNow();
      if (generationAbortRef.current === controller) generationAbortRef.current = null;
      setActiveAction(null);
      // The allowance changed (or a limit was hit): refresh what the page shows.
      void queryClient.invalidateQueries({ queryKey: queryKeys.quota(identity) });
    }
  }

  const exhausted = quota.data ? quota.data.remaining <= 0 || !quota.data.llmAvailable : false;
  const canSaveResume = signedIn && !selectedSaved && resumeText.trim().length >= MIN_TEXT_LENGTH && !busy;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Analyze a resume</h1>
        <p className="text-pretty text-muted-foreground">
          Use your resume and a job description to get tailored suggestions or draft a cover letter.
        </p>
      </header>

      <QuotaNotice quota={quota.data} loading={quota.isPending} canSignIn={canSignIn && !signedIn} onSignIn={signIn} />

      <div className="space-y-3" aria-live="polite">
        {error ? (
          <Alert
            variant={error.limit ? "warning" : "error"}
            title={error.limit ? "Limit reached" : "Something went wrong"}
          >
            {error.message}
          </Alert>
        ) : null}
        {hint ? <Alert variant="info">{hint}</Alert> : null}
        {statusMessage ? (
          <div
            role="status"
            className="flex items-center gap-2 rounded-lg border bg-card px-4 py-3 text-sm text-card-foreground"
          >
            {busy ? <Spinner className="text-primary" /> : null}
            <span>{statusMessage}</span>
            {demoMode ? (
              <Badge variant="warning" className="ml-auto">
                Demo output
              </Badge>
            ) : null}
          </div>
        ) : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Your documents</CardTitle>
          <CardDescription>
            Uploaded files are read once and discarded. You can edit the text before generating.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {signedIn && savedResumes.length > 0 ? (
            <div className="space-y-2">
              <Label htmlFor="saved-resume">Saved resume</Label>
              <NativeSelect
                id="saved-resume"
                value={savedResumeId}
                disabled={busy}
                onChange={(event) => void loadSavedResume(event.target.value)}
              >
                <option value="">Paste or upload a different resume</option>
                {savedResumes.map((resume) => (
                  <option key={resume.id} value={resume.id}>
                    {resume.name}
                    {resume.isDefault ? " (default)" : ""}
                  </option>
                ))}
              </NativeSelect>
            </div>
          ) : null}

          <DocumentField
            target="resume"
            title="Resume"
            textLabel="Resume text"
            placeholder="Paste resume text, or upload a PDF/DOCX to extract it"
            value={resumeText}
            onChange={(value) => {
              setResumeText(value);
              setSavedResumeId("");
            }}
            file={resumeFile}
            inputRef={resumeFileInputRef}
            busy={Boolean(extractingTarget)}
            disabled={busy}
            onFile={(file) => void handleDocumentFile(file, "resume")}
            onRemove={() => clearDocumentFile("resume")}
          />
          {canSaveResume ? (
            <Button variant="secondary" size="sm" onClick={() => setSaveOpen(true)}>
              <Save aria-hidden="true" /> Save to my resumes
            </Button>
          ) : null}

          <DocumentField
            target="job-description"
            title="Job description"
            textLabel="Job description"
            placeholder="Paste job description text, or upload a PDF/DOCX to extract it"
            value={jobDescriptionText}
            onChange={setJobDescriptionText}
            file={jobDescriptionFile}
            inputRef={jobDescriptionFileInputRef}
            busy={Boolean(extractingTarget)}
            disabled={busy}
            onFile={(file) => void handleDocumentFile(file, "job-description")}
            onRemove={() => clearDocumentFile("job-description")}
          />

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="tone">Tone</Label>
              <NativeSelect id="tone" value={tone} onChange={(event) => setTone(event.target.value)}>
                {TONES.map((value) => (
                  <option key={value} value={value}>
                    {value.charAt(0).toUpperCase() + value.slice(1)}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <Label htmlFor="company">Company (for the cover letter)</Label>
              <Input
                id="company"
                value={companyName}
                maxLength={200}
                autoComplete="off"
                placeholder="Optional"
                onChange={(event) => setCompanyName(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">Role (for the cover letter)</Label>
              <Input
                id="role"
                value={roleTitle}
                maxLength={200}
                autoComplete="off"
                placeholder="Optional"
                onChange={(event) => setRoleTitle(event.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <Button
              disabled={!canSubmit || Boolean(activeAction) || exhausted}
              onClick={() => void runGeneration("resume")}
            >
              {activeAction === "resume" ? "Generating suggestions…" : "Get Resume Suggestions"}
            </Button>
            <Button
              variant="secondary"
              disabled={!canSubmit || Boolean(activeAction) || exhausted}
              onClick={() => void runGeneration("cover")}
            >
              {activeAction === "cover" ? "Drafting cover letter…" : "Generate Cover Letter"}
            </Button>
            {activeAction ? (
              <Button variant="destructive" onClick={() => generationAbortRef.current?.abort()}>
                <Square aria-hidden="true" /> Stop
              </Button>
            ) : null}
          </div>
          {!canSubmit && !extractingTarget ? (
            <FieldHint>
              Add at least {MIN_TEXT_LENGTH} characters of resume and job description text to continue.
            </FieldHint>
          ) : null}
        </CardContent>
      </Card>

      {resumeSuggestions ? (
        <MarkdownResult
          title="Resume Suggestions"
          value={resumeSuggestions}
          busy={activeAction === "resume"}
          ocrStatus={ocrStatus}
        />
      ) : null}
      {coverLetter ? (
        <MarkdownResult
          title="Cover Letter"
          value={coverLetter}
          busy={activeAction === "cover"}
          ocrStatus={ocrStatus}
        />
      ) : null}

      <SaveResumeDialog
        open={saveOpen}
        onOpenChange={setSaveOpen}
        text={resumeText}
        sourceFilename={resumeFile?.name ?? null}
        ocrStatus={ocrStatus || "not_used"}
        suggestedName={resumeFile?.name.replace(/\.(pdf|docx)$/i, "") ?? ""}
        onSaved={(resume) => {
          setSavedResumeId(resume.id);
          toast.success(`Saved "${resume.name}" to your resumes.`);
        }}
      />
    </div>
  );
}
