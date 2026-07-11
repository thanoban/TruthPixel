import type {
  AuditEvent,
  ClaimListItem,
  ClaimQueueStatus,
  DashboardRuntime,
  StoredClaim,
  ReviewDecisionValue,
} from "./types";

export const DASHBOARD_API_ROOT = "/api";

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
  const response = await fetch(`${DASHBOARD_API_ROOT}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
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
  return fetchApi<ClaimListItem[]>(`/v1/claims${suffix}`);
}

export async function fetchClaim(claimId: string): Promise<StoredClaim> {
  return fetchApi<StoredClaim>(`/v1/claims/${claimId}`);
}

export async function fetchClaimAudit(claimId: string): Promise<AuditEvent[]> {
  return fetchApi<AuditEvent[]>(`/v1/claims/${claimId}/audit`);
}

export async function fetchClaimStatus(claimId: string): Promise<ClaimQueueStatus> {
  return fetchApi<ClaimQueueStatus>(`/v1/claims/${claimId}/status`);
}

export async function fetchDashboardRuntime(): Promise<DashboardRuntime> {
  return fetchApi<DashboardRuntime>("/runtime");
}

export async function submitDecision(input: {
  claimId: string;
  reviewerId: string;
  decision: ReviewDecisionValue;
  reason: string;
}): Promise<StoredClaim> {
  return fetchApi<StoredClaim>(`/v1/claims/${input.claimId}/decision`, {
    method: "POST",
    body: JSON.stringify({
      reviewer_id: input.reviewerId,
      decision: input.decision,
      reason: input.reason,
    }),
  });
}

export function getDashboardArtifactPath(downloadPath: string): string {
  return downloadPath.replace(/^\/v1\//, `${DASHBOARD_API_ROOT}/`);
}
