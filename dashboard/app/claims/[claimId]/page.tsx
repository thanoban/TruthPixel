"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  fetchClaim,
  fetchClaimAudit,
  fetchClaimStatus,
  fetchReviewerContext,
  submitDecision,
} from "../../api";
import type {
  AuditEvent,
  ClaimArtifact,
  ClaimQueueStatus,
  ReviewerContext,
  ReviewDecisionValue,
  StoredClaim,
} from "../../types";
import {
  LAYER_LABELS,
  artifactProxyPath,
  formatDecisionLabel,
  formatPercent,
  formatRelativeTimestamp,
  formatStatusLabel,
  formatTimestamp,
  humanizeEvent,
} from "../../types";

function getArtifact(claim: StoredClaim | null, kind: ClaimArtifact["kind"]): ClaimArtifact | null {
  return claim?.artifacts.find((artifact) => artifact.kind === kind) ?? null;
}

function decisionHelpText(decision: ReviewDecisionValue): string {
  switch (decision) {
    case "approve":
      return "Document why the claim can proceed without further intervention.";
    case "reject":
      return "Capture the strongest contradictory evidence before rejecting.";
    case "needs_more_info":
      return "State exactly what more evidence or workflow follow-up is required.";
  }
}

function decisionTone(decision: ReviewDecisionValue): string {
  switch (decision) {
    case "approve":
      return "approve";
    case "reject":
      return "reject";
    case "needs_more_info":
      return "more-info";
  }
}

export default function ClaimDetailPage({ params }: { params: { claimId: string } }) {
  const [claim, setClaim] = useState<StoredClaim | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [queueStatus, setQueueStatus] = useState<ClaimQueueStatus | null>(null);
  const [reviewerContext, setReviewerContext] = useState<ReviewerContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const [overlayOpacity, setOverlayOpacity] = useState(55);
  const [reviewerId, setReviewerId] = useState("reviewer-1");
  const [decision, setDecision] = useState<ReviewDecisionValue>("reject");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null);
  const [originalLoadFailed, setOriginalLoadFailed] = useState(false);
  const [heatmapLoadFailed, setHeatmapLoadFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load(showRefreshing: boolean) {
      try {
        if (showRefreshing) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }
        const [claimData, auditData, statusData, context] = await Promise.all([
          fetchClaim(params.claimId),
          fetchClaimAudit(params.claimId),
          fetchClaimStatus(params.claimId),
          fetchReviewerContext(),
        ]);
        if (!cancelled) {
          setError(null);
          setClaim(claimData);
          setAudit(auditData);
          setQueueStatus(statusData);
          setReviewerContext(context);
          setLastLoadedAt(new Date().toISOString());
          setOriginalLoadFailed(false);
          setHeatmapLoadFailed(false);
          setReviewerId((current) => {
            if (claimData.decision?.reviewer_id) {
              return claimData.decision.reviewer_id;
            }
            if (!current || current === "reviewer-1") {
              return context.reviewerIdDefault;
            }
            return current;
          });
          if (claimData.decision?.reason) {
            setReason(claimData.decision.reason);
            setDecision(claimData.decision.decision);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load claim");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    }

    void load(claim !== null);
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
        setQueueStatus(status);
        if (status.status === "completed" || status.status === "failed") {
          setRefreshTick((current) => current + 1);
        }
      } catch {}
    }, 8000);

    return () => window.clearInterval(interval);
  }, [claim, params.claimId]);

  const originalArtifact = useMemo(() => getArtifact(claim, "original_upload"), [claim]);
  const heatmapArtifact = useMemo(() => getArtifact(claim, "heatmap"), [claim]);
  const canRecordDecision = claim?.status === "completed";
  const artifactCountLabel = `${claim?.artifacts.length ?? 0} artifact${
    (claim?.artifacts.length ?? 0) === 1 ? "" : "s"
  }`;

  async function handleDecisionSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedReviewerId = reviewerId.trim();
    const trimmedReason = reason.trim();
    if (!trimmedReviewerId) {
      setError("Reviewer ID is required.");
      return;
    }
    if (decision !== "approve" && !trimmedReason) {
      setError("Add a reason before rejecting a claim or requesting more information.");
      return;
    }

    setSaving(true);
    setError(null);
    setSaveNotice(null);
    try {
      const updatedClaim = await submitDecision({
        claimId: params.claimId,
        reviewerId: trimmedReviewerId,
        decision,
        reason: trimmedReason,
      });
      setClaim(updatedClaim);
      const [auditData, statusData] = await Promise.all([
        fetchClaimAudit(params.claimId),
        fetchClaimStatus(params.claimId),
      ]);
      setAudit(auditData);
      setQueueStatus(statusData);
      setSaveNotice("Reviewer decision saved.");
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
        <div className="toolbar-actions">
          <span className="refresh-meta">
            {lastLoadedAt ? `Synced ${formatRelativeTimestamp(lastLoadedAt)}` : "Not synced yet"}
          </span>
          <button
            type="button"
            className="secondary-button"
            onClick={() => setRefreshTick((current) => current + 1)}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      {error && <p className="error-banner">{error}</p>}
      {saveNotice && <p className="success-banner">{saveNotice}</p>}

      {loading || !claim ? (
        <div className="empty-panel">
          <h3>Loading claim...</h3>
          <p>Pulling stored evidence, queue state, and reviewer history.</p>
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
              <div className="detail-badges">
                <span className={`pill ${claim.decision ? decisionTone(claim.decision.decision) : claim.status}`}>
                  {claim.decision ? formatDecisionLabel(claim.decision.decision) : formatStatusLabel(claim.status)}
                </span>
                {claim.fusion.needs_review && !claim.decision && (
                  <span className="subtle-pill attention">manual review recommended</span>
                )}
                {claim.tenant_id && <span className="subtle-pill">tenant: {claim.tenant_id}</span>}
                {reviewerContext && (
                  <span className="subtle-pill">{reviewerContext.authMode.replace(/_/g, " ")}</span>
                )}
              </div>
            </div>
            <div className="detail-metrics">
              <div className="metric-card">
                <span>Risk score</span>
                <strong>{formatPercent(claim.fusion.risk_score)}</strong>
              </div>
              <div className="metric-card">
                <span>Status</span>
                <strong>{claim.decision ? formatDecisionLabel(claim.decision.decision) : formatStatusLabel(claim.status)}</strong>
              </div>
              <div className="metric-card">
                <span>Updated</span>
                <strong>{formatTimestamp(claim.updated_at)}</strong>
              </div>
              <div className="metric-card">
                <span>Artifacts</span>
                <strong>{artifactCountLabel}</strong>
              </div>
            </div>
          </section>

          <section className="status-strip">
            <div className="status-card">
              <span>Queue state</span>
              <strong>{formatStatusLabel(queueStatus?.status ?? claim.status)}</strong>
              <p>
                Created {formatTimestamp(claim.created_at)}
                {" · "}
                Started {formatTimestamp(queueStatus?.started_at ?? claim.started_at)}
                {" · "}
                Completed {formatTimestamp(queueStatus?.completed_at ?? claim.completed_at)}
              </p>
            </div>
            <div className="status-card">
              <span>Reviewer lane</span>
              <strong>
                {claim.decision
                  ? `Handled by ${claim.decision.reviewer_id}`
                  : canRecordDecision
                    ? "Ready for decision"
                    : "Waiting on processing"}
              </strong>
              <p>{reviewerContext?.authHint || "The dashboard proxies the same stored-claim endpoints used elsewhere."}</p>
            </div>
            <div className="status-card">
              <span>Task info</span>
              <strong>{queueStatus?.task_id || claim.task_id || "Inline / no task id"}</strong>
              <p>{queueStatus?.error_message || claim.error_message || "No queue error is recorded for this claim."}</p>
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
              <div className="artifact-actions">
                {originalArtifact && (
                  <a
                    href={artifactProxyPath(originalArtifact.claim_id, originalArtifact.id)}
                    className="secondary-button button-link"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open original
                  </a>
                )}
                {heatmapArtifact && (
                  <a
                    href={artifactProxyPath(heatmapArtifact.claim_id, heatmapArtifact.id)}
                    className="secondary-button button-link"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open heatmap
                  </a>
                )}
              </div>
              {originalArtifact ? (
                <div className="overlay-stage">
                  {!originalLoadFailed ? (
                    <img
                      key={`${originalArtifact.id}-${refreshTick}`}
                      src={artifactProxyPath(originalArtifact.claim_id, originalArtifact.id)}
                      alt="Original claim upload"
                      className="stage-image"
                      onError={() => setOriginalLoadFailed(true)}
                    />
                  ) : (
                    <div className="artifact-fallback">
                      <h3>Original preview unavailable</h3>
                      <p>
                        The stored file could not be rendered inline. Open the original artifact in
                        a new tab to inspect it directly.
                      </p>
                    </div>
                  )}
                  {heatmapArtifact && !heatmapLoadFailed && (
                    <img
                      key={`${heatmapArtifact.id}-${refreshTick}`}
                      src={artifactProxyPath(heatmapArtifact.claim_id, heatmapArtifact.id)}
                      alt="Heatmap overlay"
                      className="stage-image overlay-image"
                      style={{ opacity: overlayOpacity / 100 }}
                      onError={() => setHeatmapLoadFailed(true)}
                    />
                  )}
                </div>
              ) : (
                <p className="muted-copy">No original artifact is stored for this claim yet.</p>
              )}
              {heatmapArtifact && heatmapLoadFailed && (
                <p className="inline-warning">
                  Heatmap overlay could not be rendered inline. Use the direct heatmap link above.
                </p>
              )}
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
                <div className="choice-group" role="radiogroup" aria-label="Decision">
                  {(["approve", "reject", "needs_more_info"] as ReviewDecisionValue[]).map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={option === decision ? "choice-button active" : "choice-button"}
                      onClick={() => setDecision(option)}
                    >
                      {formatDecisionLabel(option)}
                    </button>
                  ))}
                </div>
                <label>
                  Reason
                  <textarea
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    placeholder="Summarize the evidence that drove this call."
                    rows={5}
                  />
                </label>
                <p className="field-hint">{decisionHelpText(decision)}</p>
                {!canRecordDecision && (
                  <p className="inline-warning">
                    Reviewer decisions unlock once analysis is completed successfully.
                  </p>
                )}
                <button type="submit" disabled={saving || !reviewerId.trim() || !canRecordDecision}>
                  {saving
                    ? "Saving..."
                    : claim.decision
                      ? "Update decision"
                      : "Record decision"}
                </button>
              </form>
              {claim.decision && (
                <div className="decision-summary">
                  <h3>Current reviewer decision</h3>
                  <p>
                    <strong>{formatDecisionLabel(claim.decision.decision)}</strong> by{" "}
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
                {audit.length > 0 ? (
                  audit.map((event) => (
                    <div key={event.id} className="audit-item">
                      <div className="audit-meta">
                        <strong>{humanizeEvent(event.event_type)}</strong>
                        <span>{formatTimestamp(event.created_at)}</span>
                      </div>
                      {Object.keys(event.payload).length > 0 && (
                        <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="muted-copy">No audit events were recorded for this claim.</p>
                )}
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
