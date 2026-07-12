"use client";

import { useEffect, useState } from "react";
import { createSupabaseBrowserClient } from "./lib/supabase-browser";
import type { AgentFinding, ClaimArtifact, SignalResult, StoredClaim } from "./types";
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

function getRiskTone(report: StoredClaim | null): "idle" | "review" | "monitor" {
  if (!report) {
    return "idle";
  }
  return report.fusion.needs_review ? "review" : "monitor";
}

function providerLabel(signal: SignalResult): string {
  return typeof signal.evidence.provider === "string" ? signal.evidence.provider : signal.model_version;
}

function contributionFor(signal: SignalResult, report: StoredClaim): string {
  const contribution = report.fusion.contributions[signal.layer];
  return formatPercent(contribution ?? 0);
}

function signalHeadline(signal: SignalResult): string {
  if (signal.error) {
    return "Unavailable on this run";
  }
  if (signal.score === null) {
    return "No score returned";
  }
  if (signal.score >= 0.75) {
    return "Strong concern";
  }
  if (signal.score >= 0.55) {
    return "Worth review";
  }
  if (signal.score >= 0.35) {
    return "Mixed evidence";
  }
  return "Lower concern";
}

function findingTone(finding: AgentFinding): "quiet" | "alert" {
  return finding.score !== null && finding.score >= 0.6 ? "alert" : "quiet";
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
  if (typeof l2Signal.evidence.fallback_reason === "string") {
    return `L2 heatmap came from the classical CPU fallback: ${l2Signal.evidence.fallback_reason}.`;
  }
  return typeof l2Signal.evidence.note === "string" ? l2Signal.evidence.note : null;
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<StoredClaim | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [heatmapOpacity, setHeatmapOpacity] = useState(72);
  const [dragActive, setDragActive] = useState(false);
  const [limitReached, setLimitReached] = useState(false);

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
    setHeatmapOpacity(72);

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
    setLimitReached(false);
    setReport(null);

    try {
      // Signed-in users (Google/email via Supabase Auth) get a higher, account-scoped rate
      // limit than anonymous IP-based requests — see backend/app/auth.py::
      // allow_public_submission. Anonymous users simply omit this header and fall back to
      // the anonymous limit, same as before this feature existed.
      let authHeader: Record<string, string> = {};
      try {
        const supabase = createSupabaseBrowserClient();
        const { data } = await supabase.auth.getSession();
        if (data.session?.access_token) {
          authHeader = { Authorization: `Bearer ${data.session.access_token}` };
        }
      } catch {
        // Supabase env vars unset (e.g. this deployment hasn't configured auth yet) —
        // proceed anonymously rather than blocking the whole page on a missing feature.
      }

      const body = new FormData();
      body.append("image", file);
      const response = await fetch(`${API_URL}/v1/claims`, {
        method: "POST",
        headers: authHeader,
        body,
      });
      if (!response.ok) {
        if (response.status === 429) {
          setLimitReached(true);
        }
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
  const riskTone = getRiskTone(report);

  return (
    <main className="page-shell">
      <section className="hero-grid">
        <div className="hero-card hero-main">
          <p className="eyebrow">TruthPixel public checker</p>
          <h1>Upload one image. Get a real multi-signal integrity report.</h1>
          <p className="tagline">
            This public surface uses the same backend pipeline as the B2B API and reviewer
            dashboard, then turns the output into an evidence-led report instead of a binary
            verdict.
          </p>
          <div className="hero-pills">
            <span>AI-generation detection</span>
            <span>Edit forensics + heatmap</span>
            <span>Screenshot / recapture checks</span>
            <span>Human review still decides</span>
          </div>
          <div className="hero-actions">
            <button type="button" onClick={onSubmit} disabled={!file || loading}>
              {loading ? "Analyzing..." : "Run integrity check"}
            </button>
            <p>
              Public mode submits only the image. No order ID or listing context is required, so
              the consumer flow stays thin while the backend gracefully limits context-heavy checks.
            </p>
          </div>
        </div>

        <aside className="hero-card hero-side">
          <div className="hero-side-block">
            <span className="mini-label">What this page is</span>
            <strong>Top-of-funnel product surface</strong>
            <p>
              Fast self-serve checks for a single image, designed to show the full fusion story
              before a team ever integrates the API.
            </p>
          </div>
          <div className="hero-side-block">
            <span className="mini-label">Current runtime</span>
            <strong>Same backend contract as `POST /v1/claims`</strong>
            <p>
              No frontend-only detection logic lives here. The UI only uploads a file and renders
              the stored-claim response the backend returns.
            </p>
          </div>
        </aside>
      </section>

      <section className="workspace-grid">
        <section className="panel upload-panel">
          <div className="section-heading">
            <div>
              <h2>Upload an image</h2>
              <p>
                Public upload only: one image, one report, no enterprise case context. Best for
                quick checks, demos, and early product discovery.
              </p>
            </div>
            <div className="upload-meta">
              <span>15 MB max</span>
              <span>JPG / PNG / WEBP</span>
              <span>One image at a time</span>
            </div>
          </div>

          <label
            className={dragActive ? "dropzone is-active" : "dropzone"}
            onDragOver={(event) => {
              event.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragActive(false);
              onFileChange(event.dataTransfer.files?.[0] ?? null);
            }}
          >
            <span className="dropzone-kicker">{file ? "Replace image" : "Drop image here"}</span>
            <strong>{file ? file.name : "Choose a file or drag one into the workspace"}</strong>
            <p>
              TruthPixel will run the shared L1-L5 pipeline, render any available forensic heatmap,
              and return a report you can inspect or escalate.
            </p>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
            />
          </label>

          <div className="process-strip">
            <div className="process-step">
              <span>1</span>
              <div>
                <strong>Select image</strong>
                <p>Client-side size and type checks run before upload.</p>
              </div>
            </div>
            <div className="process-step">
              <span>2</span>
              <div>
                <strong>Shared backend analysis</strong>
                <p>Same stored-claim contract as the API and reviewer surfaces.</p>
              </div>
            </div>
            <div className="process-step">
              <span>3</span>
              <div>
                <strong>Human-readable result</strong>
                <p>Risk score, evidence breakdown, artifacts, and agent notes.</p>
              </div>
            </div>
          </div>

          {file ? (
            <div className="selected-file">
              <div>
                <strong>{file.name}</strong>
                <p>{fileSummary(file)}</p>
              </div>
              <button type="button" className="secondary-button" onClick={() => onFileChange(null)}>
                Clear
              </button>
            </div>
          ) : (
            <div className="idle-note">
              <strong>No image selected yet.</strong>
              <p>
                Choose a file to unlock the preview and run the same fused scoring path used across
                the product.
              </p>
            </div>
          )}
        </section>

        <aside className="panel preview-panel">
          <div className="preview-header">
            <div>
              <h2>Preview</h2>
              <p>Inspect the exact upload before it goes to the backend.</p>
            </div>
            {preview && <span className="preview-badge">Ready to analyze</span>}
          </div>

          {preview ? (
            <div className="preview-frame">
              <img src={preview} alt="Selected upload preview" className="preview" />
            </div>
          ) : (
            <div className="empty-stage">
              <strong>Image preview appears here</strong>
              <p>
                Use this surface for a single-image check when you want to see the same fused report
                without building an integration first.
              </p>
            </div>
          )}

          <div className="preview-footnote">
            <span>A few free checks anonymously, more once signed in.</span>
            <span>Sign in with Google or email — no API key needed here.</span>
          </div>
        </aside>
      </section>

      {error && (
        <p className="error">
          {error}
          {limitReached && (
            <>
              {" "}
              <a href="/login?reason=limit" className="link-button">
                Sign in to keep checking images
              </a>
            </>
          )}
        </p>
      )}

      <section className="policy-grid">
        <article className="policy-card">
          <h2>What you get back</h2>
          <p>
            A fused fraud/manipulation risk score, layer-by-layer signal breakdown, artifact access,
            and any available heatmap overlay from the forensics path.
          </p>
        </article>
        <article className="policy-card">
          <h2>What this page avoids</h2>
          <p>
            No fake certainty, no frontend-only model logic, and no separate consumer-grade scoring
            rubric that drifts away from the enterprise product.
          </p>
        </article>
        <article className="policy-card">
          <h2>Retention and privacy</h2>
          <p>
            Treat uploads as backend claims, not ephemeral chat attachments. Operators still need a
            formal retention policy if they expose anonymous uploads publicly.
          </p>
        </article>
        <article className="policy-card accent-card">
          <h2>Higher-volume path</h2>
          <p>
            Teams that need repeat use should graduate to the API or reviewer dashboard. This page
            stays intentionally thin so it remains honest, fast, and easy to host.
          </p>
        </article>
      </section>

      {report && (
        <section className="report-shell">
          <section className={`verdict-band tone-${riskTone}`}>
            <div className="verdict-copy">
              <p className="eyebrow">Latest report</p>
              <h2>
                {report.fusion.needs_review
                  ? "Escalate this image for human review"
                  : "Lower-confidence fraud or manipulation signal"}
              </h2>
              <p>
                TruthPixel is providing a confidence-scored assessment, not a verdict. This public
                surface keeps the same evidence-first framing as the enterprise flow.
              </p>
            </div>
            <div className="verdict-score">
              <strong>{formatPercent(report.fusion.risk_score)}</strong>
              <span>Fused risk score</span>
            </div>
          </section>

          <section className="report-metrics">
            <div className="metric-card">
              <span>Submission scope</span>
              <strong>{describeSubmissionScope(report)}</strong>
            </div>
            <div className="metric-card">
              <span>Claim ID</span>
              <strong>{report.claim_id}</strong>
            </div>
            <div className="metric-card">
              <span>Created</span>
              <strong>{formatTimestamp(report.created_at)}</strong>
            </div>
            <div className="metric-card">
              <span>Artifacts</span>
              <strong>{report.artifacts.length}</strong>
            </div>
          </section>

          <section className="report-grid">
            <article className="panel stage-panel">
              <div className="section-heading">
                <div>
                  <h2>Artifact stage</h2>
                  <p>Overlay forensic heatmaps on the stored upload whenever the backend emits them.</p>
                </div>
                {heatmapArtifact && (
                  <div className="stage-controls">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setShowHeatmap((current) => !current)}
                    >
                      {showHeatmap ? "Hide heatmap" : "Show heatmap"}
                    </button>
                    <label className="slider-field">
                      <span>Overlay</span>
                      <input
                        type="range"
                        min="20"
                        max="100"
                        value={heatmapOpacity}
                        onChange={(event) => setHeatmapOpacity(Number(event.target.value))}
                      />
                    </label>
                  </div>
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
                      style={{ opacity: heatmapOpacity / 100 }}
                    />
                  )}
                </div>
              ) : (
                <p className="empty-copy">The backend response did not include a stored original artifact.</p>
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
                      <div>
                        <strong>{artifact.kind.replace(/_/g, " ")}</strong>
                        <span>{artifact.filename}</span>
                      </div>
                      <em>{formatBytes(artifact.byte_size)}</em>
                    </a>
                  ))
                ) : (
                  <p className="empty-copy">No downloadable artifacts were returned for this claim.</p>
                )}
              </div>
            </article>

            <article className="panel summary-panel">
              <div className="summary-block">
                <h2>Plain-English summary</h2>
                <p className="report-text">{report.report_text}</p>
              </div>
              <div className="summary-note">
                <strong>Important context</strong>
                <p>
                  Public submissions intentionally omit listing images and order metadata, so context
                  heavy signals should be read as narrower than a tenant-backed return-fraud case.
                </p>
              </div>
            </article>
          </section>

          <section className="signal-section">
            <div className="section-heading">
              <div>
                <h2>Signal breakdown</h2>
                <p>Every layer contributes separately to the final fused score so the review story stays legible.</p>
              </div>
            </div>

            <div className="signal-grid">
              {report.signals.map((signal) => (
                <article key={signal.layer} className="signal-card">
                  <div className="signal-topline">
                    <span className="signal-layer">{LAYER_LABELS[signal.layer] ?? signal.layer}</span>
                    <span className="signal-contribution">{contributionFor(signal, report)}</span>
                  </div>
                  <h3>{signalHeadline(signal)}</h3>
                  <div className="signal-metrics">
                    <div>
                      <span>Score</span>
                      <strong>{signal.error ? "Unavailable" : formatScore(signal.score)}</strong>
                    </div>
                    <div>
                      <span>Confidence</span>
                      <strong>{formatScore(signal.confidence)}</strong>
                    </div>
                  </div>
                  <p className="signal-provider">{providerLabel(signal)}</p>
                  {signal.error && <p className="signal-warning">{signal.error}</p>}
                </article>
              ))}
            </div>
          </section>

          {report.agent_findings.length > 0 && (
            <section className="agent-section">
              <div className="section-heading">
                <div>
                  <h2>Agent findings</h2>
                  <p>When agent passes run, they add semantic or plausibility notes on top of deterministic signals.</p>
                </div>
              </div>
              <div className="agent-grid">
                {report.agent_findings.map((finding) => (
                  <article key={finding.agent} className={`agent-card tone-${findingTone(finding)}`}>
                    <div className="agent-header">
                      <strong>{finding.agent.replace(/_/g, " ")}</strong>
                      <span>
                        {finding.score !== null
                          ? `score ${formatScore(finding.score)} · conf ${formatScore(finding.confidence)}`
                          : "No score returned"}
                      </span>
                    </div>
                    {finding.findings.length > 0 ? (
                      <ul>
                        {finding.findings.map((item, index) => (
                          <li key={`${finding.agent}-${index}`}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="agent-empty">No specific findings were returned on this run.</p>
                    )}
                  </article>
                ))}
              </div>
            </section>
          )}

          <p className="disclaimer">{report.disclaimer}</p>
        </section>
      )}
    </main>
  );
}
