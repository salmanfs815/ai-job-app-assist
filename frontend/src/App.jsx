import { useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { consumeEventStream, sha256File } from "./streaming";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const MAX_UPLOAD_BYTES = Number(import.meta.env.VITE_MAX_UPLOAD_BYTES || "5242880");

export default function App() {
  const [resumeText, setResumeText] = useState("");
  const [resumeFile, setResumeFile] = useState(null);
  const [jobDescriptionText, setJobDescriptionText] = useState("");
  const [jobDescriptionFile, setJobDescriptionFile] = useState(null);
  const [tone, setTone] = useState("professional");
  const [resumeSuggestions, setResumeSuggestions] = useState("");
  const [coverLetter, setCoverLetter] = useState("");
  const [activeAction, setActiveAction] = useState(null);
  const [extractingTarget, setExtractingTarget] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [ocrHint, setOcrHint] = useState("");
  const [ocrStatus, setOcrStatus] = useState("");
  const [demoMode, setDemoMode] = useState(false);

  const documentCacheRef = useRef(new Map());
  const resumeFileInputRef = useRef(null);
  const jobDescriptionFileInputRef = useRef(null);
  const extractionAbortRef = useRef(null);
  const generationAbortRef = useRef(null);

  const canSubmit = useMemo(
    () => resumeText.trim().length > 20 && jobDescriptionText.trim().length > 20 && !extractingTarget,
    [resumeText, jobDescriptionText, extractingTarget]
  );

  async function handleDocumentFile(file, target) {
    const isResume = target === "resume";
    const label = isResume ? "resume" : "job description";
    const setFile = isResume ? setResumeFile : setJobDescriptionFile;
    const setText = isResume ? setResumeText : setJobDescriptionText;
    const inputRef = isResume ? resumeFileInputRef : jobDescriptionFileInputRef;
    extractionAbortRef.current?.abort();
    setErrorMessage("");
    setOcrHint("");
    if (isResume) setOcrStatus("");

    if (!file) return;
    const fileError = validateFileSize(file);
    if (fileError) {
      clearDocumentFile(target, false);
      setErrorMessage(fileError);
      return;
    }

    const controller = new AbortController();
    extractionAbortRef.current = controller;
    setFile(file);
    setExtractingTarget(target);
    setStatusMessage(`Reading ${label}…`);

    try {
      const hash = await sha256File(file);
      const cached = documentCacheRef.current.get(hash);
      if (cached) {
        setText(cached.text);
        if (isResume) setOcrStatus(cached.ocrStatus);
        setOcrHint(buildOcrHint(cached.ocrStatus, label));
        setStatusMessage(`${isResume ? "Resume" : "Job description"} ready (reused from this page session).`);
        return;
      }

      const formData = new FormData();
      formData.append(isResume ? "resume_file" : "job_description_file", file);
      const endpoint = isResume ? "/resume/extract" : "/job-description/extract";
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(await extractApiError(response, `${isResume ? "Resume" : "Job description"} extraction failed`));

      const data = await response.json();
      const extractedText = isResume ? data.resume_text : data.job_description_text;
      documentCacheRef.current.set(hash, { text: extractedText, ocrStatus: data.ocr_status });
      setText(extractedText);
      if (isResume) setOcrStatus(data.ocr_status);
      setOcrHint(buildOcrHint(data.ocr_status, label));
      setStatusMessage(`${isResume ? "Resume" : "Job description"} ready. Review or edit the extracted text below.`);
    } catch (error) {
      if (error.name !== "AbortError") {
        setFile(null);
        setStatusMessage("");
        setErrorMessage(error.message || `${isResume ? "Resume" : "Job description"} extraction failed`);
      }
    } finally {
      if (extractionAbortRef.current === controller) {
        extractionAbortRef.current = null;
        setExtractingTarget(null);
        if (inputRef.current) inputRef.current.value = "";
      }
    }
  }

  function clearDocumentFile(target, clearText = true) {
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
    setOcrHint("");
    setStatusMessage("");
    setExtractingTarget(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  function createFrameAppender(setValue) {
    let pending = "";
    let frameId = null;
    function flush() {
      frameId = null;
      if (!pending) return;
      const text = pending;
      pending = "";
      setValue((current) => current + text);
    }
    return {
      append(text) {
        pending += text;
        if (frameId === null) frameId = requestAnimationFrame(flush);
      },
      flushNow() {
        if (frameId !== null) cancelAnimationFrame(frameId);
        flush();
      },
    };
  }

  async function runGeneration(action) {
    generationAbortRef.current?.abort();
    const controller = new AbortController();
    generationAbortRef.current = controller;
    const isResume = action === "resume";
    const setOutput = isResume ? setResumeSuggestions : setCoverLetter;
    const appender = createFrameAppender(setOutput);
    let streamedError = null;

    setActiveAction(action);
    setOutput("");
    setErrorMessage("");
    setDemoMode(false);
    setStatusMessage(isResume ? "Preparing resume suggestions…" : "Preparing cover letter…");

    const url = isResume ? "/generate/resume-suggestions" : "/generate/cover-letter";
    const body = {
      resume_text: resumeText,
      job_description_text: jobDescriptionText,
      tone,
      ...(isResume ? {} : { company_name: "Target Company", role_title: "Software Engineer" }),
    };

    try {
      const response = await fetch(`${API_BASE}${url}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(await extractApiError(response, "Generation failed"));

      await consumeEventStream(response, (event, data) => {
        if (event === "status") {
          setStatusMessage(data.message || "Generating…");
          setDemoMode(Boolean(data.demo));
        } else if (event === "delta") {
          appender.append(data.text || "");
          setStatusMessage(isResume ? "Generating resume suggestions…" : "Drafting cover letter…");
        } else if (event === "done") {
          setDemoMode(Boolean(data.demo));
          setStatusMessage(isResume ? "Resume suggestions ready." : "Cover letter ready.");
        } else if (event === "error") {
          streamedError = new Error(data.message || "Generation failed");
        }
      });
      if (streamedError) throw streamedError;
    } catch (error) {
      if (error.name === "AbortError") {
        setStatusMessage("Generation stopped.");
      } else {
        setStatusMessage("");
        setErrorMessage(error.message || "Request failed");
      }
    } finally {
      appender.flushNow();
      if (generationAbortRef.current === controller) generationAbortRef.current = null;
      setActiveAction(null);
    }
  }

  return (
    <div className="container">
      <h1>AI Job Application Assistant</h1>
      <p>Use your resume and a job description to get tailored suggestions or draft a cover letter.</p>

      {errorMessage && <div className="error-box" role="alert">{errorMessage}</div>}
      {ocrHint && <div className="hint-box">{ocrHint}</div>}
      {statusMessage && (
        <div className="status-box" role="status" aria-live="polite">
          {(extractingTarget || activeAction) && <span className="spinner" aria-hidden="true" />}
          <span>{statusMessage}</span>
          {demoMode && <span className="demo-badge">Demo output</span>}
        </div>
      )}

      <label>Resume</label>
      <div className="file-controls">
        <label htmlFor="resume-file-input" className="file-upload-btn">
          {resumeFile ? "Replace Resume" : "Upload Resume (PDF/DOCX)"}
        </label>
        {resumeFile && (
          <button type="button" className="secondary-btn" onClick={() => clearDocumentFile("resume")} disabled={!!extractingTarget || !!activeAction}>
            Remove
          </button>
        )}
      </div>
      <input
        ref={resumeFileInputRef}
        id="resume-file-input"
        className="file-input-hidden"
        type="file"
        accept=".pdf,.docx"
        disabled={!!extractingTarget || !!activeAction}
        onChange={(event) => handleDocumentFile(event.target.files?.[0] || null, "resume")}
      />
      {resumeFile && <p className="file-name">Using uploaded file: {resumeFile.name}</p>}
      <textarea
        aria-label="Resume text"
        value={resumeText}
        onChange={(event) => setResumeText(event.target.value)}
        placeholder="Paste resume text, or upload a PDF/DOCX to extract it"
        disabled={!!extractingTarget}
      />

      <label>Job Description</label>
      <div className="file-controls">
        <label htmlFor="job-description-file-input" className="file-upload-btn">
          {jobDescriptionFile ? "Replace Job Description" : "Upload Job Description (PDF/DOCX)"}
        </label>
        {jobDescriptionFile && (
          <button type="button" className="secondary-btn" onClick={() => clearDocumentFile("job-description")} disabled={!!extractingTarget || !!activeAction}>
            Remove
          </button>
        )}
      </div>
      <input
        ref={jobDescriptionFileInputRef}
        id="job-description-file-input"
        className="file-input-hidden"
        type="file"
        accept=".pdf,.docx"
        disabled={!!extractingTarget || !!activeAction}
        onChange={(event) => handleDocumentFile(event.target.files?.[0] || null, "job-description")}
      />
      {jobDescriptionFile && <p className="file-name">Using uploaded file: {jobDescriptionFile.name}</p>}
      <textarea
        aria-label="Job description"
        value={jobDescriptionText}
        onChange={(event) => setJobDescriptionText(event.target.value)}
        placeholder="Paste job description text, or upload a PDF/DOCX to extract it"
        disabled={!!extractingTarget}
      />

      <label>Tone</label>
      <select value={tone} onChange={(event) => setTone(event.target.value)}>
        <option value="professional">Professional</option>
        <option value="concise">Concise</option>
        <option value="confident">Confident</option>
      </select>

      <div className="row">
        <button disabled={!canSubmit || !!activeAction} onClick={() => runGeneration("resume")}>
          {activeAction === "resume" ? "Generating suggestions…" : "Get Resume Suggestions"}
        </button>
        <button disabled={!canSubmit || !!activeAction} onClick={() => runGeneration("cover")}>
          {activeAction === "cover" ? "Drafting cover letter…" : "Generate Cover Letter"}
        </button>
        {activeAction && <button type="button" className="stop-btn" onClick={() => generationAbortRef.current?.abort()}>Stop</button>}
      </div>

      {resumeSuggestions && (
        <MarkdownResult title="Resume Suggestions" value={resumeSuggestions} busy={activeAction === "resume"} ocrStatus={ocrStatus} />
      )}
      {coverLetter && (
        <MarkdownResult title="Cover Letter" value={coverLetter} busy={activeAction === "cover"} ocrStatus={ocrStatus} />
      )}
    </div>
  );
}

function MarkdownResult({ title, value, busy, ocrStatus }) {
  return (
    <section aria-busy={busy}>
      <h2>{title}</h2>
      {getOcrBadgeLabel(ocrStatus) && (
        <span className={`ocr-badge ocr-badge-${ocrStatus}`}>{getOcrBadgeLabel(ocrStatus)}</span>
      )}
      <div className="markdown-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{ a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" /> }}
        >
          {value}
        </ReactMarkdown>
        {busy && <span className="stream-cursor" aria-hidden="true" />}
      </div>
    </section>
  );
}

async function extractApiError(response, fallback) {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string" && data.detail.trim()) return data.detail;
    if (Array.isArray(data?.detail) && data.detail.length > 0) {
      return data.detail.map((detail) => detail?.msg || JSON.stringify(detail)).join("; ");
    }
  } catch (_error) {
    // Use the caller's fallback for non-JSON errors.
  }
  return fallback;
}

function validateFileSize(file) {
  if (!file) return "";
  if (file.size > MAX_UPLOAD_BYTES) {
    return `File is too large (${formatBytes(file.size)}). Max allowed is ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  }
  return "";
}

function buildOcrHint(status, label) {
  if (status === "used") return `OCR fallback was used to extract text from your scanned PDF ${label}.`;
  if (status === "failed") return `OCR fallback could not extract enough text from the uploaded ${label}.`;
  return "";
}

function getOcrBadgeLabel(status) {
  if (status === "used") return "OCR used";
  if (status === "failed") return "OCR failed";
  if (status === "not_used") return "OCR not needed";
  return "";
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
