// Mirrors backend/app/schemas.py — keep in sync manually until an OpenAPI codegen step exists.

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

// Backend ClaimContext (schemas.py) — always present on the response, even when the
// public webapp submits no order/listing fields (they default to "" / []).
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

export const LAYER_LABELS: Record<LayerId, string> = {
  l1_aigen: "AI-generation detection",
  l2_forensics: "Manipulation / edit forensics",
  l3_recapture: "Screenshot / recapture detection",
  l4_metadata: "Metadata & provenance",
  l5_context: "Product context cross-check",
};
