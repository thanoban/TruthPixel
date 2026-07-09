// Mirrors backend/app/schemas.py — keep in sync manually until an OpenAPI codegen step exists.

export type LayerId = "l1_aigen" | "l2_forensics" | "l3_recapture" | "l4_metadata" | "l5_context";
export type ClaimStatus = "pending" | "processing" | "completed" | "failed";
export type ReviewDecisionValue = "approve" | "reject" | "needs_more_info";
export type ArtifactKind = "original_upload" | "heatmap";

export interface SignalResult {
  layer: LayerId;
  score: number | null;
  confidence: number;
  evidence: Record<string, unknown>;
  error: string | null;
  model_version: string;
}

export interface AgentFinding {
  agent: string;
  score: number | null;
  confidence: number;
  findings: string[];
  model: string;
}

export interface FusionResult {
  risk_score: number;
  needs_review: boolean;
  contributions: Record<string, number>;
  fusion_version: string;
}

// Always present on the backend response, even when the public webapp submits no
// order/listing fields.
export interface ClaimContext {
  order_id: string;
  product_sku: string;
  claim_reason: string;
  listing_image_urls: string[];
}

export interface ClaimReport {
  claim_id: string;
  context: ClaimContext;
  signals: SignalResult[];
  agent_findings: AgentFinding[];
  fusion: FusionResult;
  report_text: string;
  disclaimer: string;
}

export interface ClaimDecision {
  reviewer_id: string;
  decision: ReviewDecisionValue;
  reason: string;
  decided_at: string;
}

export interface ClaimArtifact {
  id: number;
  claim_id: string;
  kind: ArtifactKind;
  filename: string;
  media_type: string;
  byte_size: number;
  sha256: string;
  storage_backend: string;
  download_path: string;
  created_at: string;
}

// Backend POST /v1/claims actually returns StoredClaim (a superset of ClaimReport) —
// see backend/app/schemas.py::StoredClaim. Use this type for the /v1/claims response.
export interface StoredClaim extends ClaimReport {
  tenant_id: string | null;
  created_at: string;
  updated_at: string;
  status: ClaimStatus;
  task_id: string | null;
  error_message: string | null;
  webhook_url: string | null;
  started_at: string | null;
  completed_at: string | null;
  decision: ClaimDecision | null;
  artifacts: ClaimArtifact[];
}

export const LAYER_LABELS: Record<LayerId, string> = {
  l1_aigen: "AI-generation detection",
  l2_forensics: "Manipulation / edit forensics",
  l3_recapture: "Screenshot / recapture detection",
  l4_metadata: "Metadata & provenance",
  l5_context: "Product context cross-check",
};

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return value.toFixed(2);
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function getArtifactByKind(
  artifacts: ClaimArtifact[],
  kind: ArtifactKind,
): ClaimArtifact | undefined {
  return artifacts.find((artifact) => artifact.kind === kind);
}

export function describeSubmissionScope(claim: StoredClaim): string {
  if (claim.tenant_id === null) {
    return "Anonymous public submission";
  }
  if (claim.tenant_id === "local-dev") {
    return "Local dev submission";
  }
  return "Tenant API-key submission";
}
