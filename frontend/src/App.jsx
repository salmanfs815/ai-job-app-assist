import { useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const MAX_UPLOAD_BYTES = Number(import.meta.env.VITE_MAX_UPLOAD_BYTES || "5242880");

export default function App() {
  const [resumeText, setResumeText] = useState("");
  const [resumeFile, setResumeFile] = useState(null);
  const [jobDescriptionText, setJobDescriptionText] = useState("");
  const [tone, setTone] = useState("professional");
  const [result, setResult] = useState(null);
  const [coverLetter, setCoverLetter] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [ocrHint, setOcrHint] = useState("");
  const [ocrStatus, setOcrStatus] = useState("");

  const canSubmit = useMemo(
    () =>
      (resumeText.trim().length > 20 || !!resumeFile) &&
      jobDescriptionText.trim().length > 20,
    [resumeText, resumeFile, jobDescriptionText]
  );

  async function handleAnalyze() {
    setLoading(true);
    setResult(null);
    setErrorMessage("");
    setOcrHint("");
    setOcrStatus("");
    try {
      let res;
      if (resumeFile) {
        const fileError = validateFileSize(resumeFile);
        if (fileError) throw new Error(fileError);
        const formData = new FormData();
        formData.append("resume_file", resumeFile);
        formData.append("job_description_text", jobDescriptionText);
        formData.append("tone", tone);
        if (resumeText.trim()) formData.append("resume_text", resumeText);
        res = await fetch(`${API_BASE}/analyze-upload`, {
          method: "POST",
          body: formData,
        });
      } else {
        res = await fetch(`${API_BASE}/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            resume_text: resumeText,
            job_description_text: jobDescriptionText,
            tone,
          }),
        });
      }

      if (!res.ok) throw new Error(await extractApiError(res, "Analysis failed"));
      const status = getOcrStatus(res);
      setOcrStatus(status);
      setOcrHint(buildOcrHint(status));
      setResult(await res.json());
    } catch (err) {
      setErrorMessage(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleCoverLetter() {
    setLoading(true);
    setCoverLetter("");
    setErrorMessage("");
    setOcrHint("");
    setOcrStatus("");
    try {
      let res;
      if (resumeFile) {
        const fileError = validateFileSize(resumeFile);
        if (fileError) throw new Error(fileError);
        const formData = new FormData();
        formData.append("resume_file", resumeFile);
        formData.append("job_description_text", jobDescriptionText);
        formData.append("company_name", "Target Company");
        formData.append("role_title", "Software Engineer");
        formData.append("tone", tone);
        if (resumeText.trim()) formData.append("resume_text", resumeText);
        res = await fetch(`${API_BASE}/cover-letter-upload`, {
          method: "POST",
          body: formData,
        });
      } else {
        res = await fetch(`${API_BASE}/cover-letter`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            resume_text: resumeText,
            job_description_text: jobDescriptionText,
            company_name: "Target Company",
            role_title: "Software Engineer",
            tone,
          }),
        });
      }

      if (!res.ok) throw new Error(await extractApiError(res, "Cover letter generation failed"));
      const status = getOcrStatus(res);
      setOcrStatus(status);
      setOcrHint(buildOcrHint(status));
      const data = await res.json();
      setCoverLetter(data.cover_letter);
    } catch (err) {
      setErrorMessage(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function extractApiError(response, fallback) {
    try {
      const data = await response.json();
      if (typeof data?.detail === "string" && data.detail.trim()) return data.detail;
      if (Array.isArray(data?.detail) && data.detail.length > 0) {
        return data.detail.map((d) => d?.msg || JSON.stringify(d)).join("; ");
      }
    } catch (_e) {
      // Ignore parse failures and use fallback.
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

  function getOcrStatus(response) {
    return response.headers.get("X-Resume-OCR-Status") || "";
  }

  function buildOcrHint(status) {
    if (status === "used") {
      return "OCR fallback was used to extract text from your scanned PDF resume.";
    }
    if (status === "failed") {
      return "OCR fallback could not extract text from the uploaded resume. Text input was used instead.";
    }
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

  return (
    <div className="container">
      <h1>AI Job Application Assistant</h1>
      <p>Paste your resume and job description to get a match analysis.</p>
      {errorMessage && <div className="error-box">{errorMessage}</div>}
      {ocrHint && <div className="hint-box">{ocrHint}</div>}

      <label>Resume</label>
      <label htmlFor="resume-file-input" className="file-upload-btn">
        Upload Resume (PDF/DOCX)
      </label>
      <input
        id="resume-file-input"
        className="file-input-hidden"
        type="file"
        accept=".pdf,.docx"
        onChange={(e) => {
          const file = e.target.files?.[0] || null;
          const fileError = validateFileSize(file);
          if (fileError) {
            setResumeFile(null);
            setErrorMessage(fileError);
            setOcrHint("");
            setOcrStatus("");
            return;
          }
          setResumeFile(file);
          setErrorMessage("");
          setOcrHint("");
          setOcrStatus("");
        }}
      />
      {resumeFile && <p>Using uploaded file: {resumeFile.name}</p>}
      <textarea
        value={resumeText}
        onChange={(e) => setResumeText(e.target.value)}
        placeholder="Paste resume text (optional when file uploaded)"
      />

      <label>Job Description</label>
      <textarea
        value={jobDescriptionText}
        onChange={(e) => setJobDescriptionText(e.target.value)}
        placeholder="Paste job description text"
      />

      <label>Tone</label>
      <select value={tone} onChange={(e) => setTone(e.target.value)}>
        <option value="professional">Professional</option>
        <option value="concise">Concise</option>
        <option value="confident">Confident</option>
      </select>

      <div className="row">
        <button disabled={!canSubmit || loading} onClick={handleAnalyze}>
          {loading ? "Working..." : "Analyze Match"}
        </button>
        <button disabled={!canSubmit || loading} onClick={handleCoverLetter}>
          {loading ? "Working..." : "Generate Cover Letter"}
        </button>
      </div>

      {result && (
        <section>
          <h2>Analysis</h2>
          {getOcrBadgeLabel(ocrStatus) && (
            <span className={`ocr-badge ocr-badge-${ocrStatus}`}>{getOcrBadgeLabel(ocrStatus)}</span>
          )}
          <p><strong>Match score:</strong> {result.match_score}/100</p>
          <p><strong>Summary:</strong> {result.summary}</p>
          <p><strong>Keywords:</strong> {result.extracted_keywords.join(", ")}</p>
          <p><strong>Matched skills:</strong> {result.matched_skills.join(", ")}</p>
          <p><strong>Missing skills:</strong> {result.missing_skills.join(", ")}</p>

          <h3>Tailored Bullets</h3>
          {result.rewritten_bullets.map((b, idx) => (
            <div key={idx} className="card">
              <p><strong>Original:</strong> {b.original}</p>
              <p><strong>Tailored:</strong> {b.tailored}</p>
              <p><strong>Why:</strong> {b.rationale}</p>
            </div>
          ))}
        </section>
      )}

      {coverLetter && (
        <section>
          <h2>Cover Letter</h2>
          {getOcrBadgeLabel(ocrStatus) && (
            <span className={`ocr-badge ocr-badge-${ocrStatus}`}>{getOcrBadgeLabel(ocrStatus)}</span>
          )}
          <pre>{coverLetter}</pre>
        </section>
      )}
    </div>
  );
}
