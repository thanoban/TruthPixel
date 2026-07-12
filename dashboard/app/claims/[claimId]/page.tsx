"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fetchClaim, fetchClaimAudit, fetchClaimStatus, submitDecision } from "../../api";
import { createSupabaseBrowserClient } from "../../lib/supabase-browser";
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

export default function ClaimDetailPage({ params }: { params: { claimId: string } }) {
  const [claim, setClaim] = useState<StoredClaim | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overlayOpacity, setOverlayOpacity] = useState(55);
  const [reviewerId, setReviewerId] = useState("");
  const [decision, setDecision] = useState<ReviewDecisionValue>("reject");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

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
          Back to queue
        </Link>
        <button type="button" className="secondary-button" onClick={() => setRefreshTick((current) => current + 1)}>
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
          <section className="detail-hero">
            <div>
              <p className="eyebrow">Claim {claim.claim_id}</p>
              <h1>{claim.context.order_id || "Unlabeled review item"}</h1>
              <p className="hero-copy">
                {claim.context.claim_reason || "No customer claim reason was submitted."}
              </p>
            </div>
            <div className="detail-metrics">
              <div className="metric-card">
                <span>Risk score</span>
                <strong>{formatPercent(claim.fusion.risk_score)}</strong>
              </div>
              <div className="metric-card">
                <span>Status</span>
                <strong>{claim.decision?.decision.replace(/_/g, " ") || claim.status}</strong>
              </div>
              <div className="metric-card">
                <span>Updated</span>
                <strong>{formatTimestamp(claim.updated_at)}</strong>
              </div>
            </div>
          </section>

          <section className="detail-grid">
            <article className="panel preview-panel">
              <div className="panel-header">
                <div>
                  <h2>Artifact preview</h2>
                  <p>Original upload with optional heatmap overlay from the artifact store.</p>
                </div>
                {heatmapArtifact && (
                  <label className="opacity-control">
                    Heatmap opacity
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={overlayOpacity}
                      onChange={(event) => setOverlayOpacity(Number(event.target.value))}
                    />
                  </label>
                )}
              </div>
              {originalArtifact ? (
                <div className="overlay-stage">
                  <img
                    src={artifactProxyPath(originalArtifact.claim_id, originalArtifact.id)}
                    alt="Original claim upload"
                    className="stage-image"
                  />
                  {heatmapArtifact && (
                    <img
                      src={artifactProxyPath(heatmapArtifact.claim_id, heatmapArtifact.id)}
                      alt="Heatmap overlay"
                      className="stage-image overlay-image"
                      style={{ opacity: overlayOpacity / 100 }}
                    />
                  )}
                </div>
              ) : (
                <p className="muted-copy">No original artifact is stored for this claim yet.</p>
              )}
              {heatmapDiagnostic && <p className="muted-copy">{heatmapDiagnostic}</p>}
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

            <article className="panel">
              <div className="panel-header">
                <div>
                  <h2>Decision</h2>
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

            <article className="panel">
              <div className="panel-header">
                <div>
                  <h2>Signal breakdown</h2>
                  <p>Scores, confidence, and fusion contribution by analyzer layer.</p>
                </div>
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
                  {claim.signals.map((signal) => (
                    <tr key={signal.layer}>
                      <td>{LAYER_LABELS[signal.layer] ?? signal.layer}</td>
                      <td>{signal.error ? "unavailable" : formatPercent(signal.score)}</td>
                      <td>{formatPercent(signal.confidence)}</td>
                      <td>{formatPercent(claim.fusion.contributions[signal.layer])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="report-copy">{claim.report_text}</p>
            </article>

            <article className="panel">
              <div className="panel-header">
                <div>
                  <h2>Audit trail</h2>
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

            <article className="panel">
              <div className="panel-header">
                <div>
                  <h2>Agent findings</h2>
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
