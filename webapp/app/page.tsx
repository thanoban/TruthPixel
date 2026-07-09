"use client";

import { useEffect, useState } from "react";
import type { ClaimArtifact, SignalResult, StoredClaim } from "./types";
import {
  LAYER_LABELS,
  describeSubmissionScope,
  formatBytes,
  formatPercent,
  formatScore,
  formatTimestamp,
  getArtifactByKind,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const SUPPORTED_TYPES = ["image/jpeg", "image/png", "image/webp"];

async function buildErrorMessage(response: Response): Promise<string> {
  let detail = `${response.status} ${response.statusText}`;

  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") {
      detail = payload.detail;
    }
  } catch {}

  if (response.status === 401) {
    return `${detail}. This deployment does not currently allow anonymous public submissions.`;
  }
  if (response.status === 413) {
    return "This file is larger than the backend's 15 MB upload limit.";
  }
  if (response.status === 415) {
    return "This file type is not supported here yet. Use JPG, PNG, or WEBP.";
  }
  if (response.status === 429) {
    const retryAfter = response.headers.get("Retry-After");
    return retryAfter
      ? `${detail}. Try again in about ${retryAfter} seconds.`
      : `${detail}. Try again later.`;
  }

  return detail;
}

function fileSummary(file: File): string {
  return `${formatBytes(file.size)} · ${file.type.replace("image/", "").toUpperCase()}`;
}

function artifactUrl(artifact: ClaimArtifact): string {
  return `${API_URL}${artifact.download_path}`;
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<StoredClaim | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showHeatmap, setShowHeatmap] = useState(true);

  useEffect(() => {
    return () => {
      if (preview) {
        URL.revokeObjectURL(preview);
      }
    };
  }, [preview]);

  function onFileChange(nextFile: File | null) {
    if (preview) {
      URL.revokeObjectURL(preview);
    }

    setFile(null);
    setPreview(null);
    setReport(null);
    setError(null);

    if (!nextFile) {
      return;
    }
    if (!SUPPORTED_TYPES.includes(nextFile.type)) {
      setError("Use a JPG, PNG, or WEBP image for this public checker.");
      return;
    }
    if (nextFile.size > MAX_IMAGE_BYTES) {
      setError("Choose an image smaller than 15 MB.");
      return;
    }

    setFile(nextFile);
    setPreview(URL.createObjectURL(nextFile));
  }

  async function onSubmit() {
    if (!file) {
      return;
    }

    setLoading(true);
    setError(null);
    setReport(null);

    try {
      const body = new FormData();
      body.append("image", file);
      // Consumer check: no order/listing context — L5 and damage-plausibility no-op gracefully.
      const response = await fetch(`${API_URL}/v1/claims`, { method: "POST", body });
      if (!response.ok) {
        throw new Error(await buildErrorMessage(response));
      }
      const payload = (await response.json()) as StoredClaim;
      setReport(payload);
      setShowHeatmap(Boolean(getArtifactByKind(payload.artifacts, "heatmap")));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const originalArtifact = report ? getArtifactByKind(report.artifacts, "original_upload") : undefined;
  const heatmapArtifact = report ? getArtifactByKind(report.artifacts, "heatmap") : undefined;
  const l2Signal = report?.signals.find((signal) => signal.layer === "l2_forensics") ?? null;
  const heatmapDiagnostic = describeHeatmapState(l2Signal, heatmapArtifact ?? null);

  return (
    <main className="page-shell">
      <header className="hero">
        <p className="eyebrow">TruthPixel public checker</p>
        <h1>Run the same multi-signal integrity check without wiring an integration.</h1>
        <p className="tagline">
          This self-serve page uploads one image to the same backend pipeline used by the API and
          reviewer dashboard, then returns a confidence-scored report instead of a binary verdict.
        </p>
        <div className="hero-pills">
          <span>One image at a time</span>
          <span>JPG, PNG, WEBP</span>
          <span>Human review still decides</span>
        </div>
      </header>

      <section className="upload-box">
        <div className="section-heading">
          <div>
            <h2>Upload an image</h2>
            <p>
              Consumer-facing upload only: no order ID or listing context, so the report leans on
              the shared L1-L4 signals and any context-free L5 checks.
            </p>
          </div>
          <div className="upload-meta">
            <span>Max size: 15 MB</span>
            <span>Accepted: JPG, PNG, WEBP</span>
          </div>
        </div>

        <label className="file-picker">
          <span className="file-picker-title">{file ? "Replace image" : "Choose an image"}</span>
          <span className="file-picker-copy">
            Upload a single image to generate a fused risk score, per-signal breakdown, and any
            heatmap artifact the backend emits.
          </span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
          />
        </label>

        {file && (
          <div className="selected-file">
            <div>
              <strong>{file.name}</strong>
              <p>{fileSummary(file)}</p>
            </div>
            <button type="button" className="secondary-button" onClick={() => onFileChange(null)}>
              Clear
            </button>
          </div>
        )}

        {preview && (
          <div className="preview-frame">
            <img src={preview} alt="Selected upload preview" className="preview" />
          </div>
        )}

        <div className="action-row">
          <button type="button" onClick={onSubmit} disabled={!file || loading}>
            {loading ? "Analyzing..." : "Analyze this image"}
          </button>
          <p className="action-hint">
            If this deployment has anonymous mode turned off, the backend will return an API-key
            requirement instead of accepting the upload.
          </p>
        </div>
      </section>

      <section className="policy-grid">
        <article className="policy-card">
          <h2>What this public surface is for</h2>
          <p>
            Fast self-serve checks, not case management. It is intentionally one-image-at-a-time
            and thin over the shared backend so the same signals power the enterprise surfaces.
          </p>
        </article>

        <article className="policy-card">
          <h2>Retention and privacy</h2>
          <p>
            Treat uploads as backend records, not ephemeral chat attachments. Claims and artifacts
            may be persisted for audit and debugging unless the operator configures cleanup.
          </p>
        </article>

        <article className="policy-card">
          <h2>Risk and decisions</h2>
          <p>
            A high score is a strong review signal, not a final verdict. The product direction
            stays the same here: TruthPixel supports investigation, and humans make the call.
          </p>
        </article>

        <article className="policy-card placeholder-card">
          <h2>Anonymous flow and higher-volume path</h2>
          <p>
            Anonymous submission is valid when the host enables it. For repeat usage or team
            integration, tenant API keys already exist on the backend, but a self-serve upgrade
            or signup flow is still a placeholder on this page.
          </p>
          <span className="placeholder-badge">API-key upgrade path: planned</span>
        </article>
      </section>

      {error && <p className="error">{error}</p>}

      {report && (
        <section className="report">
          <div className="report-header">
            <div className="risk-score">
              <div className="risk-number">{formatPercent(report.fusion.risk_score)}</div>
              <div className="risk-label">
                {report.fusion.needs_review
                  ? "Escalate this image for human review"
                  : "Lower-confidence fraud/manipulation signal"}
              </div>
              <div className="status-badge">
                Status: {report.status}
                {report.decision ? ` · reviewer decision: ${report.decision.decision}` : ""}
              </div>
            </div>

            <div className="report-stats">
              <div className="stat-card">
                <span>Submission scope</span>
                <strong>{describeSubmissionScope(report)}</strong>
              </div>
              <div className="stat-card">
                <span>Claim ID</span>
                <strong>{report.claim_id}</strong>
              </div>
              <div className="stat-card">
                <span>Created</span>
                <strong>{formatTimestamp(report.created_at)}</strong>
              </div>
              <div className="stat-card">
                <span>Artifacts</span>
                <strong>{report.artifacts.length}</strong>
              </div>
            </div>
          </div>

          <div className="report-layout">
            <article className="report-panel">
              <div className="section-heading">
                <div>
                  <h2>Artifact preview</h2>
                  <p>
                    When the backend emits a heatmap, the public page can show it over the stored
                    original upload instead of only listing raw artifact URLs.
                  </p>
                </div>
                {heatmapArtifact && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setShowHeatmap((current) => !current)}
                  >
                    {showHeatmap ? "Hide heatmap" : "Show heatmap"}
                  </button>
                )}
              </div>

              {originalArtifact ? (
                <div className="artifact-stage">
                  <img
                    src={artifactUrl(originalArtifact)}
                    alt="Original uploaded image"
                    className="artifact-image"
                  />
                  {heatmapArtifact && showHeatmap && (
                    <img
                      src={artifactUrl(heatmapArtifact)}
                      alt="Heatmap overlay"
                      className="artifact-image artifact-overlay"
                    />
                  )}
                </div>
              ) : (
                <p className="empty-copy">
                  The backend response did not include a stored original artifact.
                </p>
              )}

              {heatmapDiagnostic && <p className="artifact-note">{heatmapDiagnostic}</p>}

              <div className="artifact-list">
                {report.artifacts.length > 0 ? (
                  report.artifacts.map((artifact) => (
                    <a
                      key={artifact.id}
                      href={artifactUrl(artifact)}
                      target="_blank"
                      rel="noreferrer"
                      className="artifact-link"
                    >
                      <strong>{artifact.kind.replace(/_/g, " ")}</strong>
                      <span>
                        {artifact.filename} · {formatBytes(artifact.byte_size)}
                      </span>
                    </a>
                  ))
                ) : (
                  <p className="empty-copy">
                    No downloadable artifacts were returned for this claim.
                  </p>
                )}
              </div>
            </article>

            <article className="report-panel">
              <h2>Plain-English summary</h2>
              <p className="report-text">{report.report_text}</p>
              <p className="report-note">
                Missing listing context is expected on the public surface, so any product-match
                logic should be treated as intentionally limited here.
              </p>
            </article>
          </div>

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
              {report.signals.map((signal) => (
                <tr key={signal.layer}>
                  <td>{LAYER_LABELS[signal.layer] ?? signal.layer}</td>
                  <td>{signal.error ? "unavailable" : formatScore(signal.score)}</td>
                  <td>{formatScore(signal.confidence)}</td>
                  <td>{formatPercent(report.fusion.contributions[signal.layer])}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {report.agent_findings.length > 0 && (
            <div className="agent-findings">
              <h2>Agent findings</h2>
              {report.agent_findings.map((finding) => (
                <div key={finding.agent} className="agent-block">
                  <div className="agent-header">
                    <strong>{finding.agent.replace(/_/g, " ")}</strong>
                    {finding.score !== null && (
                      <span>
                        score {formatScore(finding.score)} · conf {formatScore(finding.confidence)}
                      </span>
                    )}
                  </div>
                  {finding.findings.length > 0 ? (
                    <ul>
                      {finding.findings.map((item, index) => (
                        <li key={`${finding.agent}-${index}`}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="agent-empty">No specific findings were returned.</p>
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
