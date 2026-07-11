import type {
  ArtifactAccessResponse,
  AuditEvent,
  ClaimListItem,
  ClaimQueueStatus,
  StoredClaim,
  ReviewDecisionValue,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Reviewer auth: set NEXT_PUBLIC_API_KEY when the backend has API_AUTH_ENABLED=true.
// Unset by default, matching the backend's local-dev bypass — see dashboard/README.md.
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

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
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
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

export async function createArtifactAccessUrl(input: {
  claimId: string;
  artifactId: number;
}): Promise<ArtifactAccessResponse> {
  return fetchApi<ArtifactAccessResponse>(
    `/v1/claims/${input.claimId}/artifacts/${input.artifactId}/access`,
    { method: "POST" },
  );
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
