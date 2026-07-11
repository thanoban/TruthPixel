export type LayerId = "l1_aigen" | "l2_forensics" | "l3_recapture" | "l4_metadata" | "l5_context";

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

export interface ClaimContext {
  order_id: string;
  product_sku: string;
  claim_reason: string;
  listing_image_urls: string[];
}

export type ClaimStatus = "pending" | "processing" | "completed" | "failed";
export type ReviewDecisionValue = "approve" | "reject" | "needs_more_info";
export type ArtifactKind = "original_upload" | "heatmap";

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

export interface ArtifactAccessResponse {
  download_url: string;
  expires_at: string;
}

export interface AuditEvent {
  id: number;
  claim_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ClaimQueueStatus {
  claim_id: string;
  status: ClaimStatus;
  task_id: string | null;
  error_message: string | null;
  webhook_url: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  poll_path: string;
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

export interface StoredClaim extends ClaimReport {
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

export interface ClaimListItem {
  claim_id: string;
  created_at: string;
  updated_at: string;
  status: ClaimStatus;
  task_id: string | null;
  error_message: string | null;
  context: ClaimContext;
  fusion: FusionResult;
  decision: ClaimDecision | null;
  signal_count: number;
  artifact_count: number;
}

export const LAYER_LABELS: Record<LayerId, string> = {
  l1_aigen: "AI-generation detection",
  l2_forensics: "Edit forensics",
  l3_recapture: "Screenshot / recapture",
  l4_metadata: "Metadata & provenance",
  l5_context: "Claim context cross-check",
};

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
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

export function humanizeEvent(eventType: string): string {
  return eventType.replace(/_/g, " ");
}
