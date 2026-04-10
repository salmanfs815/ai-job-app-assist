import { useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export default function App() {
  const [resumeText, setResumeText] = useState("");
  const [jobDescriptionText, setJobDescriptionText] = useState("");
  const [tone, setTone] = useState("professional");
  const [result, setResult] = useState(null);
  const [coverLetter, setCoverLetter] = useState("");
  const [loading, setLoading] = useState(false);

  const canSubmit = useMemo(
    () => resumeText.trim().length > 20 && jobDescriptionText.trim().length > 20,
    [resumeText, jobDescriptionText]
  );

  async function handleAnalyze() {
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resumeText,
          job_description_text: jobDescriptionText,
          tone,
        }),
      });

      if (!res.ok) throw new Error("Analysis failed");
      setResult(await res.json());
    } catch (err) {
      alert(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleCoverLetter() {
    setLoading(true);
    setCoverLetter("");
    try {
      const res = await fetch(`${API_BASE}/cover-letter`, {
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

      if (!res.ok) throw new Error("Cover letter generation failed");
      const data = await res.json();
      setCoverLetter(data.cover_letter);
    } catch (err) {
      alert(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container">
      <h1>AI Job Application Assistant</h1>
      <p>Paste your resume and job description to get a match analysis.</p>

      <label>Resume</label>
      <textarea
        value={resumeText}
        onChange={(e) => setResumeText(e.target.value)}
        placeholder="Paste resume text"
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
          <pre>{coverLetter}</pre>
        </section>
      )}
    </div>
  );
}
