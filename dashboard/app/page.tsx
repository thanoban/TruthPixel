"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fetchClaimQueue, fetchDashboardRuntime } from "./api";
import type { ClaimListItem, DashboardRuntime } from "./types";
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
  const [runtime, setRuntime] = useState<DashboardRuntime | null>(null);
  const [view, setView] = useState<QueueView>("review");
  const [claims, setClaims] = useState<ClaimListItem[]>([]);
  const [search, setSearch] = useState("");
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
        const [runtimeData, items] = await Promise.all([
          fetchDashboardRuntime(),
          fetchClaimQueue({ limit: 40, ...QUEUE_COPY[view].params }),
        ]);
        if (!cancelled) {
          setRuntime(runtimeData);
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

  const filteredClaims = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return claims;
    }
    return claims.filter((item) =>
      [
        item.claim_id,
        item.context.order_id,
        item.context.product_sku,
        item.context.claim_reason,
      ]
        .filter(Boolean)
        .some((value) => value.toLowerCase().includes(query)),
    );
  }, [claims, search]);

  const totalFlagged = filteredClaims.filter((item) => item.fusion.needs_review).length;
  const totalPending = filteredClaims.filter((item) => item.status !== "completed").length;

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
          {runtime && (
            <div className="workspace-note">
              <strong>{runtime.tenant_label}</strong>
              <span>
                {runtime.reviewer_auth_mode === "tenant_api_key_proxy"
                  ? "Single-tenant pilot mode with server-side API-key proxy."
                  : "Local-dev bypass mode; backend auth is effectively off for this reviewer surface."}
              </span>
            </div>
          )}
        </div>
        <div className="hero-metrics">
          <div className="metric-card">
            <span>Claims shown</span>
            <strong>{filteredClaims.length}</strong>
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
          <div className="toolbar-actions">
            <label className="search-field">
              <span>Find claim</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Order ID, SKU, reason, or claim ID"
              />
            </label>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setRefreshTick((current) => current + 1)}
            >
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
      </section>

      {error && <p className="error-banner">{error}</p>}

      {loading ? (
        <div className="empty-panel">
          <h3>Loading queue...</h3>
        </div>
      ) : filteredClaims.length === 0 ? (
        <EmptyState view={view} />
      ) : (
        <section className="queue-grid">
          {filteredClaims.map((item) => (
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
