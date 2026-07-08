"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchClaimQueue } from "./api";
import type { ClaimListItem } from "./types";
import { formatPercent, formatTimestamp } from "./types";

type QueueView = "review" | "open" | "decided";

const QUEUE_COPY: Record<
  QueueView,
  { title: string; subtitle: string; params: { needsReview?: boolean; decided?: boolean } }
> = {
  review: {
    title: "Needs review",
    subtitle: "Highest-signal claims that the fusion engine wants a human to inspect.",
    params: { needsReview: true, decided: false },
  },
  open: {
    title: "Open queue",
    subtitle: "All undecided claims, including async jobs still processing.",
    params: { decided: false },
  },
  decided: {
    title: "Decision history",
    subtitle: "Recently closed claims for QA, reversals, and audit follow-up.",
    params: { decided: true },
  },
};

function StatusPill({ item }: { item: ClaimListItem }) {
  const label = item.decision ? item.decision.decision.replace(/_/g, " ") : item.status;
  const tone = item.decision
    ? item.decision.decision === "approve"
      ? "approve"
      : item.decision.decision === "reject"
        ? "reject"
        : "more-info"
    : item.status;
  return <span className={`pill ${tone}`}>{label}</span>;
}

function EmptyState({ view }: { view: QueueView }) {
  return (
    <div className="empty-panel">
      <h3>No claims in {QUEUE_COPY[view].title.toLowerCase()}</h3>
      <p>Run the public webapp or async API to create a claim, then refresh this queue.</p>
    </div>
  );
}

export default function ReviewerQueuePage() {
  const [view, setView] = useState<QueueView>("review");
  const [claims, setClaims] = useState<ClaimListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load(showRefreshing: boolean) {
      try {
        if (showRefreshing) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }
        setError(null);
        const items = await fetchClaimQueue({ limit: 40, ...QUEUE_COPY[view].params });
        if (!cancelled) {
          setClaims(items);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load queue");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    }

    void load(false);
    const interval = window.setInterval(() => void load(true), 15000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [view, refreshTick]);

  const totalFlagged = claims.filter((item) => item.fusion.needs_review).length;
  const totalPending = claims.filter((item) => item.status !== "completed").length;

  return (
    <main className="dashboard-shell">
      <section className="hero-card">
        <div>
          <p className="eyebrow">TruthPixel reviewer dashboard</p>
          <h1>Queue triage for suspicious claim photos</h1>
          <p className="hero-copy">
            Move from risk score to evidence, artifacts, and reviewer decisions without leaving
            the stored-claim API surface.
          </p>
        </div>
        <div className="hero-metrics">
          <div className="metric-card">
            <span>Claims loaded</span>
            <strong>{claims.length}</strong>
          </div>
          <div className="metric-card">
            <span>Flagged</span>
            <strong>{totalFlagged}</strong>
          </div>
          <div className="metric-card">
            <span>Not finished</span>
            <strong>{totalPending}</strong>
          </div>
        </div>
      </section>

      <section className="toolbar">
        <div className="tab-row">
          {(Object.keys(QUEUE_COPY) as QueueView[]).map((queueView) => (
            <button
              key={queueView}
              type="button"
              className={queueView === view ? "tab active" : "tab"}
              onClick={() => setView(queueView)}
            >
              {QUEUE_COPY[queueView].title}
            </button>
          ))}
        </div>
        <div className="toolbar-meta">
          <div>
            <h2>{QUEUE_COPY[view].title}</h2>
            <p>{QUEUE_COPY[view].subtitle}</p>
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={() => setRefreshTick((current) => current + 1)}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </section>

      {error && <p className="error-banner">{error}</p>}

      {loading ? (
        <div className="empty-panel">
          <h3>Loading queue...</h3>
        </div>
      ) : claims.length === 0 ? (
        <EmptyState view={view} />
      ) : (
        <section className="queue-grid">
          {claims.map((item) => (
            <Link key={item.claim_id} href={`/claims/${item.claim_id}`} className="claim-card">
              <div className="card-topline">
                <StatusPill item={item} />
                <span className="timestamp">{formatTimestamp(item.updated_at)}</span>
              </div>
              <h3>{item.context.order_id || item.claim_id}</h3>
              <p className="claim-meta">
                {item.context.product_sku || "No SKU"}
                {" · "}
                {item.context.claim_reason || "No claim reason provided"}
              </p>
              <div className="risk-row">
                <div>
                  <span className="label">Risk</span>
                  <strong>{formatPercent(item.fusion.risk_score)}</strong>
                </div>
                <div>
                  <span className="label">Signals</span>
                  <strong>{item.signal_count}</strong>
                </div>
                <div>
                  <span className="label">Artifacts</span>
                  <strong>{item.artifact_count}</strong>
                </div>
              </div>
              <div className="card-footer">
                <span>{item.fusion.needs_review ? "Manual review recommended" : "Low urgency"}</span>
                <span className="link-arrow">Open claim</span>
              </div>
            </Link>
          ))}
        </section>
      )}
    </main>
  );
}
