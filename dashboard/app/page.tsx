"use client";

import Link from "next/link";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { fetchClaimQueue, fetchReviewerContext } from "./api";
import type { ClaimListItem, ReviewerContext } from "./types";
import {
  formatPercent,
  formatRelativeTimestamp,
  formatStatusLabel,
  formatTimestamp,
} from "./types";

type QueueView = "review" | "open" | "decided";
type QueueBucket = "ready" | "processing" | "failed" | "decided";

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

function EmptyState({ view, searchTerm }: { view: QueueView; searchTerm: string }) {
  return (
    <div className="empty-panel">
      <h3>
        {searchTerm
          ? "No claims match the current search"
          : `No claims in ${QUEUE_COPY[view].title.toLowerCase()}`}
      </h3>
      <p>
        {searchTerm
          ? "Try a different claim ID, order ID, SKU, tenant, or reviewer."
          : "Run the public webapp or async API to create a claim, then refresh this queue."}
      </p>
    </div>
  );
}

function sortClaims(items: ClaimListItem[]): ClaimListItem[] {
  return [...items].sort((left, right) => {
    if (left.status !== right.status) {
      const order = ["failed", "processing", "pending", "completed"];
      return order.indexOf(left.status) - order.indexOf(right.status);
    }
    if (left.fusion.risk_score !== right.fusion.risk_score) {
      return right.fusion.risk_score - left.fusion.risk_score;
    }
    return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
  });
}

function bucketForClaim(item: ClaimListItem): QueueBucket {
  if (item.decision) {
    return "decided";
  }
  if (item.status === "failed") {
    return "failed";
  }
  if (item.status === "pending" || item.status === "processing") {
    return "processing";
  }
  return "ready";
}

function matchesSearch(item: ClaimListItem, search: string): boolean {
  if (!search) {
    return true;
  }

  const haystack = [
    item.claim_id,
    item.tenant_id || "",
    item.context.order_id,
    item.context.product_sku,
    item.context.claim_reason,
    item.decision?.reviewer_id || "",
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(search.toLowerCase());
}

function sectionCopy(bucket: QueueBucket): { title: string; subtitle: string } {
  switch (bucket) {
    case "ready":
      return {
        title: "Ready for a reviewer",
        subtitle: "Completed claims with evidence ready and no reviewer decision yet.",
      };
    case "processing":
      return {
        title: "Still running",
        subtitle: "Queued or processing claims that should auto-refresh into review-ready items.",
      };
    case "failed":
      return {
        title: "Processing failed",
        subtitle: "Claims that need a retry or backend follow-up before a reviewer can decide.",
      };
    case "decided":
      return {
        title: "Recently decided",
        subtitle: "Closed claims kept visible for QA, reversals, and audit checks.",
      };
  }
}

export default function ReviewerQueuePage() {
  const [view, setView] = useState<QueueView>("review");
  const [claims, setClaims] = useState<ClaimListItem[]>([]);
  const [reviewerContext, setReviewerContext] = useState<ReviewerContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(searchTerm);

  useEffect(() => {
    let cancelled = false;

    async function load(showRefreshing: boolean) {
      try {
        if (showRefreshing) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }
        const [items, context] = await Promise.all([
          fetchClaimQueue({ limit: 60, ...QUEUE_COPY[view].params }),
          fetchReviewerContext(),
        ]);
        if (!cancelled) {
          setError(null);
          setClaims(items);
          setReviewerContext(context);
          setLastLoadedAt(new Date().toISOString());
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

    void load(claims.length > 0 || reviewerContext !== null);
    const interval = autoRefresh ? window.setInterval(() => void load(true), 15000) : null;

    return () => {
      cancelled = true;
      if (interval !== null) {
        window.clearInterval(interval);
      }
    };
  }, [autoRefresh, view, refreshTick]);

  const totalFlagged = claims.filter((item) => item.fusion.needs_review).length;
  const totalQueued = claims.filter(
    (item) => item.status === "pending" || item.status === "processing",
  ).length;
  const totalFailed = claims.filter((item) => item.status === "failed").length;

  const filteredClaims = useMemo(
    () => sortClaims(claims.filter((item) => matchesSearch(item, deferredSearch.trim()))),
    [claims, deferredSearch],
  );

  const groupedClaims = useMemo(() => {
    const groups: Record<QueueBucket, ClaimListItem[]> = {
      ready: [],
      processing: [],
      failed: [],
      decided: [],
    };
    for (const item of filteredClaims) {
      groups[bucketForClaim(item)].push(item);
    }
    return groups;
  }, [filteredClaims]);

  const sections = useMemo(() => {
    const sectionOrder: QueueBucket[] =
      view === "decided" ? ["decided"] : ["ready", "processing", "failed"];
    return sectionOrder
      .map((bucket) => ({
        bucket,
        items: groupedClaims[bucket],
        ...sectionCopy(bucket),
      }))
      .filter((section) => section.items.length > 0);
  }, [groupedClaims, view]);

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
          {reviewerContext && (
            <div className="reviewer-context-banner">
              <div>
                <strong>{reviewerContext.dashboardLabel}</strong>
                <p>{reviewerContext.authHint}</p>
              </div>
              <div className="context-badges">
                <span className="subtle-pill">{reviewerContext.authMode.replace(/_/g, " ")}</span>
                <span className="subtle-pill">
                  reviewer default: {reviewerContext.reviewerIdDefault}
                </span>
                {(reviewerContext.tenantLabel || filteredClaims[0]?.tenant_id) && (
                  <span className="subtle-pill">
                    tenant: {reviewerContext.tenantLabel || filteredClaims[0]?.tenant_id}
                  </span>
                )}
              </div>
            </div>
          )}
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
            <span>Still running</span>
            <strong>{totalQueued}</strong>
          </div>
          <div className="metric-card">
            <span>Failed runs</span>
            <strong>{totalFailed}</strong>
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
            <label className="switch-row">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(event) => setAutoRefresh(event.target.checked)}
              />
              Auto-refresh
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
        <div className="queue-controls">
          <label className="search-field">
            <span>Search queue</span>
            <input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Claim ID, order ID, SKU, tenant, reviewer"
            />
          </label>
          <div className="refresh-meta">
            <span>{lastLoadedAt ? `Last synced ${formatRelativeTimestamp(lastLoadedAt)}` : "Not synced yet"}</span>
            <span>{refreshing ? "Refreshing in background" : autoRefresh ? "Auto-refresh every 15s" : "Manual refresh only"}</span>
          </div>
        </div>
      </section>

      {error && (
        <div className="error-banner">
          <strong>Queue refresh failed.</strong> {error}
        </div>
      )}

      {loading ? (
        <div className="empty-panel">
          <h3>Loading queue...</h3>
          <p>Connecting the reviewer surface to the stored-claim queue.</p>
        </div>
      ) : filteredClaims.length === 0 ? (
        <EmptyState view={view} searchTerm={deferredSearch} />
      ) : (
        <div className="queue-sections">
          {sections.map((section) => (
            <section key={section.bucket} className="queue-section">
              <div className="section-header">
                <div>
                  <h3>{section.title}</h3>
                  <p>{section.subtitle}</p>
                </div>
                <span className="section-count">{section.items.length}</span>
              </div>
              <div className="queue-grid">
                {section.items.map((item) => (
                  <Link key={item.claim_id} href={`/claims/${item.claim_id}`} className="claim-card">
                    <div className="card-topline">
                      <div className="card-pill-row">
                        <StatusPill item={item} />
                        {item.fusion.needs_review && !item.decision && (
                          <span className="subtle-pill attention">manual review</span>
                        )}
                      </div>
                      <span className="timestamp">{formatRelativeTimestamp(item.updated_at)}</span>
                    </div>
                    <div className="claim-title-block">
                      <h3>{item.context.order_id || item.claim_id}</h3>
                      <p className="claim-id">{item.claim_id}</p>
                    </div>
                    <p className="claim-meta">
                      {item.context.product_sku || "No SKU"}
                      {" · "}
                      {item.context.claim_reason || "No claim reason provided"}
                    </p>
                    <div className="meta-stack">
                      <span>Created {formatTimestamp(item.created_at)}</span>
                      <span>Updated {formatTimestamp(item.updated_at)}</span>
                      {item.tenant_id && <span>Tenant {item.tenant_id}</span>}
                      {item.decision && <span>Reviewer {item.decision.reviewer_id}</span>}
                    </div>
                    {item.error_message && <p className="inline-warning">{item.error_message}</p>}
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
                      <span>
                        {item.decision
                          ? `Decision recorded: ${item.decision.decision.replace(/_/g, " ")}`
                          : item.status === "completed"
                            ? "Evidence ready for reviewer"
                            : `Claim ${formatStatusLabel(item.status)}`}
                      </span>
                      <span className="link-arrow">Open claim</span>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
