"use client";

import { useState } from "react";
import type { ClaimArtifact, SignalResult, StoredClaim } from "./types";
import { LAYER_LABELS } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<StoredClaim | null>(null);
  const [error, setError] = useState<string | null>(null);

  function onFileChange(f: File | null) {
    setFile(f);
    setReport(null);
    setError(null);
    setPreview(f ? URL.createObjectURL(f) : null);
  }

  async function onSubmit() {
    if (!file) return;
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const body = new FormData();
      body.append("image", file);
      // Consumer check: no order/listing context — L5 and damage-plausibility no-op gracefully.
      const res = await fetch(`${API_URL}/v1/claims`, { method: "POST", body });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setReport(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const originalArtifact =
    report?.artifacts.find((artifact) => artifact.kind === "original_upload") ?? null;
  const heatmapArtifact = report?.artifacts.find((artifact) => artifact.kind === "heatmap") ?? null;
  const l2Signal = report?.signals.find((signal) => signal.layer === "l2_forensics") ?? null;
  const heatmapDiagnostic = describeHeatmapState(l2Signal, heatmapArtifact);

  return (
    <main>
      <header>
        <h1>TruthPixel</h1>
        <p className="tagline">
          Upload an image for a multi-signal integrity check — AI-generation, edit forensics,
          and screenshot/recapture detection, fused into one explainable report.
        </p>
      </header>

      <section className="upload-box">
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
        />
        {preview && <img src={preview} alt="preview" className="preview" />}
        <button onClick={onSubmit} disabled={!file || loading}>
          {loading ? "Analyzing…" : "Check this image"}
        </button>
      </section>

      {error && <p className="error">{error}</p>}

      {report && (
        <section className="report">
          <div className="risk-score">
            <div className="risk-number">{Math.round(report.fusion.risk_score * 100)}%</div>
            <div className="risk-label">
              fraud/manipulation risk {report.fusion.needs_review ? "— flagged for review" : ""}
            </div>
            <div className="status-badge">
              status: {report.status}
              {report.decision && ` — reviewer decision: ${report.decision.decision}`}
            </div>
          </div>

          {(originalArtifact || heatmapArtifact) && (
            <div className="artifact-preview">
              <div className="artifact-preview-copy">
                <h2>Artifact preview</h2>
                <p>Original upload with persisted TruFor heatmap overlay when available.</p>
              </div>
              {originalArtifact ? (
                <div className="overlay-stage">
                  <img
                    src={`${API_URL}${originalArtifact.download_path}`}
                    alt="original claim upload"
                    className="preview overlay-base"
                  />
                  {heatmapArtifact && (
                    <img
                      src={`${API_URL}${heatmapArtifact.download_path}`}
                      alt="manipulation heatmap overlay"
                      className="preview heatmap overlay-heatmap"
                    />
                  )}
                </div>
              ) : (
                heatmapArtifact && (
                  <img
                    src={`${API_URL}${heatmapArtifact.download_path}`}
                    alt="manipulation heatmap overlay"
                    className="heatmap"
                  />
                )
              )}
            </div>
          )}

          {heatmapDiagnostic && <p className="artifact-note">{heatmapDiagnostic}</p>}

          <p className="report-text">{report.report_text}</p>

          <table className="signal-table">
            <thead>
              <tr>
                <th>Signal</th>
                <th>Score</th>
                <th>Confidence</th>
                <th>Contribution</th>
              </tr>
            </thead>
            <tbody>
              {report.signals.map((s) => (
                <tr key={s.layer}>
                  <td>{LAYER_LABELS[s.layer] ?? s.layer}</td>
                  <td>{s.error ? "unavailable" : s.score !== null ? s.score.toFixed(2) : "—"}</td>
                  <td>{s.confidence.toFixed(2)}</td>
                  <td>
                    {report.fusion.contributions[s.layer] !== undefined
                      ? `${Math.round(report.fusion.contributions[s.layer] * 100)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {report.agent_findings.length > 0 && (
            <div className="agent-findings">
              <h2>Agent findings</h2>
              {report.agent_findings.map((a) => (
                <div key={a.agent} className="agent-block">
                  <div className="agent-header">
                    <strong>{a.agent.replace(/_/g, " ")}</strong>
                    {a.score !== null && (
                      <span>
                        score {a.score.toFixed(2)} (conf {a.confidence.toFixed(2)})
                      </span>
                    )}
                  </div>
                  {a.findings.length > 0 ? (
                    <ul>
                      {a.findings.map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="agent-empty">no findings reported</p>
                  )}
                </div>
              ))}
            </div>
          )}

          <p className="disclaimer">{report.disclaimer}</p>
        </section>
      )}
    </main>
  );
}

function describeHeatmapState(
  l2Signal: SignalResult | null,
  heatmapArtifact: ClaimArtifact | null
): string | null {
  if (!l2Signal || heatmapArtifact) {
    return null;
  }
  if (l2Signal.error) {
    return `L2 forensics unavailable: ${l2Signal.error}`;
  }
  const storageError =
    typeof l2Signal.evidence.heatmap_storage_error === "string"
      ? l2Signal.evidence.heatmap_storage_error
      : null;
  if (storageError) {
    return `Heatmap artifact unavailable: ${storageError}`;
  }
  return typeof l2Signal.evidence.note === "string" ? l2Signal.evidence.note : null;
}
