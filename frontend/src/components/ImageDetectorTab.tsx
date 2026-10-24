import { useState } from "react";
import { queuedFetch } from "../api";

interface Result {
  verdict: string;
  confidence_percent: number;
  explanation: string;
  filename: string;
  model: string;
}
const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");

export default function ImageDetectorTab() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [reportBusy, setReportBusy] = useState(false);

  async function analyze() {
    if (!file) return;
    setBusy(true); setError(""); setResult(null);
    try {
      const form = new FormData(); form.append("file", file);
      const response = await queuedFetch(`${API_BASE}/analyze/image`, { method: "POST", body: form });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Analysis failed");
      }
      setResult(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally { setBusy(false); }
  }

  async function download() {
    if (!result) return;
    setReportBusy(true); setError("");
    try {
      const response = await fetch(`${API_BASE}/analyze/image/report`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ result }),
      });
      if (!response.ok) throw new Error("Report generation failed");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = "Drishti_Image_Report.pdf";
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report generation failed");
    } finally { setReportBusy(false); }
  }

  return <section className="clay-card p-8 space-y-5" aria-busy={busy}>
    <h2 className="text-2xl font-bold">Image analysis</h2>
    <p>Upload an image to check for signs of AI generation.</p>
    <label className="block" htmlFor="image-upload">Choose an image</label>
    <input id="image-upload" type="file" accept="image/jpeg,image/png,image/webp,image/bmp,image/tiff"
      disabled={busy} onChange={event => { setFile(event.target.files?.[0] || null); setResult(null); setError(""); }} />
    <button className="clay-btn px-5 py-3" disabled={!file || busy} onClick={analyze}>
      {busy ? "Analysis queued or running..." : "Analyze image"}
    </button>
    <div aria-live="polite">{busy ? "Waiting for analysis. Large models can take several minutes to start." : ""}</div>
    {error ? <p role="alert" className="text-red-700">{error}</p> : null}
    {result ? <div className="space-y-3" aria-live="polite">
      <p className="text-xl font-bold">{result.verdict} - model score {result.confidence_percent}%</p>
      <p>{result.explanation}</p>
      <button className="clay-btn px-5 py-3" disabled={reportBusy} onClick={download}>
        {reportBusy ? "Preparing report..." : "Download report"}
      </button>
    </div> : null}
  </section>;
}
