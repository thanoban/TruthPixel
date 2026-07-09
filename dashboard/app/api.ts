import type {
  AuditEvent,
  ClaimListItem,
  ClaimQueueStatus,
  ReviewerContext,
  StoredClaim,
  ReviewDecisionValue,
} from "./types";

const DASHBOARD_API_URL = "/api";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") {
      return payload.detail;
    }
  } catch {}
  return `${response.status} ${response.statusText}`;
}

export async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const hasBody = init?.body !== undefined && init?.body !== null;
  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${DASHBOARD_API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as T;
}

export async function fetchClaimQueue(params: {
  limit?: number;
  needsReview?: boolean;
  decided?: boolean;
}): Promise<ClaimListItem[]> {
  const search = new URLSearchParams();
  if (params.limit) {
    search.set("limit", String(params.limit));
  }
  if (params.needsReview !== undefined) {
    search.set("needs_review", String(params.needsReview));
  }
  if (params.decided !== undefined) {
    search.set("decided", String(params.decided));
  }
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchApi<ClaimListItem[]>(`/claims${suffix}`);
}

export async function fetchClaim(claimId: string): Promise<StoredClaim> {
  return fetchApi<StoredClaim>(`/claims/${claimId}`);
}

export async function fetchClaimAudit(claimId: string): Promise<AuditEvent[]> {
  return fetchApi<AuditEvent[]>(`/claims/${claimId}/audit`);
}

export async function fetchClaimStatus(claimId: string): Promise<ClaimQueueStatus> {
  return fetchApi<ClaimQueueStatus>(`/claims/${claimId}/status`);
}

export async function submitDecision(input: {
  claimId: string;
  reviewerId: string;
  decision: ReviewDecisionValue;
  reason: string;
}): Promise<StoredClaim> {
  return fetchApi<StoredClaim>(`/claims/${input.claimId}/decision`, {
    method: "POST",
    body: JSON.stringify({
      reviewer_id: input.reviewerId,
      decision: input.decision,
      reason: input.reason,
    }),
  });
}

export async function fetchReviewerContext(): Promise<ReviewerContext> {
  return fetchApi<ReviewerContext>("/reviewer-context");
}
