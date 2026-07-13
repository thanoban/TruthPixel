"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchClaim, fetchClaimAudit, fetchClaimStatus, submitDecision } from "../../api";
import { createSupabaseBrowserClient } from "../../lib/supabase-browser";
import { riskStamp, riskToneName } from "../../theme";
import type { AuditEvent, ClaimArtifact, ReviewDecisionValue, StoredClaim } from "../../types";
import {
  LAYER_LABELS,
  artifactProxyPath,
  formatPercent,
  formatTimestamp,
  humanizeEvent,
} from "../../types";

function getArtifact(claim: StoredClaim | null, kind: ClaimArtifact["kind"]): ClaimArtifact | null {
  return claim?.artifacts.find((artifact) => artifact.kind === kind) ?? null;
}

// Drag-to-reveal comparison between the original upload and the forensic heatmap overlay —
// shares the same implementation as webapp/app/page.tsx's HeatmapCompareSlider (duplicated,
// not imported — the two Next.js apps have no shared package to import across).
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
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="18 8 22 12 18 16" />
            <polyline points="6 8 2 12 6 16" />
            <line x1="2" x2="22" y1="12" y2="12" />
          </svg>
        </div>
      </div>
    </div>
  );
}

export default function ClaimDetailPage({ params }: { params: { claimId: string } }) {
  const [claim, setClaim] = useState<StoredClaim | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewerId, setReviewerId] = useState("");
  const [decision, setDecision] = useState<ReviewDecisionValue>("reject");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);
  const [expandedLayer, setExpandedLayer] = useState<string | null>(null);

  // Prefill from the signed-in Google identity (Supabase Auth session) instead of a free-text
  // guess — ties the audit trail's reviewer_id to a real authenticated account. Still editable:
  // a reviewer submitting on a colleague's behalf can override it.
  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    supabase.auth.getUser().then(({ data }) => {
      if (data.user?.email) {
        setReviewerId(data.user.email);
      }
    });
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [claimData, auditData] = await Promise.all([
          fetchClaim(params.claimId),
          fetchClaimAudit(params.claimId),
        ]);
        if (!cancelled) {
          setClaim(claimData);
          setAudit(auditData);
          if (claimData.decision?.reason) {
            setReason(claimData.decision.reason);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load claim");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [params.claimId, refreshTick]);

  useEffect(() => {
    if (!claim || (claim.status !== "pending" && claim.status !== "processing")) {
      return;
    }

    const interval = window.setInterval(async () => {
      try {
        const status = await fetchClaimStatus(params.claimId);
        if (status.status === "completed" || status.status === "failed") {
          setRefreshTick((current) => current + 1);
        }
      } catch {}
    }, 8000);

    return () => window.clearInterval(interval);
  }, [claim, params.claimId]);

  const originalArtifact = useMemo(() => getArtifact(claim, "original_upload"), [claim]);
  const heatmapArtifact = useMemo(() => getArtifact(claim, "heatmap"), [claim]);
  const l2Signal = useMemo(
    () => claim?.signals.find((signal) => signal.layer === "l2_forensics") ?? null,
    [claim]
  );
  const heatmapDiagnostic = useMemo(
    () => describeHeatmapState(l2Signal, heatmapArtifact),
    [heatmapArtifact, l2Signal]
  );

  async function handleDecisionSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const updatedClaim = await submitDecision({
        claimId: params.claimId,
        reviewerId,
        decision,
        reason,
      });
      setClaim(updatedClaim);
      setAudit(await fetchClaimAudit(params.claimId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save decision");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="detail-shell">
      <div className="detail-header">
        <Link href="/" className="back-link">
          ← Back to queue
        </Link>
        <button type="button" className="btn-secondary" onClick={() => setRefreshTick((current) => current + 1)}>
          Refresh
        </button>
      </div>

      {error && <p className="error-banner">{error}</p>}

      {loading || !claim ? (
        <div className="empty-panel">
          <h3>Loading claim...</h3>
        </div>
      ) : (
        <>
          {(() => {
            const tone = riskToneName(claim.fusion.risk_score);
            const stamp = riskStamp(claim.fusion.risk_score);
            const offset = 314.159 * (1 - claim.fusion.risk_score);
            return (
              <section className="frame detail-hero">
                <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
                <svg width="84" height="84" viewBox="0 0 120 120" style={{ flex: "none" }}>
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
                  <p className="eyebrow">// claim {claim.claim_id.slice(0, 8)}</p>
                  <h1 style={{ fontSize: 20 }}>{claim.context.order_id || "Unlabeled review item"}</h1>
                  <p className="hero-copy" style={{ margin: "8px 0 0" }}>
                    {claim.context.claim_reason || "No customer claim reason was submitted."}
                  </p>
                </div>
                <div style={{ textAlign: "right", flex: "none" }}>
                  <div className="risk-number">{formatPercent(claim.fusion.risk_score)}</div>
                  <div className="risk-label" style={{ color: `var(--${tone})` }}>
                    {claim.decision?.decision.replace(/_/g, " ") || claim.status}
                  </div>
                </div>
                <div className="stamp" style={{ color: `var(--${tone})`, borderColor: `var(--${tone})` }}>
                  {stamp}
                </div>
              </section>
            );
          })()}

          <section className="detail-grid">
            <article className="frame panel">
              <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
              <div className="panel-header">
                <div>
                  <div className="section-label">// 01 · manipulation_heatmap.render</div>
                  <p>Drag to compare original vs. forensic overlay.</p>
                </div>
              </div>
              {originalArtifact && heatmapArtifact ? (
                <HeatmapCompareSlider
                  originalSrc={artifactProxyPath(originalArtifact.claim_id, originalArtifact.id)}
                  heatmapSrc={artifactProxyPath(heatmapArtifact.claim_id, heatmapArtifact.id)}
                />
              ) : originalArtifact ? (
                <img
                  src={artifactProxyPath(originalArtifact.claim_id, originalArtifact.id)}
                  alt="Original claim upload"
                  style={{ width: "100%", maxHeight: 300, objectFit: "cover" }}
                />
              ) : (
                <p className="muted-copy">No original artifact is stored for this claim yet.</p>
              )}
              {heatmapDiagnostic && <p className="muted-copy" style={{ marginTop: 8 }}>{heatmapDiagnostic}</p>}
              <div className="artifact-strip">
                {claim.artifacts.map((artifact) => (
                  <a
                    key={artifact.id}
                    href={artifactProxyPath(artifact.claim_id, artifact.id)}
                    className="artifact-chip"
                    target="_blank"
                    rel="noreferrer"
                  >
                    <span>{artifact.kind.replace(/_/g, " ")}</span>
                    <strong>{artifact.filename}</strong>
                  </a>
                ))}
              </div>
            </article>

            <article className="frame panel">
              <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
              <div className="panel-header">
                <div>
                  <div className="section-label">// 02 · reviewer_decision.submit</div>
                  <p>Record the final reviewer outcome on the stored claim.</p>
                </div>
              </div>
              <form className="decision-form" onSubmit={handleDecisionSubmit}>
                <label>
                  Reviewer ID
                  <input
                    value={reviewerId}
                    onChange={(event) => setReviewerId(event.target.value)}
                    placeholder="reviewer-7"
                    required
                  />
                </label>
                <label>
                  Decision
                  <select value={decision} onChange={(event) => setDecision(event.target.value as ReviewDecisionValue)}>
                    <option value="approve">Approve</option>
                    <option value="reject">Reject</option>
                    <option value="needs_more_info">Needs more info</option>
                  </select>
                </label>
                <label>
                  Reason
                  <textarea
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    placeholder="Summarize the evidence that drove this call."
                    rows={5}
                  />
                </label>
                <button type="submit" disabled={saving || !reviewerId.trim()}>
                  {saving ? "Saving..." : "Record decision"}
                </button>
              </form>
              {claim.decision && (
                <div className="decision-summary">
                  <h3>Current reviewer decision</h3>
                  <p>
                    <strong>{claim.decision.decision.replace(/_/g, " ")}</strong> by{" "}
                    {claim.decision.reviewer_id} on {formatTimestamp(claim.decision.decided_at)}
                  </p>
                  {claim.decision.reason && <p>{claim.decision.reason}</p>}
                </div>
              )}
            </article>

            <article className="frame panel">
              <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
              <div className="panel-header">
                <div>
                  <div className="section-label">// 03 · signal_breakdown.json</div>
                  <p>Scores, confidence, and fusion contribution by analyzer layer.</p>
                </div>
              </div>
              {claim.signals.map((signal) => {
                const score = signal.score ?? 0;
                const tone = riskToneName(score);
                const expanded = expandedLayer === signal.layer;
                return (
                  <div className="signal-row-wrap" key={signal.layer}>
                    <div className="signal-row" onClick={() => setExpandedLayer(expanded ? null : signal.layer)}>
                      <span
                        className="badge"
                        style={{ background: `color-mix(in oklch, var(--${tone}) 16%, transparent)`, color: `var(--${tone})` }}
                      >
                        L{signal.layer.slice(1, 2)}
                      </span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="signal-label">{LAYER_LABELS[signal.layer] ?? signal.layer}</div>
                        <div className="bar-track">
                          <div className="bar-fill" style={{ width: `${Math.round(score * 100)}%`, background: `var(--${tone})` }} />
                        </div>
                      </div>
                      <div className="score-val">{signal.error ? "—" : formatPercent(signal.score)}</div>
                      <span className={expanded ? "chevron expanded" : "chevron"}>▸</span>
                    </div>
                    {expanded && (
                      <div className="expand-pad">
                        <div className="expand-note">
                          {signal.error || (typeof signal.evidence.note === "string" ? signal.evidence.note : "no note")}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
              <p className="report-copy">{claim.report_text}</p>
            </article>

            <article className="frame panel">
              <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
              <div className="panel-header">
                <div>
                  <div className="section-label">// 04 · audit_trail.log</div>
                  <p>Append-only event history from claim queueing through review action.</p>
                </div>
              </div>
              <div className="audit-list">
                {audit.map((event) => (
                  <div key={event.id} className="audit-item">
                    <div className="audit-meta">
                      <strong>{humanizeEvent(event.event_type)}</strong>
                      <span>{formatTimestamp(event.created_at)}</span>
                    </div>
                    {Object.keys(event.payload).length > 0 && (
                      <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                    )}
                  </div>
                ))}
              </div>
            </article>

            <article className="frame panel">
              <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
              <div className="panel-header">
                <div>
                  <div className="section-label">// 05 · agent_findings.log</div>
                  <p>Optional semantic reviewer notes captured during the agent pass.</p>
                </div>
              </div>
              {claim.agent_findings.length > 0 ? (
                <div className="agent-stack">
                  {claim.agent_findings.map((finding) => (
                    <div key={finding.agent} className="agent-card">
                      <div className="agent-topline">
                        <strong>{finding.agent.replace(/_/g, " ")}</strong>
                        <span>
                          {formatPercent(finding.score)} risk · {formatPercent(finding.confidence)} confidence
                        </span>
                      </div>
                      {finding.findings.length > 0 ? (
                        <ul>
                          {finding.findings.map((item, index) => (
                            <li key={`${finding.agent}-${index}`}>{item}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted-copy">No specific findings were returned.</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted-copy">This claim did not trigger the semantic agent pass.</p>
              )}
            </article>
          </section>
        </>
      )}
    </main>
  );
}

function describeHeatmapState(
  l2Signal: StoredClaim["signals"][number] | null,
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
