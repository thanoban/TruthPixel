"use client";

import { useEffect, useRef, useState } from "react";
import { createSupabaseBrowserClient } from "./lib/supabase-browser";
import { riskStamp, riskToneName } from "./theme";
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

const LOADING_STEPS = [
  "Uploading image",
  "Running L1-L5 signal scan",
  "Cost-gated agent pass",
  "Fusing signals into risk score",
  "Preparing report",
];

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

// Drag-to-reveal comparison between the original upload and the forensic heatmap overlay —
// both real artifacts already fetched, no fake blob/position data like the source mockup.
function HeatmapCompareSlider({ originalSrc, heatmapSrc }: { originalSrc: string; heatmapSrc: string }) {
  const [pct, setPct] = useState(50);
  const frameRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  function updateFromClientX(clientX: number) {
    const el = frameRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const next = ((clientX - rect.left) / rect.width) * 100;
    setPct(Math.min(100, Math.max(0, next)));
  }

  useEffect(() => {
    function onMove(event: PointerEvent) {
      if (!draggingRef.current) return;
      updateFromClientX(event.clientX);
    }
    function onUp() {
      draggingRef.current = false;
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, []);

  return (
    <div
      ref={frameRef}
      className="compare-frame"
      onPointerDown={(event) => {
        draggingRef.current = true;
        updateFromClientX(event.clientX);
      }}
    >
      <img src={originalSrc} alt="Original upload" className="compare-base" />
      <div className="compare-clip" style={{ width: `${pct}%` }}>
        <img src={heatmapSrc} alt="Heatmap overlay" className="compare-overlay" />
      </div>
      <div className="compare-handle" style={{ left: `${pct}%` }}>
        <div className="compare-handle-line" />
        <div className="compare-handle-grip">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="18 8 22 12 18 16" />
            <polyline points="6 8 2 12 6 16" />
            <line x1="2" x2="22" y1="12" y2="12" />
          </svg>
        </div>
      </div>
    </div>
  );
}

type Phase = "idle" | "loading" | "error" | "done";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [report, setReport] = useState<StoredClaim | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [limitReached, setLimitReached] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [expandedLayer, setExpandedLayer] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (preview) {
        URL.revokeObjectURL(preview);
      }
    };
  }, [preview]);

  // Cosmetic pacing only — the backend returns all five layers at once, this just gives the
  // long real wait (15-90s, worse on a cold start) something to look at instead of a bare
  // spinner. Labels are deliberately generic ("running signal scan"), not fake per-layer
  // done/pending states tied to nothing real.
  useEffect(() => {
    if (phase !== "loading") {
      setLoadingStep(0);
      return;
    }
    const interval = window.setInterval(() => {
      setLoadingStep((current) => Math.min(current + 1, LOADING_STEPS.length - 1));
    }, 3500);
    return () => window.clearInterval(interval);
  }, [phase]);

  function onFileChange(nextFile: File | null) {
    if (preview) {
      URL.revokeObjectURL(preview);
    }

    setFile(null);
    setPreview(null);
    setReport(null);
    setError(null);
    setPhase("idle");

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

    setPhase("loading");
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
      setPhase("done");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong");
      setPhase("error");
    }
  }

  function resetFlow() {
    onFileChange(null);
  }

  const originalArtifact = report ? getArtifactByKind(report.artifacts, "original_upload") : undefined;
  const heatmapArtifact = report ? getArtifactByKind(report.artifacts, "heatmap") : undefined;
  const l2Signal = report?.signals.find((signal) => signal.layer === "l2_forensics") ?? null;
  const heatmapDiagnostic = describeHeatmapState(l2Signal, heatmapArtifact ?? null);

  return (
    <main className="page-shell">
      <div className="shell-inner">
        {phase === "idle" && (
          <>
            <div className="center-block">
              <div className="eyebrow">
                <span className="eyebrow-dot" />
                SIG_SCAN // image integrity
              </div>
              <h1 className="page-title">Verify any image in seconds</h1>
              <p className="page-sub">
                AI-generation, edit forensics and screenshot/recapture detection — fused into
                one explainable risk report.
              </p>
            </div>

            <div className="frame">
              <span className="bracket-tl" />
              <span className="bracket-tr" />
              <span className="bracket-bl" />
              <span className="bracket-br" />
              {file && preview ? (
                <div className="selected-preview">
                  <img src={preview} alt="Selected upload preview" />
                  <div className="mono-row">
                    <span>FILE {file.name}</span>
                    <span style={{ opacity: 0.5 }}>·</span>
                    <span>{fileSummary(file)}</span>
                  </div>
                  <div className="action-row">
                    <button type="button" className="btn-secondary" onClick={() => onFileChange(null)}>
                      Remove
                    </button>
                    <button type="button" className="btn-primary" onClick={onSubmit}>
                      Run integrity scan →
                    </button>
                  </div>
                </div>
              ) : (
                <label
                  className={dragActive ? "dropzone-label is-active" : "dropzone-label"}
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
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
                  />
                  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" />
                    <path d="M12 12v9" />
                    <path d="m16 16-4-4-4 4" />
                  </svg>
                  <div>
                    <div className="drop-title">Drop an image, or click to browse</div>
                    <div className="drop-sub">JPEG · PNG · WEBP — max 15MB</div>
                  </div>
                </label>
              )}
            </div>
            <p className="footnote">A few free checks anonymously, more once signed in.</p>

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

            <div className="policy-grid">
              <article className="policy-card frame">
                <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
                <h2>What you get back</h2>
                <p>A fused fraud/manipulation risk score, layer-by-layer signal breakdown, and any available heatmap overlay.</p>
              </article>
              <article className="policy-card frame">
                <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
                <h2>Same backend, no shortcuts</h2>
                <p>No frontend-only detection logic. Same stored-claim contract as the API and reviewer dashboard.</p>
              </article>
            </div>
          </>
        )}

        {phase === "loading" && (
          <>
            <div className="section-label">// 00 · running_signal_scan.sh</div>
            <div className="frame scan-frame">
              <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
              {preview && <img src={preview} alt="Analyzing" />}
              <div className="sweep-overlay" />
              <div className="dim-overlay" />
            </div>
            {LOADING_STEPS.map((label, index) => {
              const isDone = index < loadingStep;
              const isActive = index === loadingStep;
              return (
                <div className="term-row" key={label}>
                  <span
                    className="term-bracket"
                    style={{
                      color: isDone ? "var(--safe)" : isActive ? "var(--accent)" : "var(--text-faint)",
                      animation: isActive ? "tp-blink 1s step-start infinite" : "none",
                    }}
                  >
                    {isDone ? "[✓]" : isActive ? "[..]" : "[ ]"}
                  </span>
                  <span
                    className="term-label"
                    style={{
                      color: isDone || isActive ? "var(--text)" : "var(--text-faint)",
                      fontWeight: isActive ? 700 : 500,
                    }}
                  >
                    {label}
                  </span>
                  <span
                    className="term-status"
                    style={{ color: isDone ? "var(--safe)" : isActive ? "var(--accent)" : "var(--text-faint)" }}
                  >
                    {isDone ? "done" : isActive ? "running" : "queued"}
                  </span>
                </div>
              );
            })}
          </>
        )}

        {phase === "error" && (
          <div className="error-stage">
            <div className="error-icon-wrap">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                <path d="M12 9v4" />
                <path d="M12 17h.01" />
              </svg>
            </div>
            <h2>scan_failed.exception</h2>
            <p className="page-sub">
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
            <button type="button" className="btn-primary" onClick={onSubmit}>
              Retry scan
            </button>
          </div>
        )}

        {phase === "done" && report && (
          <>
            {(() => {
              const tone = riskToneName(report.fusion.risk_score);
              const stamp = riskStamp(report.fusion.risk_score);
              const offset = 314.159 * (1 - report.fusion.risk_score);
              const label = report.fusion.needs_review ? "Needs review" : "Likely authentic";
              return (
                <div className="frame verdict-card">
                  <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
                  <svg width="90" height="90" viewBox="0 0 120 120" style={{ flex: "none" }}>
                    <circle cx="60" cy="60" r="50" fill="none" stroke="var(--surface2)" strokeWidth="9" />
                    <circle
                      cx="60"
                      cy="60"
                      r="50"
                      fill="none"
                      stroke={`var(--${tone})`}
                      strokeWidth="9"
                      strokeLinecap="round"
                      strokeDasharray="314.159"
                      strokeDashoffset={offset}
                      transform="rotate(-90 60 60)"
                    />
                  </svg>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="risk-number">{formatPercent(report.fusion.risk_score)}</div>
                    <div className="risk-label" style={{ color: `var(--${tone})` }}>{label}</div>
                    <div className="mono-row" style={{ marginTop: 10 }}>
                      <span>CASE {report.claim_id.slice(0, 8)}</span>
                      <span style={{ opacity: 0.5 }}>·</span>
                      <span>{describeSubmissionScope(report)}</span>
                    </div>
                  </div>
                  <div className="stamp" style={{ color: `var(--${tone})`, borderColor: `var(--${tone})` }}>
                    {stamp}
                  </div>
                  <button type="button" className="btn-secondary" onClick={resetFlow}>
                    New scan
                  </button>
                </div>
              );
            })()}

            <div className="section-card frame">
              <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
              <div className="section-label">// 01 · manipulation_heatmap.render</div>
              <p className="page-sub" style={{ margin: "0 0 14px", maxWidth: "none" }}>
                Original left, region-level forensic overlay right — drag to compare.
              </p>
              {originalArtifact && heatmapArtifact ? (
                <HeatmapCompareSlider
                  originalSrc={artifactUrl(originalArtifact)}
                  heatmapSrc={artifactUrl(heatmapArtifact)}
                />
              ) : originalArtifact ? (
                <img src={artifactUrl(originalArtifact)} alt="Original upload" style={{ width: "100%", maxHeight: 420, objectFit: "cover" }} />
              ) : (
                <p className="page-sub" style={{ maxWidth: "none" }}>No stored artifact was returned for this claim.</p>
              )}
              {heatmapDiagnostic && <p className="compare-note">{heatmapDiagnostic}</p>}
            </div>

            <div className="callout">
              <div className="callout-label">// summary.txt</div>
              <p>{report.report_text}</p>
            </div>

            <div className="section-card frame">
              <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
              <div className="section-label">// 02 · signal_breakdown.json</div>
              {report.signals.map((signal) => {
                const score = signal.score ?? 0;
                const tone = riskToneName(score);
                const expanded = expandedLayer === signal.layer;
                return (
                  <div className="signal-row-wrap" key={signal.layer}>
                    <div
                      className="signal-row"
                      onClick={() => setExpandedLayer(expanded ? null : signal.layer)}
                    >
                      <span className="badge" style={{ background: `color-mix(in oklch, var(--${tone}) 16%, transparent)`, color: `var(--${tone})` }}>
                        L{signal.layer.slice(1, 2)}
                      </span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="signal-label">{LAYER_LABELS[signal.layer] ?? signal.layer}</div>
                        <div className="bar-track">
                          <div className="bar-fill" style={{ width: `${Math.round(score * 100)}%`, background: `var(--${tone})` }} />
                        </div>
                      </div>
                      <div>
                        <div className="score-val">{signal.error ? "—" : formatScore(signal.score)}</div>
                        <div className="score-sub">{contributionFor(signal, report)} wt</div>
                      </div>
                      <span className={expanded ? "chevron expanded" : "chevron"}>▸</span>
                    </div>
                    {expanded && (
                      <div className="expand-pad">
                        <p className="expand-blurb">{signalHeadline(signal)}</p>
                        <div className="expand-note">{signal.error || providerLabel(signal)}</div>
                        <div className="expand-meta">
                          confidence {formatScore(signal.confidence)} · model {signal.model_version}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {report.agent_findings.length > 0 && (
              <div className="section-card frame">
                <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
                <div className="section-label">// 03 · agent_findings.log</div>
                {report.agent_findings.map((finding: AgentFinding) => (
                  <div className="agent-row" key={finding.agent}>
                    <div className="agent-topline">
                      <strong className="agent-name">{finding.agent.replace(/_/g, " ")}</strong>
                      <span className="agent-meta">
                        {finding.score !== null
                          ? `score ${formatScore(finding.score)} · conf ${formatScore(finding.confidence)}`
                          : "no score returned"}
                      </span>
                    </div>
                    {finding.findings.length > 0 ? (
                      <ul className="findings-list">
                        {finding.findings.map((item, index) => (
                          <li key={`${finding.agent}-${index}`}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="no-findings">no findings reported</p>
                    )}
                  </div>
                ))}
              </div>
            )}

            <p className="disclaimer">{report.disclaimer}</p>
          </>
        )}
      </div>
    </main>
  );
}
